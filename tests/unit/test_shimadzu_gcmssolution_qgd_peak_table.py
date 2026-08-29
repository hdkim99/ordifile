from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

from ordifile.adapters._shimadzu_gcmssolution_qgd_peak_table import (
    MAX_PEAK_TABLE_BYTES,
    PEAK_TABLE_RECORD_BYTES,
    decode_mc_peak_table,
)
from ordifile.adapters.base import ParseOptions
from ordifile.adapters.shimadzu_gcmssolution_qgd import ShimadzuGcmssolutionQgdAdapter
from ordifile.core.models import DatasetBundle

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_shimadzu_gcmssolution_qgd import (  # noqa: E402
    synthetic_mc_peak_record,
    synthetic_mc_peak_streams,
    synthetic_qgd_bytes,
)

# The synthetic CFB builder only emits regular sectors, so the grid and the stored
# table are both sized past one sector.
_GRID = tuple(300_000 + index * 300 for index in range(1_100))
_FILLER: tuple[dict[str, object], ...] = tuple(
    {
        "retention_ms": 310_000 + index * 900,
        "start_ms": 309_700 + index * 900,
        "end_ms": 310_300 + index * 900,
        "area": 8.0,
        "height": 4.0,
        "name": b"Filler",
    }
    for index in range(18)
)
_PEAKS: tuple[dict[str, object], ...] = (
    {
        "retention_ms": 300_300,
        "start_ms": 300_000,
        "end_ms": 300_600,
        "area": 300.0,
        "height": 120.0,
        "name": b"Tetraethyl silicate",
    },
    {
        "retention_ms": 301_200,
        "start_ms": 300_900,
        "end_ms": 301_500,
        "area": 100.0,
        "height": 40.0,
        "name": b"",
    },
    *_FILLER,
)
_PEAK_COUNT = len(_PEAKS)


def _write(path: Path, **kwargs: object) -> Path:
    path.write_bytes(synthetic_qgd_bytes(retention_times_ms=_GRID, **kwargs))
    return path


def _parse(path: Path) -> DatasetBundle:
    return ShimadzuGcmssolutionQgdAdapter().parse(path, ParseOptions())


def test_absent_and_empty_tables_are_distinguished_without_failing() -> None:
    assert decode_mc_peak_table(None).status == "absent"
    assert decode_mc_peak_table(b"").status == "empty"
    assert decode_mc_peak_table(b"").peaks == ()


def test_matched_table_reports_rows_in_minutes_with_area_percent_corroboration() -> None:
    table, info = synthetic_mc_peak_streams(_PEAKS)

    decoded = decode_mc_peak_table(table, info)

    assert decoded.status == "matched"
    assert decoded.declared_count == _PEAK_COUNT
    assert decoded.area_percent_consistent
    first, second = decoded.peaks[0], decoded.peaks[1]
    assert first.retention_time == pytest.approx(300_300 / 60_000.0)
    assert first.start_time == pytest.approx(300_000 / 60_000.0)
    assert first.end_time == pytest.approx(300_600 / 60_000.0)
    assert first.area == pytest.approx(300.0)
    assert first.height == pytest.approx(120.0)
    assert first.area_percent == pytest.approx(100.0 * 300.0 / (400.0 + 18 * 8.0))
    assert first.compound == "Tetraethyl silicate"
    assert second.compound is None


def test_name_never_reads_past_its_terminator_into_stale_writer_memory() -> None:
    table, info = synthetic_mc_peak_streams(
        (dict(_PEAKS[0], name=b"Toluene", trailing_name_bytes=b"STALE-UNRELATED-SAMPLE"), *_FILLER)
    )

    decoded = decode_mc_peak_table(table, info)

    assert decoded.peaks[0].compound == "Toluene"
    assert decoded.undecodable_name_count == 0


def test_non_ascii_name_is_omitted_rather_than_guessed() -> None:
    table, info = synthetic_mc_peak_streams(
        (dict(_PEAKS[0], name=b"\x83g\x83\x8b\x83G\x83\x93"), *_FILLER)
    )

    decoded = decode_mc_peak_table(table, info)

    assert decoded.status == "matched"
    assert decoded.peaks[0].compound is None
    assert decoded.undecodable_name_count == 1


def test_area_percentages_that_do_not_normalise_the_area_column_are_reported() -> None:
    table, info = synthetic_mc_peak_streams(
        (dict(_PEAKS[0], area_percent=10.0), dict(_PEAKS[1], area_percent=20.0), *_FILLER)
    )

    decoded = decode_mc_peak_table(table, info)

    assert decoded.status == "matched"
    assert not decoded.area_percent_consistent


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"\x00" * (PEAK_TABLE_RECORD_BYTES + 1), "SHIMADZU_QGD_PEAK_TABLE_FRAMING_INVALID"),
        (b"\x00" * (MAX_PEAK_TABLE_BYTES + 1), "SHIMADZU_QGD_PEAK_TABLE_SIZE_UNSUPPORTED"),
    ],
)
def test_malformed_table_framing_fails_closed(payload: bytes, code: str) -> None:
    decoded = decode_mc_peak_table(payload)

    assert decoded.status == "invalid"
    assert decoded.issue_code == code


def test_declared_count_disagreement_fails_closed() -> None:
    table, _ = synthetic_mc_peak_streams(_PEAKS)
    info = struct.pack("<I", _PEAK_COUNT + 1) + b"\x00" * 4_092

    decoded = decode_mc_peak_table(table, info)

    assert decoded.issue_code == "SHIMADZU_QGD_PEAK_TABLE_COUNT_INVALID"


def test_row_that_does_not_contain_its_own_retention_time_fails_closed() -> None:
    record = synthetic_mc_peak_record(
        retention_ms=900,
        start_ms=100,
        end_ms=500,
        area=1.0,
        height=1.0,
        area_percent=100.0,
    )

    decoded = decode_mc_peak_table(record)

    assert decoded.issue_code == "SHIMADZU_QGD_PEAK_TABLE_BOUNDS_INVALID"


def test_out_of_order_rows_fail_closed() -> None:
    table, _ = synthetic_mc_peak_streams((_PEAKS[1], _PEAKS[0], *_FILLER))

    decoded = decode_mc_peak_table(table)

    assert decoded.issue_code == "SHIMADZU_QGD_PEAK_TABLE_ORDER_INVALID"


def test_non_finite_stored_value_fails_closed() -> None:
    record = bytearray(
        synthetic_mc_peak_record(
            retention_ms=300,
            start_ms=100,
            end_ms=500,
            area=1.0,
            height=1.0,
            area_percent=100.0,
        )
    )
    struct.pack_into("<d", record, 8, float("inf"))

    decoded = decode_mc_peak_table(bytes(record))

    assert decoded.issue_code == "SHIMADZU_QGD_PEAK_TABLE_VALUE_INVALID"


def test_adapter_emits_stored_peaks_with_an_explicit_unvalidated_disclosure(
    tmp_path: Path,
) -> None:
    source = _write(tmp_path / "peaks.qgd", mc_peaks=_PEAKS)

    bundle = _parse(source)

    assert len(bundle.peaks) == _PEAK_COUNT
    first = bundle.peaks[0]
    assert first.peak_number == 1
    assert first.retention_time_unit == "min"
    assert first.compound == "Tetraethyl silicate"
    assert first.compound_source == "source_file:shimadzu_gcmssolution_qgd.mc_peak_table.name"
    assert bundle.peaks[1].compound is None
    assert bundle.peaks[1].compound_source is None
    codes = {issue.code for issue in bundle.warnings}
    assert "SHIMADZU_QGD_STORED_PEAK_TABLE_UNVALIDATED" in codes
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["stored_peak_table_status"] == "matched"
    assert metadata["stored_peak_count"] == _PEAK_COUNT
    assert metadata["stored_peak_declared_count"] == _PEAK_COUNT
    assert metadata["stored_peak_value_validation"] == "internal_only_no_vendor_export"
    assert metadata["stored_peak_area_percent_consistent"] is True


def test_adapter_keeps_the_signal_when_the_stored_table_is_unusable(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "broken.qgd",
        mc_peaks=_PEAKS,
        mc_peak_table_override=b"\x00" * (PEAK_TABLE_RECORD_BYTES * 20 + 3),
    )

    bundle = _parse(source)

    assert bundle.peaks == ()
    assert len(bundle.signals) == 1
    codes = {issue.code for issue in bundle.warnings}
    assert "SHIMADZU_QGD_PEAK_TABLE_FRAMING_INVALID" in codes


def test_a_document_without_a_processing_storage_still_parses(tmp_path: Path) -> None:
    bundle = _parse(_write(tmp_path / "no-processing.qgd"))

    assert bundle.peaks == ()
    assert len(bundle.signals) == 1
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["stored_peak_table_status"] == "absent"
