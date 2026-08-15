# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Safely fetch a maintainer-approved external fixture into a local cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Never

DEFAULT_DOWNLOAD_LIMIT = 256 * 1024 * 1024
LARGE_DOWNLOAD_LIMIT = 2 * 1024 * 1024 * 1024
DEFAULT_UNCOMPRESSED_LIMIT = 2 * 1024 * 1024 * 1024
LARGE_UNCOMPRESSED_LIMIT = 8 * 1024 * 1024 * 1024
DEFAULT_MEMBER_LIMIT = 10_000
LARGE_MEMBER_LIMIT = 100_000
MAX_COMPRESSION_RATIO = 100
MAX_REDIRECTS = 5
STREAM_CHUNK_SIZE = 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_MEMBER_NAME_BYTES = 4096
MAX_MEMBER_SEGMENT_BYTES = 255
MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "fixture_id",
        "url",
        "allowed_hosts",
        "artifact_filename",
        "sha256",
        "size_bytes",
        "archive_type",
        "selected_files",
        "tree_sha256",
        "source_page_url",
        "license_name",
        "license_id",
        "license_url",
        "license_acknowledged",
        "redistribution",
        "attribution",
        "privacy_review",
        "validated_with",
        "grade",
        "ci_eligible",
    }
)
FIXTURE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
HOST_PATTERN = re.compile(
    r"(?:localhost|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\."
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*)\Z"
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
READER_ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
READER_VERSION_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}\Z")
LICENSE_ID_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.-]{0,127}\Z")
GRADES = frozenset({"ACCEPT_REDISTRIBUTABLE", "ACCEPT_EXTERNAL_ONLY", "REJECT"})
REDISTRIBUTION_VALUES = frozenset({"permitted", "prohibited", "unknown"})
PRIVACY_VALUES = frozenset({"no_personal_data_observed", "contains_personal_data", "not_reviewed"})
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class FixtureFetchError(RuntimeError):
    """A manifest, download, cache, or archive safety rule failed."""


@dataclass(frozen=True, slots=True)
class FixtureManifest:
    """Strict version-1 fixture download declaration."""

    fixture_id: str
    url: str
    allowed_hosts: tuple[str, ...]
    artifact_filename: str
    sha256: str
    size_bytes: int
    archive_type: str
    selected_files: tuple[str, ...]
    tree_sha256: str | None
    source_page_url: str
    license_name: str
    license_id: str
    license_url: str
    license_acknowledged: bool
    redistribution: str
    attribution: str
    privacy_review: str
    validated_with: tuple[tuple[str, str, str], ...]
    grade: str
    ci_eligible: bool


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Verified cached archive and an optional safely extracted fixture tree."""

    archive: Path
    extracted: Path | None
    tree_sha256: str | None
    archive_type: str


@dataclass(frozen=True, slots=True)
class _ZipMember:
    info: zipfile.ZipInfo
    normalized_name: str


def _exact_int(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise FixtureFetchError(f"{field} must be an integer from {minimum} through {maximum}")
    return value


def _exact_text(value: object, *, field: str) -> str:
    if type(value) is not str or not value:
        raise FixtureFetchError(f"{field} must be nonempty text")
    return value


def _bounded_text(value: object, *, field: str, maximum: int = 4096) -> str:
    text = _exact_text(value, field=field)
    if len(text) > maximum or any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for character in text
    ):
        raise FixtureFetchError(f"{field} exceeds its bound or contains unsafe controls")
    return text


def _normalized_host(value: object) -> str:
    host = _exact_text(value, field="allowed_hosts entry")
    try:
        host.encode("ascii")
    except UnicodeEncodeError as error:
        raise FixtureFetchError("allowed hosts must be lowercase ASCII DNS names") from error
    if host != host.casefold() or HOST_PATTERN.fullmatch(host) is None:
        raise FixtureFetchError("allowed hosts must be lowercase ASCII DNS names")
    return host


def _validate_url(url: str, allowed_hosts: tuple[str, ...], *, allow_http: bool) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise FixtureFetchError("fixture URL is malformed") from error
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if (
        parsed.scheme.casefold() not in allowed_schemes
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        scheme = "HTTPS (or test-only HTTP)" if allow_http else "HTTPS"
        raise FixtureFetchError(
            f"fixture URL must use {scheme}, name an allowed host, and omit credentials/fragments"
        )
    host = parsed.hostname.casefold()
    if host not in allowed_hosts:
        raise FixtureFetchError(f"URL host is not allowlisted: {host}")
    return host


def _validate_https_reference(value: object, *, field: str) -> str:
    url = _bounded_text(value, field=field)
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as error:
        raise FixtureFetchError(f"{field} is malformed") from error
    if not parsed.hostname:
        raise FixtureFetchError(f"{field} must be an absolute HTTPS URL")
    _validate_url(url, (parsed.hostname.casefold(),), allow_http=False)
    return url


def _normalized_member_name(value: object, *, field: str, require_canonical: bool = True) -> str:
    name = _exact_text(value, field=field)
    normalized = unicodedata.normalize("NFC", name)
    raw_parts = name.split("/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    encoded_parts = tuple(part.encode("utf-8") for part in posix.parts)
    unsafe_segment = any(
        not part
        or part[-1] in {" ", "."}
        or any(character in '<>:"|?*' for character in part)
        or part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES
        for part in posix.parts
    )
    if (
        (require_canonical and normalized != name)
        or "\\" in name
        or any(part in {"", ".", ".."} for part in raw_parts)
        or posix.is_absolute()
        or windows.drive
        or windows.root
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
        or unsafe_segment
        or len(normalized.encode("utf-8")) > MAX_MEMBER_NAME_BYTES
        or any(len(part) > MAX_MEMBER_SEGMENT_BYTES for part in encoded_parts)
    ):
        raise FixtureFetchError(f"{field} is not a canonical safe relative ZIP path: {name!r}")
    return normalized


def load_manifest(
    path: Path,
    *,
    allow_large: bool = False,
    _allow_insecure_http: bool = False,
) -> FixtureManifest:
    """Read and strictly validate one versioned JSON manifest."""

    def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise FixtureFetchError(f"fixture manifest repeats JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Never:
        raise FixtureFetchError(f"fixture manifest contains non-JSON number {value!r}")

    try:
        encoded = path.read_bytes()
        if len(encoded) > MAX_MANIFEST_BYTES:
            raise FixtureFetchError("fixture manifest exceeds the 64 KiB limit")
        raw = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise FixtureFetchError("fixture manifest is not readable strict UTF-8 JSON") from error
    if type(raw) is not dict or set(raw) != MANIFEST_KEYS:
        raise FixtureFetchError("fixture manifest must contain exactly the version-1 fields")
    if raw["schema_version"] != 1 or type(raw["schema_version"]) is not int:
        raise FixtureFetchError("schema_version must be the integer 1")
    fixture_id = _exact_text(raw["fixture_id"], field="fixture_id")
    if FIXTURE_ID_PATTERN.fullmatch(fixture_id) is None:
        raise FixtureFetchError("fixture_id must be 1-64 lowercase ASCII identifier characters")
    raw_hosts = raw["allowed_hosts"]
    if type(raw_hosts) is not list or not raw_hosts or len(raw_hosts) > 16:
        raise FixtureFetchError("allowed_hosts must be a nonempty list of at most 16 hosts")
    allowed_hosts = tuple(_normalized_host(item) for item in raw_hosts)
    if len(set(allowed_hosts)) != len(allowed_hosts):
        raise FixtureFetchError("allowed_hosts must not contain duplicates")
    url = _exact_text(raw["url"], field="url")
    _validate_url(url, allowed_hosts, allow_http=_allow_insecure_http)
    artifact_filename = _normalized_member_name(raw["artifact_filename"], field="artifact_filename")
    if len(PurePosixPath(artifact_filename).parts) != 1:
        raise FixtureFetchError("artifact_filename must be one portable basename")
    sha256 = _exact_text(raw["sha256"], field="sha256")
    if SHA256_PATTERN.fullmatch(sha256) is None:
        raise FixtureFetchError("sha256 must be exactly 64 lowercase hexadecimal characters")
    download_limit = LARGE_DOWNLOAD_LIMIT if allow_large else DEFAULT_DOWNLOAD_LIMIT
    size_bytes = _exact_int(
        raw["size_bytes"], field="size_bytes", minimum=1, maximum=download_limit
    )
    archive_type = _exact_text(raw["archive_type"], field="archive_type")
    if archive_type not in {"zip", "7z", "file"}:
        raise FixtureFetchError("archive_type must be 'zip', '7z', or 'file'")
    if archive_type == "zip" and not artifact_filename.casefold().endswith(".zip"):
        raise FixtureFetchError("ZIP artifact_filename must end in .zip")
    if archive_type == "7z" and not artifact_filename.casefold().endswith(".7z"):
        raise FixtureFetchError("7z artifact_filename must end in .7z")
    raw_selected = raw["selected_files"]
    if type(raw_selected) is not list:
        raise FixtureFetchError("selected_files must be a list")
    selected_files = tuple(
        _normalized_member_name(item, field="selected_files entry") for item in raw_selected
    )
    selected_keys = tuple(item.casefold() for item in selected_files)
    if len(set(selected_keys)) != len(selected_keys):
        raise FixtureFetchError("selected_files must not contain Unicode/casefold duplicates")
    tree_sha_value = raw["tree_sha256"]
    if archive_type == "zip":
        if not selected_files:
            raise FixtureFetchError("ZIP manifests must select at least one regular file")
        tree_sha256 = _exact_text(tree_sha_value, field="tree_sha256")
        if SHA256_PATTERN.fullmatch(tree_sha256) is None:
            raise FixtureFetchError("tree_sha256 must be 64 lowercase hexadecimal characters")
    else:
        if selected_files or tree_sha_value is not None:
            raise FixtureFetchError(
                "7z and direct-file manifests cannot select or automatically extract files"
            )
        tree_sha256 = None
    source_page_url = _validate_https_reference(raw["source_page_url"], field="source_page_url")
    license_name = _bounded_text(raw["license_name"], field="license_name", maximum=256)
    license_id = _exact_text(raw["license_id"], field="license_id")
    if LICENSE_ID_PATTERN.fullmatch(license_id) is None:
        raise FixtureFetchError("license_id must be a stable 1-128 character ASCII identifier")
    license_url = _validate_https_reference(raw["license_url"], field="license_url")
    license_acknowledged = raw["license_acknowledged"]
    if type(license_acknowledged) is not bool:
        raise FixtureFetchError("license_acknowledged must be an exact boolean")
    redistribution = _exact_text(raw["redistribution"], field="redistribution")
    if redistribution not in REDISTRIBUTION_VALUES:
        raise FixtureFetchError("redistribution has an unsupported policy value")
    attribution = _bounded_text(raw["attribution"], field="attribution")
    privacy_review = _exact_text(raw["privacy_review"], field="privacy_review")
    if privacy_review not in PRIVACY_VALUES:
        raise FixtureFetchError("privacy_review has an unsupported policy value")
    raw_validated = raw["validated_with"]
    if type(raw_validated) is not list or len(raw_validated) > 16:
        raise FixtureFetchError("validated_with must be a list of at most 16 reader results")
    validated_with: list[tuple[str, str, str]] = []
    for item in raw_validated:
        if type(item) is not dict or set(item) != {"reader", "version", "result"}:
            raise FixtureFetchError("validated_with entries require reader, version, and result")
        reader = _exact_text(item["reader"], field="validated_with reader")
        version = _exact_text(item["version"], field="validated_with version")
        result = _exact_text(item["result"], field="validated_with result")
        if READER_ID_PATTERN.fullmatch(reader) is None:
            raise FixtureFetchError("validated_with reader must be a stable lowercase ID")
        if READER_VERSION_PATTERN.fullmatch(version) is None:
            raise FixtureFetchError("validated_with version must be a bounded ASCII version")
        if result not in {"accepted", "rejected"}:
            raise FixtureFetchError("validated_with result must be accepted or rejected")
        validated_with.append((reader, version, result))
    grade = _exact_text(raw["grade"], field="grade")
    if grade not in GRADES:
        raise FixtureFetchError("grade has an unsupported decision value")
    ci_eligible = raw["ci_eligible"]
    if type(ci_eligible) is not bool:
        raise FixtureFetchError("ci_eligible must be an exact boolean")
    if grade == "ACCEPT_REDISTRIBUTABLE" and (
        not license_acknowledged
        or redistribution != "permitted"
        or privacy_review != "no_personal_data_observed"
        or not any(result == "accepted" for _, _, result in validated_with)
    ):
        raise FixtureFetchError(
            "ACCEPT_REDISTRIBUTABLE requires acknowledged permission, privacy review, "
            "and an accepted reader result"
        )
    if grade == "ACCEPT_EXTERNAL_ONLY" and (
        not license_acknowledged
        or redistribution not in {"prohibited", "unknown"}
        or privacy_review != "no_personal_data_observed"
        or not any(result == "accepted" for _, _, result in validated_with)
    ):
        raise FixtureFetchError(
            "ACCEPT_EXTERNAL_ONLY requires acknowledged terms, privacy review, "
            "non-redistributable policy, and an accepted reader result"
        )
    if ci_eligible and grade != "ACCEPT_REDISTRIBUTABLE":
        raise FixtureFetchError("ci_eligible requires ACCEPT_REDISTRIBUTABLE grade")
    return FixtureManifest(
        fixture_id,
        url,
        allowed_hosts,
        artifact_filename,
        sha256,
        size_bytes,
        archive_type,
        selected_files,
        tree_sha256,
        source_page_url,
        license_name,
        license_id,
        license_url,
        license_acknowledged,
        redistribution,
        attribution,
        privacy_review,
        tuple(validated_with),
        grade,
        ci_eligible,
    )


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: tuple[str, ...], *, allow_http: bool) -> None:
        super().__init__()
        self._allowed_hosts = allowed_hosts
        self._allow_http = allow_http
        self._redirects = 0

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        self._redirects += 1
        if self._redirects > MAX_REDIRECTS:
            raise FixtureFetchError(f"redirect count exceeds {MAX_REDIRECTS}")
        resolved = urllib.parse.urljoin(req.full_url, newurl)
        _validate_url(resolved, self._allowed_hosts, allow_http=self._allow_http)
        return super().redirect_request(req, fp, code, msg, headers, resolved)


def _safe_cache_directory(cache_dir: Path) -> Path:
    if cache_dir.is_symlink() or (cache_dir.exists() and not cache_dir.is_dir()):
        raise FixtureFetchError("cache path must be a real directory, not a symlink")
    cache_dir.mkdir(parents=True, exist_ok=True)
    if cache_dir.is_symlink():
        raise FixtureFetchError("cache directory became a symlink")
    return cache_dir.resolve()


def _safe_child_directory(root: Path, name: str) -> Path:
    child = root / name
    if child.is_symlink() or (child.exists() and not child.is_dir()):
        raise FixtureFetchError(f"cache child {name!r} must be a real directory")
    child.mkdir(exist_ok=True)
    if child.is_symlink() or not child.resolve().is_relative_to(root):
        raise FixtureFetchError(f"cache child {name!r} escapes the cache")
    return child


def _stream_sha256(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(STREAM_CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _verify_download(path: Path, manifest: FixtureManifest) -> None:
    if path.is_symlink() or not path.is_file():
        raise FixtureFetchError("cached archive must be a regular file")
    size, sha256 = _stream_sha256(path)
    if size != manifest.size_bytes:
        raise FixtureFetchError(
            f"download size mismatch: expected {manifest.size_bytes}, received {size}"
        )
    if sha256 != manifest.sha256:
        raise FixtureFetchError("download SHA-256 mismatch")


def download_fixture_archive(
    manifest: FixtureManifest,
    cache_dir: Path,
    *,
    allow_large: bool = False,
    _allow_insecure_http: bool = False,
) -> Path:
    """Download, stream-verify, and atomically cache one declared archive."""
    root = _safe_cache_directory(cache_dir)
    downloads = _safe_child_directory(root, "downloads")
    fixture_downloads = _safe_child_directory(downloads, manifest.fixture_id)
    digest_downloads = _safe_child_directory(fixture_downloads, manifest.sha256)
    target = digest_downloads / manifest.artifact_filename
    if target.exists():
        if target.is_symlink() or not target.is_file():
            raise FixtureFetchError("cached archive target is not a regular file")
        try:
            _verify_download(target, manifest)
        except FixtureFetchError:
            pass
        else:
            return target
    descriptor, partial_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".part", dir=digest_downloads
    )
    partial = Path(partial_name)
    limit = LARGE_DOWNLOAD_LIMIT if allow_large else DEFAULT_DOWNLOAD_LIMIT
    handler = _AllowlistRedirectHandler(
        manifest.allowed_hosts,
        allow_http=_allow_insecure_http,
    )
    opener = urllib.request.build_opener(handler)
    request = urllib.request.Request(
        manifest.url,
        headers={"User-Agent": "Ordifile-fixture-fetch/1"},
        method="GET",
    )
    digest = hashlib.sha256()
    received = 0
    try:
        try:
            response = opener.open(request, timeout=30)
        except FixtureFetchError:
            raise
        except (OSError, urllib.error.URLError) as error:
            raise FixtureFetchError("fixture download failed") from error
        with response, os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            final_url = response.geturl()
            _validate_url(
                final_url,
                manifest.allowed_hosts,
                allow_http=_allow_insecure_http,
            )
            raw_length = response.headers.get("Content-Length")
            if raw_length is not None:
                try:
                    declared_length = int(raw_length, 10)
                except ValueError as error:
                    raise FixtureFetchError("HTTP Content-Length is invalid") from error
                if declared_length < 0 or declared_length > limit:
                    raise FixtureFetchError("HTTP Content-Length exceeds the download limit")
                if declared_length != manifest.size_bytes:
                    raise FixtureFetchError("HTTP Content-Length differs from manifest size")
            while chunk := response.read(STREAM_CHUNK_SIZE):
                received += len(chunk)
                if received > limit or received > manifest.size_bytes:
                    raise FixtureFetchError("download exceeded its declared or configured byte cap")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if received != manifest.size_bytes:
            raise FixtureFetchError(
                f"download size mismatch: expected {manifest.size_bytes}, received {received}"
            )
        if digest.hexdigest() != manifest.sha256:
            raise FixtureFetchError("download SHA-256 mismatch")
        if target.exists() and (target.is_symlink() or not target.is_file()):
            raise FixtureFetchError("cached archive target changed to an unsafe object")
        os.replace(partial, target)
        _verify_download(target, manifest)
        return target
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        partial.unlink(missing_ok=True)


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_IFMT(mode) == stat.S_IFLNK


def _zip_member_is_special(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    kind = stat.S_IFMT(mode)
    return kind not in {0, stat.S_IFREG, stat.S_IFDIR}


def inspect_zip_archive(
    archive_path: Path,
    *,
    allow_large: bool = False,
) -> dict[str, _ZipMember]:
    """Inventory every ZIP member without extracting or trusting its paths."""
    member_limit = LARGE_MEMBER_LIMIT if allow_large else DEFAULT_MEMBER_LIMIT
    uncompressed_limit = LARGE_UNCOMPRESSED_LIMIT if allow_large else DEFAULT_UNCOMPRESSED_LIMIT
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
    except (OSError, zipfile.BadZipFile) as error:
        raise FixtureFetchError("download is not a readable ZIP archive") from error
    if len(infos) > member_limit:
        raise FixtureFetchError(f"ZIP member count exceeds {member_limit}")
    members: dict[str, _ZipMember] = {}
    kinds: dict[str, bool] = {}
    total_uncompressed = 0
    for info in infos:
        raw_name = info.orig_filename
        if "\x00" in raw_name:
            raise FixtureFetchError("ZIP member names may not contain NUL")
        name = raw_name[:-1] if info.is_dir() and raw_name.endswith("/") else raw_name
        normalized = _normalized_member_name(
            name,
            field="ZIP member",
            require_canonical=False,
        )
        key = normalized.casefold()
        if key in members:
            raise FixtureFetchError("ZIP contains duplicate Unicode/casefold member names")
        if info.flag_bits & 0x1:
            raise FixtureFetchError("encrypted ZIP members are not supported")
        if _zip_member_is_symlink(info) or _zip_member_is_special(info):
            raise FixtureFetchError("ZIP may contain only regular files and directories")
        if info.file_size < 0 or info.compress_size < 0:
            raise FixtureFetchError("ZIP contains a negative member size")
        total_uncompressed += info.file_size
        if info.file_size > uncompressed_limit or total_uncompressed > uncompressed_limit:
            raise FixtureFetchError("ZIP uncompressed size exceeds the configured limit")
        if info.file_size:
            if info.compress_size == 0:
                raise FixtureFetchError("nonempty ZIP member declares zero compressed bytes")
            if info.file_size > info.compress_size * MAX_COMPRESSION_RATIO:
                raise FixtureFetchError(
                    f"ZIP member compression ratio exceeds {MAX_COMPRESSION_RATIO}:1"
                )
        is_directory = info.is_dir()
        parts = PurePosixPath(normalized).parts
        for index in range(1, len(parts)):
            prefix = PurePosixPath(*parts[:index]).as_posix().casefold()
            if prefix in kinds and not kinds[prefix]:
                raise FixtureFetchError("ZIP file/directory prefixes conflict")
        if not is_directory:
            prefix = f"{key}/"
            if any(existing.startswith(prefix) for existing in kinds):
                raise FixtureFetchError("ZIP file/directory prefixes conflict")
        members[key] = _ZipMember(info, normalized)
        kinds[key] = is_directory
    return members


def _update_tree_digest_header(digest: Any, relative: str, size: int) -> None:
    encoded = relative.encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    digest.update(size.to_bytes(8, "big"))


def canonical_tree_digest(root: Path, relative_files: Iterable[str]) -> str:
    """Hash sorted canonical relative paths, sizes, and exact bytes using tree format v1."""
    normalized = tuple(
        sorted(_normalized_member_name(item, field="tree path") for item in relative_files)
    )
    if len({item.casefold() for item in normalized}) != len(normalized):
        raise FixtureFetchError("tree paths contain Unicode/casefold duplicates")
    digest = hashlib.sha256(b"ordifile-fixture-tree-v1\0")
    resolved_root = root.resolve()
    expected_files = set(normalized)
    expected_directories = {
        PurePosixPath(*PurePosixPath(relative).parts[:index]).as_posix()
        for relative in normalized
        for index in range(1, len(PurePosixPath(relative).parts))
    }
    actual_files: set[str] = set()
    if root.is_symlink() or not root.is_dir():
        raise FixtureFetchError("fixture tree root must be a real directory")
    for candidate in root.rglob("*"):
        relative = candidate.relative_to(root).as_posix()
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(resolved_root):
            raise FixtureFetchError("fixture tree contains a symlink or escaping path")
        if candidate.is_dir():
            if relative not in expected_directories:
                raise FixtureFetchError("fixture tree contains an undeclared directory")
        elif candidate.is_file():
            actual_files.add(relative)
        else:
            raise FixtureFetchError("fixture tree contains a non-regular filesystem object")
    if actual_files != expected_files:
        raise FixtureFetchError("fixture tree files differ from the declared selection")
    for relative in normalized:
        path = root.joinpath(*PurePosixPath(relative).parts)
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(resolved_root)
        ):
            raise FixtureFetchError("fixture tree contains a missing, symlinked, or escaping file")
        size = path.stat().st_size
        _update_tree_digest_header(digest, relative, size)
        with path.open("rb") as stream:
            while chunk := stream.read(STREAM_CHUNK_SIZE):
                digest.update(chunk)
    return digest.hexdigest()


def extract_selected_zip(
    manifest: FixtureManifest,
    archive_path: Path,
    cache_dir: Path,
    *,
    allow_large: bool = False,
) -> Path:
    """Safely extract only manifest-selected regular files into an atomic digest path."""
    if manifest.archive_type != "zip" or manifest.tree_sha256 is None:
        raise FixtureFetchError("automatic extraction is supported only for ZIP manifests")
    members = inspect_zip_archive(archive_path, allow_large=allow_large)
    selected: list[_ZipMember] = []
    for name in manifest.selected_files:
        member = members.get(name.casefold())
        if member is None or member.info.is_dir():
            raise FixtureFetchError(f"selected ZIP member is missing or not a regular file: {name}")
        if member.normalized_name != name:
            raise FixtureFetchError(
                f"selected ZIP member case or Unicode spelling differs from manifest: {name}"
            )
        selected.append(member)
    root = _safe_cache_directory(cache_dir)
    fixtures = _safe_child_directory(root, "fixtures")
    final = fixtures / f"{manifest.fixture_id}-{manifest.tree_sha256}"
    if final.exists():
        if final.is_symlink() or not final.is_dir():
            raise FixtureFetchError("extracted fixture target is not a real directory")
        actual = canonical_tree_digest(final, manifest.selected_files)
        if actual != manifest.tree_sha256:
            raise FixtureFetchError("existing fixture tree SHA-256 mismatch")
        return final
    temporary = Path(tempfile.mkdtemp(prefix=f".{manifest.fixture_id}.", dir=fixtures))
    uncompressed_limit = LARGE_UNCOMPRESSED_LIMIT if allow_large else DEFAULT_UNCOMPRESSED_LIMIT
    try:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for member in selected:
                    target = temporary.joinpath(*PurePosixPath(member.normalized_name).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() or target.is_symlink():
                        raise FixtureFetchError("selected ZIP targets collide")
                    written = 0
                    with archive.open(member.info) as source, target.open("xb") as output:
                        while chunk := source.read(STREAM_CHUNK_SIZE):
                            written += len(chunk)
                            if written > member.info.file_size or written > uncompressed_limit:
                                raise FixtureFetchError("ZIP extraction exceeded a declared size")
                            output.write(chunk)
                    if written != member.info.file_size:
                        raise FixtureFetchError("ZIP extracted size differs from its inventory")
        except (OSError, EOFError, RuntimeError, zipfile.BadZipFile) as error:
            raise FixtureFetchError("ZIP extraction failed integrity checks") from error
        actual = canonical_tree_digest(temporary, manifest.selected_files)
        if actual != manifest.tree_sha256:
            raise FixtureFetchError("extracted fixture tree SHA-256 mismatch")
        if final.exists():
            raise FixtureFetchError("fixture target appeared during extraction")
        os.replace(temporary, final)
        return final
    finally:
        if temporary.exists():
            for path in sorted(temporary.rglob("*"), reverse=True):
                if path.is_dir() and not path.is_symlink():
                    path.rmdir()
                else:
                    path.unlink()
            temporary.rmdir()


def fetch_fixture(
    manifest_path: Path,
    cache_dir: Path,
    *,
    accepted_license: str,
    allow_large: bool = False,
    allow_ci: bool = False,
    _allow_insecure_http: bool = False,
) -> FetchResult:
    """Validate, download, and optionally extract one declared external fixture."""
    manifest = load_manifest(
        manifest_path,
        allow_large=allow_large,
        _allow_insecure_http=_allow_insecure_http,
    )
    if type(accepted_license) is not str or accepted_license not in {
        manifest.license_name,
        manifest.license_id,
    }:
        raise FixtureFetchError(
            "--accept-license must exactly match the reviewed license name or license ID"
        )
    if not manifest.license_acknowledged or manifest.grade == "REJECT":
        raise FixtureFetchError("fixture license/grade does not authorize maintainer download")
    ci_value = os.environ.get("CI", "").casefold()
    in_ci = ci_value not in {"", "0", "false", "no"}
    if in_ci and not (allow_ci and manifest.ci_eligible):
        raise FixtureFetchError(
            "fixture downloads are disabled in CI unless both manifest eligibility and "
            "explicit --allow-ci opt-in are present"
        )
    archive = download_fixture_archive(
        manifest,
        cache_dir,
        allow_large=allow_large,
        _allow_insecure_http=_allow_insecure_http,
    )
    if manifest.archive_type in {"7z", "file"}:
        return FetchResult(archive, None, None, manifest.archive_type)
    extracted = extract_selected_zip(
        manifest,
        archive,
        cache_dir,
        allow_large=allow_large,
    )
    return FetchResult(archive, extracted, manifest.tree_sha256, manifest.archive_type)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument(
        "--accept-license",
        help="Exact reviewed license name or stable license ID displayed before download.",
    )
    parser.add_argument(
        "--allow-large",
        action="store_true",
        help=(
            "Raise caps from 256 MiB to 2 GiB download, 2 GiB to 8 GiB uncompressed, "
            "and 10,000 to 100,000 ZIP members; the 100:1 ratio cap remains."
        ),
    )
    parser.add_argument(
        "--allow-ci",
        action="store_true",
        help="Explicitly allow CI download only when the reviewed manifest is CI-eligible.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Maintainer-only script entry point; this is not a product console command."""
    arguments = _parser().parse_args(argv)
    try:
        manifest = load_manifest(arguments.manifest, allow_large=arguments.allow_large)
        print(f"source: {manifest.source_page_url}")
        print(f"license: {manifest.license_name} ({manifest.license_id})")
        print(f"license URL: {manifest.license_url}")
        print(f"attribution: {manifest.attribution}")
        if arguments.accept_license is None:
            raise FixtureFetchError(
                "review the displayed terms and pass --accept-license with the exact license "
                "name or ID"
            )
        result = fetch_fixture(
            arguments.manifest,
            arguments.cache_dir,
            accepted_license=arguments.accept_license,
            allow_large=arguments.allow_large,
            allow_ci=arguments.allow_ci,
        )
    except FixtureFetchError as error:
        print(f"fixture fetch failed: {error}", file=sys.stderr)
        return 1
    print(f"verified archive: {result.archive}")
    if result.extracted is None:
        print(f"automatic extraction: disabled for {result.archive_type}")
    else:
        print(f"verified fixture tree: {result.extracted}")
        print(f"tree SHA-256: {result.tree_sha256}")
    return 0


def _entry_point() -> Never:
    raise SystemExit(main())


if __name__ == "__main__":
    _entry_point()
