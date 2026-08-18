# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import sys
import zipfile
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
    assert "onefile" not in spec.casefold()


def test_source_distribution_includes_standalone_build_inputs() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '  "/packaging",' in project


def test_workflow_is_manual_native_and_uploads_path_free_evidence_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    trigger = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger
    for prohibited in ("push:", "pull_request:", "schedule:", "release:"):
        assert prohibited not in trigger
    assert "runs-on: [self-hosted, Windows, X64]" in text
    for prohibited_runner in ("windows-2025", "windows-latest", "windows-2022"):
        assert prohibited_runner not in text
    assert "runs-on: macos-15" in text
    assert text.count("github.repository == 'hdkim99/ordifile'") == 2
    assert text.count("github.event_name == 'workflow_dispatch'") == 2
    assert text.count("github.ref == 'refs/heads/main'") == 2
    windows_job = text.split("  macos-prototype:", 1)[0]
    assert "Mask persistent runner identifiers" in windows_job
    assert "::add-mask::" in windows_job
    for private_runner_value in (
        "RUNNER_WORKSPACE",
        "RUNNER_NAME",
        "USERNAME",
        "USERPROFILE",
        "COMPUTERNAME",
        "USERDOMAIN",
    ):
        assert private_runner_value in windows_job
    assert "path: source" in windows_job
    assert windows_job.count("working-directory: source") >= 7
    assert 'python-version: "3.14.3"' in text
    assert "--target windows-x86_64" in text
    assert "--standalone-smoke" in text
    assert "--standalone-window-smoke" in text
    assert text.count("QT_QPA_PLATFORM") == 2
    assert "standalone smoke 결과.xlsx" in text
    assert text.count("scripts/standalone/verify.py") == 2
    assert text.count("PYTHONNOUSERSITE") == 2
    assert "run_in_venv.py create --github-runner" in text
    assert "run_in_venv.py remove --github-runner" in text
    assert "python -m pip install" not in windows_job
    assert "pip install --quiet" in windows_job
    assert windows_job.count("run_in_venv.py run --github-runner") >= 5
    assert text.count("clean_workspace.py --workspace . --phase") == 2
    assert text.count("if: always()") >= 3
    assert "ordifile-standalone-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT-$env:GITHUB_JOB" in text
    assert text.count("Standalone scratch boundary is invalid.") == 2
    assert "actions/download-artifact@" not in text
    assert text.count("actions/upload-artifact@") == 2
    assert "standalone-candidate/standalone-manifest.json" in text
    assert "standalone-candidate/SHA256SUMS.txt" in text
    assert "standalone-candidate/\n" not in text
    assert "standalone-smoke-kit/\n" not in text
    assert "evidence only" in text
    assert "id-token: write" not in text
    assert "contents: write" not in text
    assert "release" not in "\n".join(
        line.casefold() for line in text.splitlines() if line.lstrip().startswith("uses:")
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
    )
    text = destination.read_text(encoding="utf-8")
    assert "@PROJECT_DIR@" not in text
    assert "@EXEC_DIRECTORY@" not in text
    assert "@PYTHON_PATH@" not in text
    assert str(tmp_path / "stage") in text


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
    values = standalone_build._private_build_paths(ROOT, tmp_path / "stage")
    assert str((tmp_path / "runner").resolve()) in values
    assert str(Path.home().resolve()) in values
    assert str(Path(os.path.realpath(sys.prefix))) in values


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
