from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

from ordifile.adapters._shimadzu_gcsolution_gcd_peak_table import (
    PEAK_TABLE_HEADER_BYTES,
    PEAK_TABLE_RECORD_BYTES,
    decode_peak_table,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))

from generate_shimadzu_gcsolution_gcd import synthetic_peak_table  # noqa: E402

ROWS = (
    (110_580, 106_440, 112_560, 2042.3048071317419, 505.024730795506),
    (115_560, 112_560, 119_880, 2333.0625, 369.5),
)


def test_stored_rows_decode_as_minutes_and_source_values() -> None:
    table = decode_peak_table(synthetic_peak_table(ROWS))

    assert table.status == "matched"
    assert table.revision_byte == 0x53
    assert len(table.peaks) == 2
    first = table.peaks[0]
    assert first.retention_time == pytest.approx(110_580 / 60_000)
    assert first.start_time == pytest.approx(106_440 / 60_000)
    assert first.end_time == pytest.approx(112_560 / 60_000)
    # The stored value keeps every digit the vendor's own text export rounds away.
    assert first.area == 2042.3048071317419
    assert first.height == 505.024730795506


def test_absent_stream_is_reported_without_failing() -> None:
    table = decode_peak_table(None)

    assert table.status == "absent"
    assert table.peaks == ()
    assert table.issue_code is None


def test_empty_table_is_valid_and_carries_no_rows() -> None:
    table = decode_peak_table(synthetic_peak_table(()))

    assert table.status == "matched"
    assert table.peaks == ()


def test_negative_stored_peaks_are_preserved() -> None:
    # Stored negative peaks occur in the controlled corpus and are not a failure.
    table = decode_peak_table(synthetic_peak_table(((1_000, 500, 1_500, -168.066, -7.542),)))

    assert table.status == "matched"
    assert table.peaks[0].area == -168.066
    assert table.peaks[0].height == -7.542


@pytest.mark.parametrize("revision", (0x02, 0x04, 0x05, 0x06, 0x07, 0x53))
def test_every_observed_processing_revision_is_accepted(revision: int) -> None:
    table = decode_peak_table(synthetic_peak_table(ROWS, revision=revision))

    assert table.status == "matched"
    assert table.revision_byte == revision


def test_unobserved_revision_fails_closed() -> None:
    table = decode_peak_table(synthetic_peak_table(ROWS, revision=0x11))

    assert table.status == "invalid"
    assert table.issue_code == "SHIMADZU_GCD_PEAK_TABLE_REVISION_UNSUPPORTED"


def test_unexpected_header_identity_fails_closed() -> None:
    payload = b"VXR1" + bytes(16) + bytes(PEAK_TABLE_RECORD_BYTES)

    table = decode_peak_table(payload)

    assert table.status == "invalid"
    assert table.issue_code == "SHIMADZU_GCD_PEAK_TABLE_HEADER_INVALID"


def test_reserved_header_bytes_must_stay_zero() -> None:
    table = decode_peak_table(synthetic_peak_table(ROWS, header_tail=bytes(14) + b"\x01"))

    assert table.status == "invalid"
    assert table.issue_code == "SHIMADZU_GCD_PEAK_TABLE_HEADER_INVALID"


def test_partial_record_framing_fails_closed() -> None:
    table = decode_peak_table(synthetic_peak_table(ROWS)[:-1])

    assert table.status == "invalid"
    assert table.issue_code == "SHIMADZU_GCD_PEAK_TABLE_FRAMING_INVALID"


def test_row_that_does_not_contain_its_retention_time_fails_closed() -> None:
    table = decode_peak_table(synthetic_peak_table(((1_000, 1_200, 1_500, 1.0, 1.0),)))

    assert table.status == "invalid"
    assert table.issue_code == "SHIMADZU_GCD_PEAK_TABLE_BOUNDS_INVALID"


def test_rows_out_of_source_retention_order_fail_closed() -> None:
    rows = ((2_000, 1_900, 2_100, 1.0, 1.0), (1_000, 900, 1_100, 1.0, 1.0))

    table = decode_peak_table(synthetic_peak_table(rows))

    assert table.status == "invalid"
    assert table.issue_code == "SHIMADZU_GCD_PEAK_TABLE_ORDER_INVALID"


def test_non_finite_area_fails_closed() -> None:
    payload = bytearray(synthetic_peak_table(ROWS))
    struct.pack_into("<d", payload, PEAK_TABLE_HEADER_BYTES + 8, float("nan"))

    table = decode_peak_table(bytes(payload))

    assert table.status == "invalid"
    assert table.issue_code == "SHIMADZU_GCD_PEAK_TABLE_VALUE_INVALID"


def test_oversized_table_fails_closed() -> None:
    table = decode_peak_table(b"VER1" + bytes(16) + bytes(20_000 * PEAK_TABLE_RECORD_BYTES))

    assert table.status == "invalid"
    assert table.issue_code == "SHIMADZU_GCD_PEAK_TABLE_SIZE_UNSUPPORTED"
