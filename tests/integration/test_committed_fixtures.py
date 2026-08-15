from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

from openpyxl import load_workbook  # type: ignore[import-untyped]

from labconvert.api import convert, inspect_file

FIXTURES = Path(__file__).parents[1] / "fixtures" / "synthetic"
EXAMPLES = Path(__file__).parents[2] / "examples" / "basic"
EXPECTED_XLSX_SHA256 = "fb3a739e28efab6d2ff8abee31362f1b757e447738d7ca636d2a157fa6984591"


def test_committed_xlsx_checksum_matches_fixture_documentation() -> None:
    fixture = FIXTURES / "generic_peaks.xlsx"
    actual = hashlib.sha256(fixture.read_bytes()).hexdigest()
    documentation = (FIXTURES / "README.md").read_text(encoding="utf-8")

    assert actual == EXPECTED_XLSX_SHA256
    assert f"generic_peaks.xlsx  {EXPECTED_XLSX_SHA256}" in documentation


def test_xlsx_generator_reproduces_committed_fixture_bytes(tmp_path: Path) -> None:
    fixture = FIXTURES / "generic_peaks.xlsx"
    generated = tmp_path / "generated" / "generic_peaks.xlsx"

    subprocess.run(
        [
            sys.executable,
            str(FIXTURES / "generate_xlsx.py"),
            "--output",
            str(generated),
        ],
        check=True,
    )

    generated_bytes = generated.read_bytes()
    assert generated_bytes == fixture.read_bytes()
    assert hashlib.sha256(generated_bytes).hexdigest() == EXPECTED_XLSX_SHA256
    with zipfile.ZipFile(generated) as archive:
        members = archive.infolist()
        assert [member.filename for member in members] == sorted(
            member.filename for member in members
        )
        assert all(member.compress_type == zipfile.ZIP_STORED for member in members)
        assert all(member.date_time == (2026, 1, 1, 0, 0, 0) for member in members)
        assert all(member.create_system == 3 for member in members)
        assert all(member.external_attr == 0o600 << 16 for member in members)


def test_committed_synthetic_fixtures_match_verified_support() -> None:
    expected = {
        "generic_peaks.csv": "generic_csv",
        "generic_peaks.tsv": "generic_tsv",
        "generic_peaks_semicolon.txt": "generic_semicolon",
        "generic_peaks.xlsx": "generic_xlsx",
    }
    for name, adapter_id in expected.items():
        inspected = inspect_file(FIXTURES / name)
        assert inspected.file.adapter_id == adapter_id
        assert inspected.file.bundle is not None
        assert len(inspected.file.bundle.peaks) == 2
        assert len(inspected.file.bundle.signals) == 1


def test_committed_fixtures_convert_to_one_ordered_workbook(tmp_path: Path) -> None:
    inputs = tuple(
        FIXTURES / name
        for name in (
            "generic_peaks.xlsx",
            "generic_peaks_semicolon.txt",
            "generic_peaks.tsv",
            "generic_peaks.csv",
        )
    )
    result = convert(inputs, tmp_path / "fixtures.xlsx", include_signals=True)
    assert result.success_count == 4
    assert result.failure_count == 0
    assert result.sort.effective.value == "acquired_at"

    workbook = load_workbook(result.output_path, read_only=True, data_only=False)
    try:
        samples = list(workbook["Samples"].values)
        sample_id_column = samples[0].index("sample_id")
        assert [row[sample_id_column] for row in samples[1:]] == [
            "synthetic_csv",
            "synthetic_tsv",
            "synthetic_txt",
            "synthetic_xlsx",
        ]
        assert any(name.startswith("Signals_FID") for name in workbook.sheetnames)
    finally:
        workbook.close()


def test_basic_example_demonstrates_natural_filename_sort(tmp_path: Path) -> None:
    result = convert(EXAMPLES, tmp_path / "example.xlsx", sort="filename")
    assert result.success_count == 3
    assert result.sort.effective.value == "filename"

    workbook = load_workbook(result.output_path, read_only=True, data_only=False)
    try:
        samples = list(workbook["Samples"].values)
        source_file_column = samples[0].index("source_file")
        assert [row[source_file_column] for row in samples[1:]] == [
            "sample_1.csv",
            "sample_2.csv",
            "sample_10.csv",
        ]
    finally:
        workbook.close()
