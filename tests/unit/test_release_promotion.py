# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import hashlib
import io
import sys
import tarfile
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import verify_release_promotion as promotion  # noqa: E402


def _request() -> dict[str, str]:
    spec = promotion.REVIEWED_PROMOTION
    return {
        "source_run_id": str(spec.source_run_id),
        "release_tag": spec.release_tag,
        "expected_head_sha": spec.expected_head_sha,
        "artifact_name": spec.artifact_name,
    }


def _validate_request(request: dict[str, str]) -> None:
    promotion.validate_request(
        source_run_id=request["source_run_id"],
        release_tag=request["release_tag"],
        expected_head_sha=request["expected_head_sha"],
        artifact_name=request["artifact_name"],
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_run_id", "31980576874"),
        ("source_run_id", "031980576873"),
        ("source_run_id", "31980576873;echo"),
        ("release_tag", "v0.2.0"),
        ("release_tag", "v0.2.1\nunsafe"),
        ("expected_head_sha", "0" * 40),
        ("artifact_name", "../ordifile-distributions-31980576873"),
    ),
)
def test_request_rejects_every_unreviewed_identity(field: str, value: str) -> None:
    request = _request()
    request[field] = value
    with pytest.raises(promotion.PromotionVerificationError):
        _validate_request(request)


def _source_metadata() -> tuple[dict[str, object], ...]:
    spec = promotion.REVIEWED_PROMOTION
    run: dict[str, object] = {
        "id": spec.source_run_id,
        "workflow_id": spec.workflow_id,
        "path": spec.workflow_path,
        "event": "push",
        "head_branch": spec.release_tag,
        "head_sha": spec.expected_head_sha,
        "status": "completed",
        "conclusion": "failure",
        "repository": {"full_name": spec.repository},
    }
    jobs: dict[str, object] = {
        "jobs": [
            {"name": "Validate and build once", "conclusion": "success"},
            {
                "name": "Wheel smoke / shared DGX / Python 3.14",
                "conclusion": "success",
            },
            {
                "name": "Publish the same distributions to TestPyPI",
                "conclusion": "failure",
            },
        ]
    }
    artifacts: dict[str, object] = {
        "total_count": 1,
        "artifacts": [
            {
                "id": spec.artifact_id,
                "name": spec.artifact_name,
                "size_in_bytes": spec.artifact_size,
                "expired": False,
                "digest": spec.artifact_digest,
                "workflow_run": {
                    "id": spec.source_run_id,
                    "head_branch": spec.release_tag,
                    "head_sha": spec.expected_head_sha,
                },
            }
        ],
    }
    tag_ref: dict[str, object] = {
        "ref": f"refs/tags/{spec.release_tag}",
        "object": {"type": "tag", "sha": "a" * 40},
    }
    tag_object: dict[str, object] = {
        "sha": "a" * 40,
        "tag": spec.release_tag,
        "object": {"type": "commit", "sha": spec.expected_head_sha},
    }
    return run, jobs, artifacts, tag_ref, tag_object


def _validate_source(values: tuple[dict[str, object], ...]) -> None:
    run, jobs, artifacts, tag_ref, tag_object = values
    promotion.validate_source_metadata(
        run=run,
        jobs=jobs,
        artifacts=artifacts,
        tag_ref=tag_ref,
        tag_object=tag_object,
    )


def test_source_metadata_requires_exact_run_jobs_artifact_and_tag() -> None:
    valid = _source_metadata()
    _validate_source(valid)

    mutations = []
    wrong_run = copy.deepcopy(valid)
    wrong_run[0]["path"] = ".github/workflows/other.yml"
    mutations.append(wrong_run)
    wrong_repository = copy.deepcopy(valid)
    repository = wrong_repository[0]["repository"]
    assert isinstance(repository, dict)
    repository["full_name"] = "other/ordifile"
    mutations.append(wrong_repository)
    failed_build = copy.deepcopy(valid)
    job_rows = failed_build[1]["jobs"]
    assert isinstance(job_rows, list) and isinstance(job_rows[0], dict)
    job_rows[0]["conclusion"] = "failure"
    mutations.append(failed_build)
    failed_smoke = copy.deepcopy(valid)
    job_rows = failed_smoke[1]["jobs"]
    assert isinstance(job_rows, list) and isinstance(job_rows[1], dict)
    job_rows[1]["conclusion"] = "failure"
    mutations.append(failed_smoke)
    expired = copy.deepcopy(valid)
    artifact_rows = expired[2]["artifacts"]
    assert isinstance(artifact_rows, list) and isinstance(artifact_rows[0], dict)
    artifact_rows[0]["expired"] = True
    mutations.append(expired)
    wrong_artifact_id = copy.deepcopy(valid)
    artifact_rows = wrong_artifact_id[2]["artifacts"]
    assert isinstance(artifact_rows, list) and isinstance(artifact_rows[0], dict)
    artifact_rows[0]["id"] = 1
    mutations.append(wrong_artifact_id)
    wrong_artifact_size = copy.deepcopy(valid)
    artifact_rows = wrong_artifact_size[2]["artifacts"]
    assert isinstance(artifact_rows, list) and isinstance(artifact_rows[0], dict)
    artifact_rows[0]["size_in_bytes"] = 1
    mutations.append(wrong_artifact_size)
    wrong_digest = copy.deepcopy(valid)
    artifact_rows = wrong_digest[2]["artifacts"]
    assert isinstance(artifact_rows, list) and isinstance(artifact_rows[0], dict)
    artifact_rows[0]["digest"] = "sha256:" + "0" * 64
    mutations.append(wrong_digest)
    moved_tag = copy.deepcopy(valid)
    target = moved_tag[4]["object"]
    assert isinstance(target, dict)
    target["sha"] = "0" * 40
    mutations.append(moved_tag)
    lightweight_tag = copy.deepcopy(valid)
    reference = lightweight_tag[3]["object"]
    assert isinstance(reference, dict)
    reference["type"] = "commit"
    mutations.append(lightweight_tag)

    for mutation in mutations:
        with pytest.raises(promotion.PromotionVerificationError):
            _validate_source(mutation)


def test_live_tag_revalidation_rejects_a_changed_target() -> None:
    _, _, _, tag_ref, tag_object = _source_metadata()
    promotion.validate_tag_metadata(tag_ref=tag_ref, tag_object=tag_object)

    moved = copy.deepcopy(tag_object)
    target = moved["object"]
    assert isinstance(target, dict)
    target["sha"] = "0" * 40
    with pytest.raises(promotion.PromotionVerificationError, match="target changed"):
        promotion.validate_tag_metadata(tag_ref=tag_ref, tag_object=moved)


def _artifact_tree(root: Path) -> promotion.PromotionSpec:
    packages = root / "packages"
    packages.mkdir(parents=True)
    wheel = packages / "ordifile-0.2.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("ordifile/__init__.py", b"fixture\n")
    sdist = packages / "ordifile-0.2.1.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        content = b"fixture\n"
        info = tarfile.TarInfo("ordifile-0.2.1/PKG-INFO")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    hashes = {
        wheel.name: hashlib.sha256(wheel.read_bytes()).hexdigest(),
        sdist.name: hashlib.sha256(sdist.read_bytes()).hexdigest(),
    }
    checksums = root / "SHA256SUMS.txt"
    checksums.write_text(
        "".join(f"{hashes[name]}  {name}\n" for name in (wheel.name, sdist.name)),
        encoding="ascii",
    )
    notes = root / "release-notes.md"
    notes.write_text(
        "# Ordifile v0.2.1 — Experimental GC instrument readers\n",
        encoding="utf-8",
    )
    return replace(
        promotion.REVIEWED_PROMOTION,
        wheel_sha256=hashes[wheel.name],
        sdist_sha256=hashes[sdist.name],
        checksums_sha256=hashlib.sha256(checksums.read_bytes()).hexdigest(),
        release_notes_sha256=hashlib.sha256(notes.read_bytes()).hexdigest(),
    )


def test_artifact_tree_rejects_checksum_changes_extra_files_and_duplicates(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifact"
    spec = _artifact_tree(root)
    promotion.validate_artifact_tree(root, spec=spec)

    wheel = root / "packages" / spec.wheel_name
    original_wheel = wheel.read_bytes()
    wheel.write_bytes(original_wheel + b"tampered")
    with pytest.raises(promotion.PromotionVerificationError, match="checksum"):
        promotion.validate_artifact_tree(root, spec=spec)
    wheel.write_bytes(original_wheel)

    extra = root / "packages" / "extra.whl"
    extra.write_bytes(b"extra")
    with pytest.raises(promotion.PromotionVerificationError, match="exactly"):
        promotion.validate_artifact_tree(root, spec=spec)
    extra.unlink()

    checksums = root / "SHA256SUMS.txt"
    original_checksums = checksums.read_text(encoding="ascii")
    checksums.write_text(original_checksums + original_checksums.splitlines()[0] + "\n")
    duplicate_spec = replace(
        spec,
        checksums_sha256=hashlib.sha256(checksums.read_bytes()).hexdigest(),
    )
    with pytest.raises(promotion.PromotionVerificationError, match="duplicate"):
        promotion.validate_artifact_tree(root, spec=duplicate_spec)

    linked_root = tmp_path / "artifact-link"
    linked_root.symlink_to(root, target_is_directory=True)
    with pytest.raises(promotion.PromotionVerificationError, match="symlink"):
        promotion.validate_artifact_tree(linked_root, spec=spec)


def test_index_payload_requires_exact_version_files_and_hashes() -> None:
    spec = promotion.REVIEWED_PROMOTION
    payload: dict[str, object] = {
        "info": {"name": "ordifile", "version": spec.version},
        "urls": [
            {
                "filename": spec.wheel_name,
                "url": f"https://files.pythonhosted.org/{spec.wheel_name}",
                "digests": {"sha256": spec.wheel_sha256},
            },
            {
                "filename": spec.sdist_name,
                "url": f"https://files.pythonhosted.org/{spec.sdist_name}",
                "digests": {"sha256": spec.sdist_sha256},
            },
        ],
    }
    assert set(promotion.validate_index_payload(payload)) == {spec.wheel_name, spec.sdist_name}

    wrong_version = copy.deepcopy(payload)
    info = wrong_version["info"]
    assert isinstance(info, dict)
    info["version"] = "0.2.2"
    with pytest.raises(promotion.PromotionVerificationError, match="wrong project or version"):
        promotion.validate_index_payload(wrong_version)

    wrong_hash = copy.deepcopy(payload)
    urls = wrong_hash["urls"]
    assert isinstance(urls, list) and isinstance(urls[0], dict)
    digests = urls[0]["digests"]
    assert isinstance(digests, dict)
    digests["sha256"] = "0" * 64
    with pytest.raises(promotion.PromotionVerificationError, match="file set or SHA-256"):
        promotion.validate_index_payload(wrong_hash)
