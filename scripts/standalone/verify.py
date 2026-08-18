# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Privacy, fixture, inventory, and legal gates for a standalone bundle tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat as stat_module
from collections.abc import Iterable, Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath, PureWindowsPath

from ordifile import __version__
from ordifile.api import list_formats

MAX_BUNDLE_FILES = 30_000
MAX_BUNDLE_BYTES = 4 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
FORBIDDEN_FIXTURE_SUFFIXES = frozenset({".ch", ".gcd", ".qgd", ".prm", ".raw", ".d", ".cdf"})
REQUIRED_LICENSES = frozenset(
    {
        "LGPL-3.0.txt",
        "NUITKA-RUNTIME-EXCEPTION.txt",
        "PYTHON-PSF-LICENSE.txt",
        "QT-PYSIDE-SHIBOKEN-NOTICE.md",
        "README.md",
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
    }
)
FORBIDDEN_SECRET_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN DSA PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
    b"github_pat_",
    b"ghp_",
    b"gho_",
    b"ghu_",
    b"ghs_",
    b"ghr_",
)


class StandaloneVerificationError(Exception):
    """A privacy-safe candidate verification failure."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contains(path: Path, needles: tuple[bytes, ...]) -> bool:
    if not needles:
        return False
    maximum = max(len(item) for item in needles)
    previous = b""
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            searchable = previous + chunk
            if any(item in searchable for item in needles):
                return True
            previous = searchable[-maximum:] if maximum else b""
    return False


def _text_contains(value: str, needles: tuple[bytes, ...]) -> bool:
    encoded = (value.encode("utf-8"), value.encode("utf-16le"))
    return any(needle in item for needle in needles for item in encoded)


def _has_windows_reparse_attribute(metadata: object) -> bool:
    value = getattr(metadata, "st_file_attributes", 0)
    marker = getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(value & marker)


def _reject_unneeded_network_runtime(relative: str) -> None:
    normalized_relative = relative.casefold().replace("\\", "/")
    normalized = f"/{normalized_relative}"
    name = PurePosixPath(relative).name.casefold()
    if (
        "/plugins/tls/" in normalized
        or "/qt-plugins/tls/" in normalized
        or "/networkinformation/" in normalized
        or name in {"qtnetwork", "qt6network.dll"}
        or name.startswith("qtnetwork.")
    ):
        raise StandaloneVerificationError("An unneeded Qt network component is bundled.")


def inventory_bundle(
    root: Path, *, forbidden_text: Iterable[str] = ()
) -> tuple[tuple[dict[str, object], ...], tuple[str, ...]]:
    """Inventory a bundle without following symlinks or emitting machine paths."""
    try:
        root_metadata = root.stat(follow_symlinks=False)
    except OSError as error:
        raise StandaloneVerificationError("The standalone bundle root is invalid.") from error
    if not root.is_dir() or root.is_symlink() or _has_windows_reparse_attribute(root_metadata):
        raise StandaloneVerificationError("The standalone bundle root is invalid.")
    private_values = tuple(text for text in forbidden_text if text and len(text) >= 4)
    normalized_values = {
        value
        for text in private_values
        for value in (text, text.replace("\\", "/"), text.replace("/", "\\"))
    }
    needles = FORBIDDEN_SECRET_MARKERS + tuple(
        encoded
        for value in sorted(normalized_values)
        for encoded in (value.encode("utf-8"), value.encode("utf-16le"))
    )
    files: list[dict[str, object]] = []
    licenses: set[str] = set()
    total_size = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise StandaloneVerificationError("A bundle directory is unreadable.") from error
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts or not relative:
                raise StandaloneVerificationError("A bundle path is unsafe.")
            if path.suffix.casefold() in FORBIDDEN_FIXTURE_SUFFIXES:
                raise StandaloneVerificationError("A prohibited scientific fixture is bundled.")
            _reject_unneeded_network_runtime(relative)
            if _text_contains(relative, needles):
                raise StandaloneVerificationError(
                    "Private build data is embedded in a bundle path."
                )
            metadata = entry.stat(follow_symlinks=False)
            if _has_windows_reparse_attribute(metadata):
                raise StandaloneVerificationError(
                    "A Windows reparse point is unsupported in the bundle."
                )
            if entry.is_symlink():
                target = os.readlink(path)
                target_path = PurePosixPath(target)
                windows_target = PureWindowsPath(target)
                if (
                    target_path.is_absolute()
                    or ".." in target_path.parts
                    or windows_target.is_absolute()
                    or bool(windows_target.drive)
                ):
                    raise StandaloneVerificationError("A bundle symlink escapes its root.")
                if _text_contains(target, needles):
                    raise StandaloneVerificationError(
                        "Private build data is embedded in a bundle symlink."
                    )
                encoded = target.encode("utf-8")
                files.append(
                    {
                        "path": relative,
                        "kind": "symlink",
                        "size": len(encoded),
                        "sha256": _sha256_bytes(encoded),
                    }
                )
                if len(files) > MAX_BUNDLE_FILES:
                    raise StandaloneVerificationError(
                        "The standalone file count exceeds its bound."
                    )
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(path)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise StandaloneVerificationError("A bundle entry has an unsupported type.")
            size = metadata.st_size
            total_size += size
            if total_size > MAX_BUNDLE_BYTES:
                raise StandaloneVerificationError("The standalone bundle exceeds its size bound.")
            if _contains(path, needles):
                raise StandaloneVerificationError(
                    "Private build data is embedded in the standalone bundle."
                )
            if "licenses" in (part.casefold() for part in pure.parts):
                licenses.add(path.name)
            files.append(
                {
                    "path": relative,
                    "kind": "file",
                    "size": size,
                    "sha256": _sha256_file(path),
                }
            )
            if len(files) > MAX_BUNDLE_FILES:
                raise StandaloneVerificationError("The standalone file count exceeds its bound.")
    if not files:
        raise StandaloneVerificationError("The standalone bundle is empty.")
    missing = REQUIRED_LICENSES - licenses
    if missing:
        raise StandaloneVerificationError("The standalone license inventory is incomplete.")
    return tuple(sorted(files, key=lambda item: str(item["path"]))), tuple(sorted(licenses))


def build_manifest(
    root: Path,
    *,
    commit: str,
    target: str,
    signature_state: str,
    forbidden_text: Iterable[str] = (),
) -> dict[str, object]:
    """Build a deterministic, path-safe unsigned candidate manifest."""
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise StandaloneVerificationError("The candidate commit is not a lowercase SHA-1.")
    if target not in {"windows-x86_64", "macos-arm64", "macos-x86_64"}:
        raise StandaloneVerificationError("The standalone target is unsupported.")
    if signature_state not in {"UNSIGNED_PROTOTYPE", "AD_HOC_NOT_NOTARIZED"}:
        raise StandaloneVerificationError("The candidate signature state is unsupported.")
    files, licenses = inventory_bundle(root, forbidden_text=forbidden_text)

    def installed(distribution: str) -> str:
        try:
            return version(distribution)
        except PackageNotFoundError as error:
            raise StandaloneVerificationError("A pinned build tool is unavailable.") from error

    toolchain = {
        "PySide6-Essentials": installed("PySide6-Essentials"),
        "shiboken6": installed("shiboken6"),
        "Nuitka": installed("Nuitka"),
    }
    if toolchain != {
        "PySide6-Essentials": "6.11.2",
        "shiboken6": "6.11.2",
        "Nuitka": "4.1.3",
    }:
        raise StandaloneVerificationError("The standalone toolchain versions are not pinned.")
    bundle_total_size = 0
    for item in files:
        size = item["size"]
        if type(size) is not int:
            raise StandaloneVerificationError("The standalone inventory size is invalid.")
        bundle_total_size += size
    return {
        "schema_version": 1,
        "publishable": False,
        "signature_state": signature_state,
        "ordifile_version": __version__,
        "commit": commit,
        "target": target,
        "python_version": platform.python_version(),
        "toolchain": toolchain,
        "adapter_ids": [item.adapter_id for item in list_formats()],
        "bundle_total_size": bundle_total_size,
        "files": list(files),
        "licenses": list(licenses),
    }


def write_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    temporary.replace(path)


def verify_candidate_tree(
    root: Path,
    manifest_path: Path,
    *,
    commit: str,
    target: str,
) -> None:
    """Recompute a candidate manifest from extracted bytes and reviewed source state."""
    if (
        not manifest_path.is_file()
        or manifest_path.is_symlink()
        or manifest_path.stat().st_size > MAX_MANIFEST_BYTES
    ):
        raise StandaloneVerificationError("The standalone manifest is invalid.")
    try:
        loaded = json.loads(manifest_path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StandaloneVerificationError("The standalone manifest is unreadable.") from error
    if type(loaded) is not dict:
        raise StandaloneVerificationError("The standalone manifest root is invalid.")
    outer = loaded.pop("outer_artifact", None)
    if type(outer) is not dict or set(outer) != {"filename", "size", "sha256"}:
        raise StandaloneVerificationError("The standalone outer artifact identity is invalid.")
    filename = outer.get("filename")
    size = outer.get("size")
    sha256 = outer.get("sha256")
    if (
        type(filename) is not str
        or Path(filename).name != filename
        or type(size) is not int
        or size < 1
        or type(sha256) is not str
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        raise StandaloneVerificationError("The standalone outer artifact identity is invalid.")
    signature_state = loaded.get("signature_state")
    if type(signature_state) is not str:
        raise StandaloneVerificationError("The standalone signature state is invalid.")
    expected = build_manifest(
        root,
        commit=commit,
        target=target,
        signature_state=signature_state,
    )
    if loaded != expected:
        raise StandaloneVerificationError(
            "The extracted standalone tree differs from its reviewed manifest."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify extracted standalone candidate bytes")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--target", required=True, choices=("windows-x86_64", "macos-arm64", "macos-x86_64")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        verify_candidate_tree(
            args.bundle,
            args.manifest,
            commit=args.commit,
            target=args.target,
        )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except Exception:
        print("Standalone candidate verification failed; details were withheld.")
        return 1
    print("Standalone candidate verification PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
