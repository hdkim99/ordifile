# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
WORKFLOW_ROOT = PROJECT_ROOT / ".github" / "workflows"
WORKFLOW_NAMES = (
    "agilent-v181-external.yml",
    "ci.yml",
    "release.yml",
    "shimadzu-gcd-external.yml",
    "shimadzu-qgd-external.yml",
)


def _workflow(name: str) -> str:
    return (WORKFLOW_ROOT / name).read_text(encoding="utf-8")


def _job_count(workflow: str) -> int:
    jobs = workflow.split("\njobs:\n", maxsplit=1)[1]
    return len(re.findall(r"^  [a-z][a-z0-9-]+:\s*$", jobs, flags=re.MULTILINE))


def test_every_execution_job_uses_only_the_shared_dgx_runner() -> None:
    combined = "\n".join(_workflow(name) for name in WORKFLOW_NAMES)
    for hosted_label in ("ubuntu-latest", "windows-latest", "macos-latest"):
        assert hosted_label not in combined
    for removed_label in (
        "ordifile-" + "trusted",
        "ordifile-pr-" + "ephemeral",
        "ordifile-" + "release",
    ):
        assert removed_label not in combined
    assert "pull_request_target" not in combined
    assert "cache: pip" not in combined
    assert "actions/cache" not in combined
    assert "fromJSON(" not in combined
    assert not (WORKFLOW_ROOT / "full-check.yml").exists()

    for name in WORKFLOW_NAMES:
        workflow = _workflow(name)
        assert workflow.count("runs-on: [self-hosted, dgx-spark]") == _job_count(workflow)


def test_ci_is_one_read_only_python_314_job_for_main_and_pull_requests() -> None:
    ci = _workflow("ci.yml")
    assert _job_count(ci) == 1
    assert ci.count("name: CI / required") == 1
    assert "pull_request:\n    branches: [main]" in ci
    assert "workflow_dispatch:" in ci
    assert "group: ordifile-ci-${{ github.event.pull_request.number || github.ref }}" in ci
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in ci
    assert 'python-version: "3.14"' in ci
    assert "matrix:" not in ci
    assert "permissions:\n  contents: read" in ci
    for forbidden in (
        "secrets.",
        "id-token: write",
        "attestations: write",
        "environment:",
        "fetch_external_fixture",
        "external-fixture",
        "fixture-cache",
    ):
        assert forbidden not in ci
    for command in (
        "-m ruff format --check .",
        "-m ruff check .",
        "-m mypy",
        "-m pytest",
        "-m build",
        "scripts/verify_release.py",
        '("--help",),',
        '("--version",),',
        '("formats",),',
        '("inspect", "examples/basic/sample_1.csv")',
        '"convert",',
        "load_workbook",
        'find_spec("labconvert")',
        "-m pip_audit",
    ):
        assert command in ci


def test_release_uses_the_same_runner_without_pr_or_matrix() -> None:
    release = _workflow("release.yml")
    assert "  pull_request:" not in release
    assert 'python-version: "3.14"' in release
    assert "matrix.python" not in release
    assert "strategy:" not in release
    assert "ordifile-publish-${{ github.ref }}" in release
    assert "queue: max" in release


def test_agilent_external_fixture_is_maintainer_controlled_and_non_persistent() -> None:
    workflow = _workflow("agilent-v181-external.yml")
    assert "workflow_dispatch:" in workflow
    assert "  push:" not in workflow
    assert "  pull_request:" not in workflow
    assert "github.repository == 'hdkim99/ordifile'" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "id-token: write" not in workflow
    assert "secrets." not in workflow
    assert "actions/cache" not in workflow
    assert "actions/upload-artifact" not in workflow
    assert "--allow-ci" in workflow
    assert "Remove exact external fixture cache" in workflow


def test_shimadzu_external_fixture_is_controlled_private_and_non_persistent() -> None:
    workflow = _workflow("shimadzu-gcd-external.yml")
    assert "workflow_dispatch:" in workflow
    assert "  push:" not in workflow
    assert "  pull_request:" not in workflow
    assert "github.repository == 'hdkim99/ordifile'" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "id-token: write" not in workflow
    assert "secrets." not in workflow
    assert "actions/cache" not in workflow
    assert "actions/upload-artifact" not in workflow
    assert "--allow-ci" in workflow
    assert "CC0-1.0-FS19-214-GCD" in workflow
    assert "without logging its content" in workflow
    assert '--basetemp "$RUNNER_TEMP/ordifile-shimadzu-gcd-fixture/pytest"' in workflow
    assert "Remove exact external fixture cache" in workflow


def test_shimadzu_qgd_external_fixture_is_controlled_private_and_non_persistent() -> None:
    workflow = _workflow("shimadzu-qgd-external.yml")
    assert "workflow_dispatch:" in workflow
    assert "  push:" not in workflow
    assert "  pull_request:" not in workflow
    assert "github.repository == 'hdkim99/ordifile'" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "id-token: write" not in workflow
    assert "secrets." not in workflow
    assert "actions/cache" not in workflow
    assert "actions/upload-artifact" not in workflow
    assert "--allow-ci" in workflow
    assert "CC0-1.0-B4NF-7-C23-QGD" in workflow
    assert "without logging its content" in workflow
    assert '--basetemp "$RUNNER_TEMP/ordifile-shimadzu-qgd-fixture/pytest"' in workflow
    assert "Remove exact external fixture cache" in workflow


def test_workflows_use_job_local_environments_and_bounded_cleanup() -> None:
    for name in WORKFLOW_NAMES:
        workflow = _workflow(name)
        jobs = _job_count(workflow)
        assert workflow.count("Create isolated job environment") == jobs
        assert workflow.count("Remove isolated job environment") == jobs
        assert workflow.count("--phase pre") == jobs
        assert workflow.count("--phase post") == jobs
        assert workflow.count("persist-credentials: false") == jobs
        assert "GITHUB_PATH" not in workflow
        assert "${{ runner.temp }}" not in workflow
        assert "run_in_venv.py run" in workflow
        assert "PIP_NO_CACHE_DIR" in workflow
        assert (
            len(
                re.findall(
                    r"Remove isolated job environment.*?Clean (?:persistent )?workspace after job",
                    workflow,
                    flags=re.DOTALL,
                )
            )
            == jobs
        )


def test_every_action_is_full_sha_pinned_and_dangerous_triggers_are_absent() -> None:
    workflows = tuple(_workflow(name) for name in WORKFLOW_NAMES)
    combined = "\n".join(workflows)
    for trigger in ("pull_request_target", "workflow_run", "issue_comment"):
        assert trigger not in combined

    uses = re.findall(r"^\s*uses:\s*([^\s#]+)", combined, flags=re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}", use) for use in uses)


def test_release_preserves_build_once_oidc_and_attestation_boundaries() -> None:
    release = _workflow("release.yml")

    assert release.count("Build wheel and source distribution") == 1
    assert release.count("actions/upload-artifact@") == 1
    assert release.count("id-token: write") == 3
    assert "actions/attest@" in release
    assert "pypa/gh-action-pypi-publish@" in release
    assert "artifact-metadata: write" in release
    assert "workflow_dispatch:" in release
    assert "github.ref == 'refs/heads/main'" in release
