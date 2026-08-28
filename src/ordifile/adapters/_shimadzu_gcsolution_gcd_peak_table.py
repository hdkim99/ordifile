# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded reader for the stored Shimadzu ``.GCD`` peak table.

The compound document keeps the vendor's own processed peak rows in a
``LSS Data Processing/PT-*`` stream.  Those rows are read as source-explicit
values; nothing here integrates a signal or recalculates a vendor result.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass

PEAK_TABLE_STORAGE = "LSS Data Processing"
PEAK_TABLE_NAME_PATTERN = re.compile(r"PT-[A-Za-z0-9.\-]{1,64}\Z")

PEAK_TABLE_MAGIC = b"VER1"
# The byte after the magic changes between observed processing revisions while the record
# layout below stays identical.  Only the observed values are accepted.
OBSERVED_REVISION_BYTES = frozenset({0x02, 0x04, 0x05, 0x06, 0x07, 0x53})
PEAK_TABLE_HEADER_BYTES = 20
PEAK_TABLE_RECORD_BYTES = 792
MAX_PEAK_RECORDS = 10_000
MAX_PEAK_TABLE_BYTES = PEAK_TABLE_HEADER_BYTES + MAX_PEAK_RECORDS * PEAK_TABLE_RECORD_BYTES

_RETENTION_OFFSET = 4
_AREA_OFFSET = 8
_HEIGHT_OFFSET = 24
_START_OFFSET = 56
_END_OFFSET = 60

MILLISECONDS_PER_MINUTE = 60_000.0


@dataclass(frozen=True, slots=True)
class ShimadzuGcdPeak:
    """One stored vendor peak row; times are minutes, Area/Height are source values."""

    retention_time: float
    start_time: float
    end_time: float
    area: float
    height: float


@dataclass(frozen=True, slots=True)
class ShimadzuGcdPeakTable:
    """A decoded stored peak table or a bounded, capability-local failure."""

    status: str
    peaks: tuple[ShimadzuGcdPeak, ...]
    revision_byte: int | None = None
    issue_code: str | None = None
    issue_message: str | None = None


def _invalid(code: str, message: str) -> ShimadzuGcdPeakTable:
    return ShimadzuGcdPeakTable("invalid", (), None, code, message)


def decode_peak_table(payload: bytes | None) -> ShimadzuGcdPeakTable:
    """Decode the stored peak table, or report why it is unavailable."""
    if payload is None:
        return ShimadzuGcdPeakTable("absent", ())
    if len(payload) > MAX_PEAK_TABLE_BYTES:
        return _invalid(
            "SHIMADZU_GCD_PEAK_TABLE_SIZE_UNSUPPORTED",
            "The stored peak table exceeds the bounded reader size.",
        )
    if len(payload) < PEAK_TABLE_HEADER_BYTES or not payload.startswith(PEAK_TABLE_MAGIC):
        return _invalid(
            "SHIMADZU_GCD_PEAK_TABLE_HEADER_INVALID",
            "The stored peak table lacks its validated header identity.",
        )
    revision = payload[len(PEAK_TABLE_MAGIC)]
    if revision not in OBSERVED_REVISION_BYTES:
        return _invalid(
            "SHIMADZU_GCD_PEAK_TABLE_REVISION_UNSUPPORTED",
            "The stored peak table reports an unobserved processing revision.",
        )
    if any(payload[index] for index in range(len(PEAK_TABLE_MAGIC) + 1, PEAK_TABLE_HEADER_BYTES)):
        return _invalid(
            "SHIMADZU_GCD_PEAK_TABLE_HEADER_INVALID",
            "The stored peak-table header carries unobserved reserved bytes.",
        )
    body = len(payload) - PEAK_TABLE_HEADER_BYTES
    if body % PEAK_TABLE_RECORD_BYTES:
        return _invalid(
            "SHIMADZU_GCD_PEAK_TABLE_FRAMING_INVALID",
            "The stored peak table is not a whole number of validated records.",
        )
    count = body // PEAK_TABLE_RECORD_BYTES
    if count > MAX_PEAK_RECORDS:
        return _invalid(
            "SHIMADZU_GCD_PEAK_TABLE_SIZE_UNSUPPORTED",
            "The stored peak table exceeds the bounded record count.",
        )

    peaks: list[ShimadzuGcdPeak] = []
    previous_retention = -1
    for index in range(count):
        base = PEAK_TABLE_HEADER_BYTES + index * PEAK_TABLE_RECORD_BYTES
        retention_ms = struct.unpack_from("<i", payload, base + _RETENTION_OFFSET)[0]
        start_ms = struct.unpack_from("<i", payload, base + _START_OFFSET)[0]
        end_ms = struct.unpack_from("<i", payload, base + _END_OFFSET)[0]
        area = struct.unpack_from("<d", payload, base + _AREA_OFFSET)[0]
        height = struct.unpack_from("<d", payload, base + _HEIGHT_OFFSET)[0]
        if not 0 <= start_ms <= retention_ms <= end_ms:
            return _invalid(
                "SHIMADZU_GCD_PEAK_TABLE_BOUNDS_INVALID",
                "A stored peak row does not contain its own retention time.",
            )
        if retention_ms < previous_retention:
            return _invalid(
                "SHIMADZU_GCD_PEAK_TABLE_ORDER_INVALID",
                "Stored peak rows are not in source retention order.",
            )
        previous_retention = retention_ms
        # Negative Area and Height occur for stored negative peaks and are preserved.
        if not math.isfinite(area) or not math.isfinite(height):
            return _invalid(
                "SHIMADZU_GCD_PEAK_TABLE_VALUE_INVALID",
                "A stored peak row carries a non-finite Area or Height.",
            )
        peaks.append(
            ShimadzuGcdPeak(
                retention_ms / MILLISECONDS_PER_MINUTE,
                start_ms / MILLISECONDS_PER_MINUTE,
                end_ms / MILLISECONDS_PER_MINUTE,
                area,
                height,
            )
        )
    return ShimadzuGcdPeakTable("matched", tuple(peaks), revision)
