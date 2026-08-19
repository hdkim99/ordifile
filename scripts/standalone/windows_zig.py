# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bootstrap and prove one exact job-local Zig toolchain on Windows."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections.abc import Iterable, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath, PureWindowsPath

ZIG_VERSION = "0.16.0"
ZIG_ARCHIVE_NAME = f"zig-x86_64-windows-{ZIG_VERSION}.zip"
ZIG_ROOT_NAME = f"zig-x86_64-windows-{ZIG_VERSION}"
ZIG_URL = f"https://ziglang.org/download/{ZIG_VERSION}/{ZIG_ARCHIVE_NAME}"
ZIG_ARCHIVE_SIZE = 97_217_739
ZIG_ARCHIVE_SHA256 = "68659eb5f1e4eb1437a722f1dd889c5a322c9954607f5edcf337bc3684a75a7e"
NUITKA_VERSION = "4.1.3"
PYSIDE_VERSION = "6.11.2"
WINDOWS_CPU_BASELINE_FLAG = "-march=x86_64"
WINDOWS_NUITKA_DEPENDENCY_MODE = "--experimental=force-dependencies-pefile"
MARKER_NAME = ".ordifile-zig-owned"
MAX_ARCHIVE_MEMBERS = 50_000
MAX_ARCHIVE_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
MAX_MEMBER_SIZE = 768 * 1024 * 1024
MAX_FAILURE_CLASSIFICATION_BYTES = 1024 * 1024
_IDENTITY = re.compile(r"^[0-9]+-[0-9]+-[A-Za-z0-9_-]+$")
_WINDOWS_RESERVED = {
    "aux",
    "clock$",
    "con",
    "conin$",
    "conout$",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


class ZigStageError(RuntimeError):
    """Expose only a fixed stage and never a host path or native tool transcript."""

    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


def _has_windows_reparse_attribute(metadata: object) -> bool:
    value = getattr(metadata, "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(value & marker)


def _ordinary_directory(path: Path) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISDIR(metadata.st_mode)
        and not path.is_symlink()
        and not _has_windows_reparse_attribute(metadata)
    )


def _ordinary_file(path: Path, *, nonempty: bool = False) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISREG(metadata.st_mode)
        and (not nonempty or metadata.st_size > 0)
        and not path.is_symlink()
        and not _has_windows_reparse_attribute(metadata)
    )


def _runner_identity() -> str:
    identity = "-".join(
        (
            os.environ.get("GITHUB_RUN_ID", ""),
            os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            os.environ.get("GITHUB_JOB", ""),
        )
    )
    if not _IDENTITY.fullmatch(identity):
        raise ZigStageError("identity")
    return identity


def _runner_temp() -> Path:
    raw = os.environ.get("RUNNER_TEMP")
    if not raw:
        raise ZigStageError("boundary")
    lexical = Path(raw)
    if not lexical.is_absolute() or lexical == lexical.parent:
        raise ZigStageError("boundary")
    if platform.system() == "Windows" and str(lexical).startswith("\\\\"):
        raise ZigStageError("boundary")
    try:
        current = lexical
        while True:
            if not _ordinary_directory(current):
                raise ZigStageError("boundary")
            if current == current.parent:
                break
            current = current.parent
        root = lexical.resolve(strict=True)
    except OSError as error:
        raise ZigStageError("boundary") from error
    if not _ordinary_directory(root) or root == root.parent:
        raise ZigStageError("boundary")
    return root


def _expected_root() -> Path:
    parent = _runner_temp()
    root = parent / f"ordifile-zig-{_runner_identity()}"
    if root.parent != parent:
        raise ZigStageError("boundary")
    return root


def _mask(value: str) -> None:
    if not value or any(character in value for character in "\r\n\0"):
        raise ZigStageError("environment")
    escaped = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::add-mask::{escaped}")


def _append_line(path_value: str | None, line: str) -> None:
    if not path_value or any(character in line for character in "\r\n\0"):
        raise ZigStageError("environment")
    path = Path(path_value)
    if not _ordinary_file(path):
        raise ZigStageError("environment")
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{line}\n")


def _write_environment(values: dict[str, str]) -> None:
    for value in values.values():
        _mask(value)
    for name, value in values.items():
        _append_line(os.environ.get("GITHUB_ENV"), f"{name}={value}")


def _write_cleanup_environment(root: Path, token: str) -> None:
    _write_environment(
        {
            "ORDIFILE_ZIG_ROOT": str(root),
            "ORDIFILE_ZIG_CLEANUP_TOKEN": token,
        }
    )


def _write_tool_environment(root: Path, executable: Path) -> None:
    tool_root = root / "tool" / ZIG_ROOT_NAME
    _write_environment(
        {
            "ORDIFILE_ZIG_EXE": str(executable),
            "ORDIFILE_ZIG_EXE_SHA256": _sha256(executable),
            "ORDIFILE_ZIG_TREE_SHA256": _tree_sha256(tool_root),
            "NUITKA_CACHE_DIR": str(root / "cache" / "nuitka"),
            "ZIG_LOCAL_CACHE_DIR": str(root / "cache" / "zig-local"),
            "ZIG_GLOBAL_CACHE_DIR": str(root / "cache" / "zig-global"),
        }
    )


def _create_owned_root(root: Path, token: str) -> None:
    if root != _expected_root() or not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ZigStageError("ownership")
    if root.exists() or root.is_symlink():
        raise ZigStageError("occupied")
    try:
        root.mkdir()
        if not _ordinary_directory(root) or root.resolve(strict=True) != root:
            raise ZigStageError("ownership")
        marker = root / MARKER_NAME
        with marker.open("x", encoding="ascii", newline="\n") as stream:
            stream.write(token)
        if not _ordinary_file(marker, nonempty=True) or marker.read_text(encoding="ascii") != token:
            raise ZigStageError("ownership")
        return
    except ZigStageError:
        if _owned_root(root, token):
            _remove_owned_root(root, token)
        elif _ordinary_directory(root):
            try:
                root.rmdir()
            except OSError:
                pass
        raise
    except Exception as error:
        if _owned_root(root, token):
            _remove_owned_root(root, token)
        elif _ordinary_directory(root):
            try:
                root.rmdir()
            except OSError:
                pass
        raise ZigStageError("ownership") from error


def _owned_root(root: Path, token: str) -> bool:
    try:
        expected = _expected_root()
        marker = root / MARKER_NAME
        return (
            root.resolve(strict=True) == expected
            and _ordinary_directory(root)
            and _ordinary_file(marker, nonempty=True)
            and marker.read_text(encoding="ascii") == token
        )
    except (OSError, UnicodeError, ZigStageError):
        return False


def _walk_tree(root: Path) -> Iterable[Path]:
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda entry: entry.name.casefold(), reverse=True)
        for child in children:
            path = Path(child.path)
            yield path
            if child.is_dir(follow_symlinks=False) and not child.is_symlink():
                stack.append(path)


def _safe_owned_tree(root: Path, token: str) -> bool:
    if not _owned_root(root, token):
        return False
    try:
        for path in _walk_tree(root):
            metadata = path.stat(follow_symlinks=False)
            if path.is_symlink() or _has_windows_reparse_attribute(metadata):
                return False
            if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
                return False
    except OSError:
        return False
    return True


def _remove_owned_root(root: Path, token: str) -> None:
    if not _safe_owned_tree(root, token):
        raise ZigStageError("cleanup")
    try:
        shutil.rmtree(root)
    except OSError as error:
        raise ZigStageError("cleanup") from error
    if root.exists() or root.is_symlink():
        raise ZigStageError("cleanup")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    """Hash the exact extracted tool inventory without following links."""
    if not _ordinary_directory(root):
        raise ZigStageError("tool-identity")
    try:
        entries = sorted(
            _walk_tree(root),
            key=lambda path: path.relative_to(root).as_posix().encode("utf-8"),
        )
        digest = hashlib.sha256()
        for path in entries:
            metadata = path.stat(follow_symlinks=False)
            relative = path.relative_to(root).as_posix().encode("utf-8")
            if _ordinary_directory(path):
                kind = b"D"
            elif _ordinary_file(path):
                kind = b"F"
            else:
                raise ZigStageError("tool-identity")
            digest.update(kind)
            digest.update(struct.pack(">I", len(relative)))
            digest.update(relative)
            digest.update(struct.pack(">Q", metadata.st_size))
            if kind == b"F":
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
        return digest.hexdigest()
    except ZigStageError:
        raise
    except (OSError, UnicodeError, ValueError) as error:
        raise ZigStageError("tool-identity") from error


def _download_archive(destination: Path) -> None:
    request = urllib.request.Request(ZIG_URL, headers={"User-Agent": "Ordifile-Zig-Bootstrap/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed HTTPS
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname != "ziglang.org":
                raise ZigStageError("download-origin")
            declared = response.headers.get("Content-Length")
            if declared is not None and declared != str(ZIG_ARCHIVE_SIZE):
                raise ZigStageError("download-identity")
            size = 0
            with destination.open("xb") as stream:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > ZIG_ARCHIVE_SIZE:
                        raise ZigStageError("download-identity")
                    stream.write(chunk)
    except ZigStageError:
        raise
    except Exception as error:
        raise ZigStageError("download") from error
    if (
        not _ordinary_file(destination, nonempty=True)
        or destination.stat().st_size != ZIG_ARCHIVE_SIZE
        or _sha256(destination) != ZIG_ARCHIVE_SHA256
    ):
        raise ZigStageError("download-identity")


def _safe_member_path(name: str) -> PurePosixPath:
    if not name or "\0" in name or "\\" in name:
        raise ZigStageError("archive-inventory")
    pure = PurePosixPath(name.rstrip("/"))
    windows = PureWindowsPath(name)
    if (
        pure.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or any(part in {"", ".", ".."} for part in pure.parts)
        or not pure.parts
        or pure.parts[0] != ZIG_ROOT_NAME
    ):
        raise ZigStageError("archive-inventory")
    for part in pure.parts:
        normalized_part = unicodedata.normalize("NFKC", part)
        device_name = normalized_part.split(".", 1)[0].rstrip(" .").casefold()
        if (
            ":" in normalized_part
            or normalized_part.endswith((" ", "."))
            or device_name in _WINDOWS_RESERVED
        ):
            raise ZigStageError("archive-inventory")
    return pure


def _validate_archive(archive: Path) -> tuple[zipfile.ZipInfo, ...]:
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = tuple(bundle.infolist())
    except (OSError, zipfile.BadZipFile) as error:
        raise ZigStageError("archive-inventory") from error
    if not members or len(members) > MAX_ARCHIVE_MEMBERS:
        raise ZigStageError("archive-inventory")
    seen: set[str] = set()
    total = 0
    for member in members:
        pure = _safe_member_path(member.filename)
        normalized = unicodedata.normalize("NFKC", pure.as_posix()).casefold()
        if normalized in seen or member.flag_bits & 0x1:
            raise ZigStageError("archive-inventory")
        seen.add(normalized)
        total += member.file_size
        if member.file_size > MAX_MEMBER_SIZE or total > MAX_ARCHIVE_UNCOMPRESSED:
            raise ZigStageError("archive-inventory")
        if (
            member.file_size > 1024 * 1024
            and member.file_size > max(member.compress_size, 1) * 5000
        ):
            raise ZigStageError("archive-inventory")
        unix_mode = member.external_attr >> 16
        file_type = stat.S_IFMT(unix_mode)
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise ZigStageError("archive-inventory")
        if member.is_dir() != member.filename.endswith("/"):
            raise ZigStageError("archive-inventory")
    return members


def _extract_archive(archive: Path, root: Path, members: Sequence[zipfile.ZipInfo]) -> Path:
    extracted = root / "tool"
    extracted.mkdir()
    try:
        with zipfile.ZipFile(archive) as bundle:
            for member in members:
                pure = _safe_member_path(member.filename)
                target = extracted.joinpath(*pure.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
    except ZigStageError:
        raise
    except Exception as error:
        raise ZigStageError("archive-extraction") from error
    tool_root = extracted / ZIG_ROOT_NAME
    executable = tool_root / "zig.exe"
    if not _ordinary_directory(tool_root) or not _ordinary_file(executable, nonempty=True):
        raise ZigStageError("archive-extraction")
    for path in _walk_tree(extracted):
        if not (_ordinary_directory(path) or _ordinary_file(path)):
            raise ZigStageError("archive-extraction")
    return executable


def _run_quiet(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            env=env,
        )
    except Exception as error:
        raise ZigStageError("probe") from error


def _windows_nuitka_environment(executable: Path) -> dict[str, str]:
    """Build a subprocess-only environment for the exact reviewed Zig compiler."""
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{executable.parent}{os.pathsep}{environment.get('PATH', '')}",
            "CFLAGS": WINDOWS_CPU_BASELINE_FLAG,
            "CCFLAGS": "",
            "CPPFLAGS": "",
            "CXXFLAGS": "",
            "LDFLAGS": "",
        }
    )
    environment.pop("CC", None)
    environment.pop("CXX", None)
    return environment


def _nuitka_probe_command(source: Path, output: Path, *, pyside: bool) -> tuple[str, ...]:
    command = [
        sys.executable,
        "-m",
        "nuitka",
        str(source),
        "--follow-imports",
        f"--output-dir={output}",
        "--standalone",
        "--quiet",
        "--static-libpython=no",
        "--zig",
        WINDOWS_NUITKA_DEPENDENCY_MODE,
    ]
    if pyside:
        command.extend(
            (
                "--enable-plugin=pyside6",
                "--noinclude-qt-translations",
                "--noinclude-qt-plugins=tls",
            )
        )
    return tuple(command)


def _validate_nuitka_report(output: Path, stem: str, executable: Path) -> None:
    try:
        from .build import _validate_zig_scons_report
    except ImportError:
        from build import _validate_zig_scons_report  # type: ignore[attr-defined,no-redef]

    try:
        _validate_zig_scons_report(output, stem, executable)
    except ValueError as error:
        raise ZigStageError("nuitka-report") from error


def _classify_nuitka_failure(
    completed: subprocess.CompletedProcess[bytes],
    *,
    prefix: str,
) -> str:
    """Return one fixed category without decoding or exposing native output."""
    if prefix not in {"nuitka", "pyside"}:
        return "nuitka-compile-unclassified"
    captured = (completed.stdout or b"") + (completed.stderr or b"")
    if len(captured) > MAX_FAILURE_CLASSIFICATION_BYTES:
        return f"{prefix}-compile-unclassified"

    marker = b"failed unexpectedly in scons c backend compilation."
    if captured.lower().count(marker) == 1:
        return f"{prefix}-scons-backend"
    return f"{prefix}-compile-unclassified"


def _validate_zig_identity(executable: Path) -> None:
    completed = _run_quiet((str(executable), "version"), cwd=executable.parent, timeout=30)
    if completed.returncode != 0 or completed.stdout.strip() != ZIG_VERSION.encode("ascii"):
        raise ZigStageError("zig-version")


def _configured_zig() -> tuple[Path, Path, str]:
    root_value = os.environ.get("ORDIFILE_ZIG_ROOT")
    executable_value = os.environ.get("ORDIFILE_ZIG_EXE")
    token = os.environ.get("ORDIFILE_ZIG_CLEANUP_TOKEN", "")
    executable_sha256 = os.environ.get("ORDIFILE_ZIG_EXE_SHA256", "")
    tree_sha256 = os.environ.get("ORDIFILE_ZIG_TREE_SHA256", "")
    if (
        not root_value
        or not executable_value
        or not token
        or not re.fullmatch(r"[0-9a-f]{64}", executable_sha256)
        or not re.fullmatch(r"[0-9a-f]{64}", tree_sha256)
    ):
        raise ZigStageError("environment")
    root = Path(root_value)
    executable = Path(executable_value)
    tool_root = root / "tool" / ZIG_ROOT_NAME
    try:
        if (
            not _safe_owned_tree(root, token)
            or not _ordinary_directory(tool_root)
            or not _ordinary_file(executable, nonempty=True)
            or executable != tool_root / "zig.exe"
            or not executable.resolve(strict=True).is_relative_to(root.resolve(strict=True))
            or _sha256(executable) != executable_sha256
            or _tree_sha256(tool_root) != tree_sha256
        ):
            raise ZigStageError("environment")
    except OSError as error:
        raise ZigStageError("environment") from error
    _validate_zig_identity(executable)
    return root, executable, token


def _validate_pe_x64(executable: Path) -> None:
    if not _ordinary_file(executable, nonempty=True):
        raise ZigStageError("probe")
    try:
        with executable.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ZigStageError("probe")
            stream.seek(0x3C)
            offset_bytes = stream.read(4)
            if len(offset_bytes) != 4:
                raise ZigStageError("probe")
            stream.seek(struct.unpack("<I", offset_bytes)[0])
            if stream.read(4) != b"PE\0\0" or stream.read(2) != b"\x64\x86":
                raise ZigStageError("probe")
    except ZigStageError:
        raise
    except OSError as error:
        raise ZigStageError("probe") from error


def _validate_pyside_probe_bundle(bundle: Path) -> None:
    if not _ordinary_directory(bundle):
        raise ZigStageError("pyside-output")
    platform_plugins: list[Path] = []
    try:
        for path in _walk_tree(bundle):
            if not (_ordinary_directory(path) or _ordinary_file(path)):
                raise ZigStageError("pyside-output")
            relative = path.relative_to(bundle)
            parts = tuple(part.casefold() for part in relative.parts)
            if path.name.casefold() == "zig.exe":
                raise ZigStageError("pyside-output")
            if (
                _ordinary_file(path)
                and path.name.casefold() == "qwindows.dll"
                and ("platforms" in parts)
            ):
                platform_plugins.append(path)
    except (OSError, ValueError) as error:
        raise ZigStageError("pyside-output") from error
    if len(platform_plugins) != 1:
        raise ZigStageError("pyside-output")


def _validate_plain_probe_bundle(bundle: Path) -> None:
    if not _ordinary_directory(bundle):
        raise ZigStageError("nuitka-output")
    try:
        for path in _walk_tree(bundle):
            if not (_ordinary_directory(path) or _ordinary_file(path)):
                raise ZigStageError("nuitka-output")
            if path.name.casefold() == "zig.exe":
                raise ZigStageError("nuitka-output")
    except OSError as error:
        raise ZigStageError("nuitka-output") from error


def _run_packaged_probe(candidate: Path, probe: Path, *, stage: str) -> None:
    environment = os.environ.copy()
    environment.update({"PYTHONPATH": "", "PYTHONNOUSERSITE": "1", "QT_QPA_PLATFORM": "offscreen"})
    try:
        executed = subprocess.run(
            (str(candidate),),
            cwd=probe,
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=60,
            env=environment,
        )
    except Exception as error:
        raise ZigStageError(stage) from error
    if executed.returncode != 0:
        raise ZigStageError(stage)


def bootstrap() -> None:
    if platform.system() != "Windows" or os.environ.get(
        "PROCESSOR_ARCHITECTURE", ""
    ).casefold() not in {
        "amd64",
        "x86_64",
    }:
        raise ZigStageError("platform")
    root = _expected_root()
    token = uuid.uuid4().hex
    _write_cleanup_environment(root, token)
    _create_owned_root(root, token)
    ready = False
    try:
        archive = root / ZIG_ARCHIVE_NAME
        _download_archive(archive)
        members = _validate_archive(archive)
        executable = _extract_archive(archive, root, members)
        archive.unlink()
        _validate_zig_identity(executable)
        _write_tool_environment(root, executable)
        ready = True
    finally:
        if not ready:
            _remove_owned_root(root, token)
    print(f"Windows job-local Zig bootstrap PASS version={ZIG_VERSION} target=windows-x86_64")


def verify_native() -> None:
    root, executable, _token = _configured_zig()
    probe = root / "probe-native"
    if probe.exists() or probe.is_symlink():
        raise ZigStageError("probe")
    probe.mkdir()
    try:
        source = probe / "probe.c"
        source.write_text(
            "#include <windows.h>\nint main(void) { return GetCurrentProcessId() == 0 ? 1 : 0; }\n",
            encoding="ascii",
            newline="\n",
        )
        output = probe / "probe.exe"
        completed = _run_quiet(
            (
                str(executable),
                "cc",
                WINDOWS_CPU_BASELINE_FLAG,
                str(source),
                "-o",
                str(output),
            ),
            cwd=probe,
            timeout=5 * 60,
        )
        if completed.returncode != 0:
            raise ZigStageError("native-compile-link")
        _validate_pe_x64(output)
        executed = _run_quiet((str(output),), cwd=probe, timeout=30)
        if executed.returncode != 0:
            raise ZigStageError("native-execute")
    finally:
        if probe.exists() and _ordinary_directory(probe):
            shutil.rmtree(probe)
    _configured_zig()
    print(f"Windows Zig native probe PASS version={ZIG_VERSION} target=windows-x86_64")


def verify_nuitka() -> None:
    root, executable, _token = _configured_zig()
    try:
        nuitka_version = version("Nuitka")
    except PackageNotFoundError as error:
        raise ZigStageError("nuitka-environment") from error
    if nuitka_version != NUITKA_VERSION or sys.version_info[:3] != (3, 14, 3):
        raise ZigStageError("nuitka-environment")
    probe = root / "probe-nuitka"
    if probe.exists() or probe.is_symlink():
        raise ZigStageError("nuitka-probe")
    probe.mkdir()
    try:
        source = probe / "probe.py"
        source.write_text("raise SystemExit(0)\n", encoding="ascii", newline="\n")
        output = probe / "result"
        output.mkdir()
        completed = _run_quiet(
            _nuitka_probe_command(source, output, pyside=False),
            cwd=probe,
            timeout=20 * 60,
            env=_windows_nuitka_environment(executable),
        )
        if completed.returncode != 0:
            raise ZigStageError(
                _classify_nuitka_failure(
                    completed,
                    prefix="nuitka",
                )
            )
        _validate_nuitka_report(output, source.stem, executable)
        bundle = output / "probe.dist"
        _validate_plain_probe_bundle(bundle)
        candidate = bundle / "probe.exe"
        _validate_pe_x64(candidate)
        _run_packaged_probe(candidate, probe, stage="nuitka-execute")
    finally:
        if probe.exists() and _ordinary_directory(probe):
            shutil.rmtree(probe)
    _configured_zig()
    print(
        "Windows plain Nuitka Zig probe PASS "
        f"python=3.14.3 nuitka={NUITKA_VERSION} zig={ZIG_VERSION} target=windows-x86_64"
    )


def verify_pyside() -> None:
    root, executable, _token = _configured_zig()
    try:
        versions = {
            "Nuitka": version("Nuitka"),
            "PySide6-Essentials": version("PySide6-Essentials"),
            "shiboken6": version("shiboken6"),
        }
    except PackageNotFoundError as error:
        raise ZigStageError("pyside-environment") from error
    if versions != {
        "Nuitka": NUITKA_VERSION,
        "PySide6-Essentials": PYSIDE_VERSION,
        "shiboken6": PYSIDE_VERSION,
    } or sys.version_info[:3] != (3, 14, 3):
        raise ZigStageError("pyside-environment")
    probe = root / "probe-pyside"
    if probe.exists() or probe.is_symlink():
        raise ZigStageError("pyside-probe")
    probe.mkdir()
    try:
        source = probe / "probe.py"
        source.write_text(
            "from PySide6.QtWidgets import QApplication, QWidget\n"
            "app = QApplication(['ordifile-zig-probe'])\n"
            "window = QWidget()\n"
            "window.show()\n"
            "app.processEvents()\n"
            "raise SystemExit(0 if window.isVisible() else 1)\n",
            encoding="ascii",
            newline="\n",
        )
        output = probe / "result"
        output.mkdir()
        completed = _run_quiet(
            _nuitka_probe_command(source, output, pyside=True),
            cwd=probe,
            timeout=20 * 60,
            env=_windows_nuitka_environment(executable),
        )
        if completed.returncode != 0:
            raise ZigStageError(
                _classify_nuitka_failure(
                    completed,
                    prefix="pyside",
                )
            )
        _validate_nuitka_report(output, source.stem, executable)
        bundle = output / "probe.dist"
        _validate_pyside_probe_bundle(bundle)
        candidate = bundle / "probe.exe"
        _validate_pe_x64(candidate)
        _run_packaged_probe(candidate, probe, stage="pyside-execute")
    finally:
        if probe.exists() and _ordinary_directory(probe):
            shutil.rmtree(probe)
    _configured_zig()
    print(
        "Windows PySide6/Nuitka Zig probe PASS "
        f"python=3.14.3 nuitka={NUITKA_VERSION} pyside6={PYSIDE_VERSION} "
        f"zig={ZIG_VERSION} target=windows-x86_64"
    )


def cleanup() -> None:
    root_value = os.environ.get("ORDIFILE_ZIG_ROOT")
    token = os.environ.get("ORDIFILE_ZIG_CLEANUP_TOKEN", "")
    if not root_value and not token:
        return
    if not root_value or not token:
        raise ZigStageError("cleanup")
    root = Path(root_value)
    if root != _expected_root():
        raise ZigStageError("cleanup")
    if not root.exists() and not root.is_symlink():
        return
    _remove_owned_root(root, token)
    print("Windows job-local Zig cleanup PASS")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the exact job-local Windows Zig toolchain")
    parser.add_argument(
        "mode", choices=("bootstrap", "verify-native", "verify-nuitka", "verify-pyside", "cleanup")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    mode = build_parser().parse_args(argv).mode
    try:
        {
            "bootstrap": bootstrap,
            "verify-native": verify_native,
            "verify-nuitka": verify_nuitka,
            "verify-pyside": verify_pyside,
            "cleanup": cleanup,
        }[mode]()
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except ZigStageError as error:
        print(f"Windows job-local Zig operation failed at stage={error.stage}; details withheld.")
        return 1
    except Exception:
        print("Windows job-local Zig operation failed at stage=unknown; details withheld.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
