# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
WORKFLOW_ROOT = PROJECT_ROOT / ".github" / "workflows"
WORKFLOW_NAMES = ("ci.yml", "full-check.yml", "release.yml")


def _workflow(name: str) -> str:
    return (WORKFLOW_ROOT / name).read_text(encoding="utf-8")


def _job_count(workflow: str) -> int:
    jobs = workflow.split("\njobs:\n", maxsplit=1)[1]
    return len(re.findall(r"^  [a-z][a-z0-9-]+:\s*$", jobs, flags=re.MULTILINE))


def test_every_execution_job_queues_only_on_self_hosted_trust_labels() -> None:
    combined = "\n".join(_workflow(name) for name in WORKFLOW_NAMES)
    for hosted_label in ("ubuntu-latest", "windows-latest", "macos-latest"):
        assert hosted_label not in combined
    assert "pull_request_target" not in combined
    assert "cache: pip" not in combined

    ci = _workflow("ci.yml")
    assert _job_count(ci) == 1
    assert ci.count("name: CI / required") == 1
    assert 'fromJSON(\'["self-hosted","ordifile-trusted"]\')' in ci
    assert 'fromJSON(\'["self-hosted","ordifile-pr-ephemeral"]\')' in ci
    assert "github.event.pull_request.user.login == 'dependabot[bot]'" in ci
    assert "github.actor == 'dependabot[bot]'" in ci
    assert "pull_request:\n    branches: [main]" in ci
    assert "workflow_dispatch:" in ci
    assert "format('pr-{0}-{1}', github.event.pull_request.number, github.head_ref)" in ci
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in ci

    full = _workflow("full-check.yml")
    assert "runs-on: [self-hosted, ordifile-trusted]" in full
    assert "ordifile-trusted-single-capacity" in full
    assert 'python: ["3.11", "3.14"]' in full
    assert "max-parallel: 1" in full
    assert "python-version: ${{ matrix.python }}" in full

    release = _workflow("release.yml")
    assert "  pull_request:" not in release
    assert release.count("runs-on: [self-hosted, ordifile-release, Linux, X64]") == _job_count(
        release
    )
    assert "ordifile-release-single-capacity" in release
    assert "queue: max" in release
    smoke = release.split("  smoke:", maxsplit=1)[1].split("\n  publish-testpypi:", maxsplit=1)[0]
    assert 'python: ["3.11", "3.14"]' in smoke
    assert "max-parallel: 1" in smoke
    assert "python-version: ${{ matrix.python }}" in smoke
    assert "ORDIFILE_CI_VENV_SUFFIX: py-${{ matrix.python }}" in smoke


def test_external_pr_route_has_no_privileged_or_persistent_features() -> None:
    ci = _workflow("ci.yml")

    for forbidden in (
        "secrets.",
        "id-token: write",
        "attestations: write",
        "actions/cache",
        "fetch_external_fixture",
        "external-fixture",
        "fixture-cache",
    ):
        assert forbidden not in ci
    assert "permissions:\n  contents: read" in ci
    assert "persist-credentials: false" in ci


def test_workflows_serialize_single_capacity_and_use_job_local_environments() -> None:
    for name in WORKFLOW_NAMES:
        workflow = _workflow(name)
        jobs = _job_count(workflow)
        if name != "ci.yml":
            assert "cancel-in-progress: false" in workflow
            assert "single-capacity" in workflow
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
        assert (
            "python -m pip install --upgrade pip" not in workflow or "ORDIFILE_CI_VENV" in workflow
        )


def test_every_action_is_full_sha_pinned_and_dangerous_triggers_are_absent() -> None:
    workflows = tuple(_workflow(name) for name in WORKFLOW_NAMES)
    combined = "\n".join(workflows)
    for trigger in ("pull_request_target", "workflow_run", "issue_comment"):
        assert trigger not in combined

    uses = re.findall(r"^\s*uses:\s*([^\s#]+)", combined, flags=re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}", use) for use in uses)


def test_no_job_uses_a_bare_generic_self_hosted_label() -> None:
    combined = "\n".join(_workflow(name) for name in WORKFLOW_NAMES)
    assert "runs-on: self-hosted" not in combined
    for line in combined.splitlines():
        if "runs-on:" in line and "self-hosted" in line:
            assert "ordifile-" in line
    for expression in re.findall(r"fromJSON\('([^']+)'\)", combined):
        assert "ordifile-" in expression


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
