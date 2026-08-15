# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Read-only, deterministic discovery and hashing."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from ordifile.core.models import Issue, Severity, SourceFile

_NATURAL_PART = re.compile(r"(\d+)")
_HASH_CHUNK = 1024 * 1024


def natural_key(value: str) -> tuple[tuple[int, object], ...]:
    """Return a stable, case-insensitive key with numeric runs compared numerically."""
    parts: list[tuple[int, object]] = []
    for part in _NATURAL_PART.split(value.casefold()):
        if part.isdigit():
            parts.append((0, int(part)))
        else:
            parts.append((1, part))
    return tuple(parts)


def sha256_file(path: Path) -> str:
    """Hash a file through a bounded-memory read-only stream."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path_identity(path: Path) -> str:
    """Return a conservative cross-platform identity for possibly absent paths."""
    return unicodedata.normalize("NFC", str(path.resolve(strict=False))).casefold()


def paths_alias(first: Path, second: Path) -> bool:
    """Compare portable path spelling and existing filesystem identity."""
    if portable_path_identity(first) == portable_path_identity(second):
        return True
    try:
        first_id = _reliable_file_id(first)
        second_id = _reliable_file_id(second)
    except OSError:
        first_id = second_id = None
    if first_id is not None and second_id is not None and first_id == second_id:
        return True
    try:
        return first.exists() and second.exists() and os.path.samefile(first, second)
    except OSError:
        return False


def _reliable_file_id(path: Path) -> tuple[int, int] | None:
    stat = path.stat(follow_symlinks=False)
    if stat.st_ino == 0:
        return None
    return (stat.st_dev, stat.st_ino)


def _is_ordifile_artifact(path: Path, output: Path) -> bool:
    if portable_path_identity(path.parent) != portable_path_identity(output.parent):
        return False
    if paths_alias(path, output):
        return True
    if path.name.casefold().startswith(".ordifile_"):
        return True
    sidecar_pattern = re.compile(
        rf"^{re.escape(output.stem)}_.+_[0-9]{{3}}\.csv$",
        re.IGNORECASE,
    )
    return sidecar_pattern.fullmatch(path.name) is not None


@dataclass(frozen=True, slots=True)
class DiscoveryRecord:
    """A discovered input and any issue that prevents parsing it."""

    source: SourceFile
    issues: tuple[Issue, ...] = ()


def _placeholder(path: Path, relative: str, order: int) -> SourceFile:
    return SourceFile(
        path=path,
        relative_path=relative,
        name=path.name or str(path),
        size=0,
        sha256=None,
        modified_at=None,
        input_order=order,
    )


def _source(path: Path, relative: str, order: int) -> SourceFile:
    stat = path.stat(follow_symlinks=False)
    modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    return SourceFile(
        path=path,
        relative_path=relative,
        name=path.name,
        size=stat.st_size,
        sha256=sha256_file(path),
        modified_at=modified,
        input_order=order,
    )


def _directory_members(root: Path, recursive: bool) -> Iterable[Path]:
    if not recursive:
        yield from sorted(root.iterdir(), key=lambda path: natural_key(path.name))
        return
    members: list[Path] = []

    def raise_walk_error(error: OSError) -> None:
        raise error

    for directory, directories, files in os.walk(root, followlinks=False, onerror=raise_walk_error):
        directory_path = Path(directory)
        # Record symlinked directories as rejected inputs instead of traversing them.
        symlink_directories = [name for name in directories if (directory_path / name).is_symlink()]
        directories[:] = [name for name in directories if name not in symlink_directories]
        members.extend(directory_path / name for name in symlink_directories)
        members.extend(directory_path / name for name in files)
    yield from sorted(
        members,
        key=lambda path: natural_key(path.relative_to(root).as_posix()),
    )


def discover_files(
    inputs: Sequence[str | os.PathLike[str]],
    *,
    recursive: bool = False,
    extensions: Iterable[str] | None = None,
    warn_file_bytes: int | None = None,
    max_file_bytes: int | None = None,
    artifact_output: Path | None = None,
) -> tuple[DiscoveryRecord, ...]:
    """Discover inputs without following links or collapsing duplicate paths."""
    allowed = None
    if extensions is not None:
        allowed = {
            extension.casefold() if extension.startswith(".") else f".{extension.casefold()}"
            for extension in extensions
        }
    candidates: list[tuple[Path, str, Issue | None]] = []

    for raw in inputs:
        path = Path(raw)
        if path.is_symlink():
            candidates.append(
                (
                    path,
                    path.name,
                    Issue(
                        "SYMLINK_REJECTED",
                        "Symbolic links are not followed; provide the target explicitly.",
                        Severity.ERROR,
                        path.name,
                    ),
                )
            )
        elif not path.exists():
            candidates.append(
                (
                    path,
                    path.name,
                    Issue(
                        "INPUT_NOT_FOUND",
                        "The input path does not exist.",
                        Severity.ERROR,
                        path.name,
                    ),
                )
            )
        elif path.is_file():
            if allowed is None or path.suffix.casefold() in allowed:
                candidates.append((path, path.name, None))
        elif path.is_dir():
            try:
                members = tuple(_directory_members(path, recursive))
            except (OSError, UnicodeError) as error:
                candidates.append(
                    (
                        path,
                        path.name,
                        Issue(
                            "INPUT_DISCOVERY_FAILED",
                            f"Directory contents could not be discovered ({type(error).__name__}).",
                            Severity.ERROR,
                            path.name,
                        ),
                    )
                )
                continue
            for member in members:
                relative = member.relative_to(path).as_posix()
                if artifact_output is not None and _is_ordifile_artifact(member, artifact_output):
                    candidates.append(
                        (
                            member,
                            relative,
                            Issue(
                                "ORDIFILE_ARTIFACT_EXCLUDED",
                                "An Ordifile workbook, sidecar, or temporary artifact was "
                                "excluded from folder discovery and retained in the audit log.",
                                Severity.WARNING,
                                relative,
                            ),
                        )
                    )
                    continue
                if member.is_symlink():
                    candidates.append(
                        (
                            member,
                            relative,
                            Issue(
                                "SYMLINK_REJECTED",
                                "Symbolic links are not followed.",
                                Severity.ERROR,
                                relative,
                            ),
                        )
                    )
                elif member.is_file() and (allowed is None or member.suffix.casefold() in allowed):
                    candidates.append((member, relative, None))
        else:
            candidates.append(
                (
                    path,
                    path.name,
                    Issue(
                        "INPUT_TYPE_UNSUPPORTED",
                        "The input is neither a regular file nor a directory.",
                        Severity.ERROR,
                        path.name,
                    ),
                )
            )

    # The list above preserves explicit input order; directory contents are naturally ordered.
    seen: dict[Path, int] = {}
    seen_file_ids: dict[tuple[int, int], int] = {}
    seen_paths: list[tuple[Path, int]] = []
    records: list[DiscoveryRecord] = []
    for index, (path, relative, discovery_issue) in enumerate(candidates):
        if discovery_issue is not None:
            records.append(DiscoveryRecord(_placeholder(path, relative, index), (discovery_issue,)))
            continue
        try:
            source = _source(path, relative, index)
        except (OSError, UnicodeError) as error:
            records.append(
                DiscoveryRecord(
                    _placeholder(path, relative, index),
                    (
                        Issue(
                            "INPUT_READ_FAILED",
                            f"The input could not be read ({type(error).__name__}).",
                            Severity.ERROR,
                            relative,
                        ),
                    ),
                )
            )
            continue
        try:
            resolved = path.resolve(strict=True)
        except (OSError, UnicodeError) as error:
            records.append(
                DiscoveryRecord(
                    source,
                    (
                        Issue(
                            "INPUT_RESOLVE_FAILED",
                            f"Input identity could not be resolved ({type(error).__name__}).",
                            Severity.ERROR,
                            relative,
                        ),
                    ),
                )
            )
            continue
        size_issues: list[Issue] = []
        if max_file_bytes is not None and source.size > max_file_bytes:
            size_issues.append(
                Issue(
                    "INPUT_SIZE_LIMIT",
                    f"Input size exceeds the configured {max_file_bytes}-byte hard limit; "
                    "integrity was hashed, but detection and parsing were not attempted.",
                    Severity.ERROR,
                    relative,
                )
            )
        elif warn_file_bytes is not None and source.size >= warn_file_bytes:
            size_issues.append(
                Issue(
                    "INPUT_SIZE_WARNING",
                    f"Input size meets or exceeds the configured {warn_file_bytes}-byte warning "
                    "threshold; processing continues without truncation.",
                    Severity.WARNING,
                    relative,
                )
            )
        first_input_order = seen.get(resolved)
        try:
            file_id = _reliable_file_id(path)
        except OSError:
            file_id = None
        if first_input_order is None and file_id is not None:
            first_input_order = seen_file_ids.get(file_id)
        elif first_input_order is None and file_id is None:
            for prior_path, prior_order in seen_paths:
                try:
                    if os.path.samefile(path, prior_path):
                        first_input_order = prior_order
                        break
                except OSError:
                    continue
        if first_input_order is not None:
            source = SourceFile(
                path=source.path,
                relative_path=source.relative_path,
                name=source.name,
                size=source.size,
                sha256=source.sha256,
                modified_at=source.modified_at,
                input_order=source.input_order,
                duplicate_of=first_input_order,
            )
            records.append(
                DiscoveryRecord(
                    source,
                    (
                        *size_issues,
                        Issue(
                            "DUPLICATE_INPUT",
                            "This file identity was already supplied and was not parsed twice; "
                            "content-hash equality alone is not used for duplicate detection.",
                            Severity.WARNING,
                            relative,
                            (("first_input_order", str(first_input_order)),),
                        ),
                    ),
                )
            )
        else:
            seen[resolved] = index
            if file_id is not None:
                seen_file_ids[file_id] = index
            seen_paths.append((path, index))
            records.append(DiscoveryRecord(source, tuple(size_issues)))

    ordered = sorted(records, key=lambda record: record.source.input_order)
    collision_groups: dict[str, list[int]] = {}
    for position, record in enumerate(ordered):
        collision_groups.setdefault(record.source.relative_path.casefold(), []).append(position)
    for positions in collision_groups.values():
        if len(positions) < 2:
            continue
        for collision_index, position in enumerate(positions, start=1):
            record = ordered[position]
            distinguished = f"input_{collision_index:03d}/{record.source.relative_path}"
            ordered[position] = replace(
                record,
                source=replace(record.source, relative_path=distinguished),
            )
    # A source path could itself contain the `input_NNN/` prefix created above. Make a
    # second deterministic pass so disambiguation can never create a new collision.
    used_relative_paths: set[str] = set()
    for position, record in enumerate(ordered):
        candidate = record.source.relative_path
        attempt = 1
        while candidate.casefold() in used_relative_paths:
            candidate = (
                f"record_{record.source.input_order + 1:06d}_{attempt:03d}/"
                f"{record.source.relative_path}"
            )
            attempt += 1
        used_relative_paths.add(candidate.casefold())
        if candidate != record.source.relative_path:
            ordered[position] = replace(
                record,
                source=replace(record.source, relative_path=candidate),
            )
    return tuple(ordered)
