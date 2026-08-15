from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook  # type: ignore[import-untyped]

from ordifile.api import convert
from ordifile.core.errors import ExportLimitError
from ordifile.exporters import excel


def _peak_file(path: Path, rows: int) -> None:
    content = ["sample_id,retention_time,area,compound"]
    content.extend(f"sample,{index},{index * 10},C{index}" for index in range(rows))
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


def test_row_heavy_sheets_split_without_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(excel, "MAX_EXCEL_ROWS", 4)
    source = tmp_path / "peaks.csv"
    _peak_file(source, 8)
    output = tmp_path / "result.xlsx"
    result = convert(source, output)
    peak_sheets = [name for name in result.sheets if name.startswith("Peaks")]
    assert peak_sheets == ["Peaks", "Peaks_002", "Peaks_003"]
    workbook = load_workbook(output, read_only=True, data_only=False)
    try:
        count = sum(max(workbook[name].max_row - 1, 0) for name in peak_sheets)
        assert count == 8
    finally:
        workbook.close()


def test_peak_matrix_columns_split_and_preserve_occurrences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = excel._SheetData(
        "Peak_Matrix",
        ("sample_id", "A", "A_2", "B", "C"),
        (("sample", 1, 2, 3, 4),),
    )
    monkeypatch.setattr(excel, "MAX_EXCEL_COLUMNS", 3)
    segments = excel._column_segments(dataset)
    assert [item.headers for item in segments] == [
        ("sample_id", "A", "A_2"),
        ("sample_id", "B", "C"),
    ]
    assert segments[0].rows[0] == ("sample", 1, 2)


def test_impractical_sheet_plan_requires_explicit_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(excel, "MAX_EXCEL_ROWS", 3)
    monkeypatch.setattr(excel, "MAX_WORKBOOK_SHEETS", 6)
    source = tmp_path / "peaks.csv"
    _peak_file(source, 8)
    with pytest.raises(ExportLimitError) as caught:
        convert(source, tmp_path / "error.xlsx")
    assert caught.value.code == "WORKBOOK_SHEET_LIMIT"

    result = convert(source, tmp_path / "sidecar.xlsx", sidecar_mode="csv")
    assert result.sidecars
    for record in result.sidecars:
        path = tmp_path / record.relative_path
        assert path.exists()
        assert len(record.sha256) == 64
    workbook = load_workbook(result.output_path, read_only=True, data_only=False)
    try:
        manifest_rows = [
            row
            for name in workbook.sheetnames
            if name.startswith("Manifest")
            for row in workbook[name].values
        ]
        assert any(row[0] == "sidecar" and row[2] for row in manifest_rows)
    finally:
        workbook.close()
