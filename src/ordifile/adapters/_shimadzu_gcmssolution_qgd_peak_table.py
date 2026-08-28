# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded reader for the stored Shimadzu ``.QGD`` mass-chromatogram peak table.

The compound document keeps the vendor's own processed peak rows in
``GCMS Data Processing/MC Peak Table``.  Those rows are read as source-explicit
values; nothing here integrates a signal or recalculates a vendor result.

The stored values have **not** been compared against a GCMSsolution export,
because no raw/export pair is available for any fixture that carries a populated
table.  See ``docs/research/shimadzu-gcmssolution-qgd-mc-peak-table-investigation.md``
for what the field meanings were checked against instead.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

PEAK_TABLE_RECORD_BYTES = 208
MAX_PEAK_RECORDS = 10_000
MAX_PEAK_TABLE_BYTES = MAX_PEAK_RECORDS * PEAK_TABLE_RECORD_BYTES
MAX_PEAK_INFO_BYTES = 4_096

_RETENTION_OFFSET = 4
_AREA_OFFSET = 8
_HEIGHT_OFFSET = 16
_START_OFFSET = 40
_END_OFFSET = 44
_AREA_PERCENT_OFFSET = 72
_NAME_OFFSET = 80

# Bytes after the name's NUL terminator are uninitialised writer memory that can hold
# fragments of unrelated strings, so the name is never scanned past the terminator.
_NAME_LIMIT = PEAK_TABLE_RECORD_BYTES

MILLISECONDS_PER_MINUTE = 60_000.0

# The stored Area percentages are a normalisation of the stored Area column.  Every
# observed table reproduces them to floating-point noise, so the relation is checked
# as a structural invariant rather than assumed.
AREA_PERCENT_TOTAL = 100.0
_AREA_PERCENT_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class ShimadzuQgdPeak:
    """One stored vendor peak row; times are minutes, Area/Height are source values."""

    retention_time: float
    start_time: float
    end_time: float
    area: float
    height: float
    area_percent: float
    compound: str | None


@dataclass(frozen=True, slots=True)
class ShimadzuQgdPeakTable:
    """A decoded stored peak table or a bounded, capability-local failure."""

    status: str
    peaks: tuple[ShimadzuQgdPeak, ...]
    declared_count: int | None = None
    undecodable_name_count: int = 0
    area_percent_consistent: bool = False
    issue_code: str | None = None
    issue_message: str | None = None


def _invalid(code: str, message: str) -> ShimadzuQgdPeakTable:
    return ShimadzuQgdPeakTable("invalid", (), None, 0, False, code, message)


def _declared_count(info_payload: bytes | None) -> int | None:
    """Return the record count declared by ``MC Peak Info``, when it is readable."""
    if info_payload is None or len(info_payload) < 4 or len(info_payload) > MAX_PEAK_INFO_BYTES:
        return None
    return int(struct.unpack_from("<I", info_payload, 0)[0])


def _decode_name(record: bytes) -> tuple[str | None, bool]:
    """Return the stored compound name and whether its bytes were undecodable."""
    raw = record[_NAME_OFFSET:_NAME_LIMIT].split(b"\x00", 1)[0]
    if not raw:
        return None, False
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        # The stored code page is not recorded in the document, so a non-ASCII name is
        # reported as undecodable rather than guessed at.
        return None, True
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        return None, True
    stripped = text.strip()
    return (stripped or None), False


def decode_mc_peak_table(
    payload: bytes | None,
    info_payload: bytes | None = None,
) -> ShimadzuQgdPeakTable:
    """Decode the stored mass-chromatogram peak table, or report why it is unavailable."""
    if payload is None:
        return ShimadzuQgdPeakTable("absent", ())
    if not payload:
        # A file that was acquired but never integrated stores an empty table.
        return ShimadzuQgdPeakTable("empty", ())
    if len(payload) > MAX_PEAK_TABLE_BYTES:
        return _invalid(
            "SHIMADZU_QGD_PEAK_TABLE_SIZE_UNSUPPORTED",
            "The stored peak table exceeds the bounded reader size.",
        )
    if len(payload) % PEAK_TABLE_RECORD_BYTES:
        return _invalid(
            "SHIMADZU_QGD_PEAK_TABLE_FRAMING_INVALID",
            "The stored peak table is not a whole number of validated records.",
        )
    count = len(payload) // PEAK_TABLE_RECORD_BYTES
    declared = _declared_count(info_payload)
    if declared is not None and declared != count:
        return _invalid(
            "SHIMADZU_QGD_PEAK_TABLE_COUNT_INVALID",
            "The stored peak count disagrees with the stored peak-table length.",
        )

    peaks: list[ShimadzuQgdPeak] = []
    undecodable_names = 0
    previous_retention = -1
    for index in range(count):
        base = index * PEAK_TABLE_RECORD_BYTES
        record = payload[base : base + PEAK_TABLE_RECORD_BYTES]
        retention_ms = struct.unpack_from("<i", record, _RETENTION_OFFSET)[0]
        start_ms = struct.unpack_from("<i", record, _START_OFFSET)[0]
        end_ms = struct.unpack_from("<i", record, _END_OFFSET)[0]
        area = struct.unpack_from("<d", record, _AREA_OFFSET)[0]
        height = struct.unpack_from("<d", record, _HEIGHT_OFFSET)[0]
        area_percent = struct.unpack_from("<d", record, _AREA_PERCENT_OFFSET)[0]
        if not 0 <= start_ms <= retention_ms <= end_ms:
            return _invalid(
                "SHIMADZU_QGD_PEAK_TABLE_BOUNDS_INVALID",
                "A stored peak row does not contain its own retention time.",
            )
        if retention_ms < previous_retention:
            return _invalid(
                "SHIMADZU_QGD_PEAK_TABLE_ORDER_INVALID",
                "Stored peak rows are not in source retention order.",
            )
        previous_retention = retention_ms
        if not (math.isfinite(area) and math.isfinite(height) and math.isfinite(area_percent)):
            return _invalid(
                "SHIMADZU_QGD_PEAK_TABLE_VALUE_INVALID",
                "A stored peak row carries a non-finite Area, Height, or Area percentage.",
            )
        compound, undecodable = _decode_name(record)
        undecodable_names += undecodable
        peaks.append(
            ShimadzuQgdPeak(
                retention_ms / MILLISECONDS_PER_MINUTE,
                start_ms / MILLISECONDS_PER_MINUTE,
                end_ms / MILLISECONDS_PER_MINUTE,
                area,
                height,
                area_percent,
                compound,
            )
        )

    area_total = math.fsum(peak.area for peak in peaks)
    percent_total = math.fsum(peak.area_percent for peak in peaks)
    consistent = abs(percent_total - AREA_PERCENT_TOTAL) <= _AREA_PERCENT_TOLERANCE and (
        area_total > 0
        and all(
            abs(AREA_PERCENT_TOTAL * peak.area / area_total - peak.area_percent)
            <= _AREA_PERCENT_TOLERANCE
            for peak in peaks
        )
    )
    return ShimadzuQgdPeakTable(
        "matched",
        tuple(peaks),
        declared,
        undecodable_names,
        consistent,
    )
