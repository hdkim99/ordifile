# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
WORKFLOW_ROOT = PROJECT_ROOT / ".github" / "workflows"
WORKFLOW_NAMES = (
    "agilent-result-xml-external.yml",
    "agilent-v181-external.yml",
    "ci.yml",
    "release.yml",
    "shimadzu-gcd-external.yml",
    "shimadzu-qgd-external.yml",
    "shimadzu-result-ascii-external.yml",
)


def _workflow(name: str) -> str:
    return (WORKFLOW_ROOT / name).read_text(encoding="utf-8")


def _job_count(workflow: str) -> int:
    jobs = workflow.split("\njobs:\n", maxsplit=1)[1]
    return len(re.findall(r"^  [a-z][a-z0-9-]+:\s*$", jobs, flags=re.MULTILINE))


def test_execution_jobs_use_the_shared_dgx_except_hosted_release_publication() -> None:
    combined = "\n".join(_workflow(name) for name in WORKFLOW_NAMES)
    for hosted_label in ("windows-latest", "macos-latest"):
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
        if name == "release.yml":
            continue
        workflow = _workflow(name)
        assert "ubuntu-latest" not in workflow
        assert workflow.count("runs-on: [self-hosted, dgx-spark]") == _job_count(workflow)

    release = _workflow("release.yml")
    assert release.count("runs-on: [self-hosted, dgx-spark]") == 2
    assert release.count("runs-on: macos-15") == 1
    assert release.count("runs-on: ubuntu-latest") == _job_count(release) - 3


def test_ci_is_read_only_and_covers_supported_python_versions() -> None:
    ci = _workflow("ci.yml")
    assert _job_count(ci) == 2
    assert ci.count("name: CI / required") == 1
    assert "name: CI / Python ${{ matrix.python }} compatibility" in ci
    assert "pull_request:\n    branches: [main]" in ci
    assert "workflow_dispatch:" in ci
    assert "group: ordifile-ci-${{ github.event.pull_request.number || github.ref }}" in ci
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in ci
    assert 'python-version: "3.14"' in ci
    assert 'python: ["3.11", "3.12", "3.13"]' in ci
    assert "python-version: ${{ matrix.python }}" in ci
    assert "fetch-depth: 0" in ci
    assert "scripts/ci/verify_contributor_attribution.py" in ci
    assert 'event-name "$ORDIFILE_EVENT_NAME"' in ci
    assert "-m pytest --no-cov" in ci
    assert "-m pip check" in ci
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


def test_release_uses_dgx_for_build_hosted_macos_for_gui_and_ubuntu_for_publication() -> None:
    release = _workflow("release.yml")
    assert "  pull_request:" not in release
    assert 'python-version: "3.14"' in release
    assert "matrix.python" not in release
    assert "strategy:" not in release
    assert "ordifile-publish-${{ github.ref }}" in release
    assert "queue: max" in release
    assert "mode == 'dry-run'" in release
    assert "mode == 'promote-existing'" in release
    assert "mode == 'finalize-existing'" in release
    assert release.count("runs-on: [self-hosted, dgx-spark]") == 2
    assert release.count("runs-on: macos-15") == 1
    assert release.count("runs-on: ubuntu-latest") == _job_count(release) - 3
    assert "GUI wheel smoke / macOS / Python 3.14" in release
    assert "ordifile[gui] @" in release
    assert '"QT_QPA_PLATFORM": "offscreen"' in release
    assert "shutil.copyfile(plugin, platforms / plugin.name)" in release
    assert "needs: [build, smoke, gui-smoke]" in release


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
    assert "--privacy-minimal-output" in workflow
    assert "Remove exact external fixture cache" in workflow


def test_agilent_result_xml_external_fixture_is_controlled_private_and_non_persistent() -> None:
    workflow = _workflow("agilent-result-xml-external.yml")
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
    assert "CECILL-2.1-IFPEN-GC2ASM-RESULT-XML" in workflow
    assert "without logging its content" in workflow
    assert '--basetemp "$RUNNER_TEMP/ordifile-agilent-result-xml-fixture/pytest"' in workflow
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


def test_shimadzu_result_ascii_external_fixtures_are_controlled_and_non_persistent() -> None:
    workflow = _workflow("shimadzu-result-ascii-external.yml")
    assert "workflow_dispatch:" in workflow
    assert "  push:" not in workflow
    assert "  pull_request:" not in workflow
    assert "github.repository == 'hdkim99/ordifile'" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "id-token: write" not in workflow
    assert "secrets." not in workflow
    assert "actions/cache" not in workflow
    assert "actions/upload-artifact" not in workflow
    assert workflow.count("--allow-ci") == 2
    assert "GPL-3.0-OR-LATER-CHROMCONVERTER-LADDER-ASCII" in workflow
    assert "CC0-1.0-FS19-214-GCD" in workflow
    assert workflow.count("without logging its content") == 2
    assert '--basetemp "$RUNNER_TEMP/ordifile-shimadzu-result-ascii-fixtures/pytest"' in workflow
    assert "if: always()" in workflow
    assert "Remove exact external fixture cache" in workflow


def test_workflows_use_job_local_environments_and_bounded_cleanup() -> None:
    for name in WORKFLOW_NAMES:
        workflow = _workflow(name)
        jobs = _job_count(workflow)
        persistent_jobs = 10 if name == "release.yml" else jobs
        assert workflow.count("Create isolated job environment") == persistent_jobs
        assert workflow.count("Remove isolated job environment") == persistent_jobs
        assert workflow.count("--phase pre") == persistent_jobs
        assert workflow.count("--phase post") == persistent_jobs
        expected_checkouts = jobs + 1 if name == "release.yml" else jobs
        assert workflow.count("persist-credentials: false") == expected_checkouts
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
            == persistent_jobs
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
    assert release.count("id-token: write") == 6
    assert release.count("actions/attest@") == 2
    assert release.count("pypa/gh-action-pypi-publish@") == 4
    assert "artifact-metadata: write" in release
    assert "workflow_dispatch:" in release
    assert "github.ref == 'refs/heads/main'" in release
    assert "artifact-ids: 9272226213" in release
    assert "run-id: 31980576873" in release
    assert "digest-mismatch: error" in release
    assert release.count("verify_release_promotion.py tag") == 2


def test_release_finalization_republishes_nothing() -> None:
    release = _workflow("release.yml")
    finalization = release.split("  promote-publish-github-release:", maxsplit=1)[1].split(
        "\n  smoke:", maxsplit=1
    )[0]

    assert "always()" in finalization
    assert "inputs.mode == 'finalize-existing'" in finalization
    assert "needs.promote-validate-existing.result == 'success'" in finalization
    assert "verify_release_promotion.py index --index testpypi" in finalization
    assert "verify_release_promotion.py index --index pypi" in finalization
    assert (
        "for subject in release-artifact/packages/* release-artifact/SHA256SUMS.txt" in finalization
    )
    assert 'gh attestation verify "$subject"' in finalization
    assert "--deny-self-hosted-runners" in finalization
    assert "--source-digest fdc18aed133a56c3389e3f060d1ac926ecf4db13" in finalization
    assert 'release.get("body") != (root / "release-notes.md").read_text' in finalization
    assert 'gh release edit "$RELEASE_TAG" --draft=false' in finalization
    assert "Require the v0.2.1 GitHub Release to be public" in finalization
    assert 'test "$(gh release view' in finalization
    for forbidden in (
        "pypa/gh-action-pypi-publish@",
        "actions/attest@",
        "actions/upload-artifact@",
        "Build wheel and source distribution",
        "id-token: write",
        "environment:",
    ):
        assert forbidden not in finalization
