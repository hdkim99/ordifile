# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Verify Ordifile release archives and run a checkout-free wheel smoke test."""

from __future__ import annotations

import argparse
import ast
import base64
import configparser
import csv
import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unicodedata
import zipfile
from dataclasses import dataclass
from email.message import Message
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Never
from xml.etree import ElementTree

PROJECT_NAME = "ordifile"
LEGACY_NAME = "labconvert"
CONSOLE_ENTRY_POINT = "ordifile.cli.main:main"
SEMVER_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)
MANDATORY_WORKBOOK_SHEETS = frozenset(
    {"Manifest", "Samples", "Peak_Matrix", "Peaks", "Metadata", "Import_Log"}
)
LICENSE_FILES = ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md")
SDIST_MAINTAINER_FILES = (
    "scripts/verify_release.py",
    "scripts/fetch_external_fixture.py",
    "scripts/generate_demo_assets.sh",
    "scripts/render_demo_assets.swift",
    "tests/fixtures/synthetic/generate_xlsx.py",
)
WHEEL_FORBIDDEN_TOP_LEVEL = frozenset({"scripts", "tests"})
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class ReleaseVerificationError(RuntimeError):
    """A release artifact failed a deterministic verification rule."""


@dataclass(frozen=True, slots=True)
class ReleaseArtifacts:
    """The two release archives verified for one version."""

    wheel: Path
    sdist: Path
    checksums: Path


def require_semver(value: str, *, field: str) -> str:
    """Return a strict SemVer string or raise a release verification error."""
    if SEMVER_PATTERN.fullmatch(value) is None:
        raise ReleaseVerificationError(f"{field} must be a strict SemVer value: {value!r}")
    return value


def _read_pyproject(source_root: Path) -> tuple[str, str]:
    try:
        parsed = tomllib.loads((source_root / "pyproject.toml").read_text(encoding="utf-8"))
        project = parsed["project"]
        name = project["name"]
        version = project["version"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise ReleaseVerificationError(
            "pyproject.toml has no readable static project version"
        ) from error
    if type(name) is not str or type(version) is not str:
        raise ReleaseVerificationError("pyproject project name and version must be strings")
    return name, version


def _read_source_version(source_root: Path) -> str:
    version_path = source_root / "src" / PROJECT_NAME / "_version.py"
    try:
        module = ast.parse(version_path.read_text(encoding="utf-8"), filename=str(version_path))
    except (OSError, SyntaxError) as error:
        raise ReleaseVerificationError(
            "the source version module is not readable Python"
        ) from error
    values: list[str] = []
    for statement in module.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if isinstance(target, ast.Name) and target.id == "__version__":
            if (
                not isinstance(statement.value, ast.Constant)
                or type(statement.value.value) is not str
            ):
                raise ReleaseVerificationError("source __version__ must be one literal string")
            values.append(statement.value.value)
    if len(values) != 1:
        raise ReleaseVerificationError("source must define __version__ exactly once")
    return values[0]


def verify_source_version(source_root: Path, expected_version: str, tag: str | None = None) -> None:
    """Verify strict tag, pyproject, and source-module version agreement."""
    require_semver(expected_version, field="expected-version")
    if tag is not None and tag != f"v{expected_version}":
        raise ReleaseVerificationError(f"tag must be exactly 'v{expected_version}', not {tag!r}")
    project_name, project_version = _read_pyproject(source_root)
    if project_name != PROJECT_NAME:
        raise ReleaseVerificationError(
            f"project name must be {PROJECT_NAME!r}, not {project_name!r}"
        )
    require_semver(project_version, field="project.version")
    source_version = _read_source_version(source_root)
    require_semver(source_version, field="source __version__")
    if project_version != expected_version or source_version != expected_version:
        raise ReleaseVerificationError(
            "expected, pyproject, and source versions must be identical: "
            f"expected={expected_version!r}, project={project_version!r}, "
            f"source={source_version!r}"
        )


def _safe_archive_name(name: str, *, is_directory: bool = False) -> str:
    candidate = name
    if is_directory and candidate.endswith("/"):
        candidate = candidate[:-1]
    normalized = unicodedata.normalize("NFC", candidate)
    raw_parts = candidate.split("/")
    path = PurePosixPath(normalized)
    unsafe_segment = any(
        part[-1] in {" ", "."}
        or any(character in '<>:"|?*' for character in part)
        or part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES
        for part in raw_parts
        if part
    )
    if (
        not candidate
        or normalized != candidate
        or "\x00" in candidate
        or "\\" in candidate
        or (not is_directory and name.endswith("/"))
        or any(part in {"", ".", ".."} for part in raw_parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in candidate)
        or unsafe_segment
        or path.is_absolute()
    ):
        raise ReleaseVerificationError(f"unsafe archive member path: {name!r}")
    return normalized


def _metadata_value(metadata: Message, key: str) -> str:
    value = metadata.get(key)
    if value is None:
        raise ReleaseVerificationError(f"package metadata is missing {key}")
    return value


def _verify_core_metadata(raw: bytes, expected_version: str) -> Message:
    metadata = BytesParser().parsebytes(raw)
    if _metadata_value(metadata, "Name") != PROJECT_NAME:
        raise ReleaseVerificationError("artifact metadata has the wrong project name")
    if _metadata_value(metadata, "Version") != expected_version:
        raise ReleaseVerificationError("artifact metadata has the wrong version")
    if _metadata_value(metadata, "License-Expression") != "Apache-2.0":
        raise ReleaseVerificationError("artifact metadata must declare Apache-2.0")
    license_names = {PurePosixPath(value).name for value in metadata.get_all("License-File", [])}
    if not set(LICENSE_FILES).issubset(license_names):
        raise ReleaseVerificationError("artifact metadata is missing required License-File entries")
    return metadata


def _record_digest(content: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")


def _verify_wheel_record(archive: zipfile.ZipFile, record_name: str) -> None:
    names = archive.namelist()
    try:
        rows = tuple(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
    except (KeyError, UnicodeDecodeError, csv.Error) as error:
        raise ReleaseVerificationError("wheel RECORD is unreadable") from error
    records: dict[str, tuple[str, str]] = {}
    for row in rows:
        if len(row) != 3 or row[0] in records:
            raise ReleaseVerificationError("wheel RECORD has malformed or duplicate rows")
        records[row[0]] = (row[1], row[2])
    if set(records) != set(names):
        raise ReleaseVerificationError("wheel RECORD does not cover every archive member exactly")
    for name in names:
        digest, size = records[name]
        if name == record_name:
            if digest or size:
                raise ReleaseVerificationError(
                    "wheel RECORD must leave its own hash and size empty"
                )
            continue
        content = archive.read(name)
        if digest != f"sha256={_record_digest(content)}" or size != str(len(content)):
            raise ReleaseVerificationError(f"wheel RECORD mismatch for {name!r}")


def verify_wheel(path: Path, expected_version: str, source_root: Path) -> None:
    """Verify wheel identity, content, licenses, entry point, and RECORD hashes."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            canonical_names: list[str] = []
            member_keys: set[str] = set()
            for info in infos:
                canonical = _safe_archive_name(
                    info.orig_filename,
                    is_directory=info.is_dir(),
                )
                key = canonical.casefold()
                if key in member_keys:
                    raise ReleaseVerificationError(
                        "wheel contains normalized or casefold duplicate member names"
                    )
                member_keys.add(key)
                canonical_names.append(canonical)
                if PurePosixPath(canonical).parts[0].casefold() in WHEEL_FORBIDDEN_TOP_LEVEL:
                    raise ReleaseVerificationError(
                        "wheel must not contain maintainer scripts or test fixtures"
                    )
            lowered = tuple(name.casefold() for name in canonical_names)
            if any(name.startswith(f"{LEGACY_NAME}/") for name in lowered):
                raise ReleaseVerificationError("wheel contains the legacy package")
            if not any(name.startswith(f"{PROJECT_NAME}/") for name in names):
                raise ReleaseVerificationError("wheel does not contain the Ordifile package")
            dist_info = [
                name
                for name in names
                if name.endswith(".dist-info/METADATA")
                and PurePosixPath(name).parts[0].startswith(f"{PROJECT_NAME}-")
            ]
            if len(dist_info) != 1:
                raise ReleaseVerificationError("wheel must contain one Ordifile METADATA file")
            prefix = dist_info[0].removesuffix("METADATA")
            _verify_core_metadata(archive.read(dist_info[0]), expected_version)
            entry_name = f"{prefix}entry_points.txt"
            try:
                entry_text = archive.read(entry_name).decode("utf-8")
            except (KeyError, UnicodeDecodeError) as error:
                raise ReleaseVerificationError(
                    "wheel entry_points.txt is missing or invalid"
                ) from error
            parser = configparser.ConfigParser(interpolation=None)
            try:
                parser.read_string(entry_text)
            except configparser.Error as error:
                raise ReleaseVerificationError("wheel entry_points.txt is malformed") from error
            if parser.sections() != ["console_scripts"] or dict(parser["console_scripts"]) != {
                PROJECT_NAME: CONSOLE_ENTRY_POINT
            }:
                raise ReleaseVerificationError("wheel must expose only the ordifile console script")
            if LEGACY_NAME in entry_text.casefold():
                raise ReleaseVerificationError("wheel exposes a legacy entry point")
            for license_name in LICENSE_FILES:
                candidates = [
                    name
                    for name in names
                    if name.startswith(f"{prefix}licenses/")
                    and PurePosixPath(name).name == license_name
                ]
                if len(candidates) != 1:
                    raise ReleaseVerificationError(f"wheel is missing {license_name}")
                if archive.read(candidates[0]) != (source_root / license_name).read_bytes():
                    raise ReleaseVerificationError(f"wheel {license_name} differs from source")
            source_members = [name for name in names if name.startswith(f"{PROJECT_NAME}/")]
            for name in source_members:
                if name.endswith(".py") and LEGACY_NAME.encode() in archive.read(name).lower():
                    raise ReleaseVerificationError(f"wheel source retains legacy name in {name}")
            record_name = f"{prefix}RECORD"
            _verify_wheel_record(archive, record_name)
    except (OSError, zipfile.BadZipFile) as error:
        raise ReleaseVerificationError(f"wheel is unreadable: {path.name}") from error


def verify_sdist(path: Path, expected_version: str, source_root: Path) -> None:
    """Verify sdist identity, safe regular content, licenses, and package layout."""
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if any(not (member.isfile() or member.isdir()) for member in members):
                raise ReleaseVerificationError(
                    "sdist may contain only regular files and directories"
                )
            canonical_names: list[str] = []
            member_keys: set[str] = set()
            for member in members:
                canonical = _safe_archive_name(member.name, is_directory=member.isdir())
                key = canonical.casefold()
                if key in member_keys:
                    raise ReleaseVerificationError(
                        "sdist contains normalized or casefold duplicate member names"
                    )
                member_keys.add(key)
                canonical_names.append(canonical)
            roots = {PurePosixPath(name).parts[0] for name in canonical_names}
            if len(roots) != 1:
                raise ReleaseVerificationError("sdist must have one top-level directory")
            root = next(iter(roots))
            if root != f"{PROJECT_NAME}-{expected_version}":
                raise ReleaseVerificationError("sdist top-level directory has the wrong identity")

            def read_member(relative: str) -> bytes:
                name = f"{root}/{relative}"
                member = archive.getmember(name)
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ReleaseVerificationError(
                        f"sdist member is not a regular file: {relative}"
                    )
                return extracted.read()

            _verify_core_metadata(read_member("PKG-INFO"), expected_version)
            if f"{root}/src/{PROJECT_NAME}/__init__.py" not in names:
                raise ReleaseVerificationError("sdist is missing the Ordifile package")
            if any(f"/src/{LEGACY_NAME}/" in f"/{name.casefold()}" for name in names):
                raise ReleaseVerificationError("sdist contains the legacy package")
            for license_name in LICENSE_FILES:
                if read_member(license_name) != (source_root / license_name).read_bytes():
                    raise ReleaseVerificationError(f"sdist {license_name} differs from source")
            for relative in SDIST_MAINTAINER_FILES:
                if f"{root}/{relative}" not in names:
                    raise ReleaseVerificationError(
                        f"sdist is missing required maintainer file: {relative}"
                    )
                if read_member(relative) != (source_root / relative).read_bytes():
                    raise ReleaseVerificationError(
                        f"sdist maintainer file differs from source: {relative}"
                    )
            for member in members:
                package_prefix = f"{root}/src/{PROJECT_NAME}/"
                if (
                    member.isfile()
                    and member.name.startswith(package_prefix)
                    and member.name.endswith(".py")
                ):
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise ReleaseVerificationError("sdist Python member is unreadable")
                    if LEGACY_NAME.encode() in extracted.read().lower():
                        raise ReleaseVerificationError(
                            f"sdist source retains legacy name in {member.name}"
                        )
    except (OSError, KeyError, tarfile.TarError) as error:
        raise ReleaseVerificationError(f"sdist is unreadable: {path.name}") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256sums(artifacts: tuple[Path, ...], output: Path) -> None:
    """Atomically write a stable filename-sorted GNU-style SHA256SUMS file."""
    if output.exists() and (output.is_symlink() or not output.is_file()):
        raise ReleaseVerificationError("SHA256SUMS output must be a regular file or absent")
    unique_names = {path.name for path in artifacts}
    if len(unique_names) != len(artifacts):
        raise ReleaseVerificationError("release artifact basenames must be unique")
    content = "".join(
        f"{_sha256(path)}  {path.name}\n" for path in sorted(artifacts, key=lambda p: p.name)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _extract_wheel_for_smoke(wheel: Path, destination: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        member_keys: set[str] = set()
        for info in archive.infolist():
            canonical = _safe_archive_name(
                info.orig_filename,
                is_directory=info.is_dir(),
            )
            key = canonical.casefold()
            if key in member_keys:
                raise ReleaseVerificationError(
                    "wheel smoke input contains normalized or casefold duplicate members"
                )
            member_keys.add(key)
            if info.is_dir():
                continue
            target = destination.joinpath(*PurePosixPath(canonical).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)


def _run_isolated_python(site: Path, cwd: Path, arguments: list[str]) -> None:
    bootstrap = (
        "import pathlib,sys;"
        f"site=pathlib.Path({str(site)!r}).resolve();"
        "sys.path.insert(0,str(site));"
        "import ordifile;"
        "module=pathlib.Path(ordifile.__file__).resolve();"
        "assert module.is_relative_to(site), module;"
        "from ordifile.cli.main import main;"
        f"raise SystemExit(main({arguments!r}))"
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-I", "-c", bootstrap],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ReleaseVerificationError(
            "clean-wheel CLI smoke failed: "
            f"stdout={completed.stdout[-1000:]!r}, stderr={completed.stderr[-1000:]!r}"
        )


def _verify_smoke_workbook(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as workbook:
            raw = workbook.read("xl/workbook.xml")
        root = ElementTree.fromstring(raw)
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as error:
        raise ReleaseVerificationError(
            "clean-wheel smoke did not create a readable XLSX"
        ) from error
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    names = {element.attrib.get("name", "") for element in root.iter(f"{namespace}sheet")}
    if not MANDATORY_WORKBOOK_SHEETS.issubset(names):
        raise ReleaseVerificationError("smoke workbook is missing mandatory sheets")


def run_clean_wheel_smoke(wheel: Path) -> None:
    """Import only extracted wheel code from a temporary cwd and run CLI conversion."""
    with tempfile.TemporaryDirectory(prefix="ordifile-release-smoke-") as raw_temp:
        workspace = Path(raw_temp)
        site = workspace / "wheel-site"
        site.mkdir()
        _extract_wheel_for_smoke(wheel, site)
        cwd = workspace / "empty-cwd"
        cwd.mkdir()
        source = cwd / "smoke.csv"
        source.write_text(
            "sample_id,sequence,retention_time,area,compound\nrelease_smoke,1,1.25,42,synthetic\n",
            encoding="utf-8",
        )
        _run_isolated_python(site, cwd, ["--version"])
        _run_isolated_python(site, cwd, ["formats"])
        _run_isolated_python(
            site,
            cwd,
            ["convert", source.name, "--output", "Ordifile_Result.xlsx"],
        )
        _verify_smoke_workbook(cwd / "Ordifile_Result.xlsx")


def verify_release(
    *,
    source_root: Path,
    dist_dir: Path,
    expected_version: str,
    tag: str | None = None,
    checksums: Path | None = None,
    smoke: bool = True,
) -> ReleaseArtifacts:
    """Verify one wheel/sdist pair, write checksums, and optionally run smoke tests."""
    source_root = source_root.resolve()
    dist_dir = dist_dir.resolve()
    if not source_root.is_dir() or not dist_dir.is_dir():
        raise ReleaseVerificationError(
            "source root and dist directory must be existing directories"
        )
    verify_source_version(source_root, expected_version, tag)
    wheels = tuple(sorted(dist_dir.glob(f"{PROJECT_NAME}-{expected_version}-*.whl")))
    sdists = tuple(sorted(dist_dir.glob(f"{PROJECT_NAME}-{expected_version}.tar.gz")))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseVerificationError(
            "dist directory must contain exactly one matching wheel and one matching sdist"
        )
    unrelated = tuple(
        path
        for path in dist_dir.iterdir()
        if path.is_file()
        and path.name != "SHA256SUMS"
        and path.suffix in {".whl", ".gz", ".zip"}
        and path not in {wheels[0], sdists[0]}
    )
    if unrelated:
        raise ReleaseVerificationError("dist directory contains unrelated release archives")
    verify_wheel(wheels[0], expected_version, source_root)
    verify_sdist(sdists[0], expected_version, source_root)
    if smoke:
        run_clean_wheel_smoke(wheels[0])
    checksum_path = (dist_dir / "SHA256SUMS") if checksums is None else checksums.resolve()
    if checksum_path in {wheels[0], sdists[0]}:
        raise ReleaseVerificationError("SHA256SUMS output must not alias a release archive")
    write_sha256sums((wheels[0], sdists[0]), checksum_path)
    return ReleaseArtifacts(wheels[0], sdists[0], checksum_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--tag", help="Optional exact v-prefixed release tag to verify.")
    parser.add_argument("--checksums", type=Path, help="SHA256SUMS destination.")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip clean-wheel CLI smoke.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point used by the release workflow."""
    arguments = _parser().parse_args(argv)
    tag = arguments.tag
    if tag is None and os.environ.get("GITHUB_REF_TYPE") == "tag":
        tag = os.environ.get("GITHUB_REF_NAME")
    try:
        artifacts = verify_release(
            source_root=arguments.source_root,
            dist_dir=arguments.dist_dir,
            expected_version=arguments.expected_version,
            tag=tag,
            checksums=arguments.checksums,
            smoke=not arguments.skip_smoke,
        )
    except ReleaseVerificationError as error:
        print(f"release verification failed: {error}", file=sys.stderr)
        return 1
    print(f"verified wheel: {artifacts.wheel.name}")
    print(f"verified sdist: {artifacts.sdist.name}")
    print(f"checksums: {artifacts.checksums}")
    return 0


def _entry_point() -> Never:
    raise SystemExit(main())


if __name__ == "__main__":
    _entry_point()
