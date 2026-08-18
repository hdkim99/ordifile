# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate local-only YL-Clarity Result exports from owner-controlled PRM files.

This maintainer tool is deliberately separate from Ordifile's runtime.  It uses only
documented vendor commands, opens a temporary copy of one chromatogram at a time, and
never saves a chromatogram.  The exact YL-Clarity OEM command compatibility remains a
pilot-time question; no vendor executable or fixture is bundled with Ordifile.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Never, Protocol, cast

MAX_COMMAND_CHARACTERS = 126
MAX_INPUT_FILES = 256
MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_EXPORT_BYTES = 64 * 1024 * 1024
MAX_ZIP_MEMBERS = 512
MAX_ZIP_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_ZIP_MEMBER_NAME_BYTES = 4096
MAX_ZIP_SEGMENT_BYTES = 255
MAX_DIRECTORY_ENTRIES = 10_000
MAX_DIRECTORY_DEPTH = 64
MAX_RESULT_ROWS = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 3600
MANIFEST_FILENAME = "youngin-result-export-manifest.json"
_SHA256_BUFFER = 1024 * 1024
_SAFE_ZIP_SEGMENT = re.compile(r"[^\x00-\x1f<>:\"|?*]+\Z")
_SAFE_PRODUCT_VERSION = re.compile(r"[0-9]{1,4}(?:\.[0-9]{1,4}){1,5}\Z")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RT_HEADERS = frozenset({"rt", "rtime", "rettime", "retentime", "retentiontime"})
_AREA_HEADERS = frozenset({"area", "peakarea"})
_HEIGHT_HEADERS = frozenset({"height", "peakheight"})
_SIGNAL_HEADERS = frozenset({"signal", "signalname", "detector", "channel"})
_REGISTRY_APP_NAMES = ("YL-Clarity.exe", "Clarity.exe")
_REGISTRY_ROOT_NAMES = ("HKEY_LOCAL_MACHINE", "HKEY_CURRENT_USER")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
_WORKTREE_LOCAL_ROOTS = frozenset({".external-fixtures", ".research-downloads", "fixture-cache"})
_FATAL_CLEANUP_ERRORS = frozenset({"output_cleanup_failed", "vendor_cleanup_failed"})
_IS_WINDOWS = os.name == "nt"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class BridgeError(RuntimeError):
    """A bounded bridge policy or export validation failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ExecutableInfo:
    """A validated executable location without a PATH lookup."""

    path: Path
    discovery: str
    product_version: str | None = None


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    """One PRM source plus the original object used for immutability checks."""

    path: Path
    sha256: str
    size_bytes: int
    integrity_path: Path
    integrity_sha256: str

    @property
    def public_id(self) -> str:
        return f"source-{self.sha256}"


@dataclass(frozen=True, slots=True)
class HeaderEvidence:
    """Privacy-safe facts established from one exported Result Table header."""

    encoding: str
    delimiter: str
    header_line: int
    has_retention_time: bool
    has_area: bool
    has_height: bool
    has_signal: bool
    nonempty_rows_after_header: int
    rows_with_retention_time: int
    rows_with_area: int
    rows_with_height: int
    distinct_nonempty_signal_values: int

    def __post_init__(self) -> None:
        counts = (
            self.rows_with_retention_time,
            self.rows_with_area,
            self.rows_with_height,
            self.distinct_nonempty_signal_values,
        )
        if self.nonempty_rows_after_header < 0 or any(
            count < 0 or count > self.nonempty_rows_after_header for count in counts
        ):
            raise ValueError("header structural counts are inconsistent")


@dataclass(frozen=True, slots=True)
class ExportRecord:
    """A privacy-safe per-source result for the local manifest."""

    source_id: str
    source_sha256: str
    source_size_bytes: int
    status: str
    error_code: str | None
    original_hash_preserved: bool
    export_filename: str | None
    export_sha256: str | None
    export_size_bytes: int | None
    header: HeaderEvidence | None

    def __post_init__(self) -> None:
        if (
            _SHA256_HEX.fullmatch(self.source_sha256) is None
            or self.source_id != f"source-{self.source_sha256}"
            or not 1 <= self.source_size_bytes <= MAX_SOURCE_BYTES
        ):
            raise ValueError("export record source identity is inconsistent")
        complete = (
            self.export_filename is not None
            and self.export_sha256 is not None
            and self.export_size_bytes is not None
            and self.header is not None
        )
        empty = (
            self.export_filename is None
            and self.export_sha256 is None
            and self.export_size_bytes is None
            and self.header is None
        )
        if self.status == "success":
            if (
                self.error_code is not None
                or not self.original_hash_preserved
                or not complete
                or self.export_filename != f"{self.source_id}.txt"
                or self.export_sha256 is None
                or _SHA256_HEX.fullmatch(self.export_sha256) is None
                or self.export_size_bytes is None
                or not 1 <= self.export_size_bytes <= MAX_EXPORT_BYTES
            ):
                raise ValueError("successful export record is inconsistent")
        elif self.status == "failed":
            if self.error_code is None or not empty:
                raise ValueError("failed export record is inconsistent")
        else:
            raise ValueError("export record status is invalid")

    def to_json(self) -> dict[str, object]:
        header: dict[str, object] | None = None
        if self.header is not None:
            header = {
                "encoding": self.header.encoding,
                "delimiter": self.header.delimiter,
                "header_line": self.header.header_line,
                "retention_time": self.header.has_retention_time,
                "area": self.header.has_area,
                "height": self.header.has_height,
                "signal": self.header.has_signal,
                # This is deliberately not named peak_count: a vendor export may
                # include a summary/Total row that only the exact adapter can classify.
                "nonempty_rows_after_header": self.header.nonempty_rows_after_header,
                "rows_with_retention_time": self.header.rows_with_retention_time,
                "rows_with_area": self.header.rows_with_area,
                "rows_with_height": self.header.rows_with_height,
                # Values themselves remain private; only their structural cardinality
                # is persisted for single/multi-signal pilot decisions.
                "distinct_nonempty_signal_values": (self.header.distinct_nonempty_signal_values),
            }
        return {
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "source_size_bytes": self.source_size_bytes,
            "status": self.status,
            "error_code": self.error_code,
            "original_hash_preserved": self.original_hash_preserved,
            "export_filename": self.export_filename,
            "export_sha256": self.export_sha256,
            "export_size_bytes": self.export_size_bytes,
            "header": header,
        }


@dataclass(frozen=True, slots=True)
class BridgeManifest:
    """Local-only manifest containing hashes and counts but no source names or paths."""

    mode: str
    discovered_inputs: int
    selected_inputs: int
    successful_exports: int
    failed_exports: int
    original_sources_modified: int
    pilot_gate: str
    executable_discovery: str
    executable_product_version: str | None
    records: tuple[ExportRecord, ...]

    def __post_init__(self) -> None:
        if (
            not 1 <= self.selected_inputs <= self.discovered_inputs <= MAX_INPUT_FILES
            or self.selected_inputs != len(self.records)
            or self.successful_exports != sum(record.status == "success" for record in self.records)
            or self.failed_exports != sum(record.status == "failed" for record in self.records)
            or self.original_sources_modified
            != sum(not record.original_hash_preserved for record in self.records)
            or self.pilot_gate != ("passed" if self.records[0].status == "success" else "failed")
        ):
            raise ValueError("bridge manifest counts are inconsistent")

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "tool": "youngin_yl_clarity_export_bridge",
            "mode": self.mode,
            "vendor_command_profile": "open_prm_export_results_close_discard",
            "oem_command_capability": "pilot_required",
            "discovered_inputs": self.discovered_inputs,
            "selected_inputs": self.selected_inputs,
            "successful_exports": self.successful_exports,
            "failed_exports": self.failed_exports,
            "original_sources_modified": self.original_sources_modified,
            "pilot_gate": self.pilot_gate,
            "executable": {
                "found": True,
                "discovery": self.executable_discovery,
                "product_version": self.executable_product_version,
            },
            "records": [record.to_json() for record in self.records],
        }


Runner = Callable[
    [tuple[str, ...], Path, Path, int],
    subprocess.CompletedProcess[str],
]
Logger = Callable[[str], None]
GitIgnoreProbe = Callable[[Path, Path], bool]


class _WinReg(Protocol):
    HKEY_LOCAL_MACHINE: object
    HKEY_CURRENT_USER: object
    KEY_READ: int

    def OpenKey(
        self,
        key: object,
        sub_key: str,
        reserved: int = 0,
        access: int = 0,
    ) -> AbstractContextManager[object]: ...

    def QueryValueEx(self, key: object, value_name: str | None) -> tuple[object, int]: ...


def _sha256_and_size(path: Path, *, maximum_bytes: int | None = None) -> tuple[str, int]:
    """Hash and size one stable regular-file snapshot."""

    try:
        path_lstat = os.lstat(path)
        if stat.S_ISLNK(path_lstat.st_mode) or _path_is_link_or_reparse(path):
            raise BridgeError("source_not_regular", "Every source must be a regular file.")
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not os.path.samestat(path_lstat, before):
                raise BridgeError("source_changed_during_read", "A source changed before reading.")
            if maximum_bytes is not None and (
                before.st_size <= 0 or before.st_size > maximum_bytes
            ):
                raise BridgeError("source_size_invalid", "A source object violates its size bound.")
            digest = hashlib.sha256()
            total = 0
            while chunk := stream.read(_SHA256_BUFFER):
                total += len(chunk)
                if maximum_bytes is not None and total > maximum_bytes:
                    raise BridgeError(
                        "source_size_invalid", "A source object violates its size bound."
                    )
                digest.update(chunk)
            after = os.fstat(stream.fileno())
    except OSError as error:
        raise BridgeError("source_unreadable", "A source object cannot be read.") from error
    if not _same_open_file(before, after, total):
        raise BridgeError("source_changed_during_read", "A source changed while it was read.")
    return digest.hexdigest(), total


def sha256_file(path: Path, *, maximum_bytes: int | None = None) -> str:
    """Hash a regular file while enforcing an optional byte bound."""

    return _sha256_and_size(path, maximum_bytes=maximum_bytes)[0]


def _same_open_file(before: os.stat_result, after: os.stat_result, total: int) -> bool:
    return (
        stat.S_ISREG(before.st_mode)
        and os.path.samestat(before, after)
        and before.st_size == after.st_size == total
        and before.st_mtime_ns == after.st_mtime_ns
    )


def _bounded_copy_snapshot(
    source: Path,
    target: Path,
    *,
    expected_sha256: str,
    maximum_bytes: int,
) -> None:
    """Copy and hash one stable source snapshot into an exclusively created target."""

    try:
        source_lstat = os.lstat(source)
        if stat.S_ISLNK(source_lstat.st_mode) or _path_is_link_or_reparse(source):
            raise BridgeError("source_reparse_point", "A source is a link or reparse point.")
        with source.open("rb") as input_stream, target.open("xb") as output_stream:
            before = os.fstat(input_stream.fileno())
            if not os.path.samestat(source_lstat, before):
                raise BridgeError("source_changed_during_read", "A source changed before staging.")
            digest = hashlib.sha256()
            total = 0
            while chunk := input_stream.read(_SHA256_BUFFER):
                total += len(chunk)
                if total > maximum_bytes:
                    raise BridgeError("source_size_invalid", "A source exceeds its size bound.")
                output_stream.write(chunk)
                digest.update(chunk)
            output_stream.flush()
            after = os.fstat(input_stream.fileno())
            if total <= 0 or not _same_open_file(before, after, total):
                raise BridgeError("source_changed_during_read", "A source changed while staging.")
            if digest.hexdigest() != expected_sha256:
                raise BridgeError("staging_copy_mismatch", "The staged PRM hash does not match.")
    except BridgeError:
        target.unlink(missing_ok=True)
        raise
    except OSError as error:
        target.unlink(missing_ok=True)
        raise BridgeError("staging_copy_failed", "The temporary PRM copy failed.") from error


def _read_bounded_snapshot(path: Path, *, maximum_bytes: int) -> bytes:
    """Read one stable, regular, non-reparse file snapshot with a strict size bound."""

    try:
        path_lstat = os.lstat(path)
        if stat.S_ISLNK(path_lstat.st_mode) or _path_is_link_or_reparse(path):
            raise BridgeError("export_not_regular", "The Result export is not a regular file.")
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not os.path.samestat(path_lstat, before):
                raise BridgeError("export_changed", "The Result export changed before reading.")
            if before.st_size <= 0:
                raise BridgeError("export_empty", "The vendor Result export is empty.")
            if before.st_size > maximum_bytes:
                raise BridgeError(
                    "export_too_large", "The vendor Result export exceeds its size bound."
                )
            content = stream.read(maximum_bytes + 1)
            after = os.fstat(stream.fileno())
    except FileNotFoundError as error:
        raise BridgeError("export_missing", "The vendor Result export was not created.") from error
    except BridgeError:
        raise
    except OSError as error:
        raise BridgeError(
            "export_unreadable", "The vendor Result export cannot be read."
        ) from error
    if len(content) > maximum_bytes:
        raise BridgeError("export_too_large", "The vendor Result export exceeds its size bound.")
    if not _same_open_file(before, after, len(content)):
        raise BridgeError("export_changed", "The Result export changed while reading.")
    return content


def _write_exclusive_snapshot(target: Path, content: bytes) -> None:
    """Persist already-hashed bytes through exclusive creation without following links."""

    created = False
    try:
        with target.open("xb") as stream:
            created = True
            stream.write(content)
            stream.flush()
            status = os.fstat(stream.fileno())
            if status.st_size != len(content):
                raise BridgeError("output_copy_mismatch", "The Result export write was incomplete.")
    except FileExistsError as error:
        raise BridgeError("output_exists", "A deterministic output already exists.") from error
    except BridgeError:
        if created:
            _remove_partial_output(target)
        raise
    except OSError as error:
        if created:
            _remove_partial_output(target)
        raise BridgeError(
            "output_write_failed", "The Result export could not be written."
        ) from error


def _remove_partial_output(path: Path) -> None:
    """Remove an exclusively created partial private output or fail closed."""

    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise BridgeError(
            "output_cleanup_failed", "A partial local-only output could not be removed."
        ) from error


def _path_is_link_or_reparse(path: Path) -> bool:
    """Detect POSIX links and Windows junction/reparse points without following them."""

    try:
        status = os.lstat(path)
    except OSError as error:
        raise BridgeError(
            "source_unreadable", "A filesystem object cannot be inspected."
        ) from error
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(status.st_mode) or bool(attributes & reparse_flag)


def _safe_product_version(value: str | None) -> str | None:
    """Allow only non-identifying dotted numeric product versions in public metadata."""

    if value is None or _SAFE_PRODUCT_VERSION.fullmatch(value) is None:
        return None
    return value


def _validate_executable(
    path: Path, *, discovery: str, version: str | None = None
) -> ExecutableInfo:
    expanded = path.expanduser()
    if _path_is_link_or_reparse(expanded):
        raise BridgeError("executable_not_regular", "The vendor executable is not a regular file.")
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as error:
        raise BridgeError("executable_not_found", "The vendor executable was not found.") from error
    if not resolved.is_file():
        raise BridgeError("executable_not_regular", "The vendor executable is not a regular file.")
    if os.name == "nt" and resolved.suffix.casefold() != ".exe":
        raise BridgeError("executable_not_windows", "The vendor executable must be a Windows EXE.")
    return ExecutableInfo(resolved, discovery, _safe_product_version(version))


def _registry_executable_candidates() -> tuple[tuple[Path, str | None], ...]:
    if not _IS_WINDOWS:
        return ()
    winreg = cast(_WinReg, importlib.import_module("winreg"))

    roots = {
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
    }
    candidates: list[tuple[Path, str | None]] = []
    for root_name in _REGISTRY_ROOT_NAMES:
        root = roots[root_name]
        for application in _REGISTRY_APP_NAMES:
            key_name = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{application}"
            try:
                with winreg.OpenKey(root, key_name, 0, winreg.KEY_READ) as key:
                    raw_path, _ = winreg.QueryValueEx(key, None)
                    try:
                        raw_version, _ = winreg.QueryValueEx(key, "Version")
                    except OSError:
                        raw_version = None
            except OSError:
                continue
            if isinstance(raw_path, str) and raw_path:
                version = raw_version if isinstance(raw_version, str) and raw_version else None
                candidates.append((Path(raw_path), version))
    return tuple(candidates)


def discover_executable(
    explicit: Path | None,
    *,
    registry_candidates: Iterable[tuple[Path, str | None]] | None = None,
) -> ExecutableInfo:
    """Resolve an explicit or bounded App Paths entry without consulting PATH."""

    if explicit is not None:
        return _validate_executable(explicit, discovery="explicit")
    candidates = (
        tuple(registry_candidates)
        if registry_candidates is not None
        else _registry_executable_candidates()
    )
    for path, version in candidates[: len(_REGISTRY_ROOT_NAMES) * len(_REGISTRY_APP_NAMES)]:
        try:
            return _validate_executable(path, discovery="registry", version=version)
        except BridgeError:
            continue
    raise BridgeError(
        "executable_not_found",
        "No explicit or registered YL-Clarity/Clarity executable was found.",
    )


def _safe_zip_name(name: str) -> PurePosixPath:
    normalized = unicodedata.normalize("NFC", name)
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    parts = normalized.split("/")
    unsafe_segment = any(
        part[-1] in {" ", "."}
        or _windows_reserved_segment(part)
        or len(part.encode("utf-8")) > MAX_ZIP_SEGMENT_BYTES
        for part in posix.parts
    )
    if (
        not name
        or normalized != name
        or "\\" in name
        or posix.is_absolute()
        or windows.drive
        or windows.root
        or any(part in {"", ".", ".."} for part in parts if part != "")
        or any(_SAFE_ZIP_SEGMENT.fullmatch(part) is None for part in posix.parts)
        or unsafe_segment
        or len(normalized.encode("utf-8")) > MAX_ZIP_MEMBER_NAME_BYTES
    ):
        raise BridgeError("zip_path_unsafe", "The ZIP contains an unsafe member path.")
    return posix


def _windows_reserved_segment(segment: str) -> bool:
    """Reject Windows device aliases, including spaced and superscript spellings."""

    stem = segment.split(".", 1)[0].rstrip(" .")
    compatibility_stem = unicodedata.normalize("NFKC", stem).upper()
    return compatibility_stem in _WINDOWS_RESERVED_NAMES


def _zip_is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def _collect_zip_sources(archive_path: Path, extraction_root: Path) -> list[SourceCandidate]:
    archive_sha = sha256_file(archive_path, maximum_bytes=MAX_SOURCE_BYTES)
    candidates: list[SourceCandidate] = []
    normalized_names: set[str] = set()
    total_uncompressed = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ZIP_MEMBERS:
                raise BridgeError("zip_member_count", "The ZIP violates its member-count bound.")
            prm_infos: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for info in infos:
                relative = _safe_zip_name(info.filename.rstrip("/"))
                normalized = relative.as_posix().casefold()
                if normalized in normalized_names:
                    raise BridgeError("zip_duplicate_member", "The ZIP contains duplicate members.")
                normalized_names.add(normalized)
                if info.flag_bits & 0x1:
                    raise BridgeError("zip_encrypted", "Encrypted ZIP members are not accepted.")
                if _zip_is_symlink(info):
                    raise BridgeError("zip_symlink", "ZIP symbolic links are not accepted.")
                if info.is_dir():
                    continue
                total_uncompressed += info.file_size
                if (
                    info.file_size < 0
                    or info.file_size > MAX_SOURCE_BYTES
                    or total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES
                    or (
                        info.compress_size == 0
                        and info.file_size > 0
                        or info.compress_size > 0
                        and info.file_size > info.compress_size * MAX_COMPRESSION_RATIO
                    )
                ):
                    raise BridgeError("zip_size_invalid", "The ZIP violates a size bound.")
                if relative.suffix.casefold() != ".prm":
                    continue
                prm_infos.append((info, relative))
                if len(prm_infos) > MAX_INPUT_FILES:
                    raise BridgeError(
                        "source_count", "The ZIP exceeds the PRM count bound before extraction."
                    )
            for info, relative in sorted(
                prm_infos,
                key=lambda item: (item[1].as_posix().casefold(), item[1].as_posix()),
            ):
                target = extraction_root.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                digest = hashlib.sha256()
                with archive.open(info) as source, target.open("xb") as destination:
                    while chunk := source.read(_SHA256_BUFFER):
                        written += len(chunk)
                        if written > MAX_SOURCE_BYTES or written > info.file_size:
                            raise BridgeError("zip_size_invalid", "A ZIP member exceeds its bound.")
                        destination.write(chunk)
                        digest.update(chunk)
                if written == 0 or written != info.file_size:
                    raise BridgeError(
                        "zip_member_invalid", "A PRM ZIP member is empty or truncated."
                    )
                candidates.append(
                    SourceCandidate(
                        target,
                        digest.hexdigest(),
                        written,
                        archive_path,
                        archive_sha,
                    )
                )
    except BridgeError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, OSError, RuntimeError) as error:
        raise BridgeError("zip_malformed", "The ZIP is malformed or truncated.") from error
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.path.relative_to(extraction_root).as_posix().casefold(),
            candidate.path.relative_to(extraction_root).as_posix(),
        ),
    )


def _within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _directory_prm_paths(directory: Path) -> tuple[Path, ...]:
    discovered: list[Path] = []
    pending: list[tuple[Path, int]] = [(directory, 0)]
    visited_entries = 0
    while pending:
        current, depth = pending.pop()
        if depth > MAX_DIRECTORY_DEPTH:
            raise BridgeError("directory_depth", "The input exceeds the directory-depth bound.")
        try:
            with os.scandir(current) as iterator:
                entries = sorted(
                    iterator,
                    key=lambda entry: (entry.name.casefold(), entry.name),
                )
        except OSError as error:
            raise BridgeError(
                "directory_unreadable", "An input directory cannot be read completely."
            ) from error
        child_directories: list[Path] = []
        for entry in entries:
            visited_entries += 1
            if visited_entries > MAX_DIRECTORY_ENTRIES:
                raise BridgeError("directory_entries", "The input exceeds its entry-count bound.")
            child = Path(entry.path)
            if _path_is_link_or_reparse(child):
                raise BridgeError(
                    "source_reparse_point",
                    "Input directories may not contain links or reparse points.",
                )
            try:
                resolved_child = child.resolve(strict=True)
                is_directory = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError as error:
                raise BridgeError(
                    "directory_unreadable", "An input entry cannot be inspected completely."
                ) from error
            if not _within_root(resolved_child, directory):
                raise BridgeError(
                    "source_outside_root", "An input entry resolves outside the intake root."
                )
            if is_directory:
                child_directories.append(resolved_child)
            elif is_file and resolved_child.suffix.casefold() == ".prm":
                discovered.append(resolved_child)
                if len(discovered) > MAX_INPUT_FILES:
                    raise BridgeError("source_count", "The input exceeds the PRM count bound.")
        for child_directory in reversed(child_directories):
            pending.append((child_directory, depth + 1))
    return tuple(
        sorted(
            discovered,
            key=lambda path: (
                path.relative_to(directory).as_posix().casefold(),
                path.relative_to(directory).as_posix(),
            ),
        )
    )


def collect_sources(input_path: Path, extraction_root: Path) -> tuple[SourceCandidate, ...]:
    """Collect one PRM, a bounded PRM directory, or a safely extracted ZIP."""

    expanded = input_path.expanduser()
    try:
        if _path_is_link_or_reparse(expanded):
            raise BridgeError(
                "source_reparse_point", "Link and reparse-point inputs are not accepted."
            )
        resolved = expanded.resolve(strict=True)
    except BridgeError:
        raise
    except OSError as error:
        raise BridgeError("source_not_found", "The input source was not found.") from error
    candidates: list[SourceCandidate]
    if resolved.is_dir():
        candidates = []
        for path in _directory_prm_paths(resolved):
            sha256, size = _sha256_and_size(path, maximum_bytes=MAX_SOURCE_BYTES)
            candidates.append(SourceCandidate(path, sha256, size, path, sha256))
    elif resolved.is_file() and resolved.suffix.casefold() == ".prm":
        sha256, size = _sha256_and_size(resolved, maximum_bytes=MAX_SOURCE_BYTES)
        candidates = [SourceCandidate(resolved, sha256, size, resolved, sha256)]
    elif resolved.is_file() and resolved.suffix.casefold() == ".zip":
        candidates = _collect_zip_sources(resolved, extraction_root)
    else:
        raise BridgeError("source_type", "Input must be one PRM, a directory, or a ZIP.")
    if not candidates:
        raise BridgeError("source_empty", "No bounded PRM input was found.")
    if len(candidates) > MAX_INPUT_FILES:
        raise BridgeError("source_count", "The input exceeds the PRM count bound.")
    seen_hashes: set[str] = set()
    for candidate in candidates:
        if candidate.sha256 in seen_hashes:
            raise BridgeError("source_duplicate", "Duplicate PRM content is ambiguous.")
        seen_hashes.add(candidate.sha256)
    return tuple(candidates)


def _operational_alias(sha256: str, prefix: str, suffix: str) -> str:
    return f"{prefix}-{sha256[:16]}{suffix}"


def build_vendor_command(
    executable: Path,
    staged_prm: Path,
    temporary_export: Path,
) -> tuple[str, ...]:
    """Build the documented ordered command and enforce Clarity's 126-char limit."""

    if staged_prm.parent != temporary_export.parent:
        raise BridgeError("command_workspace", "Vendor input and output must share a workspace.")
    command = (
        executable.name,
        staged_prm.name,
        f"export_results={temporary_export.name}",
        "prm_close_discard",
    )
    command_line = subprocess.list2cmdline(command)
    if len(command_line) > MAX_COMMAND_CHARACTERS:
        raise BridgeError("command_too_long", "The vendor command exceeds 126 characters.")
    return command


def _decode_export(content: bytes) -> tuple[str, str]:
    attempts: Sequence[tuple[str, str]] = (
        ("utf-8-sig", "utf-8-sig"),
        ("utf-16", "utf-16"),
        ("cp1252", "windows-1252"),
    )
    for codec, label in attempts:
        try:
            decoded = content.decode(codec)
        except (UnicodeDecodeError, UnicodeError):
            continue
        if "\x00" not in decoded:
            return decoded, label
    raise BridgeError("export_encoding", "The Result export encoding is unsupported.")


def _normalized_header(value: str) -> str:
    # Clarity commonly appends units in brackets, e.g. ``Reten. Time [min]`` and
    # ``Area [detector units.s]``.  The bridge proves the semantic column exists but
    # leaves unit interpretation to the exact result adapter.
    label_without_unit = re.sub(r"\s*[\[(][^\])]*[\])]\s*$", "", value.strip())
    return "".join(character for character in label_without_unit.casefold() if character.isalnum())


def _candidate_delimiters(line: str) -> tuple[str, ...]:
    candidates = tuple(delimiter for delimiter in ("\t", ",", ";") if delimiter in line)
    return candidates or ("whitespace",)


def _split_header(line: str, delimiter: str) -> list[str]:
    if delimiter == "whitespace":
        return re.split(r"\s{2,}", line.strip())
    try:
        return next(csv.reader([line], delimiter=delimiter))
    except csv.Error as error:
        raise BridgeError(
            "export_table_malformed", "The Result export table is malformed."
        ) from error


def _first_column(columns: Sequence[str], aliases: frozenset[str]) -> int | None:
    return next((index for index, column in enumerate(columns) if column in aliases), None)


def _structural_column_counts(
    lines: Sequence[str],
    *,
    delimiter: str,
    retention_time_column: int,
    area_column: int,
    height_column: int | None,
    signal_column: int | None,
) -> tuple[int, int, int, int, int]:
    nonempty_rows = 0
    rows_with_retention_time = 0
    rows_with_area = 0
    rows_with_height = 0
    signal_value_digests: set[bytes] = set()
    for line in lines:
        if not line.strip():
            continue
        nonempty_rows += 1
        if nonempty_rows > MAX_RESULT_ROWS:
            raise BridgeError("export_row_count", "The Result export exceeds its row bound.")
        fields = _split_header(line, delimiter)
        if retention_time_column < len(fields) and fields[retention_time_column].strip():
            rows_with_retention_time += 1
        if area_column < len(fields) and fields[area_column].strip():
            rows_with_area += 1
        if (
            height_column is not None
            and height_column < len(fields)
            and fields[height_column].strip()
        ):
            rows_with_height += 1
        if signal_column is not None and signal_column < len(fields):
            signal = fields[signal_column].strip()
            if signal:
                signal_value_digests.add(hashlib.sha256(signal.encode("utf-8")).digest())
    return (
        nonempty_rows,
        rows_with_retention_time,
        rows_with_area,
        rows_with_height,
        len(signal_value_digests),
    )


def _inspect_result_content(content: bytes) -> HeaderEvidence:
    text, encoding = _decode_export(content)
    lines = text.splitlines()
    for line_index, line in enumerate(lines[:100]):
        if not line.strip():
            continue
        for delimiter in _candidate_delimiters(line):
            columns = [_normalized_header(value) for value in _split_header(line, delimiter)]
            retention_time_column = _first_column(columns, _RT_HEADERS)
            area_column = _first_column(columns, _AREA_HEADERS)
            if retention_time_column is None or area_column is None:
                continue
            height_column = _first_column(columns, _HEIGHT_HEADERS)
            signal_column = _first_column(columns, _SIGNAL_HEADERS)
            structural_counts = _structural_column_counts(
                lines[line_index + 1 :],
                delimiter=delimiter,
                retention_time_column=retention_time_column,
                area_column=area_column,
                height_column=height_column,
                signal_column=signal_column,
            )
            return HeaderEvidence(
                encoding,
                "tab" if delimiter == "\t" else delimiter,
                line_index + 1,
                True,
                True,
                height_column is not None,
                signal_column is not None,
                *structural_counts,
            )
    raise BridgeError(
        "export_header_missing_rt_area",
        "The vendor Result export lacks an explicit retention-time and area header.",
    )


def inspect_result_export(path: Path) -> HeaderEvidence:
    """Require an explicit RT+Area header from one bounded stable snapshot."""

    return _inspect_result_content(_read_bounded_snapshot(path, maximum_bytes=MAX_EXPORT_BYTES))


def _default_runner(
    command: tuple[str, ...],
    executable: Path,
    working_directory: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    if os.environ.get("CI", "").casefold() in {"1", "true", "yes"}:
        raise BridgeError("ci_execution_refused", "Vendor export execution is disabled in CI.")
    if not _IS_WINDOWS:
        raise BridgeError("windows_required", "Vendor export execution requires Windows.")
    try:
        process = subprocess.Popen(
            list(command),
            cwd=working_directory,
            executable=str(executable),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        _terminate_new_process_tree(process)
        raise BridgeError("vendor_timeout", "The vendor export command timed out.") from error
    except OSError as error:
        raise BridgeError(
            "vendor_launch_failed", "The vendor export command could not start."
        ) from error
    return subprocess.CompletedProcess(command, returncode, "", "")


def _windows_taskkill_executable() -> Path:
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise BridgeError("vendor_cleanup_failed", "Windows process cleanup is unavailable.")
    candidate = Path(system_root) / "System32" / "taskkill.exe"
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise BridgeError(
            "vendor_cleanup_failed", "Windows process cleanup is unavailable."
        ) from error
    if not resolved.is_file() or _path_is_link_or_reparse(resolved):
        raise BridgeError("vendor_cleanup_failed", "Windows process cleanup is unavailable.")
    return resolved


def _terminate_new_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate only the newly launched command's PID tree after a timeout."""

    try:
        taskkill = _windows_taskkill_executable()
        completed = subprocess.run(
            [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            shell=False,
        )
    except (BridgeError, OSError, subprocess.SubprocessError) as error:
        try:
            process.kill()
        except OSError:
            pass
        raise BridgeError(
            "vendor_cleanup_failed", "The timed-out vendor process tree could not be verified."
        ) from error
    if completed.returncode != 0:
        try:
            process.kill()
        except OSError:
            pass
        raise BridgeError(
            "vendor_cleanup_failed", "The timed-out vendor process tree could not be verified."
        )
    try:
        process.wait(timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        try:
            process.kill()
        except OSError:
            pass
        raise BridgeError(
            "vendor_cleanup_failed", "The timed-out vendor process tree could not be verified."
        ) from error


def _failure_record(
    candidate: SourceCandidate,
    error_code: str,
    original_preserved: bool,
) -> ExportRecord:
    return ExportRecord(
        candidate.public_id,
        candidate.sha256,
        candidate.size_bytes,
        "failed",
        error_code,
        original_preserved,
        None,
        None,
        None,
        None,
    )


def _remove_temporary_file(path: Path) -> None:
    """Remove a staged private object or stop with a sanitized cleanup error."""

    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise BridgeError(
            "temporary_cleanup_failed", "A temporary local-only object could not be removed."
        ) from error


def _process_one(
    candidate: SourceCandidate,
    executable: ExecutableInfo,
    workspace: Path,
    output_directory: Path,
    runner: Runner,
    timeout_seconds: int,
) -> ExportRecord:
    operational_source = workspace / _operational_alias(candidate.sha256, "s", ".prm")
    operational_export = workspace / _operational_alias(candidate.sha256, "r", ".txt")
    persistent_name = f"{candidate.public_id}.txt"
    persistent_export = output_directory / persistent_name
    original_preserved = True
    persistent_written = False
    try:
        if (
            sha256_file(candidate.integrity_path, maximum_bytes=MAX_SOURCE_BYTES)
            != candidate.integrity_sha256
        ):
            return _failure_record(candidate, "original_changed_before_export", False)
        _bounded_copy_snapshot(
            candidate.path,
            operational_source,
            expected_sha256=candidate.sha256,
            maximum_bytes=MAX_SOURCE_BYTES,
        )
        command = build_vendor_command(executable.path, operational_source, operational_export)
        completed = runner(command, executable.path, workspace, timeout_seconds)
        if completed.returncode != 0:
            raise BridgeError("vendor_exit_nonzero", "The vendor export command failed.")
        export_content = _read_bounded_snapshot(operational_export, maximum_bytes=MAX_EXPORT_BYTES)
        header = _inspect_result_content(export_content)
        export_sha256 = hashlib.sha256(export_content).hexdigest()
        export_size = len(export_content)
        original_preserved = (
            sha256_file(candidate.integrity_path, maximum_bytes=MAX_SOURCE_BYTES)
            == candidate.integrity_sha256
        )
        if not original_preserved:
            raise BridgeError("original_changed_during_export", "An original source changed.")
        _write_exclusive_snapshot(persistent_export, export_content)
        persistent_written = True
        return ExportRecord(
            candidate.public_id,
            candidate.sha256,
            candidate.size_bytes,
            "success",
            None,
            True,
            persistent_name,
            export_sha256,
            export_size,
            header,
        )
    except BridgeError as error:
        if error.code in _FATAL_CLEANUP_ERRORS:
            raise
        try:
            original_preserved = (
                sha256_file(candidate.integrity_path, maximum_bytes=MAX_SOURCE_BYTES)
                == candidate.integrity_sha256
            )
        except BridgeError:
            original_preserved = False
        return _failure_record(candidate, error.code, original_preserved)
    except (OSError, subprocess.SubprocessError):
        try:
            original_preserved = (
                sha256_file(candidate.integrity_path, maximum_bytes=MAX_SOURCE_BYTES)
                == candidate.integrity_sha256
            )
        except BridgeError:
            original_preserved = False
        return _failure_record(candidate, "vendor_execution_error", original_preserved)
    finally:
        cleanup_failed = False
        for temporary in (operational_source, operational_export):
            try:
                _remove_temporary_file(temporary)
            except BridgeError:
                cleanup_failed = True
        if cleanup_failed:
            if persistent_written:
                _remove_partial_output(persistent_export)
            raise BridgeError(
                "temporary_cleanup_failed", "A temporary local-only object could not be removed."
            )


def _find_git_worktree_root(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        marker = candidate / ".git"
        try:
            if marker.exists() or marker.is_symlink():
                return candidate
        except OSError as error:
            raise BridgeError(
                "output_git_policy_unresolved", "The output Git boundary cannot be inspected."
            ) from error
    return None


def _default_git_ignore_probe(worktree: Path, output: Path) -> bool:
    del output
    ignore_file = worktree / ".gitignore"
    try:
        if _path_is_link_or_reparse(ignore_file):
            return False
        content = _read_bounded_snapshot(ignore_file, maximum_bytes=64 * 1024).decode("utf-8")
    except (BridgeError, UnicodeDecodeError):
        return False
    patterns = {
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return all(f"{root}/" in patterns or f"/{root}/" in patterns for root in _WORKTREE_LOCAL_ROOTS)


def _project_root() -> Path:
    try:
        return _PROJECT_ROOT.resolve(strict=True)
    except OSError as error:
        raise BridgeError(
            "output_git_policy_unresolved", "The project output boundary cannot be verified."
        ) from error


def _enforce_worktree_output_policy(
    output: Path,
    *,
    git_ignore_probe: GitIgnoreProbe,
) -> None:
    worktree = _find_git_worktree_root(output)
    if worktree is None:
        return
    if worktree.resolve(strict=True) != _project_root():
        raise BridgeError(
            "output_foreign_worktree", "Output inside another Git worktree is refused."
        )
    relative = output.relative_to(worktree)
    if not relative.parts or relative.parts[0] not in _WORKTREE_LOCAL_ROOTS:
        raise BridgeError(
            "output_not_private_root",
            "Worktree output must use an approved local-only fixture root.",
        )
    if not git_ignore_probe(worktree, output):
        raise BridgeError(
            "output_not_gitignored", "Worktree output is not protected by Git ignore rules."
        )


def _prepare_output_directory(
    output_directory: Path,
    *,
    git_ignore_probe: GitIgnoreProbe,
) -> Path:
    expanded = output_directory.expanduser()
    if expanded.exists() and _path_is_link_or_reparse(expanded):
        raise BridgeError("output_symlink", "The output directory may not be a symlink.")
    try:
        expanded.mkdir(parents=True, exist_ok=True)
        resolved = expanded.resolve(strict=True)
    except OSError as error:
        raise BridgeError("output_unavailable", "The output directory is unavailable.") from error
    if not resolved.is_dir():
        raise BridgeError("output_not_directory", "The output target is not a directory.")
    _enforce_worktree_output_policy(resolved, git_ignore_probe=git_ignore_probe)
    manifest_path = resolved / MANIFEST_FILENAME
    if manifest_path.exists() or manifest_path.is_symlink():
        raise BridgeError("manifest_exists", "The local manifest already exists.")
    return resolved


def _write_manifest(path: Path, manifest: BridgeManifest) -> None:
    created = False
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            created = True
            json.dump(manifest.to_json(), stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
    except FileExistsError as error:
        raise BridgeError("manifest_exists", "The local manifest already exists.") from error
    except OSError as error:
        if created:
            _remove_partial_output(path)
        raise BridgeError(
            "manifest_write_failed", "The local manifest could not be written."
        ) from error


def _rollback_successful_exports(output: Path, records: Sequence[ExportRecord]) -> None:
    """Remove every persistent export created by the current aborted invocation."""

    cleanup_failed = False
    for record in records:
        if record.status != "success" or record.export_filename is None:
            continue
        try:
            _remove_partial_output(output / record.export_filename)
        except BridgeError:
            cleanup_failed = True
    if cleanup_failed:
        raise BridgeError(
            "output_cleanup_failed", "An aborted local-only export could not be removed."
        )


def _emit_status(logger: Logger, message: str) -> None:
    """Write a privacy-safe status while keeping output failures transactional."""

    try:
        logger(message)
    except Exception as error:
        # The logger is an injected output boundary.  Its exception text may contain
        # private sink details, so convert it to a fixed code and let run_bridge roll
        # back every export created by this invocation.
        raise BridgeError("status_output_failed", "The sanitized status output failed.") from error


def run_bridge(
    input_path: Path,
    output_directory: Path,
    *,
    executable: Path | None,
    batch: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner: Runner | None = None,
    logger: Logger | None = None,
    registry_candidates: Iterable[tuple[Path, str | None]] | None = None,
    git_ignore_probe: GitIgnoreProbe | None = None,
) -> BridgeManifest:
    """Run a one-file pilot by default, or a deterministic isolated batch."""

    if not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise BridgeError("timeout_invalid", "Timeout must be within the supported bound.")
    executable_info = discover_executable(
        executable,
        registry_candidates=registry_candidates,
    )
    output = _prepare_output_directory(
        output_directory,
        git_ignore_probe=(
            git_ignore_probe if git_ignore_probe is not None else _default_git_ignore_probe
        ),
    )
    emit = logger if logger is not None else print
    selected_runner = runner if runner is not None else _default_runner
    records: list[ExportRecord] = []
    try:
        with tempfile.TemporaryDirectory(
            prefix="oy-", ignore_cleanup_errors=True
        ) as temporary_name:
            temporary_root = Path(temporary_name)
            extraction_root = temporary_root / "x"
            workspace = temporary_root / "w"
            extraction_root.mkdir()
            workspace.mkdir()
            candidates = collect_sources(input_path, extraction_root)
            planned = candidates if batch else candidates[:1]
            mode = "batch" if batch else "pilot"
            for index, candidate in enumerate(planned):
                record = _process_one(
                    candidate,
                    executable_info,
                    workspace,
                    output,
                    selected_runner,
                    timeout_seconds,
                )
                records.append(record)
                _emit_status(emit, f"{candidate.public_id}: {record.status.upper()}")
                # A batch is authorized only by a successful RT+Area pilot.  Later
                # failures remain isolated and do not stop other sources.
                if batch and index == 0 and record.status != "success":
                    break
        pilot_gate = "passed" if records and records[0].status == "success" else "failed"
        manifest = BridgeManifest(
            mode,
            len(candidates),
            len(records),
            sum(record.status == "success" for record in records),
            sum(record.status == "failed" for record in records),
            sum(not record.original_hash_preserved for record in records),
            pilot_gate,
            executable_info.discovery,
            executable_info.product_version,
            tuple(records),
        )
        _write_manifest(output / MANIFEST_FILENAME, manifest)
    except BaseException:
        # Transactional cleanup must also run for cancellation or an unexpected
        # callback/programming failure.  The original exception is re-raised after
        # removing only outputs recorded as created by this invocation.
        _rollback_successful_exports(output, records)
        raise
    return manifest


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if not 1 <= parsed <= MAX_TIMEOUT_SECONDS:
        raise argparse.ArgumentTypeError(f"must be from 1 through {MAX_TIMEOUT_SECONDS}")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Locally export YL-Clarity Result Tables from temporary PRM copies. "
            "The default is a one-file pilot."
        )
    )
    parser.add_argument("input", type=Path, help="one PRM, a PRM directory, or a ZIP")
    parser.add_argument("--output", required=True, type=Path, help="new local export directory")
    parser.add_argument(
        "--executable",
        type=Path,
        help="explicit YL-Clarity/Clarity executable; otherwise bounded App Paths lookup",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="export all inputs; omit this option for a deterministic one-file pilot",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"per-file timeout in seconds (1-{MAX_TIMEOUT_SECONDS})",
    )
    return parser


def _fatal(error: BridgeError) -> Never:
    print(f"ERROR [{error.code}]: {error}", file=sys.stderr)
    raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        manifest = run_bridge(
            arguments.input,
            arguments.output,
            executable=arguments.executable,
            batch=arguments.batch,
            timeout_seconds=arguments.timeout,
        )
    except BridgeError as error:
        _fatal(error)
    print(f"Completed: {manifest.successful_exports} succeeded, {manifest.failed_exports} failed.")
    return 0 if manifest.failed_exports == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
