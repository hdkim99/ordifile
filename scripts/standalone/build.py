# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Build one native unsigned Ordifile candidate with official pyside6-deploy."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import zipfile
from collections.abc import Sequence
from importlib.metadata import distribution
from pathlib import Path

from ordifile import __version__

try:
    from .verify import build_manifest, write_manifest
except ImportError:
    from verify import build_manifest, write_manifest  # type: ignore[import-not-found,no-redef]

NUITKA_VERSION = "4.1.3"
LICENSE_DISTRIBUTIONS = (
    "defusedxml",
    "et-xmlfile",
    "olefile",
    "openpyxl",
    "XlsxWriter",
)
BUILD_FAILURE_STAGES = frozenset(
    {
        "archive",
        "bundle-audit",
        "bundle-discovery",
        "deploy",
        "license-inventory",
        "prepare",
        "signature-inspection",
        "unknown",
    }
)


class StandaloneBuildStageError(RuntimeError):
    """Report only a fixed build stage while withholding private tool output."""

    def __init__(self, stage: str) -> None:
        safe_stage = stage if stage in BUILD_FAILURE_STAGES else "unknown"
        super().__init__(safe_stage)
        self.stage = safe_stage


def _render_spec(template: Path, destination: Path, stage: Path, executable_dir: Path) -> None:
    text = template.read_text(encoding="utf-8")
    replacements = {
        "@PROJECT_DIR@": stage.as_posix(),
        "@EXEC_DIRECTORY@": executable_dir.as_posix(),
        "@PYTHON_PATH@": Path(sys.executable).as_posix(),
    }
    for marker, value in replacements.items():
        text = text.replace(marker, value)
    if "@" in text:
        raise ValueError("The standalone deployment template has unresolved markers.")
    destination.write_text(text, encoding="utf-8", newline="\n")


def _deploy_executable() -> Path:
    scripts = Path(sysconfig.get_path("scripts"))
    executable = scripts / ("pyside6-deploy.exe" if os.name == "nt" else "pyside6-deploy")
    if not executable.is_file():
        raise ValueError("pyside6-deploy is unavailable in the active build environment.")
    return executable


def _bundle_candidate(directory: Path, target: str) -> Path:
    if target.startswith("macos-"):
        candidates = tuple(directory.glob("*.app"))
    else:
        candidates = tuple(path for path in directory.glob("*.dist") if path.is_dir())
    if len(candidates) != 1:
        raise ValueError("pyside6-deploy did not create exactly one standalone bundle.")
    return candidates[0]


def _validate_native_target(target: str) -> None:
    machine = (
        os.uname().machine.casefold()
        if hasattr(os, "uname")
        else os.environ.get("PROCESSOR_ARCHITECTURE", "").casefold()
    )
    expected = {
        "darwin": {"arm64": "macos-arm64", "x86_64": "macos-x86_64"},
        "win32": {"amd64": "windows-x86_64", "x86_64": "windows-x86_64"},
    }.get(sys.platform, {}).get(machine)
    if expected != target:
        raise ValueError("The requested standalone target is not native to this build host.")


def _license_destination(bundle: Path, target: str) -> Path:
    if target.startswith("macos-"):
        return bundle / "Contents" / "Resources" / "licenses"
    return bundle / "licenses"


def _copy_distribution_licenses(destination: Path) -> None:
    package_root = destination / "python-packages"
    for name in LICENSE_DISTRIBUTIONS:
        installed = distribution(name)
        candidates = tuple(
            item
            for item in installed.files or ()
            if item.name.casefold().startswith(("license", "licence", "copying", "notice"))
        )
        if not candidates:
            raise ValueError("An embedded Python dependency has no installed license file.")
        target = package_root / f"{installed.metadata['Name']}-{installed.version}"
        target.mkdir(parents=True)
        for index, item in enumerate(candidates, start=1):
            source = Path(str(installed.locate_file(item)))
            if not source.is_file() or source.is_symlink():
                raise ValueError("An embedded Python dependency license file is invalid.")
            shutil.copy2(source, target / f"{index:02d}-{item.name}")


def _tree_entries(root: Path) -> tuple[Path, ...]:
    entries: list[Path] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        children = sorted(os.scandir(directory), key=lambda item: item.name, reverse=True)
        for child in children:
            path = Path(child.path)
            entries.append(path)
            if child.is_dir(follow_symlinks=False) and not child.is_symlink():
                stack.append(path)
    return tuple(sorted(entries, key=lambda item: item.relative_to(root).as_posix()))


def _deterministic_zip(source: Path, destination: Path) -> None:
    root_name = source.name
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in _tree_entries(source):
            relative = Path(root_name) / path.relative_to(source)
            if path.is_dir() and not path.is_symlink():
                continue
            info = zipfile.ZipInfo(relative.as_posix(), (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            if path.is_symlink():
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                data = os.readlink(path).encode("utf-8")
            else:
                mode = path.stat(follow_symlinks=False).st_mode & 0o777
                info.external_attr = (stat.S_IFREG | mode) << 16
                data = path.read_bytes()
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _private_build_paths(source: Path, stage: Path) -> tuple[str, ...]:
    candidates = {
        str(source.resolve()),
        str(stage.resolve()),
        str(Path.home().resolve()),
        str(Path(sys.prefix).resolve()),
        str(Path(sys.executable).resolve()),
        str(Path(tempfile.gettempdir()).resolve()),
    }
    for name in ("GITHUB_WORKSPACE", "RUNNER_TEMP", "RUNNER_TOOL_CACHE"):
        value = os.environ.get(name)
        if value:
            candidates.add(str(Path(value).resolve()))
    return tuple(sorted(candidates))


def build_candidate(source: Path, output: Path, *, commit: str, target: str) -> Path:
    """Build into a disposable project and emit only the audited outer artifact set."""
    if output.exists():
        raise ValueError("The standalone candidate output already exists.")
    _validate_native_target(target)
    packaging = source / "packaging" / "standalone"
    scripts = source / "scripts" / "standalone"
    if not packaging.is_dir() or not scripts.is_dir():
        raise ValueError("The standalone packaging sources are incomplete.")
    with tempfile.TemporaryDirectory(prefix="ordifile-standalone-build-") as temporary:
        temporary_stage = Path(temporary)
        build_stage = "prepare"
        try:
            executable_dir = temporary_stage / "result"
            executable_dir.mkdir()
            shutil.copy2(scripts / "entry.py", temporary_stage / "Ordifile.py")
            shutil.copy2(scripts / "smoke.py", temporary_stage / "smoke.py")
            spec = temporary_stage / "pysidedeploy.spec"
            _render_spec(packaging / "pysidedeploy.spec.in", spec, temporary_stage, executable_dir)
            build_stage = "deploy"
            command = [
                str(_deploy_executable()),
                "-c",
                str(spec),
                "--force",
                f"--nuitka-version={NUITKA_VERSION}",
            ]
            completed = subprocess.run(
                command,
                cwd=temporary_stage,
                check=False,
                capture_output=True,
                text=True,
                timeout=45 * 60,
            )
            if completed.returncode != 0:
                raise ValueError("Deployment command failed.")
            build_stage = "bundle-discovery"
            bundle = _bundle_candidate(executable_dir, target)
            build_stage = "license-inventory"
            licenses = _license_destination(bundle, target)
            shutil.copytree(packaging / "licenses", licenses)
            shutil.copy2(source / "LICENSE", licenses / "LICENSE")
            shutil.copy2(source / "NOTICE", licenses / "NOTICE")
            shutil.copy2(source / "THIRD_PARTY_NOTICES.md", licenses / "THIRD_PARTY_NOTICES.md")
            _copy_distribution_licenses(licenses)
            build_stage = "signature-inspection"
            signature_state = "UNSIGNED_PROTOTYPE"
            if target.startswith("macos-"):
                signature = subprocess.run(
                    ["codesign", "-dv", "--verbose=4", str(bundle)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if signature.returncode == 0 and "Signature=adhoc" in signature.stderr:
                    signature_state = "AD_HOC_NOT_NOTARIZED"
            build_stage = "bundle-audit"
            manifest = build_manifest(
                bundle,
                commit=commit,
                target=target,
                signature_state=signature_state,
                forbidden_text=_private_build_paths(source, temporary_stage),
            )
            build_stage = "archive"
            output.mkdir(parents=True)
            archive = output / f"Ordifile-{__version__}-{target}-UNSIGNED.zip"
            _deterministic_zip(bundle, archive)
            archive_sha256 = _sha256(archive)
            manifest["outer_artifact"] = {
                "filename": archive.name,
                "size": archive.stat().st_size,
                "sha256": archive_sha256,
            }
            write_manifest(output / "standalone-manifest.json", manifest)
            (output / "SHA256SUMS.txt").write_text(
                f"{archive_sha256}  {archive.name}\n",
                encoding="ascii",
                newline="\n",
            )
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception:
            raise StandaloneBuildStageError(build_stage) from None
    return archive


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an unsigned Ordifile standalone candidate")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--target", required=True, choices=("windows-x86_64", "macos-arm64", "macos-x86_64")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        build_candidate(args.source, args.output, commit=args.commit, target=args.target)
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except StandaloneBuildStageError as error:
        print(
            f"Standalone candidate build failed at stage={error.stage}; "
            "captured details were withheld."
        )
        return 1
    except Exception:
        print("Standalone candidate build failed at stage=preflight; details were withheld.")
        return 1
    print("Unsigned standalone candidate build PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
