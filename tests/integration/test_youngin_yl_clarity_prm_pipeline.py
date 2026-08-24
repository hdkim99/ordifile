from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook  # type: ignore[import-untyped]

from ordifile.api import convert, inspect_file
from ordifile.cli.main import main

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_youngin_yl_clarity_prm import synthetic_prm_bytes  # noqa: E402


def test_inspect_and_cli_report_decoded_records_not_scientific_signals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "FID_STD_001.prm"
    source.write_bytes(synthetic_prm_bytes())

    inspected = inspect_file(source)
    assert inspected.file.adapter_id == "youngin_yl_clarity_prm_raw"
    assert inspected.file.source.detected_format == "youngin_yl_clarity_prm_raw"
    assert {issue.code for issue in inspected.file.issues} >= {
        "YOUNGIN_PRM_EXPERIMENTAL_RAW_RECORDS"
    }

    assert main(["inspect", str(source)]) == 0
    output = capsys.readouterr().out
    assert "Scientific signals: 0" in output
    assert "Decoded record series: 1" in output
    assert "Exact profile: YL-Clarity 9.0.1.19 observed PRM raw profile" in output
    assert "Channels: 1" in output
    assert "Scientific signal available: No" in output
    assert "Retention-time unit: not available" in output
    assert "Signal units: not available" in output
    assert "Peak Result availability: unsupported" in output


def test_inspect_and_cli_report_validated_9_1_scientific_signals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "scientific.prm"
    source.write_bytes(
        synthetic_prm_bytes(
            producer_text="YL-Clarity 9.1.0.76 FULL, SN: SYNTHETIC",
            channels=((1.0, 2.0), (3.0, 4.0)),
        )
    )

    inspected = inspect_file(source)
    assert inspected.file.adapter_id == "youngin_yl_clarity_prm_raw"
    assert {issue.code for issue in inspected.file.issues} >= {
        "YOUNGIN_PRM_EXPERIMENTAL_SCIENTIFIC_SIGNAL"
    }

    assert main(["inspect", str(source)]) == 0
    output = capsys.readouterr().out
    assert "Scientific signals: 2" in output
    assert "Decoded record series: 0" in output
    assert "Exact profile: YL-Clarity 9.1.0.76 observed PRM scientific-signal profile" in output
    assert "Channels: 2" in output
    assert "Scientific signal available: Yes" in output
    assert "Retention-time unit: min" in output
    assert "Signal units: FID=pA, TCD=mV" in output
    assert "Scientific signal points: 4" in output
    assert "Peak Result availability: unsupported" in output


def test_valid_and_corrupt_prm_batch_isolated_and_workbook_reopens(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    first_data = synthetic_prm_bytes(channels=((1.0, 2.0, 3.0),))
    second_data = synthetic_prm_bytes(channels=((10.0, 20.0),))
    third_data = synthetic_prm_bytes(channels=((5.0,), (6.0, 7.0)))
    (inputs / "FID_STD_001.prm").write_bytes(first_data)
    (inputs / "TCD_STD_001.prm").write_bytes(second_data)
    (inputs / "MIXED_SAMPLE_001.prm").write_bytes(third_data)
    (inputs / "FID_STD_002.prm").write_bytes(synthetic_prm_bytes()[:-21])
    output = tmp_path / "result.xlsx"

    result = convert(inputs, output, extensions=(".prm",), include_signals=True)

    assert result.success_count == 3
    assert result.failure_count == 1
    assert output.is_file()
    workbook = load_workbook(output, read_only=True, data_only=False)
    try:
        fid_rows = list(workbook["Signals_Records_native_label_FI"].values)
        tcd_rows = list(workbook["Signals_Records_native_label_TC"].values)
        assert fid_rows[0][-1] == "series_kind"
        assert len(fid_rows) - 1 == 1
        assert len(tcd_rows) - 1 == 7
        assert [row[7] for row in fid_rows[1:]] == [5.0]
        assert {row[-1] for row in fid_rows[1:] + tcd_rows[1:]} == {"decoded_records"}
        samples = list(workbook["Samples"].iter_rows(min_row=2, values_only=True))
        assert {row[1] for row in samples if row[12] != "failed"} == {
            f"PRM_{hashlib.sha256(first_data).hexdigest()[:16]}",
            f"PRM_{hashlib.sha256(second_data).hexdigest()[:16]}",
            f"PRM_{hashlib.sha256(third_data).hexdigest()[:16]}",
        }
        metadata = list(workbook["Metadata"].iter_rows(min_row=2, values_only=True))
        assert not any(row[3] == "user_supplied_group" for row in metadata)
        import_log = list(workbook["Import_Log"].iter_rows(min_row=2, values_only=True))
        assert {row[4] for row in import_log} == {"warning", "failed"}
        assert all(row[9] for row in import_log)
    finally:
        workbook.close()


def test_workbook_does_not_expose_ignored_embedded_metadata(tmp_path: Path) -> None:
    source = tmp_path / "FID_STD_001.prm"
    private_marker = "PRIVATE_OPERATOR_AND_LOCAL_PATH"
    source.write_bytes(synthetic_prm_bytes(embedded_private_text=private_marker.encode("utf-8")))
    output = tmp_path / "privacy.xlsx"

    convert(source, output, include_signals=True)
    workbook = load_workbook(output, read_only=True, data_only=False)
    try:
        assert not any(
            private_marker in str(value)
            for sheet in workbook.worksheets
            for row in sheet.iter_rows(values_only=True)
            for value in row
            if value is not None
        )
    finally:
        workbook.close()


def test_validated_9_1_profile_writes_scientific_signal_sheets(tmp_path: Path) -> None:
    source = tmp_path / "scientific.prm"
    source.write_bytes(
        synthetic_prm_bytes(
            producer_text="YL-Clarity 9.1.0.76 FULL, SN: SYNTHETIC",
            channels=((1.0, 2.0), (3.0, 4.0)),
        )
    )
    output = tmp_path / "scientific.xlsx"

    result = convert(source, output, include_signals=True)

    assert result.success_count == 1
    workbook = load_workbook(output, read_only=True, data_only=False)
    try:
        assert "Signals_FID" in workbook.sheetnames
        assert "Signals_TCD" in workbook.sheetnames
        assert not any(name.startswith("Signals_Records_") for name in workbook.sheetnames)
        fid_rows = list(workbook["Signals_FID"].values)
        tcd_rows = list(workbook["Signals_TCD"].values)
        assert fid_rows[0] == (
            "sample_id",
            "source_file",
            "channel",
            "detector",
            "x",
            "x_label",
            "x_unit",
            "y",
            "y_label",
            "y_unit",
        )
        assert {row[2] for row in fid_rows[1:]} == {"native_label_FID"}
        assert {row[3] for row in fid_rows[1:]} == {"FID"}
        assert {row[5] for row in fid_rows[1:]} == {"retention_time"}
        assert {row[6] for row in fid_rows[1:]} == {"min"}
        assert {row[8] for row in fid_rows[1:]} == {"detector_response"}
        assert [row[9] for row in fid_rows[1:]] == ["pA", "pA"]
        assert [row[9] for row in tcd_rows[1:]] == ["mV", "mV"]
        assert [row[4] for row in fid_rows[1:]] == pytest.approx([0.0, 1 / 600])
        metadata = {
            row[3]: row[4] for row in workbook["Metadata"].iter_rows(min_row=2, values_only=True)
        }
        assert metadata["representation"] == "scientific_signal"
        assert metadata["producer_version"] == "YL-Clarity 9.1.0.76"
        assert metadata["peak_table_status"] == "unsupported"
        import_log = list(workbook["Import_Log"].iter_rows(min_row=2, values_only=True))
        assert import_log[0][2] == "youngin_yl_clarity_prm_raw"
        assert "YOUNGIN_PRM_EXPERIMENTAL_SCIENTIFIC_SIGNAL" in import_log[0][5]
        assert "Peaks" in workbook.sheetnames
        assert list(workbook["Peaks"].iter_rows(min_row=2, values_only=True)) == []
    finally:
        workbook.close()
