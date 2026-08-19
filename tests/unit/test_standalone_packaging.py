# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import inspect
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402
from standalone import build as standalone_build  # noqa: E402
from standalone import entry as standalone_entry  # noqa: E402
from standalone import verify as standalone_verify  # noqa: E402

LICENSES = ROOT / "packaging" / "standalone" / "licenses"
WORKFLOW = ROOT / ".github" / "workflows" / "standalone.yml"
WINDOWS_REUSABLE = ROOT / ".github" / "workflows" / "standalone-windows-reusable.yml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(tmp_path: Path) -> Path:
    root = tmp_path / "Ordifile.app"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "Ordifile").write_bytes(b"public synthetic application")
    destination = root / "licenses"
    destination.mkdir()
    for name in standalone_verify.REQUIRED_LICENSES:
        (destination / name).write_text(f"synthetic notice for {name}\n", encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _pinned_manifest_toolchain(monkeypatch: pytest.MonkeyPatch) -> None:
    versions = {
        "PySide6-Essentials": "6.11.2",
        "shiboken6": "6.11.2",
        "Nuitka": "4.1.3",
    }
    monkeypatch.setattr(standalone_verify, "version", versions.__getitem__)


def test_exact_standalone_license_bytes_are_pinned() -> None:
    assert _sha256(LICENSES / "LGPL-3.0.txt") == (
        "a853c2ffec17057872340eee242ae4d96cbf2b520ae27d903e1b2fef1a5f9d1c"
    )
    assert _sha256(LICENSES / "NUITKA-RUNTIME-EXCEPTION.txt") == (
        "20ff0ae581adf436a7b06e50e67a6c8913aec1ea4e60dba138d0a0bee7ee520c"
    )
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in (LICENSES / "LGPL-3.0.txt").read_text(
        encoding="utf-8"
    )
    runtime = (LICENSES / "NUITKA-RUNTIME-EXCEPTION.txt").read_text(encoding="utf-8")
    assert "No Weakening of Nuitka Copyleft" in runtime
    assert "AGPLv3" in runtime


def test_build_lock_and_deployment_template_pin_primary_toolchain() -> None:
    lock = (ROOT / "packaging" / "standalone" / "requirements-build.lock").read_text(
        encoding="utf-8"
    )
    spec = (ROOT / "packaging" / "standalone" / "pysidedeploy.spec.in").read_text(encoding="utf-8")
    assert "Nuitka==4.1.3" in lock
    assert "PySide6-Essentials==6.11.2" in lock
    assert "shiboken6==6.11.2" in lock
    assert "Nuitka==4.1.3" in spec
    assert "mode = standalone" in spec
    assert "input_file = Ordifile.py" in spec
    assert "--noinclude-qt-plugins=tls" in spec
    assert "@STATIC_LIBPYTHON@" in spec
    assert "onefile" not in spec.casefold()


def test_source_distribution_includes_standalone_build_inputs() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '  "/packaging",' in project


def test_workflow_is_manual_native_and_uploads_path_free_evidence_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    windows_job = WINDOWS_REUSABLE.read_text(encoding="utf-8")
    combined = text + windows_job
    trigger = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger
    assert "expected_commit:" in trigger
    assert "Exact reviewed 40-character commit" in trigger
    assert "required: true" in trigger
    for prohibited in ("push:", "pull_request:", "schedule:", "release:"):
        assert prohibited not in trigger
    assert "windows-prototype:" not in text
    assert "runs-on: [self-hosted, Windows, X64]" not in text
    assert "runs-on: [self-hosted, Windows, X64]" in windows_job
    for prohibited_runner in ("windows-2025", "windows-latest", "windows-2022"):
        assert prohibited_runner not in combined
    assert "runs-on: macos-15" in text
    macos_job = text.split("  macos-prototype:", 1)[1]
    preflight = text.split("  macos-prototype:", 1)[0]
    assert "dispatch-preflight:" in preflight
    assert "runs-on: ubuntu-latest" in preflight
    assert "actions/checkout@" not in preflight
    assert "actions/upload-artifact@" not in preflight
    assert "Standalone dispatch identity is not authorized." in preflight
    assert "Standalone dispatch ref is not authorized." in preflight
    assert "Standalone dispatch commit identity is invalid." in preflight
    assert text.count("needs: dispatch-preflight") == 1
    assert text.count("github.repository == 'hdkim99/ordifile'") == 1
    assert text.count("github.event_name == 'workflow_dispatch'") == 1
    assert text.count("github.ref_type == 'branch'") == 1
    assert text.count("github.ref == 'refs/heads/main'") == 1
    assert text.count("github.ref == 'refs/heads/build/standalone-prototype'") == 1
    assert text.count("github.sha == inputs.expected_commit") == 1
    assert text.count("github.workflow_sha == github.sha") == 1
    assert text.count("ref: ${{ github.sha }}") == 1
    assert text.count("EXPECTED_COMMIT: ${{ inputs.expected_commit }}") == 2
    assert text.count("^[0-9a-f]{40}$") == 2
    assert text.count("git rev-parse HEAD") == 1
    assert "Mask persistent runner identifiers" in windows_job
    assert "::add-mask::" in windows_job
    for private_runner_value in (
        "RUNNER_WORKSPACE",
        "RUNNER_TOOL_CACHE",
        "AGENT_TOOLSDIRECTORY",
        "RUNNER_NAME",
        "USERNAME",
        "USERPROFILE",
        "COMPUTERNAME",
        "USERDOMAIN",
    ):
        assert private_runner_value in windows_job
    reusable_trigger = windows_job.split("permissions:", 1)[0]
    assert "workflow_call:" in reusable_trigger
    assert "expected_commit:" in reusable_trigger
    assert "required: true" in reusable_trigger
    assert "type: string" in reusable_trigger
    for prohibited in (
        "workflow_dispatch:",
        "push:",
        "pull_request:",
        "pull_request_target:",
        "schedule:",
        "release:",
    ):
        assert prohibited not in reusable_trigger
    assert "CALLER_OWNER: ${{ github.repository_owner }}" in windows_job
    assert "CALLER_EVENT: ${{ github.event_name }}" in windows_job
    assert "CALLER_REF: ${{ github.ref }}" in windows_job
    assert '"$CALLER_OWNER" != "hdkim99"' in windows_job
    assert '"$CALLER_EVENT" != "workflow_dispatch"' in windows_job
    assert '"$CALLER_REF" != "refs/heads/main"' in windows_job
    assert "/.github/workflows/ordifile-windows-validation.yml@refs/heads/main" in windows_job
    assert "job.workflow_repository" in windows_job
    assert "job.workflow_file_path" in windows_job
    assert "job.workflow_ref" in windows_job
    assert "job.workflow_sha" in windows_job
    reusable_preflight = windows_job.split("  windows-prototype:", 1)[0]
    assert "caller-preflight:" in reusable_preflight
    assert "runs-on: ubuntu-latest" in reusable_preflight
    assert "\n    if:" not in reusable_preflight
    assert "Reusable Windows caller identity is invalid." in reusable_preflight
    assert "actions/checkout@" not in reusable_preflight
    assert "actions/upload-artifact@" not in reusable_preflight
    assert "needs: caller-preflight" in windows_job
    assert windows_job.count("PSExecutionPolicyPreference: Bypass") == 1
    assert "Set-ExecutionPolicy" not in windows_job
    assert r"$checksum -split '\s+', 2" in windows_job
    assert r'$checksum -split "\\s+", 2' not in windows_job
    assert "$manifest.files | Where-Object" in windows_job
    assert '$_.kind -eq "file"' in windows_job
    assert "Standalone archive root inventory is invalid." in windows_job
    assert "Standalone manifest executable inventory is invalid." in windows_job
    assert windows_job.count("Standalone manifest executable path is invalid.") == 2
    assert '-Recurse -Filter "Ordifile.exe"' not in windows_job
    assert "$expandedEntries.Count -ne 1" in windows_job
    assert "-not $expandedEntries[0].PSIsContainer" in windows_job
    assert "[IO.FileAttributes]::ReparsePoint" in windows_job
    assert "[IO.Path]::IsPathRooted($relativeExecutable)" in windows_job
    assert (
        "$executablePath.StartsWith($bundleBoundary, "
        "[StringComparison]::OrdinalIgnoreCase)" in windows_job
    )
    assert "Test-Path -LiteralPath $executablePath -PathType Leaf" in windows_job
    assert "--bundle $bundleRoot" in windows_job
    assert windows_job.index("--bundle $bundleRoot") < windows_job.index("--standalone-smoke")
    assert "repository: hdkim99/ordifile" in windows_job
    assert "ref: ${{ inputs.expected_commit }}" in windows_job
    assert "secrets: inherit" not in windows_job
    assert "path: source" in windows_job
    assert windows_job.count("working-directory: source") >= 7
    assert windows_job.count('python-version: "3.14.3"') == 1
    assert "Verify Windows native compiler capability" in windows_job
    assert "Get-Command cl.exe -CommandType Application" in windows_job
    assert "_MSC_VER < 1930" in windows_job
    assert "!defined(_M_X64)" in windows_job
    assert "ACTIVE_PATH_MSVC_2022_PLUS" in windows_job
    assert "PATH_CL_VERSION_OR_ARCH_UNSUPPORTED" in windows_job
    assert "PATH_CL_COMPILE_LINK_FAILED" in windows_job
    assert "PATH_CL_EXECUTION_FAILED" in windows_job
    assert "Windows native compiler probe cleanup failed." in windows_job
    assert (
        "              }\n            }\n            catch {\n"
        '              $activeStatus = "PATH_CL_PROBE_FAILED"\n'
        "            }\n            finally {"
    ) in windows_job
    assert (
        "              }\n            }\n            }\n            catch {\n"
        '              $activeStatus = "PATH_CL_PROBE_FAILED"'
    ) not in windows_job
    assert "function Test-ProbeRootIdentity" in windows_job
    assert "$probeCreated = $true" in windows_job
    assert "$probeOwned = $true" in windows_job
    assert windows_job.count("Test-ProbeRootIdentity") >= 4
    assert "$runnerTemp.TrimEnd($trimCharacters)" in windows_job
    assert "Get-Item -LiteralPath $probeRoot -Force -ErrorAction SilentlyContinue" not in (
        windows_job
    )
    assert "Get-Item -LiteralPath $probeRoot -Force -ErrorAction Stop" in windows_job
    assert "Test-Path -LiteralPath $probeRoot -ErrorAction Stop" in windows_job
    assert "ordifile-compiler-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT-$env:GITHUB_JOB" in (
        windows_job
    )
    assert "Microsoft.VisualStudio.Component.VC.Tools.x86.x64" in windows_job
    assert '-version "[17.0,)"' in windows_job
    assert "Common7/Tools/VsDevCmd.bat" in windows_job
    for fixed_category in (
        "PROGRAM_FILES_X86_UNAVAILABLE",
        "VSWHERE_UNAVAILABLE",
        "VSWHERE_QUERY_FAILED",
        "VC_TOOLS_UNAVAILABLE",
        "DEVELOPER_SHELL_UNAVAILABLE",
        "PATH_CL_UNAVAILABLE",
        "PATH_CL_PROBE_UNAVAILABLE",
        "PATH_CL_PROBE_FAILED",
    ):
        assert fixed_category in windows_job
    assert "Windows native compiler capability is unavailable;" in windows_job
    assert "registered=NOT_EVALUATED; active=$activeStatus." in windows_job
    assert windows_job.index("registered=NOT_EVALUATED") < windows_job.index(
        '$registeredStatus = "PROGRAM_FILES_X86_UNAVAILABLE"'
    )
    assert "& $developerShell" not in windows_job
    assert "-prerelease" not in windows_job
    assert "GITHUB_ENV" not in windows_job
    for host_mutation in (
        "winget install",
        "choco install",
        "Start-Process",
        "Set-ItemProperty",
        "New-ItemProperty",
    ):
        assert host_mutation not in windows_job
    assert "actions/setup-python@" not in macos_job
    assert "python-build-standalone/releases/download/20260203/" in macos_job
    assert "cpython-3.14.3%2B20260203-aarch64-apple-darwin-install_only.tar.gz" in macos_job
    assert "5bb1ad03aa2d8afe15140f56fedaab2ba95033785ad0367775899d42ac8aeb3c" in macos_job
    assert "/usr/bin/shasum -a 256 --check >/dev/null" in macos_job
    assert "The Python runtime archive inventory failed." in macos_job
    assert "The Python runtime archive path boundary is invalid." in macos_job
    assert "The Python runtime archive type inventory failed." in macos_job
    assert "The Python runtime archive member type is invalid." in macos_job
    assert "The Python runtime archive link inventory is invalid." in macos_job
    assert "python/bin/python3 -> python3.14" in macos_job
    assert "python/lib/pkgconfig/python3.pc -> python-3.14.pc" in macos_job
    assert "The Python runtime installation-input cleanup failed." in macos_job
    assert "trap cleanup_runtime_install_inputs EXIT" in macos_job
    assert "--strip-components=1" in macos_job
    assert 'runtime="/opt/ordifile-python-3.14.3"' in macos_job
    assert 'python_bin="${runtime}/bin/python3.14"' in macos_job
    assert 'target="macos-arm64"' in macos_job
    assert 'target="macos-x86_64"' not in macos_job
    assert "print(platform.machine())" in macos_job
    assert "print(sys.prefix)" in macos_job
    assert "print(sys.executable)" in macos_job
    assert "print(sys.base_prefix)" in macos_job
    assert macos_job.count("python3.14 scripts/standalone/") == 3
    assert "A Mach-O dependency inventory failed." in macos_job
    assert "A Mach-O load-command inventory failed." in macos_job
    assert "A bundle file-type inventory failed." in macos_job
    assert "The bundle file inventory failed." in macos_job
    assert "The bundle file inventory cleanup failed." in macos_job
    assert "The main executable depends on the build-host Python runtime." in macos_job
    assert "The embedded Python runtime depends on the build-host runtime." in macos_job
    assert "An extension library depends on the build-host Python runtime." in macos_job
    assert "Another bundle component depends on the build-host Python runtime." in macos_job
    assert "The main executable has a build-host Python runtime load command." in macos_job
    assert "The embedded Python runtime has a build-host runtime load command." in macos_job
    assert "An extension library has a build-host Python runtime load command." in macos_job
    assert "Another bundle component has a build-host Python runtime load command." in macos_job
    assert 'relative_member="${member#"${bundle}"/}"' in macos_job
    assert macos_job.count('case "${relative_member}" in') == 2
    assert 'file_description="$(/usr/bin/file -b "${member}" 2>/dev/null)"' in macos_job
    assert '/usr/bin/file -b "${member}" |' not in macos_job
    assert 'done < "${file_inventory}"' in macos_job
    assert "done < <(/usr/bin/find" not in macos_job
    assert "/usr/bin/otool -L" in macos_job
    assert "/usr/bin/otool -l" in macos_job
    assert "/usr/bin/sudo -n /bin/mv" in macos_job
    assert "The Python runtime isolation identity is invalid." in macos_job
    assert "The Python runtime isolation root is invalid." in macos_job
    assert "The Python runtime isolation boundary is invalid." in macos_job
    assert "The source Python runtime state is invalid." in macos_job
    assert "The Python runtime isolation destination is occupied." in macos_job
    assert "The Python runtime restore state is invalid." in macos_job
    assert "The Python runtime restore operation failed." in macos_job
    assert "The restored Python runtime state is invalid." in macos_job
    assert "The Python runtime isolation operation failed." in macos_job
    assert "The isolated Python runtime state is invalid." in macos_job
    assert macos_job.count('|| -L "${') >= 6
    assert macos_job.count(">/dev/null 2>&1") >= 2
    assert "trap restore_python_runtime EXIT" in macos_job
    assert "trap - EXIT" in macos_job
    assert "--target windows-x86_64" in windows_job
    assert "--standalone-smoke" in combined
    assert "--standalone-window-smoke" in combined
    assert combined.count("QT_QPA_PLATFORM") == 2
    assert "standalone smoke 결과.xlsx" in combined
    assert combined.count("scripts/standalone/verify.py") == 2
    assert combined.count("PYTHONNOUSERSITE") == 2
    assert "run_in_venv.py create --github-runner" in windows_job
    assert "run_in_venv.py remove --github-runner" in windows_job
    assert "python -m pip install" not in windows_job
    assert "pip install --quiet" in windows_job
    assert windows_job.count("run_in_venv.py run --github-runner") >= 5
    assert windows_job.count("clean_workspace.py --workspace . --phase") == 2
    assert windows_job.count("if: always()") >= 3
    assert (
        "ordifile-standalone-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT-$env:GITHUB_JOB"
        in windows_job
    )
    assert windows_job.count("Standalone scratch boundary is invalid.") == 2
    assert "actions/download-artifact@" not in combined
    assert combined.count("actions/upload-artifact@") == 2
    windows_evidence = windows_job.split("      - name: Upload path-free Windows evidence only", 1)[
        1
    ].split("      - name: Remove isolated Windows job environment", 1)[0]
    evidence_gate = windows_job.split(
        "      - name: Require complete Windows evidence after a successful smoke", 1
    )[1].split("      - name: Upload path-free Windows evidence only", 1)[0]
    assert "        if: success()" in evidence_gate
    assert evidence_gate.count("Test-Path -LiteralPath $_ -PathType Leaf") == 1
    assert "Standalone Windows evidence inventory is incomplete." in evidence_gate
    assert evidence_gate.count("standalone-manifest.json") == 1
    assert evidence_gate.count("SHA256SUMS.txt") == 1
    assert evidence_gate.count("standalone-smoke-report.json") == 1
    assert "        if: always()" in windows_evidence
    assert (
        "          if-no-files-found: ${{ job.status == 'success' && 'error' || 'warn' }}"
        in windows_evidence
    )
    assert (
        "          name: ordifile-standalone-windows-evidence-"
        "${{ github.run_id }}-${{ github.run_attempt }}" in windows_evidence
    )
    evidence_paths = windows_evidence.split("          path: |\n", 1)[1].split(
        "          if-no-files-found:", 1
    )[0]
    assert [line.strip() for line in evidence_paths.splitlines() if line.strip()] == [
        "source/standalone-candidate/standalone-manifest.json",
        "source/standalone-candidate/SHA256SUMS.txt",
        "source/standalone-smoke-report.json",
    ]
    assert "continue-on-error" not in windows_evidence
    assert "          overwrite: false" in windows_evidence
    assert "standalone-candidate/standalone-manifest.json" in combined
    assert "standalone-candidate/SHA256SUMS.txt" in combined
    assert "standalone-candidate/\n" not in combined
    assert "standalone-smoke-kit/\n" not in combined
    assert "evidence only" in combined
    assert "id-token: write" not in combined
    assert "contents: write" not in combined
    assert "release" not in "\n".join(
        line.casefold() for line in combined.splitlines() if line.lstrip().startswith("uses:")
    )


def test_manifest_schema_keeps_prototypes_non_publishable() -> None:
    schema = json.loads(
        (ROOT / "packaging" / "standalone" / "manifest.schema.json").read_text(encoding="utf-8")
    )
    assert schema["properties"]["publishable"] == {"const": False}
    assert set(schema["properties"]["signature_state"]["enum"]) == {
        "UNSIGNED_PROTOTYPE",
        "AD_HOC_NOT_NOTARIZED",
    }
    assert {
        "files",
        "licenses",
        "adapter_ids",
        "bundle_total_size",
        "outer_artifact",
    } <= set(schema["required"])
    assert schema["properties"]["outer_artifact"]["required"] == [
        "filename",
        "size",
        "sha256",
    ]


def test_inventory_is_path_safe_and_has_complete_license_inventory(tmp_path: Path) -> None:
    root = _candidate(tmp_path)
    files, licenses = standalone_verify.inventory_bundle(root)
    assert [str(item["path"]) for item in files] == sorted(str(item["path"]) for item in files)
    assert standalone_verify.REQUIRED_LICENSES <= set(licenses)
    assert all(not str(item["path"]).startswith(str(tmp_path)) for item in files)


@pytest.mark.parametrize("suffix", (".PRM", ".GCD", ".QGD", ".CH", ".raw"))
def test_inventory_rejects_native_or_private_fixture_suffix(tmp_path: Path, suffix: str) -> None:
    root = _candidate(tmp_path)
    (root / "bin" / f"private{suffix}").write_bytes(b"fixture")
    with pytest.raises(
        standalone_verify.StandaloneVerificationError,
        match="prohibited scientific fixture",
    ):
        standalone_verify.inventory_bundle(root)


@pytest.mark.parametrize("suffix", (".D", ".RAW"))
def test_inventory_rejects_native_or_private_fixture_directory(tmp_path: Path, suffix: str) -> None:
    root = _candidate(tmp_path)
    directory = root / "bin" / f"private{suffix}"
    directory.mkdir()
    (directory / "opaque.bin").write_bytes(b"fixture")
    with pytest.raises(
        standalone_verify.StandaloneVerificationError,
        match="prohibited scientific fixture",
    ):
        standalone_verify.inventory_bundle(root)


def test_inventory_rejects_utf8_utf16_private_paths_and_credential_markers(
    tmp_path: Path,
) -> None:
    for index, payload in enumerate(
        (
            b"private-build-root",
            "private-build-root".encode("utf-16le"),
            b"-----BEGIN PRIVATE KEY-----",
            b"-----BEGIN RSA PRIVATE KEY-----",
            b"-----BEGIN EC PRIVATE KEY-----",
            b"-----BEGIN DSA PRIVATE KEY-----",
            b"ghp_synthetic",
        )
    ):
        root = _candidate(tmp_path / str(index))
        (root / "bin" / "payload.bin").write_bytes(payload)
        with pytest.raises(
            standalone_verify.StandaloneVerificationError,
            match="Private build data",
        ):
            standalone_verify.inventory_bundle(
                root,
                forbidden_text=("private-build-root",),
            )


def test_inventory_rejects_sensitive_relative_path(tmp_path: Path) -> None:
    root = _candidate(tmp_path)
    (root / "bin" / "github_pat_synthetic.txt").write_text("public", encoding="utf-8")
    with pytest.raises(
        standalone_verify.StandaloneVerificationError,
        match="bundle path",
    ):
        standalone_verify.inventory_bundle(root)


def test_inventory_rejects_escaping_symlink(tmp_path: Path) -> None:
    root = _candidate(tmp_path)
    link = root / "bin" / "escape"
    try:
        link.symlink_to("../../outside")
    except OSError:
        pytest.skip("The test host cannot create symlinks.")
    with pytest.raises(
        standalone_verify.StandaloneVerificationError,
        match="symlink escapes",
    ):
        standalone_verify.inventory_bundle(root)


@pytest.mark.parametrize(
    "target",
    (r"C:\private\candidate", "github_pat_synthetic"),
)
def test_inventory_rejects_windows_absolute_or_sensitive_symlink_target(
    tmp_path: Path, target: str
) -> None:
    root = _candidate(tmp_path)
    link = root / "bin" / "unsafe-link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("The test host cannot create symlinks.")
    with pytest.raises(standalone_verify.StandaloneVerificationError):
        standalone_verify.inventory_bundle(root)


def test_windows_reparse_attribute_is_rejected() -> None:
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    assert standalone_verify._has_windows_reparse_attribute(
        SimpleNamespace(st_file_attributes=marker)
    )
    assert not standalone_verify._has_windows_reparse_attribute(
        SimpleNamespace(st_file_attributes=0)
    )


def test_bundle_root_windows_reparse_attribute_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _candidate(tmp_path)
    monkeypatch.setattr(standalone_verify, "_has_windows_reparse_attribute", lambda _: True)
    with pytest.raises(
        standalone_verify.StandaloneVerificationError,
        match="bundle root is invalid",
    ):
        standalone_verify.inventory_bundle(root)


@pytest.mark.parametrize(
    "relative",
    (
        Path("Contents/MacOS/QtNetwork"),
        Path("Contents/MacOS/PySide6/QtNetwork.abi3.so"),
        Path("Contents/MacOS/PySide6/qt-plugins/tls/backend.dylib"),
        Path("Contents/MacOS/PySide6/Qt/plugins/tls/backend.dylib"),
        Path("plugins/networkinformation/plugin.dll"),
    ),
)
def test_inventory_rejects_unneeded_qt_network_runtime(tmp_path: Path, relative: Path) -> None:
    root = _candidate(tmp_path)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic network component")
    with pytest.raises(
        standalone_verify.StandaloneVerificationError,
        match="unneeded Qt network component",
    ):
        standalone_verify.inventory_bundle(root)


def test_deterministic_archive_preserves_relative_symlink(tmp_path: Path) -> None:
    source = tmp_path / "Ordifile.app"
    source.mkdir()
    executable = source / "Ordifile"
    executable.write_bytes(b"application")
    executable.chmod(0o755)
    link = source / "current"
    try:
        link.symlink_to("Ordifile")
    except OSError:
        pytest.skip("The test host cannot create symlinks.")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    standalone_build._deterministic_zip(source, first)
    standalone_build._deterministic_zip(source, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert names == ["Ordifile.app/Ordifile", "Ordifile.app/current"]
        assert archive.read("Ordifile.app/current") == b"Ordifile"


def test_rendered_spec_resolves_only_known_temporary_markers(tmp_path: Path) -> None:
    destination = tmp_path / "rendered.spec"
    standalone_build._render_spec(
        ROOT / "packaging" / "standalone" / "pysidedeploy.spec.in",
        destination,
        tmp_path / "stage",
        tmp_path / "result",
        target="macos-arm64",
    )
    text = destination.read_text(encoding="utf-8")
    assert "@PROJECT_DIR@" not in text
    assert "@EXEC_DIRECTORY@" not in text
    assert "@PYTHON_PATH@" not in text
    assert "@STATIC_LIBPYTHON@" not in text
    assert str(tmp_path / "stage") in text
    assert "--static-libpython=no" in text

    standalone_build._render_spec(
        ROOT / "packaging" / "standalone" / "pysidedeploy.spec.in",
        destination,
        tmp_path / "stage",
        tmp_path / "result",
        target="windows-x86_64",
    )
    assert "--static-libpython=no" in destination.read_text(encoding="utf-8")


def test_native_target_gate_accepts_only_current_host() -> None:
    machine = platform.machine().casefold()
    current = {
        ("darwin", "arm64"): "macos-arm64",
        ("darwin", "x86_64"): "macos-x86_64",
        ("win32", "amd64"): "windows-x86_64",
        ("win32", "x86_64"): "windows-x86_64",
    }.get((sys.platform, machine))
    if current is None:
        with pytest.raises(ValueError, match="not native"):
            standalone_build._validate_native_target("macos-arm64")
        return
    standalone_build._validate_native_target(current)
    wrong = "windows-x86_64" if current.startswith("macos") else "macos-arm64"
    with pytest.raises(ValueError, match="not native"):
        standalone_build._validate_native_target(wrong)


def test_deployment_failure_detects_caught_upstream_exception_without_exposing_detail() -> None:
    success = subprocess.CompletedProcess(["pyside6-deploy"], 0, "deployment complete", "")
    swallowed = subprocess.CompletedProcess(
        ["pyside6-deploy"],
        0,
        f"{standalone_build.DEPLOY_EXCEPTION_MARKER} private path and credential detail",
        "",
    )
    failed = subprocess.CompletedProcess(["pyside6-deploy"], 1, "", "private detail")

    assert not standalone_build._deployment_failed(success)
    assert standalone_build._deployment_failed(swallowed)
    assert standalone_build._deployment_failed(failed)
    assert "private" not in standalone_build.DEPLOY_EXCEPTION_MARKER.casefold()


@pytest.mark.parametrize(
    ("target", "name"),
    [("windows-x86_64", "Ordifile.dist"), ("macos-arm64", "Ordifile.app")],
)
def test_bundle_candidate_requires_one_real_nonreparse_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, name: str
) -> None:
    result = tmp_path / "result"
    result.mkdir()
    invalid_file = result / name
    invalid_file.write_bytes(b"not a bundle directory")
    with pytest.raises(ValueError, match="bundle root is invalid"):
        standalone_build._bundle_candidate(result, target)
    invalid_file.unlink()

    outside = tmp_path / "outside"
    outside.mkdir()
    link = result / name
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("The test host cannot create directory symlinks.")
    with pytest.raises(ValueError, match="bundle root is invalid"):
        standalone_build._bundle_candidate(result, target)
    link.unlink()

    bundle = result / name
    bundle.mkdir()
    assert standalone_build._bundle_candidate(result, target) == bundle
    monkeypatch.setattr(standalone_build, "_has_windows_reparse_attribute", lambda metadata: True)
    with pytest.raises(ValueError, match="bundle root is invalid"):
        standalone_build._bundle_candidate(result, target)


def test_build_rejects_caught_deployment_exception_with_fixed_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(standalone_build, "_validate_native_target", lambda target: None)
    monkeypatch.setattr(standalone_build, "_deploy_executable", lambda: Path("pyside6-deploy"))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            ["pyside6-deploy"],
            0,
            f"{standalone_build.DEPLOY_EXCEPTION_MARKER} private path and credential detail",
            "",
        ),
    )

    with pytest.raises(standalone_build.StandaloneBuildStageError) as captured:
        standalone_build.build_candidate(
            ROOT,
            tmp_path / "candidate",
            commit="0" * 40,
            target="windows-x86_64",
        )
    assert captured.value.stage == "deploy"
    assert str(captured.value) == "deploy"
    assert "private" not in str(captured.value)


@pytest.mark.parametrize(
    ("target", "relative"),
    [
        ("windows-x86_64", Path("Ordifile.exe")),
        ("macos-arm64", Path("Contents/MacOS/Ordifile")),
    ],
)
def test_native_entrypoint_requires_expected_regular_nonzero_file(
    tmp_path: Path, target: str, relative: Path
) -> None:
    bundle = tmp_path / ("Ordifile.app" if target.startswith("macos-") else "Ordifile.dist")
    entrypoint = bundle / relative
    entrypoint.parent.mkdir(parents=True)

    with pytest.raises(ValueError, match="entry point is invalid"):
        standalone_build._validate_native_entrypoint(bundle, target)

    entrypoint.mkdir()
    with pytest.raises(ValueError, match="entry point is invalid"):
        standalone_build._validate_native_entrypoint(bundle, target)
    entrypoint.rmdir()

    entrypoint.write_bytes(b"")
    with pytest.raises(ValueError, match="entry point is invalid"):
        standalone_build._validate_native_entrypoint(bundle, target)

    entrypoint.write_bytes(b"public synthetic native entry point")
    assert standalone_build._validate_native_entrypoint(bundle, target) == entrypoint


def test_native_entrypoint_rejects_link_and_windows_reparse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "Ordifile.dist"
    bundle.mkdir()
    target = bundle / "target.exe"
    target.write_bytes(b"public synthetic native entry point")
    link = bundle / "Ordifile.exe"
    try:
        link.symlink_to(target.name)
    except OSError:
        pytest.skip("The test host cannot create symlinks.")
    with pytest.raises(ValueError, match="entry point is invalid"):
        standalone_build._validate_native_entrypoint(bundle, "windows-x86_64")

    link.unlink()
    link.write_bytes(b"public synthetic native entry point")
    monkeypatch.setattr(standalone_build, "_has_windows_reparse_attribute", lambda metadata: True)
    with pytest.raises(ValueError, match="entry point is invalid"):
        standalone_build._validate_native_entrypoint(bundle, "windows-x86_64")


def test_macos_entrypoint_rejects_linked_intermediate_directory(tmp_path: Path) -> None:
    bundle = tmp_path / "Ordifile.app"
    bundle.mkdir()
    outside_contents = tmp_path / "outside-contents"
    entrypoint = outside_contents / "MacOS" / "Ordifile"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_bytes(b"public synthetic native entry point")
    try:
        (bundle / "Contents").symlink_to(outside_contents, target_is_directory=True)
    except OSError:
        pytest.skip("The test host cannot create directory symlinks.")

    with pytest.raises(ValueError, match="directory chain is invalid"):
        standalone_build._validate_native_entrypoint(bundle, "macos-arm64")


def test_license_destination_requires_real_internal_ancestors(tmp_path: Path) -> None:
    bundle = tmp_path / "Ordifile.app"
    contents = bundle / "Contents"
    contents.mkdir(parents=True)
    outside_resources = tmp_path / "outside-resources"
    outside_resources.mkdir()
    try:
        (contents / "Resources").symlink_to(outside_resources, target_is_directory=True)
    except OSError:
        pytest.skip("The test host cannot create directory symlinks.")

    with pytest.raises(ValueError, match="directory chain is invalid"):
        standalone_build._license_destination(bundle, "macos-arm64")
    assert not (outside_resources / "licenses").exists()

    (contents / "Resources").unlink()
    (contents / "Resources").mkdir()
    destination = standalone_build._license_destination(bundle, "macos-arm64")
    assert destination == contents / "Resources" / "licenses"
    destination.mkdir()
    with pytest.raises(ValueError, match="license destination is invalid"):
        standalone_build._license_destination(bundle, "macos-arm64")
    destination.rmdir()
    destination.symlink_to(tmp_path / "missing-license-root", target_is_directory=True)
    assert destination.is_symlink() and not destination.exists()
    with pytest.raises(ValueError, match="license destination is invalid"):
        standalone_build._license_destination(bundle, "macos-arm64")


@pytest.mark.parametrize("license_only", [False, True])
def test_build_rejects_partial_deployment_before_license_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, license_only: bool
) -> None:
    monkeypatch.setattr(standalone_build, "_validate_native_target", lambda target: None)
    monkeypatch.setattr(standalone_build, "_deploy_executable", lambda: Path("pyside6-deploy"))

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args
        stage = Path(str(kwargs["cwd"]))
        bundle = stage / "result" / "Ordifile.dist"
        bundle.mkdir()
        if license_only:
            licenses = bundle / "licenses"
            licenses.mkdir()
            (licenses / "NOTICE").write_text("partial deployment\n", encoding="utf-8")
        return subprocess.CompletedProcess(["pyside6-deploy"], 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        standalone_build,
        "_copy_distribution_licenses",
        lambda destination: pytest.fail("license injection must not run for a partial deployment"),
    )

    with pytest.raises(standalone_build.StandaloneBuildStageError) as captured:
        standalone_build.build_candidate(
            ROOT,
            tmp_path / "candidate",
            commit="0" * 40,
            target="windows-x86_64",
        )
    assert captured.value.stage == "deploy-output"
    assert not (tmp_path / "candidate").exists()


def test_native_entrypoint_gate_precedes_license_and_manifest_work() -> None:
    source = inspect.getsource(standalone_build.build_candidate)
    entrypoint_gate = source.index("_validate_native_entrypoint(bundle, target)")
    assert entrypoint_gate < source.index('shutil.copytree(packaging / "licenses", licenses)')
    assert entrypoint_gate < source.index("_copy_distribution_licenses(licenses)")
    assert entrypoint_gate < source.index("manifest = build_manifest(")
    assert entrypoint_gate < source.index("_deterministic_zip(bundle, archive)")


def test_build_cli_reports_only_fixed_failure_stage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_build(*args: object, **kwargs: object) -> Path:
        del args, kwargs
        raise standalone_build.StandaloneBuildStageError("bundle-audit")

    monkeypatch.setattr(standalone_build, "build_candidate", fail_build)
    assert (
        standalone_build.main(
            [
                "--source",
                "private-source-sentinel",
                "--output",
                "private-output-sentinel",
                "--commit",
                "0" * 40,
                "--target",
                "macos-arm64",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == (
        "Standalone candidate build failed at stage=bundle-audit; captured details were withheld.\n"
    )
    assert "private-source-sentinel" not in captured.out
    assert "private-output-sentinel" not in captured.out

    monkeypatch.setattr(
        standalone_build,
        "build_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            standalone_build.StandaloneBuildStageError("private-stage-sentinel")
        ),
    )
    assert (
        standalone_build.main(
            [
                "--source",
                "private-source-sentinel",
                "--output",
                "private-output-sentinel",
                "--commit",
                "0" * 40,
                "--target",
                "macos-arm64",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == (
        "Standalone candidate build failed at stage=unknown; captured details were withheld.\n"
    )
    assert "private-stage-sentinel" not in captured.out


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("An unneeded Qt network component is bundled.", "bundle-audit-network-runtime"),
        ("Private build data is embedded in a bundle path.", "bundle-audit-private-data"),
        ("Private build data is embedded in a bundle symlink.", "bundle-audit-private-data"),
        ("Private build data is embedded in the standalone bundle.", "bundle-audit-private-data"),
        ("A prohibited scientific fixture is bundled.", "bundle-audit-prohibited-data"),
        ("private arbitrary verification detail", "bundle-audit"),
    ],
)
def test_bundle_audit_failure_stage_is_allowlisted(message: str, expected: str) -> None:
    error = standalone_verify.StandaloneVerificationError(message)
    stage = standalone_build._bundle_audit_failure_stage(error)
    assert stage == expected
    assert stage in standalone_build.BUILD_FAILURE_STAGES
    assert "private arbitrary" not in stage


def test_build_candidate_converts_internal_detail_to_fixed_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine = platform.machine().casefold()
    current = {
        ("darwin", "arm64"): "macos-arm64",
        ("darwin", "x86_64"): "macos-x86_64",
        ("win32", "amd64"): "windows-x86_64",
        ("win32", "x86_64"): "windows-x86_64",
    }.get((sys.platform, machine))
    if current is None:
        pytest.skip("Standalone native target is unavailable on this test host.")

    def fail_render(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("private internal path and credential sentinel")

    monkeypatch.setattr(standalone_build, "_render_spec", fail_render)
    with pytest.raises(standalone_build.StandaloneBuildStageError) as captured:
        standalone_build.build_candidate(
            ROOT,
            tmp_path / "candidate",
            commit="0" * 40,
            target=current,
        )
    assert captured.value.stage == "prepare"
    assert str(captured.value) == "prepare"
    assert "private" not in str(captured.value)


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, MemoryError])
def test_build_candidate_preserves_nonordinary_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[BaseException],
) -> None:
    machine = platform.machine().casefold()
    current = {
        ("darwin", "arm64"): "macos-arm64",
        ("darwin", "x86_64"): "macos-x86_64",
        ("win32", "amd64"): "windows-x86_64",
        ("win32", "x86_64"): "windows-x86_64",
    }.get((sys.platform, machine))
    if current is None:
        pytest.skip("Standalone native target is unavailable on this test host.")

    def fail_render(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise exception_type()

    monkeypatch.setattr(standalone_build, "_render_spec", fail_render)
    with pytest.raises(exception_type):
        standalone_build.build_candidate(
            ROOT,
            tmp_path / "candidate",
            commit="0" * 40,
            target=current,
        )


def test_build_cli_sanitizes_unclassified_preflight_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_build(*args: object, **kwargs: object) -> Path:
        del args, kwargs
        raise RuntimeError("private preflight sentinel")

    monkeypatch.setattr(standalone_build, "build_candidate", fail_build)
    assert (
        standalone_build.main(
            [
                "--source",
                "private-source-sentinel",
                "--output",
                "private-output-sentinel",
                "--commit",
                "0" * 40,
                "--target",
                "macos-arm64",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == (
        "Standalone candidate build failed at stage=preflight; details were withheld.\n"
    )
    assert "private" not in captured.out


def test_build_cli_preserves_success_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(
        standalone_build,
        "build_candidate",
        lambda *args, **kwargs: tmp_path / "Ordifile-0.4.0-macos-arm64-UNSIGNED.zip",
    )
    assert (
        standalone_build.main(
            [
                "--source",
                "source",
                "--output",
                "candidate",
                "--commit",
                "0" * 40,
                "--target",
                "macos-arm64",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == "Unsigned standalone candidate build PASS\n"


def test_entry_routes_explicit_smoke_without_launching_desktop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[str] = []

    def fake_smoke(arguments: list[str]) -> int:
        received.extend(arguments)
        return 7

    monkeypatch.setattr(standalone_entry, "smoke_main", fake_smoke)
    assert standalone_entry.main(["--standalone-smoke", "--kit", "public-kit"]) == 7
    assert received == ["run", "--kit", "public-kit"]


def test_entry_routes_window_smoke_and_sanitizes_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(standalone_entry, "_window_smoke", lambda: 0)
    assert standalone_entry.main(["--standalone-window-smoke"]) == 0

    def fail() -> int:
        raise RuntimeError("private failure detail")

    monkeypatch.setattr(standalone_entry, "_window_smoke", fail)
    assert standalone_entry.main(["--standalone-window-smoke"]) == 1
    captured = capsys.readouterr()
    assert "private failure detail" not in captured.err
    assert captured.err == "Standalone window smoke failed; details were withheld.\n"


def test_private_build_path_inventory_includes_environment_without_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    values = standalone_build._private_build_paths(
        ROOT, tmp_path / "stage", target="windows-x86_64"
    )
    assert str((tmp_path / "runner").resolve()) in values
    assert str(Path.home().resolve()) in values
    assert str(Path(os.path.realpath(sys.prefix))) in values


@pytest.mark.parametrize(
    ("category", "value_factory"),
    [
        ("source", lambda source, stage: str(source.resolve())),
        ("temporary", lambda source, stage: str(stage.resolve())),
        ("runtime-prefix", lambda source, stage: str(Path(sys.prefix).resolve())),
        ("runtime-executable", lambda source, stage: str(Path(sys.executable).resolve())),
        ("home", lambda source, stage: str(Path.home().resolve())),
    ],
)
def test_private_bundle_data_classification_is_category_only(
    tmp_path: Path,
    category: str,
    value_factory: Callable[[Path, Path], str],
) -> None:
    source = tmp_path / "source"
    stage = tmp_path / "stage"
    bundle = _candidate(tmp_path / category)
    value = value_factory(source, stage)
    (bundle / "bin" / "Ordifile").write_text(value, encoding="utf-8")
    assert standalone_build._classify_private_bundle_data(
        bundle, source, stage, target="windows-x86_64"
    ) == (f"bundle-audit-private-{category}")


def test_private_bundle_data_prefers_runtime_over_containing_temporary_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    stage = tmp_path / "stage"
    runtime = tmp_path / "tool-cache" / "python"
    bundle = _candidate(tmp_path / "candidate")
    monkeypatch.setattr(sys, "prefix", str(runtime))
    monkeypatch.setattr(sys, "executable", str(runtime / "bin" / "python"))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    (bundle / "bin" / "Ordifile").write_text(str(runtime), encoding="utf-8")

    assert standalone_build._classify_private_bundle_data(
        bundle, source, stage, target="windows-x86_64"
    ) == ("bundle-audit-private-runtime-prefix")


def test_private_bundle_data_classifies_runner_tool_cache_without_exposing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    stage = tmp_path / "stage"
    tool_cache = tmp_path / "tool-cache"
    bundle = _candidate(tmp_path / "candidate")
    monkeypatch.setenv("RUNNER_TOOL_CACHE", str(tool_cache))
    (bundle / "bin" / "Ordifile").write_text(str(tool_cache), encoding="utf-8")

    assert standalone_build._classify_private_bundle_data(
        bundle, source, stage, target="windows-x86_64"
    ) == ("bundle-audit-private-runtime-tool-cache")


def test_official_macos_runtime_is_public_but_other_private_roots_remain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    stage = tmp_path / "stage"
    monkeypatch.setattr(sys, "prefix", str(standalone_build.PINNED_MACOS_PYTHON_PREFIX))
    monkeypatch.setattr(
        sys,
        "executable",
        str(standalone_build.PINNED_MACOS_PYTHON_EXECUTABLE),
    )

    values = standalone_build._private_build_paths(source, stage, target="macos-arm64")

    assert str(standalone_build.PINNED_MACOS_PYTHON_PREFIX) not in values
    assert str(standalone_build.PINNED_MACOS_PYTHON_EXECUTABLE) not in values
    assert str(source.resolve()) in values
    assert str(stage.resolve()) in values
    assert str(Path.home().resolve()) in values

    windows_values = standalone_build._private_build_paths(source, stage, target="windows-x86_64")
    assert str(standalone_build.PINNED_MACOS_PYTHON_PREFIX) in windows_values
    assert str(standalone_build.PINNED_MACOS_PYTHON_EXECUTABLE) in windows_values


def test_official_macos_runtime_exception_requires_both_exact_literals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    stage = tmp_path / "stage"
    monkeypatch.setattr(sys, "prefix", str(standalone_build.PINNED_MACOS_PYTHON_PREFIX))
    near_miss = standalone_build.PINNED_MACOS_PYTHON_EXECUTABLE.with_name("python3")
    monkeypatch.setattr(sys, "executable", str(near_miss))

    values = standalone_build._private_build_paths(source, stage, target="macos-arm64")

    assert str(standalone_build.PINNED_MACOS_PYTHON_PREFIX) in values
    assert str(near_miss) in values


def test_official_macos_runtime_exception_keeps_resolved_symlink_targets_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual_prefix = tmp_path / "actual-runtime"
    (actual_prefix / "bin").mkdir(parents=True)
    actual_executable = actual_prefix / "bin" / "python3.14"
    actual_executable.write_bytes(b"synthetic runtime")
    public_prefix = tmp_path / "public-runtime"
    public_prefix.symlink_to(actual_prefix, target_is_directory=True)
    public_executable = public_prefix / "bin" / "python3.14"
    monkeypatch.setattr(standalone_build, "PINNED_MACOS_PYTHON_PREFIX", public_prefix)
    monkeypatch.setattr(standalone_build, "PINNED_MACOS_PYTHON_EXECUTABLE", public_executable)
    monkeypatch.setattr(sys, "prefix", str(public_prefix))
    monkeypatch.setattr(sys, "executable", str(public_executable))

    values = standalone_build._private_build_paths(
        tmp_path / "source", tmp_path / "stage", target="macos-arm64"
    )

    assert str(public_prefix) not in values
    assert str(public_executable) not in values
    assert str(actual_prefix.resolve()) in values
    assert str(actual_executable.resolve()) in values


def test_extracted_candidate_must_equal_manifest_and_expected_commit(tmp_path: Path) -> None:
    root = _candidate(tmp_path)
    commit = "a" * 40
    manifest = standalone_verify.build_manifest(
        root,
        commit=commit,
        target="macos-arm64",
        signature_state="UNSIGNED_PROTOTYPE",
    )
    manifest["outer_artifact"] = {
        "filename": "Ordifile-0.4.0-macos-arm64-UNSIGNED.zip",
        "size": 123,
        "sha256": "b" * 64,
    }
    path = tmp_path / "manifest.json"
    standalone_verify.write_manifest(path, manifest)
    standalone_verify.verify_candidate_tree(
        root,
        path,
        commit=commit,
        target="macos-arm64",
    )

    changed = json.loads(path.read_text(encoding="ascii"))
    changed["files"][0]["sha256"] = "c" * 64
    path.write_text(json.dumps(changed), encoding="ascii")
    with pytest.raises(
        standalone_verify.StandaloneVerificationError,
        match="differs from its reviewed manifest",
    ):
        standalone_verify.verify_candidate_tree(
            root,
            path,
            commit=commit,
            target="macos-arm64",
        )

    standalone_verify.write_manifest(path, manifest)
    with pytest.raises(
        standalone_verify.StandaloneVerificationError,
        match="differs from its reviewed manifest",
    ):
        standalone_verify.verify_candidate_tree(
            root,
            path,
            commit="d" * 40,
            target="macos-arm64",
        )
