# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import BinaryIO, TextIO, cast
from unittest.mock import Mock

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "local"))
import youngin_yl_clarity_export_bridge as bridge  # noqa: E402


def _prm(path: Path, marker: bytes = b"synthetic-prm") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(marker)
    return path


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic executable placeholder")
    return path


def _result_table(
    *,
    include_area: bool = True,
    include_height: bool = True,
    include_signal: bool = True,
) -> bytes:
    columns = ["R.Time"]
    if include_area:
        columns.append("Area")
    if include_height:
        columns.append("Height")
    if include_signal:
        columns.append("Signal Name")
    return ("\t".join(columns) + "\n1.25\t100\t25\tSignal A\n").encode()


def _official_style_result_table(*, rows: int = 1) -> bytes:
    header = "Reten. Time [min]\tArea [detector units.s]\tHeight [detector units]\n"
    return (header + "".join(f"{index}.25\t100\t25\n" for index in range(rows))).encode()


class FakeRunner:
    def __init__(
        self,
        outputs: tuple[bytes | None, ...],
        *,
        returncodes: tuple[int, ...] | None = None,
    ) -> None:
        self.outputs = outputs
        self.returncodes = returncodes or tuple(0 for _ in outputs)
        self.commands: list[tuple[str, ...]] = []
        self.working_directories: list[Path] = []
        self.staged_contents: list[bytes] = []

    def __call__(
        self,
        command: tuple[str, ...],
        executable: Path,
        working_directory: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        index = len(self.commands)
        self.commands.append(command)
        assert executable.is_file()
        self.working_directories.append(working_directory)
        self.staged_contents.append((working_directory / command[1]).read_bytes())
        output = self.outputs[index]
        if output is not None:
            output_name = command[2].split("=", 1)[1]
            (working_directory / output_name).write_bytes(output)
        assert timeout_seconds == bridge.DEFAULT_TIMEOUT_SECONDS
        return subprocess.CompletedProcess(command, self.returncodes[index], "private stdout", "")


def _patch_encrypted_flags(content: bytes) -> bytes:
    patched = bytearray(content)
    local = patched.index(b"PK\x03\x04")
    central = patched.index(b"PK\x01\x02")
    local_flags = int.from_bytes(patched[local + 6 : local + 8], "little") | 1
    central_flags = int.from_bytes(patched[central + 8 : central + 10], "little") | 1
    patched[local + 6 : local + 8] = local_flags.to_bytes(2, "little")
    patched[central + 8 : central + 10] = central_flags.to_bytes(2, "little")
    return bytes(patched)


def test_pilot_uses_explicit_executable_ordered_command_and_sha_aliases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _prm(tmp_path / "private sample name.PRM")
    executable = _executable(tmp_path / "vendor" / "YL-Clarity.exe")
    output = tmp_path / "exports"
    runner = FakeRunner((_result_table(),))
    messages: list[str] = []
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    monkeypatch.setenv("PATH", str(decoy))
    original = source.read_bytes()

    manifest = bridge.run_bridge(
        source,
        output,
        executable=executable,
        runner=runner,
        logger=messages.append,
    )

    digest = hashlib.sha256(original).hexdigest()
    assert source.read_bytes() == original
    assert manifest.mode == "pilot"
    assert manifest.successful_exports == 1
    assert manifest.original_sources_modified == 0
    assert manifest.records[0].source_id == f"source-{digest}"
    assert manifest.records[0].header == bridge.HeaderEvidence(
        "utf-8-sig", "tab", 1, True, True, True, True, 1, 1, 1, 1, 1
    )
    command = runner.commands[0]
    assert command[0] == executable.name
    assert command[1] == f"s-{digest[:16]}.prm"
    assert command[2] == f"export_results=r-{digest[:16]}.txt"
    assert command[3] == "prm_close_discard"
    assert len(subprocess.list2cmdline(command)) <= bridge.MAX_COMMAND_CHARACTERS
    assert not Path(command[1]).is_absolute()
    assert not Path(command[2].split("=", 1)[1]).is_absolute()
    assert (output / f"source-{digest}.txt").is_file()
    assert messages == [f"source-{digest}: SUCCESS"]


def test_manifest_and_logs_exclude_private_names_paths_and_vendor_output(
    tmp_path: Path,
) -> None:
    secret_name = "operator-private-sample.PRM"
    source = _prm(tmp_path / secret_name)
    executable = _executable(tmp_path / "private-install" / "YL-Clarity.exe")
    output = tmp_path / "exports"
    runner = FakeRunner((_result_table(),))
    messages: list[str] = []

    bridge.run_bridge(
        source,
        output,
        executable=executable,
        runner=runner,
        logger=messages.append,
    )

    manifest_text = (output / bridge.MANIFEST_FILENAME).read_text(encoding="utf-8")
    public_surface = manifest_text + "\n" + "\n".join(messages)
    assert secret_name not in public_surface
    assert str(tmp_path) not in public_surface
    assert "private stdout" not in public_surface
    manifest = json.loads(manifest_text)
    assert manifest["executable"] == {
        "discovery": "explicit",
        "found": True,
        "product_version": None,
    }
    schema = json.loads(
        (
            PROJECT_ROOT
            / "docs"
            / "research"
            / "youngin-yl-clarity-result-export-local-manifest.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["additionalProperties"] is False
    assert set(manifest) == set(schema["required"]) == set(schema["properties"])
    record = manifest["records"][0]
    record_schema = schema["$defs"]["record"]
    assert set(record) == set(record_schema["required"]) == set(record_schema["properties"])
    assert record_schema["properties"]["source_size_bytes"]["maximum"] == (bridge.MAX_SOURCE_BYTES)
    assert record_schema["properties"]["export_size_bytes"]["maximum"] == (bridge.MAX_EXPORT_BYTES)
    assert (
        schema["properties"]["executable"]["properties"]["product_version"]["pattern"]
        == rf"^{bridge._SAFE_PRODUCT_VERSION.pattern[:-2]}$"
    )
    header = record["header"]
    header_schema = schema["$defs"]["header"]
    assert set(header) == set(header_schema["required"]) == set(header_schema["properties"])


def test_official_style_headers_strip_unit_suffix_and_count_entire_bounded_export(
    tmp_path: Path,
) -> None:
    rows = 7_000
    output = _official_style_result_table(rows=rows)
    assert len(output) > 64 * 1024
    manifest = bridge.run_bridge(
        _prm(tmp_path / "source.prm"),
        tmp_path / "exports",
        executable=_executable(tmp_path / "YL-Clarity.exe"),
        runner=FakeRunner((output,)),
        logger=lambda _: None,
    )

    evidence = manifest.records[0].header
    assert evidence is not None
    assert evidence.has_retention_time is True
    assert evidence.has_area is True
    assert evidence.has_height is True
    assert evidence.nonempty_rows_after_header == rows
    assert evidence.rows_with_retention_time == rows
    assert evidence.rows_with_area == rows
    assert evidence.rows_with_height == rows
    assert evidence.distinct_nonempty_signal_values == 0
    public = manifest.records[0].to_json()["header"]
    assert isinstance(public, dict)
    assert "result_rows" not in public
    assert public["nonempty_rows_after_header"] == rows


def test_manifest_counts_structural_rt_area_height_and_distinct_signal_values(
    tmp_path: Path,
) -> None:
    table = (
        b"R.Time\tArea\tHeight\tSignal Name\n"
        b"1.0\t10\t2\tSignal A\n"
        b"2.0\t20\t\tSignal A\n"
        b"\t30\t4\tSignal B\n"
    )
    manifest = bridge.run_bridge(
        _prm(tmp_path / "source.prm"),
        tmp_path / "exports",
        executable=_executable(tmp_path / "YL-Clarity.exe"),
        runner=FakeRunner((table,)),
        logger=lambda _: None,
    )

    evidence = manifest.records[0].header
    assert evidence is not None
    assert evidence.nonempty_rows_after_header == 3
    assert evidence.rows_with_retention_time == 2
    assert evidence.rows_with_area == 3
    assert evidence.rows_with_height == 2
    assert evidence.distinct_nonempty_signal_values == 2


def test_directory_order_is_deterministic_and_pilot_processes_one(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    _prm(inputs / "z.PRM", b"z")
    _prm(inputs / "A.prm", b"a")
    _prm(inputs / "middle.prm", b"m")
    executable = _executable(tmp_path / "YL-Clarity.exe")
    runner = FakeRunner((_result_table(),))

    manifest = bridge.run_bridge(
        inputs,
        tmp_path / "exports",
        executable=executable,
        runner=runner,
        logger=lambda _: None,
    )

    assert manifest.discovered_inputs == 3
    assert manifest.selected_inputs == 1
    assert runner.staged_contents == [b"a"]


def test_batch_isolates_vendor_failure_and_continues(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    original = {
        "a.prm": b"a",
        "b.prm": b"b",
        "c.prm": b"c",
    }
    for name, content in original.items():
        _prm(inputs / name, content)
    runner = FakeRunner(
        (_result_table(), None, _result_table(include_height=False, include_signal=False)),
        returncodes=(0, 7, 0),
    )

    manifest = bridge.run_bridge(
        inputs,
        tmp_path / "exports",
        executable=_executable(tmp_path / "YL-Clarity.exe"),
        batch=True,
        runner=runner,
        logger=lambda _: None,
    )

    assert len(runner.commands) == 3
    assert manifest.successful_exports == 2
    assert manifest.failed_exports == 1
    assert [record.status for record in manifest.records] == ["success", "failed", "success"]
    assert manifest.records[1].error_code == "vendor_exit_nonzero"
    assert manifest.records[2].header is not None
    assert manifest.records[2].header.has_height is False
    assert manifest.records[2].header.has_signal is False
    assert {name: (inputs / name).read_bytes() for name in original} == original


def test_batch_stops_after_failed_pilot_and_reports_only_attempted_input(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    _prm(inputs / "a.prm", b"a")
    _prm(inputs / "b.prm", b"b")
    _prm(inputs / "c.prm", b"c")
    runner = FakeRunner((None, _result_table(), _result_table()))

    manifest = bridge.run_bridge(
        inputs,
        tmp_path / "exports",
        executable=_executable(tmp_path / "YL-Clarity.exe"),
        batch=True,
        runner=runner,
        logger=lambda _: None,
    )

    assert manifest.discovered_inputs == 3
    assert manifest.selected_inputs == 1
    assert manifest.pilot_gate == "failed"
    assert len(runner.commands) == 1
    assert len(manifest.records) == 1
    assert manifest.records[0].error_code == "export_missing"


def test_detects_original_source_mutation_without_publishing_export(tmp_path: Path) -> None:
    source = _prm(tmp_path / "source.prm", b"original")
    executable = _executable(tmp_path / "YL-Clarity.exe")

    def mutating_runner(
        command: tuple[str, ...],
        executable: Path,
        working_directory: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        source.write_bytes(b"changed")
        exported = working_directory / command[2].split("=", 1)[1]
        exported.write_bytes(_result_table())
        return subprocess.CompletedProcess(command, 0, "", "")

    manifest = bridge.run_bridge(
        source,
        tmp_path / "exports",
        executable=executable,
        runner=mutating_runner,
        logger=lambda _: None,
    )

    assert manifest.failed_exports == 1
    assert manifest.original_sources_modified == 1
    assert manifest.records[0].error_code == "original_changed_during_export"
    assert tuple((tmp_path / "exports").glob("source-*.txt")) == ()


@pytest.mark.parametrize(
    ("output", "expected_code"),
    [
        (None, "export_missing"),
        (b"", "export_empty"),
        (_result_table(include_area=False), "export_header_missing_rt_area"),
    ],
)
def test_missing_empty_or_area_less_export_is_a_structured_failure(
    tmp_path: Path,
    output: bytes | None,
    expected_code: str,
) -> None:
    manifest = bridge.run_bridge(
        _prm(tmp_path / "source.prm"),
        tmp_path / "exports",
        executable=_executable(tmp_path / "YL-Clarity.exe"),
        runner=FakeRunner((output,)),
        logger=lambda _: None,
    )

    assert manifest.failed_exports == 1
    assert manifest.records[0].error_code == expected_code


def test_safe_zip_intake_exports_without_modifying_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "private-source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("group/B.prm", b"b")
        archive.writestr("group/a.PRM", b"a")
        archive.writestr("notes.txt", b"ignored")
    before = archive_path.read_bytes()
    runner = FakeRunner((_result_table(), _result_table()))

    manifest = bridge.run_bridge(
        archive_path,
        tmp_path / "exports",
        executable=_executable(tmp_path / "YL-Clarity.exe"),
        batch=True,
        runner=runner,
        logger=lambda _: None,
    )

    assert archive_path.read_bytes() == before
    assert manifest.successful_exports == 2
    assert runner.staged_contents == [b"a", b"b"]
    assert all(record.original_hash_preserved for record in manifest.records)


@pytest.mark.parametrize(
    ("member_name", "expected_code"),
    [
        ("../escape.prm", "zip_path_unsafe"),
        ("/absolute.prm", "zip_path_unsafe"),
        (r"C:\private.prm", "zip_path_unsafe"),
    ],
)
def test_zip_traversal_and_absolute_members_are_rejected(
    tmp_path: Path,
    member_name: str,
    expected_code: str,
) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(member_name, b"prm")

    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            archive_path,
            tmp_path / "exports",
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
        )
    assert caught.value.code == expected_code
    assert not (tmp_path.parent / "escape.prm").exists()


def test_zip_symlink_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("linked.prm")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "target.prm")

    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            archive_path,
            tmp_path / "exports",
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
        )
    assert caught.value.code == "zip_symlink"


@pytest.mark.parametrize(
    "member_name",
    [
        "CON.prm",
        "CON .prm",
        "COM¹.prm",
        "CONIN$.prm",
        "folder/aux.txt",
        "trailing. /x.prm",
    ],
)
def test_zip_windows_reserved_and_trailing_segments_are_rejected(
    tmp_path: Path,
    member_name: str,
) -> None:
    archive_path = tmp_path / "windows-unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(member_name, b"prm")
    extraction = tmp_path / "extracted"
    extraction.mkdir()

    with pytest.raises(bridge.BridgeError) as caught:
        bridge.collect_sources(archive_path, extraction)
    assert caught.value.code == "zip_path_unsafe"
    assert tuple(extraction.rglob("*.prm")) == ()


def test_zip_prm_count_gate_runs_before_any_extraction(tmp_path: Path) -> None:
    archive_path = tmp_path / "too-many.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for index in range(bridge.MAX_INPUT_FILES + 1):
            archive.writestr(f"source-{index:03d}.prm", b"prm")
    extraction = tmp_path / "extracted"
    extraction.mkdir()

    with pytest.raises(bridge.BridgeError) as caught:
        bridge.collect_sources(archive_path, extraction)
    assert caught.value.code == "source_count"
    assert tuple(extraction.rglob("*.prm")) == ()


def test_encrypted_zip_member_is_rejected_before_read(tmp_path: Path) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("source.prm", b"prm")
    archive_path = tmp_path / "encrypted.zip"
    archive_path.write_bytes(_patch_encrypted_flags(stream.getvalue()))

    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            archive_path,
            tmp_path / "exports",
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
        )
    assert caught.value.code == "zip_encrypted"


def test_malformed_zip_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "malformed.zip"
    archive_path.write_bytes(b"not a zip")

    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            archive_path,
            tmp_path / "exports",
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
        )
    assert caught.value.code == "zip_malformed"


def test_directory_symlink_is_rejected_without_following_it(tmp_path: Path) -> None:
    outside = _prm(tmp_path / "outside.prm")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    link = inputs / "linked.prm"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            inputs,
            tmp_path / "exports",
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
        )
    assert caught.value.code == "source_reparse_point"


def test_unreadable_directory_subtree_is_a_structured_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = tmp_path / "inputs"
    _prm(inputs / "visible.prm")
    blocked = inputs / "blocked"
    _prm(blocked / "hidden.prm")
    original_scandir = os.scandir

    def failing_scandir(path: Path | str | int) -> object:
        if not isinstance(path, int) and Path(path) == blocked:
            raise PermissionError("synthetic unreadable subtree")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", failing_scandir)
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            inputs,
            tmp_path / "exports",
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
        )
    assert caught.value.code == "directory_unreadable"


def test_reparse_helper_and_directory_intake_reject_windows_junctions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthetic_status = Mock(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
    monkeypatch.setattr(os, "lstat", Mock(return_value=synthetic_status))
    assert bridge._path_is_link_or_reparse(tmp_path) is True
    monkeypatch.undo()

    inputs = tmp_path / "inputs"
    _prm(inputs / "visible.prm")
    junction = inputs / "junction"
    _prm(junction / "outside.prm")
    original_probe = bridge._path_is_link_or_reparse

    def junction_probe(path: Path) -> bool:
        return path == junction or original_probe(path)

    monkeypatch.setattr(bridge, "_path_is_link_or_reparse", junction_probe)
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            inputs,
            tmp_path / "exports-junction",
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
        )
    assert caught.value.code == "source_reparse_point"


def test_command_length_gate_is_exact_and_never_uses_a_shell(tmp_path: Path) -> None:
    workspace = tmp_path / "w"
    workspace.mkdir()
    staged = workspace / "s-1234567890abcdef.prm"
    exported = workspace / "r-1234567890abcdef.txt"
    normal = bridge.build_vendor_command(Path("C:/YL/Clarity.exe"), staged, exported)
    assert len(subprocess.list2cmdline(normal)) <= 126
    long_staged = workspace / ("s-" + "x" * 100 + ".prm")
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.build_vendor_command(Path("C:/YL/Clarity.exe"), long_staged, exported)
    assert caught.value.code == "command_too_long"


def test_explicit_and_registry_discovery_do_not_consult_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit = _executable(tmp_path / "explicit" / "YL-Clarity.exe")
    registered = _executable(tmp_path / "registered" / "Clarity.exe")
    decoy = tmp_path / "path-decoy"
    decoy.mkdir()
    _executable(decoy / "YL-Clarity.exe")
    monkeypatch.setenv("PATH", str(decoy))

    assert bridge.discover_executable(explicit) == bridge.ExecutableInfo(
        explicit.resolve(), "explicit", None
    )
    assert bridge.discover_executable(
        None,
        registry_candidates=((tmp_path / "missing.exe", None), (registered, "9.0.1.19")),
    ) == bridge.ExecutableInfo(registered.resolve(), "registry", "9.0.1.19")
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.discover_executable(None, registry_candidates=())
    assert caught.value.code == "executable_not_found"


def test_registry_version_manifest_value_is_strict_numeric_dotted(tmp_path: Path) -> None:
    executable = _executable(tmp_path / "Clarity.exe")
    safe = bridge.discover_executable(None, registry_candidates=((executable, "9.0.1.19"),))
    unsafe = bridge.discover_executable(
        None, registry_candidates=((executable, "9.0.1.19 private-user-data"),)
    )
    assert safe.product_version == "9.0.1.19"
    assert unsafe.product_version is None


def test_default_vendor_execution_is_refused_in_ci(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "true")
    with pytest.raises(bridge.BridgeError) as caught:
        bridge._default_runner(("YL-Clarity.exe",), tmp_path / "YL-Clarity.exe", tmp_path, 1)
    assert caught.value.code == "ci_execution_refused"


def test_default_runner_uses_exact_executable_list_args_and_no_shell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _executable(tmp_path / "vendor" / "YL-Clarity.exe").resolve()
    process = Mock()
    process.wait.return_value = 0
    popen_mock = Mock(return_value=process)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(bridge, "_IS_WINDOWS", True)
    monkeypatch.setattr(subprocess, "Popen", popen_mock)
    command = (executable.name, "s-123.prm", "export_results=r-123.txt", "prm_close_discard")

    completed = bridge._default_runner(command, executable, tmp_path, 17)
    assert completed.returncode == 0
    process.wait.assert_called_once_with(timeout=17)
    popen_mock.assert_called_once_with(
        list(command),
        cwd=tmp_path,
        executable=str(executable),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def test_timeout_terminates_only_new_vendor_process_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _executable(tmp_path / "vendor" / "YL-Clarity.exe").resolve()
    system_root = tmp_path / "Windows"
    taskkill = _executable(system_root / "System32" / "taskkill.exe").resolve()
    process = Mock(pid=4321)
    process.wait.side_effect = [subprocess.TimeoutExpired("Clarity.exe", 1), 0]
    popen_mock = Mock(return_value=process)
    taskkill_completed = subprocess.CompletedProcess([str(taskkill)], 0, "", "")
    run_mock = Mock(return_value=taskkill_completed)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("SystemRoot", str(system_root))
    monkeypatch.setattr(bridge, "_IS_WINDOWS", True)
    monkeypatch.setattr(subprocess, "Popen", popen_mock)
    monkeypatch.setattr(subprocess, "run", run_mock)

    with pytest.raises(bridge.BridgeError) as caught:
        bridge._default_runner((executable.name,), executable, tmp_path, 1)
    assert caught.value.code == "vendor_timeout"
    run_mock.assert_called_once_with(
        [str(taskkill), "/PID", "4321", "/T", "/F"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        shell=False,
    )
    process.kill.assert_not_called()
    assert process.wait.call_args_list[-1].kwargs == {"timeout": 10}


def test_timeout_cleanup_failure_is_not_hidden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _executable(tmp_path / "vendor" / "YL-Clarity.exe").resolve()
    system_root = tmp_path / "Windows"
    taskkill = _executable(system_root / "System32" / "taskkill.exe").resolve()
    process = Mock(pid=4321)
    process.wait.side_effect = subprocess.TimeoutExpired("Clarity.exe", 1)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("SystemRoot", str(system_root))
    monkeypatch.setattr(bridge, "_IS_WINDOWS", True)
    monkeypatch.setattr(subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess([str(taskkill)], 1, "", "")),
    )

    with pytest.raises(bridge.BridgeError) as caught:
        bridge._default_runner((executable.name,), executable, tmp_path, 1)
    assert caught.value.code == "vendor_cleanup_failed"
    process.kill.assert_called_once_with()


def test_vendor_cleanup_uncertainty_aborts_the_batch_without_manifest(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    _prm(sources / "a.prm", b"a")
    _prm(sources / "b.prm", b"b")
    attempts = 0

    def cleanup_failure_runner(
        command: tuple[str, ...],
        executable: Path,
        working_directory: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        del command, executable, working_directory, timeout_seconds
        nonlocal attempts
        attempts += 1
        raise bridge.BridgeError(
            "vendor_cleanup_failed", "Synthetic process-tree cleanup uncertainty."
        )

    output = tmp_path / "exports"
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            sources,
            output,
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            batch=True,
            runner=cleanup_failure_runner,
            logger=lambda _: None,
        )
    assert caught.value.code == "vendor_cleanup_failed"
    assert attempts == 1
    assert not (output / bridge.MANIFEST_FILENAME).exists()


def test_late_fatal_cleanup_rolls_back_prior_batch_exports(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    _prm(sources / "a.prm", b"a")
    _prm(sources / "b.prm", b"b")
    attempts = 0

    def late_cleanup_failure_runner(
        command: tuple[str, ...],
        executable: Path,
        working_directory: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        del executable, timeout_seconds
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise bridge.BridgeError(
                "vendor_cleanup_failed", "Synthetic process-tree cleanup uncertainty."
            )
        exported = working_directory / command[2].split("=", 1)[1]
        exported.write_bytes(_result_table())
        return subprocess.CompletedProcess(command, 0, "", "")

    output = tmp_path / "exports"
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            sources,
            output,
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            batch=True,
            runner=late_cleanup_failure_runner,
            logger=lambda _: None,
        )
    assert caught.value.code == "vendor_cleanup_failed"
    assert attempts == 2
    assert tuple(output.glob("source-*.txt")) == ()
    assert not (output / bridge.MANIFEST_FILENAME).exists()


def test_temporary_cleanup_failure_is_sanitized_and_removes_persistent_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_unlink = Path.unlink

    def guarded_unlink(path: Path, missing_ok: bool = False) -> None:
        if path.name.startswith("s-"):
            raise PermissionError("synthetic private temp location")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", guarded_unlink)
    output = tmp_path / "exports"
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            _prm(tmp_path / "source.prm"),
            output,
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
            logger=lambda _: None,
        )
    assert caught.value.code == "temporary_cleanup_failed"
    assert "synthetic private temp location" not in str(caught.value)
    assert tuple(output.glob("source-*.txt")) == ()
    assert not (output / bridge.MANIFEST_FILENAME).exists()


def test_existing_manifest_prevents_destructive_rerun(tmp_path: Path) -> None:
    output = tmp_path / "exports"
    output.mkdir()
    manifest = output / bridge.MANIFEST_FILENAME
    manifest.write_text("existing", encoding="utf-8")

    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            _prm(tmp_path / "source.prm"),
            output,
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
        )
    assert caught.value.code == "manifest_exists"
    assert manifest.read_text(encoding="utf-8") == "existing"


def test_worktree_output_requires_approved_ignored_local_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    monkeypatch.setattr(bridge, "_PROJECT_ROOT", repository)
    source = _prm(repository / "source.prm")
    executable = _executable(repository / "YL-Clarity.exe")

    with pytest.raises(bridge.BridgeError) as unapproved:
        bridge.run_bridge(
            source,
            repository / "exports",
            executable=executable,
            runner=FakeRunner((_result_table(),)),
            git_ignore_probe=lambda _root, _output: True,
        )
    assert unapproved.value.code == "output_not_private_root"

    with pytest.raises(bridge.BridgeError) as unignored:
        bridge.run_bridge(
            source,
            repository / ".research-downloads" / "youngin-result",
            executable=executable,
            runner=FakeRunner((_result_table(),)),
            git_ignore_probe=lambda _root, _output: False,
        )
    assert unignored.value.code == "output_not_gitignored"

    accepted = bridge.run_bridge(
        source,
        repository / ".external-fixtures" / "youngin-result",
        executable=executable,
        runner=FakeRunner((_result_table(),)),
        git_ignore_probe=lambda _root, _output: True,
        logger=lambda _: None,
    )
    assert accepted.successful_exports == 1


def test_default_worktree_policy_reads_exact_tracked_ignore_roots_without_git_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_mock = Mock(side_effect=AssertionError("git subprocess must not run"))
    monkeypatch.setattr(subprocess, "run", run_mock)
    output = PROJECT_ROOT / ".research-downloads" / "youngin-result"

    assert bridge._default_git_ignore_probe(PROJECT_ROOT, output) is True
    bridge._enforce_worktree_output_policy(
        output,
        git_ignore_probe=bridge._default_git_ignore_probe,
    )
    run_mock.assert_not_called()


def test_foreign_git_worktree_is_refused_even_for_ignored_named_root(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign"
    (foreign / ".git").mkdir(parents=True)
    output = foreign / ".external-fixtures" / "youngin"
    output.mkdir(parents=True)

    with pytest.raises(bridge.BridgeError) as caught:
        bridge._enforce_worktree_output_policy(
            output,
            git_ignore_probe=lambda _root, _output: True,
        )
    assert caught.value.code == "output_foreign_worktree"


def test_persistent_output_symlink_race_does_not_modify_target(tmp_path: Path) -> None:
    source = _prm(tmp_path / "source.prm")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "exports"
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"do not modify")

    def racing_runner(
        command: tuple[str, ...],
        executable: Path,
        working_directory: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        exported = working_directory / command[2].split("=", 1)[1]
        exported.write_bytes(_result_table())
        (output / f"source-{digest}.txt").symlink_to(victim)
        return subprocess.CompletedProcess(command, 0, "", "")

    try:
        manifest = bridge.run_bridge(
            source,
            output,
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=racing_runner,
            logger=lambda _: None,
        )
    except OSError:
        pytest.skip("symlink creation is unavailable")
    assert manifest.records[0].error_code == "output_exists"
    assert victim.read_bytes() == b"do not modify"


def test_partial_private_output_and_manifest_are_removed_after_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "source-output.txt"
    real_open = Path.open

    class PartialWriter:
        def __init__(self, path: Path) -> None:
            self._stream = cast(BinaryIO, real_open(path, "xb"))

        def __enter__(self) -> PartialWriter:
            return self

        def __exit__(self, *args: object) -> None:
            self._stream.close()

        def write(self, content: bytes) -> int:
            self._stream.write(content[:3])
            self._stream.flush()
            raise OSError("synthetic write failure")

        def flush(self) -> None:
            self._stream.flush()

        def fileno(self) -> int:
            return int(self._stream.fileno())

    def partial_open(path: Path, mode: str = "r", *args: object, **kwargs: object) -> object:
        assert path == output
        assert mode == "xb"
        assert not args
        assert not kwargs
        return PartialWriter(path)

    monkeypatch.setattr(Path, "open", partial_open)
    with pytest.raises(bridge.BridgeError) as caught:
        bridge._write_exclusive_snapshot(output, b"private result content")
    assert caught.value.code == "output_write_failed"
    assert not output.exists()

    monkeypatch.setattr(Path, "open", real_open)
    source_sha = "a" * 64
    failed_record = bridge.ExportRecord(
        f"source-{source_sha}", source_sha, 1, "failed", "synthetic", True, None, None, None, None
    )
    manifest = bridge.BridgeManifest(
        "pilot", 1, 1, 0, 1, 0, "failed", "explicit", None, (failed_record,)
    )
    manifest_path = tmp_path / bridge.MANIFEST_FILENAME

    def fail_dump(value: object, stream: TextIO, **kwargs: object) -> None:
        del value
        del kwargs
        stream.write('{"partial":')
        raise OSError("synthetic manifest failure")

    monkeypatch.setattr(json, "dump", fail_dump)
    with pytest.raises(bridge.BridgeError) as caught:
        bridge._write_manifest(manifest_path, manifest)
    assert caught.value.code == "manifest_write_failed"
    assert not manifest_path.exists()


def test_manifest_failure_rolls_back_successful_invocation_exports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_dump = json.dump

    def fail_dump(value: object, stream: TextIO, **kwargs: object) -> None:
        del value, kwargs
        stream.write('{"partial":')
        raise OSError("synthetic manifest failure")

    monkeypatch.setattr(json, "dump", fail_dump)
    output = tmp_path / "exports"
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            _prm(tmp_path / "source.prm"),
            output,
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
            logger=lambda _: None,
        )
    assert caught.value.code == "manifest_write_failed"
    assert tuple(output.glob("source-*.txt")) == ()
    assert not (output / bridge.MANIFEST_FILENAME).exists()
    monkeypatch.setattr(json, "dump", real_dump)


def test_status_output_failure_is_sanitized_and_rolls_back_export(tmp_path: Path) -> None:
    output = tmp_path / "exports"

    def broken_status_sink(message: str) -> None:
        del message
        raise BrokenPipeError("synthetic private sink location")

    with pytest.raises(bridge.BridgeError) as caught:
        bridge.run_bridge(
            _prm(tmp_path / "source.prm"),
            output,
            executable=_executable(tmp_path / "YL-Clarity.exe"),
            runner=FakeRunner((_result_table(),)),
            logger=broken_status_sink,
        )
    assert caught.value.code == "status_output_failed"
    assert "synthetic private sink location" not in str(caught.value)
    assert tuple(output.glob("source-*.txt")) == ()
    assert not (output / bridge.MANIFEST_FILENAME).exists()


def test_integrity_rechecks_are_bounded_and_manifest_identities_are_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _prm(tmp_path / "source.prm")
    executable = _executable(tmp_path / "YL-Clarity.exe")
    original_sha256_file = bridge.sha256_file
    bounds: list[int | None] = []

    def bounded_sha256(path: Path, *, maximum_bytes: int | None = None) -> str:
        bounds.append(maximum_bytes)
        return original_sha256_file(path, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(bridge, "sha256_file", bounded_sha256)
    manifest = bridge.run_bridge(
        source,
        tmp_path / "exports",
        executable=executable,
        runner=FakeRunner((_result_table(),)),
        logger=lambda _: None,
    )
    assert manifest.successful_exports == 1
    assert bounds and set(bounds) == {bridge.MAX_SOURCE_BYTES}

    source_sha = "a" * 64
    export_sha = "b" * 64
    header = bridge.HeaderEvidence("utf-8-sig", "tab", 1, True, True, False, False, 1, 1, 1, 0, 0)
    with pytest.raises(ValueError, match="source identity"):
        bridge.ExportRecord(
            f"source-{'c' * 64}",
            source_sha,
            1,
            "success",
            None,
            True,
            f"source-{source_sha}.txt",
            export_sha,
            1,
            header,
        )
    with pytest.raises(ValueError, match="successful export"):
        bridge.ExportRecord(
            f"source-{source_sha}",
            source_sha,
            1,
            "success",
            None,
            True,
            "wrong.txt",
            export_sha,
            1,
            header,
        )
