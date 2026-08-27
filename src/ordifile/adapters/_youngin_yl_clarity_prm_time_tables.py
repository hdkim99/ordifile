# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded reader for current-history YL-Clarity PRM processing tables.

Numeric operation codes are preserved as observed data.  This module deliberately does
not assign vendor operation names that are absent from the public format evidence.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from pathlib import Path

from ordifile.adapters._youngin_yl_clarity_prm_binary import PrmCurrentRevisionLayout

PEAK_WIDTH_KEY = b"\x09PeakWidth\x02"
INT_TYPE_KEY = b"\x07IntType\x01"
UTF16_VALUE_PREFIX = bytes.fromhex("fffeff")
DEFAULT_EVENT_OPCODES = (50, 51, 65, 72, 46, 47)
OBSERVED_OPTIONAL_OPCODES = frozenset({11, 12, 32})

MAX_PRM_FILE_BYTES = 16 * 1024 * 1024
TABLE_SLOT_COUNT = 32
MAX_EVENTS_PER_TABLE = 1_024


@dataclass(frozen=True, slots=True)
class PrmTimedEvent:
    """One source-ordered opaque processing event."""

    source_order: int
    opcode: int
    a_time: float
    b_time: float
    text: str
    value: float
    group: int
    group_text: str
    guid: str


@dataclass(frozen=True, slots=True)
class PrmTimeTable:
    """One numbered non-GPC processing table."""

    slot_number: int
    events: tuple[PrmTimedEvent, ...]
    payload_sha256: str


@dataclass(frozen=True, slots=True)
class PrmCurrentMethod:
    """Optional current-history method capability."""

    status: str
    integration_type: int | None
    tables: tuple[PrmTimeTable, ...]
    method_span_sha256: str | None = None
    issue_code: str | None = None
    issue_message: str | None = None


class _DecodeError(Exception):
    pass


def _invalid(code: str, message: str) -> PrmCurrentMethod:
    return PrmCurrentMethod("invalid", None, (), None, code, message)


def _find_all(data: bytes, marker: bytes, *, start: int, end: int) -> tuple[int, ...]:
    offsets: list[int] = []
    cursor = start
    while True:
        offset = data.find(marker, cursor, end)
        if offset < 0:
            return tuple(offsets)
        offsets.append(offset)
        cursor = offset + 1


def _framed_text(value: str) -> bytes:
    if len(value) > 255:
        raise ValueError("bounded table name is too long")
    return UTF16_VALUE_PREFIX + bytes((len(value),)) + value.encode("utf-16-le")


def _read_u32(data: bytes, cursor: int, boundary: int) -> tuple[int, int]:
    if cursor + 4 > boundary:
        raise _DecodeError
    return int(struct.unpack_from("<I", data, cursor)[0]), cursor + 4


def _read_typed_value(
    data: bytes,
    cursor: int,
    boundary: int,
    *,
    name: str,
    value_type: int,
    size: int,
) -> tuple[bytes, int]:
    key = bytes((len(name),)) + name.encode("ascii") + bytes((value_type,))
    if data[cursor : cursor + len(key)] != key or cursor + len(key) + size > boundary:
        raise _DecodeError
    start = cursor + len(key)
    return data[start : start + size], start + size


def _read_text_value(data: bytes, cursor: int, boundary: int, *, name: str) -> tuple[str, int]:
    key = bytes((len(name),)) + name.encode("ascii") + b"\x03"
    prefix_end = cursor + len(key) + len(UTF16_VALUE_PREFIX)
    if (
        data[cursor : cursor + len(key)] != key
        or prefix_end >= boundary
        or data[cursor + len(key) : prefix_end] != UTF16_VALUE_PREFIX
    ):
        raise _DecodeError
    character_count = data[prefix_end]
    value_start = prefix_end + 1
    value_end = value_start + character_count * 2
    if value_end > boundary:
        raise _DecodeError
    try:
        value = data[value_start:value_end].decode("utf-16-le", errors="strict")
    except UnicodeDecodeError as error:
        raise _DecodeError from error
    return value, value_end


def _parse_table(
    data: bytes,
    *,
    start: int,
    boundary: int,
    table_name: str,
    slot_number: int,
) -> tuple[PrmTimeTable, int]:
    cursor = start + len(_framed_text(table_name))
    event_count, cursor = _read_u32(data, cursor, boundary)
    if event_count < 1 or event_count > MAX_EVENTS_PER_TABLE:
        raise _DecodeError
    first_item, cursor = _read_u32(data, cursor, boundary)
    if first_item != 1:
        raise _DecodeError

    events: list[PrmTimedEvent] = []
    for item_number in range(1, event_count + 1):
        item_frame = _framed_text(f"Item{item_number}")
        if data[cursor : cursor + len(item_frame)] != item_frame:
            raise _DecodeError
        cursor += len(item_frame)
        object_version, cursor = _read_u32(data, cursor, boundary)
        property_count, cursor = _read_u32(data, cursor, boundary)
        if object_version != 0 or property_count != 8:
            raise _DecodeError

        encoded, cursor = _read_typed_value(
            data, cursor, boundary, name="OpCode", value_type=1, size=4
        )
        opcode = int(struct.unpack("<I", encoded)[0])
        encoded, cursor = _read_typed_value(
            data, cursor, boundary, name="ATime", value_type=2, size=8
        )
        a_time = float(struct.unpack("<d", encoded)[0])
        encoded, cursor = _read_typed_value(
            data, cursor, boundary, name="BTime", value_type=2, size=8
        )
        b_time = float(struct.unpack("<d", encoded)[0])
        text, cursor = _read_text_value(data, cursor, boundary, name="Text")
        encoded, cursor = _read_typed_value(
            data, cursor, boundary, name="Group", value_type=1, size=4
        )
        group = int(struct.unpack("<I", encoded)[0])
        group_text, cursor = _read_text_value(data, cursor, boundary, name="GroupStr")
        encoded, cursor = _read_typed_value(
            data, cursor, boundary, name="Value", value_type=2, size=8
        )
        value = float(struct.unpack("<d", encoded)[0])
        guid, cursor = _read_text_value(data, cursor, boundary, name="GUID")
        if not all(math.isfinite(candidate) for candidate in (a_time, b_time, value)):
            raise _DecodeError
        events.append(
            PrmTimedEvent(
                item_number,
                opcode,
                a_time,
                b_time,
                text,
                value,
                group,
                group_text,
                guid,
            )
        )

    if data.find(b"\x06OpCode\x01", cursor, boundary) >= 0:
        raise _DecodeError
    return (
        PrmTimeTable(
            slot_number,
            tuple(events),
            hashlib.sha256(data[start:cursor]).hexdigest(),
        ),
        cursor,
    )


def read_prm_time_tables(
    path: Path,
    *,
    expected_sha256: str,
    layout: PrmCurrentRevisionLayout,
    history_count: int,
) -> PrmCurrentMethod:
    """Decode exact current-history table framing without affecting raw Signals."""
    try:
        size = path.stat().st_size
        if size > MAX_PRM_FILE_BYTES:
            return _invalid(
                "YOUNGIN_PRM_TIME_TABLE_FILE_SIZE_UNSUPPORTED",
                "The source exceeds the bounded PRM processing-table reader size.",
            )
        data = path.read_bytes()
    except OSError:
        return _invalid(
            "YOUNGIN_PRM_TIME_TABLE_READ_FAILED",
            "The optional PRM processing tables could not be read.",
        )
    if len(data) != size or hashlib.sha256(data).hexdigest() != expected_sha256:
        return _invalid(
            "YOUNGIN_PRM_TIME_TABLE_SOURCE_CHANGED",
            "The source changed between structural and processing-table decoding.",
        )
    method_end = layout.detector_count_offset
    if (
        history_count < 1
        or method_end <= 0
        or method_end > layout.revision_body_start
        or layout.revision_header_start > method_end
    ):
        return _invalid(
            "YOUNGIN_PRM_TIME_TABLE_LAYOUT_INVALID",
            "The structural parser did not provide a valid current method boundary.",
        )

    peak_width_offsets = _find_all(data, PEAK_WIDTH_KEY, start=0, end=method_end)
    if len(peak_width_offsets) != history_count:
        return PrmCurrentMethod(
            "absent" if not peak_width_offsets else "invalid",
            None,
            (),
            None,
            None if not peak_width_offsets else "YOUNGIN_PRM_TIME_TABLE_HISTORY_INVALID",
            None
            if not peak_width_offsets
            else "Processing-table history does not match the structural history count.",
        )
    method_start = peak_width_offsets[-1]
    if method_start >= layout.revision_header_start:
        return _invalid(
            "YOUNGIN_PRM_TIME_TABLE_LAYOUT_INVALID",
            "The current processing-table span does not precede its integration header.",
        )

    expected_names = tuple(
        name
        for slot in range(1, TABLE_SLOT_COUNT + 1)
        for name in (f"TimeTable{slot}", f"GPCTimeTable{slot}")
    )
    positions: list[int] = []
    for name in expected_names:
        matches = _find_all(data, _framed_text(name), start=method_start, end=method_end)
        if len(matches) != 1:
            return _invalid(
                "YOUNGIN_PRM_TIME_TABLE_STRUCTURE_INVALID",
                "The current method lacks one exact ordered processing-table set.",
            )
        positions.append(matches[0])
    if positions != sorted(positions):
        return _invalid(
            "YOUNGIN_PRM_TIME_TABLE_STRUCTURE_INVALID",
            "The current processing tables are not in exact slot order.",
        )

    int_type_offsets = _find_all(data, INT_TYPE_KEY, start=method_start, end=method_end)
    if len(int_type_offsets) != 1:
        return _invalid(
            "YOUNGIN_PRM_TIME_TABLE_INTEGRATION_TYPE_INVALID",
            "The current method does not contain one bounded integration type.",
        )
    int_type_value_offset = int_type_offsets[0] + len(INT_TYPE_KEY)
    if int_type_value_offset + 4 > method_end:
        return _invalid(
            "YOUNGIN_PRM_TIME_TABLE_INTEGRATION_TYPE_INVALID",
            "The current method integration type is truncated.",
        )
    integration_type = int(struct.unpack_from("<I", data, int_type_value_offset)[0])

    tables: list[PrmTimeTable] = []
    try:
        for index, (name, position) in enumerate(zip(expected_names, positions, strict=True)):
            boundary = positions[index + 1] if index + 1 < len(positions) else method_end
            table, _cursor = _parse_table(
                data,
                start=position,
                boundary=boundary,
                table_name=name,
                slot_number=index // 2 + 1,
            )
            if not name.startswith("GPC"):
                tables.append(table)
    except _DecodeError:
        return _invalid(
            "YOUNGIN_PRM_TIME_TABLE_STRUCTURE_INVALID",
            "A current processing table has unsupported bounded framing.",
        )
    if len(tables) != TABLE_SLOT_COUNT:
        return _invalid(
            "YOUNGIN_PRM_TIME_TABLE_STRUCTURE_INVALID",
            "The current method does not expose exactly 32 numbered processing tables.",
        )
    return PrmCurrentMethod(
        "matched",
        integration_type,
        tuple(tables),
        hashlib.sha256(data[method_start:method_end]).hexdigest(),
    )
