# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from standalone import build as standalone_build  # noqa: E402
from standalone import windows_zig  # noqa: E402


def _workflow_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    environment = tmp_path / "github-env"
    environment.write_text("", encoding="utf-8")
    github_path = tmp_path / "github-path"
    github_path.write_text("", encoding="utf-8")
    values = {
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_JOB": "windows-prototype",
        "GITHUB_ENV": str(environment),
        "GITHUB_PATH": str(github_path),
        "PROCESSOR_ARCHITECTURE": "AMD64",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _safe_archive(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{windows_zig.ZIG_ROOT_NAME}/", b"")
        archive.writestr(f"{windows_zig.ZIG_ROOT_NAME}/zig.exe", b"public synthetic executable")
        archive.writestr(f"{windows_zig.ZIG_ROOT_NAME}/lib/std.zig", b"public synthetic source")


def test_official_zig_asset_identity_is_exactly_pinned() -> None:
    assert windows_zig.ZIG_VERSION == "0.16.0"
    assert windows_zig.ZIG_ARCHIVE_NAME == "zig-x86_64-windows-0.16.0.zip"
    assert windows_zig.ZIG_URL == (
        "https://ziglang.org/download/0.16.0/zig-x86_64-windows-0.16.0.zip"
    )
    assert windows_zig.ZIG_ARCHIVE_SIZE == 97_217_739
    assert windows_zig.ZIG_ARCHIVE_SHA256 == (
        "68659eb5f1e4eb1437a722f1dd889c5a322c9954607f5edcf337bc3684a75a7e"
    )


def test_windows_direct_nuitka_contract_has_no_fallback_or_wrapper() -> None:
    command = standalone_build._windows_nuitka_command(Path("Ordifile.py"), Path("result"))
    assert command[:4] == [sys.executable, "-m", "nuitka", "Ordifile.py"]
    assert "--follow-imports" in command
    assert "--enable-plugin=pyside6" in command
    assert "--standalone" in command
    assert "--static-libpython=no" in command
    assert "--noinclude-qt-translations" in command
    assert "--noinclude-qt-plugins=tls" in command
    assert command.count("--nofollow-import-to=PySide6.QtNetwork") == 1
    assert command.count("--noinclude-qt-plugins=networkinformation") == 1
    assert "--zig" in command
    assert "--experimental=force-dependencies-pefile" in command
    assert "--include-qt-plugins=platforms" not in command
    combined = " ".join(command).casefold()
    for prohibited in (
        "pyside6-deploy",
        "--mingw64",
        "--msvc",
        "--clang",
        "--onefile",
        "--assume-yes-for-downloads",
    ):
        assert prohibited not in combined


def test_plain_and_pyside_probes_share_the_exact_noninteractive_backend() -> None:
    source = Path("probe.py")
    output = Path("result")
    plain = windows_zig._nuitka_probe_command(source, output, pyside=False)
    pyside = windows_zig._nuitka_probe_command(source, output, pyside=True)

    for command in (plain, pyside):
        assert command[:4] == (sys.executable, "-m", "nuitka", "probe.py")
        assert "--standalone" in command
        assert "--static-libpython=no" in command
        assert "--zig" in command
        assert "--experimental=force-dependencies-pefile" in command
        assert "--assume-yes-for-downloads" not in command
    assert "--enable-plugin=pyside6" not in plain
    assert "--nofollow-import-to=PySide6.QtNetwork" not in plain
    assert "--noinclude-qt-plugins=networkinformation" not in plain
    assert "--enable-plugin=pyside6" in pyside
    assert pyside.count("--nofollow-import-to=PySide6.QtNetwork") == 1
    assert pyside.count("--noinclude-qt-plugins=networkinformation") == 1


@pytest.mark.parametrize(
    "relative",
    (
        Path("Qt6Network.dll"),
        Path("PySide6/QtNetwork.pyd"),
        Path("PySide6/qt-plugins/networkinformation/qnetworklistmanager.dll"),
    ),
)
def test_pyside_probe_rejects_qt_network_runtime(tmp_path: Path, relative: Path) -> None:
    bundle = tmp_path / "probe.dist"
    platform = bundle / "PySide6" / "qt-plugins" / "platforms" / "qwindows.dll"
    platform.parent.mkdir(parents=True)
    platform.write_bytes(b"synthetic platform plugin")
    network = bundle / relative
    network.parent.mkdir(parents=True, exist_ok=True)
    network.write_bytes(b"synthetic network runtime")

    with pytest.raises(windows_zig.ZigStageError, match="pyside-output"):
        windows_zig._validate_pyside_probe_bundle(bundle)


def test_windows_nuitka_environment_is_child_only_and_has_no_compiler_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "zig.exe"
    monkeypatch.setenv("CC", "foreign-compiler")
    monkeypatch.setenv("CXX", "foreign-compiler")

    environment = windows_zig._windows_nuitka_environment(executable)

    assert environment["PATH"].split(os.pathsep, 1)[0] == str(tmp_path)
    assert environment["CFLAGS"] == windows_zig.WINDOWS_CPU_BASELINE_FLAG
    assert environment["CCFLAGS"] == ""
    assert "CC" not in environment
    assert "CXX" not in environment
    assert os.environ["CC"] == "foreign-compiler"
    assert os.environ["CXX"] == "foreign-compiler"


@pytest.mark.parametrize("stream", ("stdout", "stderr"))
def test_nuitka_failure_classifier_returns_only_a_fixed_scons_stage(
    stream: str,
) -> None:
    private_canary = b"C:\\private\\runner\\token-secret"
    marker = b"FATAL: Failed unexpectedly in Scons C backend compilation."
    values = {"stdout": b"", "stderr": b""}
    values[stream] = private_canary + b"\n" + marker
    completed = subprocess.CompletedProcess(
        ("private-command",), 1, values["stdout"], values["stderr"]
    )
    stage = windows_zig._classify_nuitka_failure(
        completed,
        prefix="pyside",
    )

    assert stage == "pyside-scons-backend"
    assert private_canary.decode("ascii") not in stage


@pytest.mark.parametrize(
    "captured",
    (
        b"unrecognized private failure",
        b"Failed unexpectedly in Scons C backend compilation.\n" * 2,
        b"x" * (windows_zig.MAX_FAILURE_CLASSIFICATION_BYTES + 1),
    ),
)
def test_nuitka_failure_classifier_falls_back_for_unknown_ambiguous_or_oversized_output(
    captured: bytes,
) -> None:
    completed = subprocess.CompletedProcess(("private-command",), 1, captured, b"")

    assert (
        windows_zig._classify_nuitka_failure(
            completed,
            prefix="nuitka",
        )
        == "nuitka-compile-unclassified"
    )


def test_nuitka_failure_classifier_does_not_infer_stage_from_an_unrelated_failure() -> None:
    private_canary = b"C:\\private\\runner\\post-compile-token"
    completed = subprocess.CompletedProcess(("private-command",), 1, private_canary, b"")

    stage = windows_zig._classify_nuitka_failure(completed, prefix="pyside")

    assert stage == "pyside-compile-unclassified"
    assert private_canary.decode("ascii") not in stage


def test_direct_nuitka_uses_only_subprocess_local_zig_path_and_cpu_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zig = tmp_path / "tool" / "zig.exe"
    zig.parent.mkdir()
    zig.write_bytes(b"public synthetic zig")
    output = tmp_path / "result"
    output.mkdir()
    report = output / "Ordifile.build" / "scons-report.txt"

    monkeypatch.setattr(standalone_build, "_validated_windows_zig", lambda: zig)
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured.update(kwargs)
        report.parent.mkdir()
        report.write_text(
            "zig_mode=True\n"
            "msvc_mode=False\n"
            "mingw_mode=False\n"
            "c_flags=-march=x86_64\n"
            "the_cc_name=zig.exe\n"
            f"the_compiler={zig}\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    standalone_build._run_windows_nuitka(tmp_path / "Ordifile.py", output)
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["PATH"].split(os.pathsep, 1)[0] == str(zig.parent)
    assert environment["CFLAGS"] == "-march=x86_64"
    assert environment["CCFLAGS"] == ""
    assert "CC" not in environment
    assert "CXX" not in environment
    assert captured["stdin"] is subprocess.DEVNULL
    captured_command = captured["command"]
    assert isinstance(captured_command, list)
    assert "--zig" in captured_command
    assert "--experimental=force-dependencies-pefile" in captured_command


def test_build_rejects_a_linked_zig_directory_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_environment(tmp_path, monkeypatch)
    root = windows_zig._expected_root()
    token = "d" * 32
    windows_zig._create_owned_root(root, token)
    real = root / "real"
    real.mkdir()
    linked = root / "linked"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("The test host cannot create directory symlinks.")
    executable = linked / "zig.exe"
    executable.write_bytes(b"public synthetic zig")
    monkeypatch.setenv("ORDIFILE_ZIG_ROOT", str(root))
    monkeypatch.setenv("ORDIFILE_ZIG_EXE", str(executable))
    monkeypatch.setenv("ORDIFILE_ZIG_CLEANUP_TOKEN", token)

    with pytest.raises(ValueError, match="job-local Zig compiler is invalid"):
        standalone_build._validated_windows_zig()


def test_runner_temp_rejects_a_lexical_link_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("The test host cannot create directory symlinks.")
    monkeypatch.setenv("RUNNER_TEMP", str(linked))

    with pytest.raises(windows_zig.ZigStageError, match="boundary"):
        windows_zig._runner_temp()


@pytest.mark.parametrize(
    "content",
    [
        "zig_mode=False\nmsvc_mode=True\nmingw_mode=False\nc_flags=-march=x86_64\n",
        "zig_mode=True\nmsvc_mode=False\nmingw_mode=True\nc_flags=-march=x86_64\n",
        "zig_mode=True\nmsvc_mode=False\nmingw_mode=False\nc_flags=\n",
    ],
)
def test_scons_backend_report_rejects_fallback_and_missing_baseline(
    tmp_path: Path, content: str
) -> None:
    report = tmp_path / "Ordifile.build" / "scons-report.txt"
    report.parent.mkdir()
    report.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="backend identity is invalid"):
        standalone_build._validate_zig_scons_report(tmp_path, "Ordifile", tmp_path / "zig.exe")


def test_scons_backend_report_rejects_duplicate_or_linked_identity(
    tmp_path: Path,
) -> None:
    report = tmp_path / "Ordifile.build" / "scons-report.txt"
    report.parent.mkdir()
    report.write_text(
        "zig_mode=True\nzig_mode=True\nmsvc_mode=False\nmingw_mode=False\nc_flags=-march=x86_64\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="backend identity is invalid"):
        standalone_build._validate_zig_scons_report(tmp_path, "Ordifile", tmp_path / "zig.exe")

    report.unlink()
    outside = tmp_path.parent / f"{tmp_path.name}-outside-report"
    outside.write_text(
        "zig_mode=True\nmsvc_mode=False\nmingw_mode=False\nc_flags=-march=x86_64\n",
        encoding="utf-8",
    )
    try:
        report.symlink_to(outside)
    except OSError:
        pytest.skip("The test host cannot create symlinks.")
    with pytest.raises(ValueError, match="compiler report is unavailable"):
        standalone_build._validate_zig_scons_report(tmp_path, "Ordifile", tmp_path / "zig.exe")


def test_scons_backend_report_requires_the_exact_compiler_path(tmp_path: Path) -> None:
    zig = tmp_path / "zig.exe"
    zig.write_bytes(b"public synthetic zig")
    report = tmp_path / "Ordifile.build" / "scons-report.txt"
    report.parent.mkdir()
    report.write_text(
        "zig_mode=True\n"
        "msvc_mode=False\n"
        "mingw_mode=False\n"
        "c_flags=-march=x86_64\n"
        "the_cc_name=zig.exe\n"
        f"the_compiler={tmp_path / 'other-zig.exe'}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="backend identity is invalid"):
        standalone_build._validate_zig_scons_report(tmp_path, "Ordifile", zig)


def test_zig_archive_inventory_accepts_only_one_bounded_safe_root(tmp_path: Path) -> None:
    safe = tmp_path / "safe.zip"
    _safe_archive(safe)
    members = windows_zig._validate_archive(safe)
    assert len(members) == 3

    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr(f"{windows_zig.ZIG_ROOT_NAME}/../escape.exe", b"unsafe")
    with pytest.raises(windows_zig.ZigStageError, match="archive-inventory"):
        windows_zig._validate_archive(traversal)

    alternate_root = tmp_path / "alternate.zip"
    with zipfile.ZipFile(alternate_root, "w") as archive:
        archive.writestr("other/zig.exe", b"unsafe")
    with pytest.raises(windows_zig.ZigStageError, match="archive-inventory"):
        windows_zig._validate_archive(alternate_root)


def test_zig_archive_inventory_rejects_casefold_nfkc_and_link_collisions(tmp_path: Path) -> None:
    collision = tmp_path / "collision.zip"
    with zipfile.ZipFile(collision, "w") as archive:
        archive.writestr(f"{windows_zig.ZIG_ROOT_NAME}/A.txt", b"one")
        archive.writestr(f"{windows_zig.ZIG_ROOT_NAME}/Ａ.txt", b"two")
    with pytest.raises(windows_zig.ZigStageError, match="archive-inventory"):
        windows_zig._validate_archive(collision)

    linked = tmp_path / "linked.zip"
    with zipfile.ZipFile(linked, "w") as archive:
        info = zipfile.ZipInfo(f"{windows_zig.ZIG_ROOT_NAME}/zig.exe")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b"outside")
    with pytest.raises(windows_zig.ZigStageError, match="archive-inventory"):
        windows_zig._validate_archive(linked)


@pytest.mark.parametrize(
    "name",
    ("CON .txt", "COM¹", "LPT².log", "CONIN$", "CONOUT$", "CLOCK$"),
)
def test_zig_archive_inventory_rejects_windows_device_aliases(tmp_path: Path, name: str) -> None:
    archive_path = tmp_path / "reserved.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(f"{windows_zig.ZIG_ROOT_NAME}/{name}", b"unsafe")
    with pytest.raises(windows_zig.ZigStageError, match="archive-inventory"):
        windows_zig._validate_archive(archive_path)


def test_pyside_probe_requires_one_windows_platform_plugin_and_no_zig(tmp_path: Path) -> None:
    bundle = tmp_path / "probe.dist"
    plugin = bundle / "PySide6" / "plugins" / "platforms" / "qwindows.dll"
    plugin.parent.mkdir(parents=True)
    plugin.write_bytes(b"public synthetic Qt platform plugin")
    windows_zig._validate_pyside_probe_bundle(bundle)

    plugin.unlink()
    with pytest.raises(windows_zig.ZigStageError, match="pyside-output"):
        windows_zig._validate_pyside_probe_bundle(bundle)

    plugin.write_bytes(b"public synthetic Qt platform plugin")
    (bundle / "zig.exe").write_bytes(b"synthetic build tool")
    with pytest.raises(windows_zig.ZigStageError, match="pyside-output"):
        windows_zig._validate_pyside_probe_bundle(bundle)


def test_owned_zig_root_cleanup_never_deletes_foreign_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_environment(tmp_path, monkeypatch)
    root = windows_zig._expected_root()
    token = "a" * 32
    windows_zig._create_owned_root(root, token)
    (root / "public.txt").write_text("public synthetic data\n", encoding="utf-8")

    with pytest.raises(windows_zig.ZigStageError, match="cleanup"):
        windows_zig._remove_owned_root(root, "different-token")
    assert root.is_dir()

    windows_zig._remove_owned_root(root, token)
    assert not root.exists()


def test_job_environment_exports_only_bounded_values_and_never_changes_github_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_environment(tmp_path, monkeypatch)
    root = windows_zig._expected_root()
    token = "b" * 32
    windows_zig._write_cleanup_environment(root, token)
    windows_zig._create_owned_root(root, token)
    executable = root / "tool" / windows_zig.ZIG_ROOT_NAME / "zig.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"public synthetic zig")
    windows_zig._write_tool_environment(root, executable)

    environment = Path(os.environ["GITHUB_ENV"]).read_text(encoding="utf-8").splitlines()
    assert {line.split("=", 1)[0] for line in environment} == {
        "ORDIFILE_ZIG_ROOT",
        "ORDIFILE_ZIG_EXE",
        "ORDIFILE_ZIG_CLEANUP_TOKEN",
        "ORDIFILE_ZIG_EXE_SHA256",
        "ORDIFILE_ZIG_TREE_SHA256",
        "NUITKA_CACHE_DIR",
        "ZIG_LOCAL_CACHE_DIR",
        "ZIG_GLOBAL_CACHE_DIR",
    }
    assert Path(os.environ["GITHUB_PATH"]).read_text(encoding="utf-8") == ""
    windows_zig._remove_owned_root(root, token)


def test_configured_zig_rejects_tool_bytes_changed_after_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_environment(tmp_path, monkeypatch)
    root = windows_zig._expected_root()
    token = "e" * 32
    windows_zig._create_owned_root(root, token)
    executable = root / "tool" / windows_zig.ZIG_ROOT_NAME / "zig.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"public synthetic zig")
    monkeypatch.setenv("ORDIFILE_ZIG_ROOT", str(root))
    monkeypatch.setenv("ORDIFILE_ZIG_EXE", str(executable))
    monkeypatch.setenv("ORDIFILE_ZIG_CLEANUP_TOKEN", token)
    monkeypatch.setenv("ORDIFILE_ZIG_EXE_SHA256", windows_zig._sha256(executable))
    monkeypatch.setenv("ORDIFILE_ZIG_TREE_SHA256", windows_zig._tree_sha256(executable.parent))
    monkeypatch.setattr(windows_zig, "_validate_zig_identity", lambda _path: None)

    executable.write_bytes(b"changed synthetic zig")
    with pytest.raises(windows_zig.ZigStageError, match="environment"):
        windows_zig._configured_zig()


def test_cleanup_identity_is_exported_before_owned_root_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_environment(tmp_path, monkeypatch)
    events: list[str] = []

    monkeypatch.setattr("standalone.windows_zig.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        windows_zig,
        "_write_cleanup_environment",
        lambda _root, _token: events.append("cleanup-environment"),
    )

    def stop_after_environment(_root: Path, _token: str) -> None:
        events.append("create-root")
        raise windows_zig.ZigStageError("synthetic-stop")

    monkeypatch.setattr(windows_zig, "_create_owned_root", stop_after_environment)
    with pytest.raises(windows_zig.ZigStageError, match="synthetic-stop"):
        windows_zig.bootstrap()
    assert events == ["cleanup-environment", "create-root"]


def test_cleanup_accepts_an_already_removed_exact_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workflow_environment(tmp_path, monkeypatch)
    root = windows_zig._expected_root()
    monkeypatch.setenv("ORDIFILE_ZIG_ROOT", str(root))
    monkeypatch.setenv("ORDIFILE_ZIG_CLEANUP_TOKEN", "c" * 32)
    windows_zig.cleanup()


def test_windows_zig_source_has_no_host_install_or_compiler_fallback() -> None:
    source = (ROOT / "scripts" / "standalone" / "windows_zig.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "standalone-windows-reusable.yml").read_text(
        encoding="utf-8"
    )
    combined = f"{source}\n{workflow}".casefold()
    for prohibited in (
        "setx ",
        "set-executionpolicy",
        "start-service",
        "restart-service",
        "choco ",
        "winget ",
        "visual studio installer",
        "windows_toolchain.ps1",
        "--mingw64",
        "--msvc",
        "windows-latest",
        "windows-2025",
    ):
        assert prohibited not in combined
    assert "github_path" not in source.casefold()
