# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Verify the one reviewed existing-artifact release promotion request.

This script never builds, uploads, edits a tag, or changes a release artifact.  It
validates GitHub API responses and the extracted artifact bytes before the release
workflow is allowed to publish them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Never
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen


class PromotionVerificationError(RuntimeError):
    """The existing-artifact promotion failed a deterministic safety gate."""


@dataclass(frozen=True, slots=True)
class PromotionSpec:
    """Immutable facts reviewed for one release-artifact promotion."""

    repository: str
    workflow_id: int
    workflow_path: str
    source_run_id: int
    release_tag: str
    expected_head_sha: str
    artifact_name: str
    artifact_id: int
    artifact_size: int
    artifact_digest: str
    wheel_name: str
    wheel_sha256: str
    sdist_name: str
    sdist_sha256: str
    checksums_sha256: str
    release_notes_sha256: str

    @property
    def version(self) -> str:
        """Return the version encoded by the reviewed v-prefixed tag."""
        return self.release_tag.removeprefix("v")


REVIEWED_PROMOTION = PromotionSpec(
    repository="hdkim99/ordifile",
    workflow_id=335280011,
    workflow_path=".github/workflows/release.yml",
    source_run_id=31980576873,
    release_tag="v0.2.1",
    expected_head_sha="33e1b6ec4d6d822e1a0b532e0d075adc4d79c788",
    artifact_name="ordifile-distributions-31980576873",
    artifact_id=9272226213,
    artifact_size=584321,
    artifact_digest="sha256:44a4040411ea5870d1dfb78e4a0d0969ccfbde666357441bd03c0ddf34de6216",
    wheel_name="ordifile-0.2.1-py3-none-any.whl",
    wheel_sha256="0d485620f46fb86cd37518ee9cd3cb38ecb4e421d2a96fc8666e4399616b4fa8",
    sdist_name="ordifile-0.2.1.tar.gz",
    sdist_sha256="14f71d8ebd4581c4c3001c724de5bb547b5274f165941af628d6f9b02e85ef39",
    checksums_sha256="9bf97b3025a2d312d4f50367fada036261149df67eb3cc5435ee2d3ef742f222",
    release_notes_sha256="b56e4b307535ffd6892d1144a8f83efa1e639abd6e989b446c7457100a908215",
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CHECKSUM_LINE = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)\Z")
_FORBIDDEN_NATIVE_SUFFIXES = frozenset({".ch", ".gcd", ".qgd", ".raw"})
_FORBIDDEN_UPSTREAM_PATH_PARTS = frozenset({"chromconverter", "shimadzu-qgd2csv", "qgd2csv"})
_INDEXES = {
    "testpypi": (
        "https://test.pypi.org/pypi/ordifile/0.2.1/json",
        "test-files.pythonhosted.org",
    ),
    "pypi": (
        "https://pypi.org/pypi/ordifile/0.2.1/json",
        "files.pythonhosted.org",
    ),
}
_MAX_DISTRIBUTION_BYTES = 64 * 1024 * 1024


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PromotionVerificationError(f"{field} must be a JSON object")
    return value


def _sequence(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise PromotionVerificationError(f"{field} must be a JSON array")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PromotionVerificationError(f"unreadable GitHub API response: {path}") from error
    return _mapping(value, field=str(path))


def validate_request(
    *,
    source_run_id: str,
    release_tag: str,
    expected_head_sha: str,
    artifact_name: str,
    spec: PromotionSpec = REVIEWED_PROMOTION,
) -> None:
    """Require the dispatch inputs to identify the one audited promotion exactly."""
    if not source_run_id.isascii() or not source_run_id.isdecimal():
        raise PromotionVerificationError("source_run_id must contain ASCII decimal digits only")
    supplied = (
        source_run_id,
        release_tag,
        expected_head_sha,
        artifact_name,
    )
    expected = (
        str(spec.source_run_id),
        spec.release_tag,
        spec.expected_head_sha,
        spec.artifact_name,
    )
    if supplied != expected:
        raise PromotionVerificationError(
            "dispatch inputs do not match the reviewed immutable v0.2.1 promotion"
        )


def validate_source_metadata(
    *,
    run: dict[str, Any],
    jobs: dict[str, Any],
    artifacts: dict[str, Any],
    tag_ref: dict[str, Any],
    tag_object: dict[str, Any],
    spec: PromotionSpec = REVIEWED_PROMOTION,
) -> None:
    """Validate source workflow, job, artifact, and annotated-tag API responses."""
    repository = _mapping(run.get("repository"), field="run.repository")
    expected_run_fields: dict[str, object] = {
        "id": spec.source_run_id,
        "workflow_id": spec.workflow_id,
        "path": spec.workflow_path,
        "event": "push",
        "head_branch": spec.release_tag,
        "head_sha": spec.expected_head_sha,
        "status": "completed",
        "conclusion": "failure",
    }
    for field, expected in expected_run_fields.items():
        if run.get(field) != expected:
            raise PromotionVerificationError(f"source run {field} differs from the reviewed value")
    if repository.get("full_name") != spec.repository:
        raise PromotionVerificationError("source run belongs to a different repository")

    job_rows = _sequence(jobs.get("jobs"), field="jobs.jobs")
    expected_jobs = {
        "Validate and build once": "success",
        "Wheel smoke / shared DGX / Python 3.14": "success",
        "Publish the same distributions to TestPyPI": "failure",
    }
    for name, conclusion in expected_jobs.items():
        matches = [
            _mapping(row, field=f"job {name}")
            for row in job_rows
            if isinstance(row, dict) and row.get("name") == name
        ]
        if len(matches) != 1 or matches[0].get("conclusion") != conclusion:
            raise PromotionVerificationError(
                f"source job {name!r} does not have the reviewed conclusion {conclusion!r}"
            )

    if artifacts.get("total_count") != 1:
        raise PromotionVerificationError("source run must contain exactly one artifact")
    artifact_rows = _sequence(artifacts.get("artifacts"), field="artifacts.artifacts")
    if len(artifact_rows) != 1:
        raise PromotionVerificationError("source artifact response is inconsistent")
    artifact = _mapping(artifact_rows[0], field="source artifact")
    expected_artifact_fields: dict[str, object] = {
        "id": spec.artifact_id,
        "name": spec.artifact_name,
        "size_in_bytes": spec.artifact_size,
        "expired": False,
        "digest": spec.artifact_digest,
    }
    for field, expected in expected_artifact_fields.items():
        if artifact.get(field) != expected:
            raise PromotionVerificationError(
                f"source artifact {field} differs from the reviewed value"
            )
    artifact_run = _mapping(artifact.get("workflow_run"), field="artifact.workflow_run")
    if (
        artifact_run.get("id") != spec.source_run_id
        or artifact_run.get("head_branch") != spec.release_tag
        or artifact_run.get("head_sha") != spec.expected_head_sha
    ):
        raise PromotionVerificationError("source artifact workflow identity changed")

    validate_tag_metadata(tag_ref=tag_ref, tag_object=tag_object, spec=spec)


def validate_tag_metadata(
    *,
    tag_ref: dict[str, Any],
    tag_object: dict[str, Any],
    spec: PromotionSpec = REVIEWED_PROMOTION,
) -> None:
    """Require the live release ref to remain one direct annotated commit tag."""
    reference = _mapping(tag_ref.get("object"), field="tag reference object")
    if tag_ref.get("ref") != f"refs/tags/{spec.release_tag}" or reference.get("type") != "tag":
        raise PromotionVerificationError("release ref is missing or is not an annotated tag")
    annotated_target = _mapping(tag_object.get("object"), field="annotated tag target")
    if (
        tag_object.get("sha") != reference.get("sha")
        or tag_object.get("tag") != spec.release_tag
        or annotated_target.get("type") != "commit"
        or annotated_target.get("sha") != spec.expected_head_sha
    ):
        raise PromotionVerificationError("annotated release tag target changed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_archive_member_names(path: Path) -> None:
    try:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                names = tuple(info.filename for info in archive.infolist())
        else:
            with tarfile.open(path, "r:gz") as archive:
                names = tuple(member.name for member in archive.getmembers())
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise PromotionVerificationError(f"unreadable distribution archive: {path.name}") from error
    for name in names:
        candidate = PurePosixPath(name)
        lowered_parts = tuple(part.casefold() for part in candidate.parts)
        if (
            candidate.suffix.casefold() in _FORBIDDEN_NATIVE_SUFFIXES
            or ".external-fixtures" in lowered_parts
            or any(part in _FORBIDDEN_UPSTREAM_PATH_PARTS for part in lowered_parts)
        ):
            raise PromotionVerificationError(
                f"distribution contains forbidden fixture or upstream source path: {name!r}"
            )


def validate_artifact_tree(
    root: Path,
    *,
    spec: PromotionSpec = REVIEWED_PROMOTION,
) -> None:
    """Validate the extracted artifact tree without changing any file bytes."""
    if root.is_symlink():
        raise PromotionVerificationError("release artifact root must not be a symlink")
    root = root.resolve()
    if not root.is_dir():
        raise PromotionVerificationError("release artifact root must be a real directory")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise PromotionVerificationError("release artifact must not contain symlinks")

    expected_root = {"packages", "SHA256SUMS.txt", "release-notes.md"}
    actual_root = {path.name for path in root.iterdir()}
    if actual_root != expected_root or not (root / "packages").is_dir():
        raise PromotionVerificationError("release artifact has unexpected top-level entries")

    packages = root / "packages"
    package_entries = tuple(packages.iterdir())
    expected_package_names = {spec.wheel_name, spec.sdist_name}
    if {path.name for path in package_entries} != expected_package_names or any(
        not path.is_file() for path in package_entries
    ):
        raise PromotionVerificationError(
            "release artifact packages must be exactly one reviewed wheel and one sdist"
        )

    checksums = root / "SHA256SUMS.txt"
    try:
        lines = checksums.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise PromotionVerificationError("SHA256SUMS.txt is not readable ASCII") from error
    manifest: dict[str, str] = {}
    for line in lines:
        match = _CHECKSUM_LINE.fullmatch(line)
        if match is None:
            raise PromotionVerificationError("SHA256SUMS.txt has a malformed entry")
        digest, filename = match.groups()
        if filename in manifest:
            raise PromotionVerificationError("SHA256SUMS.txt has a duplicate entry")
        manifest[filename] = digest
    expected_hashes = {
        spec.wheel_name: spec.wheel_sha256,
        spec.sdist_name: spec.sdist_sha256,
    }
    if manifest != expected_hashes:
        raise PromotionVerificationError("SHA256SUMS.txt differs from the reviewed hashes")
    for filename, expected in expected_hashes.items():
        if not _SHA256.fullmatch(expected) or _sha256(packages / filename) != expected:
            raise PromotionVerificationError(f"distribution checksum mismatch: {filename}")
    if _sha256(checksums) != spec.checksums_sha256:
        raise PromotionVerificationError("SHA256SUMS.txt bytes differ from the source artifact")

    notes = root / "release-notes.md"
    if _sha256(notes) != spec.release_notes_sha256:
        raise PromotionVerificationError("release notes bytes differ from the source artifact")
    try:
        first_line = notes.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, UnicodeDecodeError, IndexError) as error:
        raise PromotionVerificationError("release notes are unreadable or empty") from error
    if first_line != "# Ordifile v0.2.1 — Experimental GC instrument readers":
        raise PromotionVerificationError("release notes do not identify Ordifile v0.2.1")

    for package in package_entries:
        _validate_archive_member_names(package)


def validate_index_payload(
    payload: dict[str, Any],
    *,
    spec: PromotionSpec = REVIEWED_PROMOTION,
) -> dict[str, str]:
    """Return the exact published filenames and URLs from one package-index response."""
    info = _mapping(payload.get("info"), field="index info")
    if info.get("name") != "ordifile" or info.get("version") != spec.version:
        raise PromotionVerificationError("package index returned the wrong project or version")
    rows = _sequence(payload.get("urls"), field="index urls")
    expected_hashes = {
        spec.wheel_name: spec.wheel_sha256,
        spec.sdist_name: spec.sdist_sha256,
    }
    urls: dict[str, str] = {}
    digests: dict[str, str] = {}
    for raw in rows:
        row = _mapping(raw, field="index file")
        filename = row.get("filename")
        url = row.get("url")
        digest_map = _mapping(row.get("digests"), field="index file digests")
        sha256 = digest_map.get("sha256")
        if not isinstance(filename, str) or not isinstance(url, str) or not isinstance(sha256, str):
            raise PromotionVerificationError("package index file metadata is malformed")
        if filename in urls:
            raise PromotionVerificationError("package index returned a duplicate filename")
        urls[filename] = url
        digests[filename] = sha256
    if digests != expected_hashes:
        raise PromotionVerificationError("package index file set or SHA-256 differs")
    return urls


def require_index_absent(index: str) -> None:
    """Require the reviewed version to be absent from one package index."""
    endpoint, _ = _INDEXES[index]
    try:
        with urlopen(endpoint, timeout=30):
            pass
    except HTTPError as error:
        if error.code == 404:
            return
        raise PromotionVerificationError(
            f"{index} returned HTTP {error.code} while checking version absence"
        ) from error
    except (URLError, TimeoutError) as error:
        raise PromotionVerificationError(f"could not check {index} version absence") from error
    raise PromotionVerificationError(f"ordifile 0.2.1 already exists on {index}")


def verify_index(
    index: str,
    root: Path,
    *,
    spec: PromotionSpec = REVIEWED_PROMOTION,
) -> None:
    """Download both published files and require byte identity with the source artifact."""
    validate_artifact_tree(root, spec=spec)
    endpoint, expected_host = _INDEXES[index]
    last_error: Exception | None = None
    for attempt in range(1, 7):
        try:
            with urlopen(endpoint, timeout=30) as response:
                payload = json.load(response)
            urls = validate_index_payload(_mapping(payload, field="index response"), spec=spec)
            for filename, url in urls.items():
                parsed = urlparse(url)
                if parsed.scheme != "https" or parsed.hostname != expected_host:
                    raise PromotionVerificationError(
                        "package index returned an unexpected file host"
                    )
                with urlopen(url, timeout=60) as response:
                    final = urlparse(response.geturl())
                    if final.scheme != "https" or final.hostname != expected_host:
                        raise PromotionVerificationError(
                            "package download redirected away from the expected host"
                        )
                    content = response.read(_MAX_DISTRIBUTION_BYTES + 1)
                if len(content) > _MAX_DISTRIBUTION_BYTES:
                    raise PromotionVerificationError("published distribution exceeds size bound")
                source = root / "packages" / filename
                if content != source.read_bytes():
                    raise PromotionVerificationError(
                        f"published bytes differ from source artifact: {filename}"
                    )
            return
        except (
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
            KeyError,
            PromotionVerificationError,
        ) as error:
            last_error = error
            if attempt < 6:
                time.sleep(10)
    raise PromotionVerificationError(f"{index} byte verification failed") from last_error


def _request_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--artifact-name", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    request = subparsers.add_parser("request", help="Validate dispatch inputs.")
    _request_arguments(request)
    source = subparsers.add_parser("source", help="Validate GitHub source metadata JSON.")
    _request_arguments(source)
    source.add_argument("--run-json", type=Path, required=True)
    source.add_argument("--jobs-json", type=Path, required=True)
    source.add_argument("--artifacts-json", type=Path, required=True)
    source.add_argument("--tag-ref-json", type=Path, required=True)
    source.add_argument("--tag-object-json", type=Path, required=True)
    tag = subparsers.add_parser("tag", help="Revalidate live annotated-tag JSON.")
    tag.add_argument("--tag-ref-json", type=Path, required=True)
    tag.add_argument("--tag-object-json", type=Path, required=True)
    artifact = subparsers.add_parser("artifact", help="Validate extracted artifact bytes.")
    artifact.add_argument("--root", type=Path, required=True)
    index_absent = subparsers.add_parser(
        "index-absent", help="Require ordifile 0.2.1 to be absent from an index."
    )
    index_absent.add_argument("--index", choices=tuple(_INDEXES), required=True)
    index = subparsers.add_parser("index", help="Verify exact published index bytes.")
    index.add_argument("--index", choices=tuple(_INDEXES), required=True)
    index.add_argument("--root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one promotion verification command."""
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command in {"request", "source"}:
            validate_request(
                source_run_id=arguments.source_run_id,
                release_tag=arguments.release_tag,
                expected_head_sha=arguments.expected_head_sha,
                artifact_name=arguments.artifact_name,
            )
        if arguments.command == "source":
            validate_source_metadata(
                run=_load_json(arguments.run_json),
                jobs=_load_json(arguments.jobs_json),
                artifacts=_load_json(arguments.artifacts_json),
                tag_ref=_load_json(arguments.tag_ref_json),
                tag_object=_load_json(arguments.tag_object_json),
            )
        elif arguments.command == "tag":
            validate_tag_metadata(
                tag_ref=_load_json(arguments.tag_ref_json),
                tag_object=_load_json(arguments.tag_object_json),
            )
        elif arguments.command == "artifact":
            validate_artifact_tree(arguments.root)
        elif arguments.command == "index-absent":
            require_index_absent(arguments.index)
        elif arguments.command == "index":
            verify_index(arguments.index, arguments.root)
    except PromotionVerificationError as error:
        print(f"promotion verification failed: {error}", file=sys.stderr)
        return 1
    return 0


def _entry_point() -> Never:
    raise SystemExit(main())


if __name__ == "__main__":
    _entry_point()
