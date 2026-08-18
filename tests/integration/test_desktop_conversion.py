# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from openpyxl import load_workbook  # type: ignore[import-untyped]

from ordifile.api import convert
from ordifile.core.models import BatchOutcome
from ordifile.desktop.models import DesktopRequest
from ordifile.desktop.services import convert_selection, inspect_selection

FIXTURE = Path("tests/fixtures/synthetic/generic_peaks.csv")


def _sheet_values(path: Path, sheet_name: str) -> list[tuple[object, ...]]:
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        return list(workbook[sheet_name].iter_rows(values_only=True))
    finally:
        workbook.close()


def test_desktop_service_discovers_folder_and_reports_detected_adapter(tmp_path: Path) -> None:
    input_folder = tmp_path / "inputs"
    input_folder.mkdir()
    (input_folder / "peaks.csv").write_bytes(FIXTURE.read_bytes())

    report = inspect_selection((input_folder,), sort="auto")

    assert report.outcome is BatchOutcome.SUCCESS
    assert len(report.files) == 1
    assert report.files[0].adapter_id == "generic_csv"
    assert "Verified" in report.files[0].format_name


def test_desktop_and_cli_api_create_equivalent_scientific_tables(tmp_path: Path) -> None:
    desktop_output = tmp_path / "desktop.xlsx"
    api_output = tmp_path / "api.xlsx"

    desktop = convert_selection(DesktopRequest((FIXTURE,), desktop_output, "input_order"))
    direct = convert((FIXTURE,), api_output, sort="input_order")

    assert desktop.outcome is BatchOutcome.SUCCESS
    assert direct.success_count == 1
    for sheet in ("Samples", "Peak_Matrix", "Peaks", "Metadata", "Import_Log"):
        assert _sheet_values(desktop_output, sheet) == _sheet_values(api_output, sheet)


def test_desktop_conversion_exposes_partial_failure_and_writes_workbook(tmp_path: Path) -> None:
    unsupported = tmp_path / "unsupported.bin"
    unsupported.write_bytes(b"not a supported input")
    output = tmp_path / "partial.xlsx"

    report = convert_selection(DesktopRequest((FIXTURE, unsupported), output))

    assert report.outcome is BatchOutcome.PARTIAL_SUCCESS
    assert report.success_count == 1
    assert report.failure_count == 1
    assert output.is_file()
    assert any(file.status.value == "Failed" for file in report.files)


def test_desktop_conversion_exposes_all_failed_without_hiding_diagnostics(
    tmp_path: Path,
) -> None:
    unsupported = tmp_path / "unsupported.bin"
    unsupported.write_bytes(b"not a supported input")
    output = tmp_path / "failed.xlsx"

    report = convert_selection(DesktopRequest((unsupported,), output))

    assert report.outcome is BatchOutcome.FAILED
    assert report.failure_count == 1
    assert report.files[0].message


def test_desktop_refuses_existing_output_without_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "existing.xlsx"
    original = b"do not replace"
    output.write_bytes(original)

    report = convert_selection(DesktopRequest((FIXTURE,), output))

    assert report.outcome is BatchOutcome.FAILED
    assert report.error_code == "OUTPUT_EXISTS"
    assert output.read_bytes() == original


def test_desktop_conversion_requires_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    output = tmp_path / "offline.xlsx"

    report = convert_selection(DesktopRequest((FIXTURE,), output))

    assert report.outcome is BatchOutcome.SUCCESS
    assert output.is_file()
