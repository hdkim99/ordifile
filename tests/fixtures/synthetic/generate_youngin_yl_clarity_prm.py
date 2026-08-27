# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate invented PRM-shaped bytes for structural parser tests only."""

from __future__ import annotations

import gzip
import struct
from collections.abc import Sequence

START_MAGIC = bytes.fromhex("5aa50008")
FOOTER_MARKER = bytes.fromhex("4d4bfa08")
INFO_VALUE_KEY = b"\x04Info\x03\xff\xfe\xff"
PRODUCER_PREFIX_TEXT = "YL-Clarity 9.0.1.19 FULL, SN: "
COUNT_KEY = b"\x10CountOfDetectors\x01"
VERSION_KEY = b"\x0dChromVersion1\x01"
RAW_DATA_KEY = b"\x08RAWData6\x05"
PRM_DATA_KEY = b"\x07PRMData\x05"
DET_NAME_KEY = b"\x07DetName\x03\xff\xfe\xff\x03"
DET_NAME_FIXED_TAIL = (
    b"\x0fPDASpectrumName\x03\xff\xfe\xff\x00"
    b"\x0eMSSpectrumName\x03\xff\xfe\xff\x00"
    b"\x09DetSigGen\x01\x00\x00\x00\x00"
)
INT_TYPE_KEY = b"\x07IntType\x01"
MARKERS_DATA_PREFIX = (
    bytes.fromhex("fffeff07")
    + "Markers".encode("utf-16-le")
    + bytes(4)
    + struct.pack("<I", 1)
    + b"\x04Data\x04"
)
DEFAULT_TIME_TABLE_EVENTS = (
    (50, 0.0, 0.0, 0.1, 32),
    (51, 0.0, 0.0, 0.1, 32),
    (65, 0.0, 0.0, 1.0, 32),
    (72, 0.0, 0.0, 0.0, 32),
    (46, 0.0, 0.0, 0.0, 32),
    (47, 0.0, 0.0, 0.0, 32),
)


def _gzip_payload(values: Sequence[float]) -> tuple[bytes, bytes]:
    payload = b"".join(struct.pack("<f", value) for value in values)
    return payload, gzip.compress(payload, mtime=0)


def _metadata(
    record_count: int,
    *,
    raw_size: int | None = None,
    d_step: int = 1,
    d_size: int | None = None,
    min_ticks: float = 600.0,
) -> bytes:
    return (
        b"\x07RAWSize\x01"
        + struct.pack("<I", record_count if raw_size is None else raw_size)
        + b"\x05DStep\x01"
        + struct.pack("<I", d_step)
        + b"\x05DSize\x01"
        + struct.pack("<I", record_count if d_size is None else d_size)
        + b"\x08MinTicks\x02"
        + struct.pack("<d", min_ticks)
    )


def _framed_text(value: str) -> bytes:
    return bytes.fromhex("fffeff") + bytes((len(value),)) + value.encode("utf-16-le")


def _typed_u32(name: str, value: int) -> bytes:
    return bytes((len(name),)) + name.encode("ascii") + b"\x01" + struct.pack("<I", value)


def _typed_double(name: str, value: float) -> bytes:
    return bytes((len(name),)) + name.encode("ascii") + b"\x02" + struct.pack("<d", value)


def _typed_text(name: str, value: str) -> bytes:
    return bytes((len(name),)) + name.encode("ascii") + b"\x03" + _framed_text(value)


def _time_table(
    name: str,
    events: tuple[tuple[int, float, float, float, int], ...],
) -> bytes:
    data = bytearray(_framed_text(name))
    data.extend(struct.pack("<II", len(events), 1))
    for item_number, (opcode, a_time, b_time, value, group) in enumerate(events, start=1):
        data.extend(_framed_text(f"Item{item_number}"))
        data.extend(struct.pack("<II", 0, 8))
        data.extend(_typed_u32("OpCode", opcode))
        data.extend(_typed_double("ATime", a_time))
        data.extend(_typed_double("BTime", b_time))
        data.extend(_typed_text("Text", ""))
        data.extend(_typed_u32("Group", group))
        data.extend(_typed_text("GroupStr", " "))
        data.extend(_typed_double("Value", value))
        data.extend(_typed_text("GUID", f"{{00000000-0000-0000-0000-{item_number:012d}}}"))
    return bytes(data)


def _processing_method(
    *,
    integration_type: int,
    channel_events: tuple[tuple[tuple[int, float, float, float, int], ...], ...],
) -> bytes:
    data = bytearray(_typed_double("PeakWidth", 0.01))
    data.extend(_typed_double("NoiseThreshold", 0.0))
    data.extend(_typed_u32("SmoothingWindow", 2))
    for slot in range(1, 33):
        extras = channel_events[slot - 1] if slot <= len(channel_events) else ()
        data.extend(_time_table(f"TimeTable{slot}", DEFAULT_TIME_TABLE_EVENTS + extras))
        data.extend(_time_table(f"GPCTimeTable{slot}", DEFAULT_TIME_TABLE_EVENTS))
    data.extend(INT_TYPE_KEY)
    data.extend(struct.pack("<I", integration_type))
    # The marker reader intentionally has an independent, narrow integration-header
    # bound.  Invented padding keeps IntType inside that existing 64-byte window.
    data.extend(bytes(51))
    return bytes(data)


def synthetic_prm_bytes(
    *,
    channels: tuple[tuple[float, ...], ...] = ((1.25, -2.5, 3.75),),
    history_count: int = 1,
    detector_count: int | None = None,
    history_versions: tuple[int, ...] | None = None,
    producer_text: str = PRODUCER_PREFIX_TEXT + "SYNTHETIC",
    raw_size_override: int | None = None,
    d_step: int = 1,
    d_size_override: int | None = None,
    min_ticks: float = 600.0,
    duplicate_mismatch_channel: int | None = None,
    trailing: bytes = b"",
    footer_suffix: bytes = bytes(16),
    embedded_private_text: bytes = b"",
    stored_labels: tuple[str, ...] | None = None,
    payload_suffix: bytes = b"",
    gzip_trailing: bytes = b"",
    marker_records: tuple[tuple[tuple[int, int], ...], ...] | None = None,
    integration_type: int | None = None,
    time_table_events: tuple[tuple[tuple[int, float, float, float, int], ...], ...] | None = None,
) -> bytes:
    """Return deterministic invented bytes matching only the observed structural facts."""
    structural_count = len(channels) if detector_count is None else detector_count
    labels = stored_labels or (("TCD",) if len(channels) == 1 else ("FID", "TCD"))
    if len(labels) != len(channels):
        raise ValueError("stored_labels must match channels")
    if marker_records is not None and len(marker_records) != len(channels):
        raise ValueError("marker_records must match channels")
    if time_table_events is not None and len(time_table_events) != len(channels):
        raise ValueError("time_table_events must match channels")
    versions = history_versions or tuple(range(1, history_count + 1))
    data = bytearray(START_MAGIC)
    if len(producer_text) > 255:
        raise ValueError("producer_text is too long for the invented framed Info value")
    data.extend(INFO_VALUE_KEY)
    data.append(len(producer_text))
    data.extend(producer_text.encode("utf-16-le"))
    data.extend(bytes(16))
    data.extend(embedded_private_text)
    for index in range(history_count):
        if marker_records is not None:
            selected_integration_type = 0x17 if integration_type is None else integration_type
            data.extend(
                _processing_method(
                    integration_type=selected_integration_type,
                    channel_events=time_table_events
                    if time_table_events is not None
                    else tuple(() for _ in channels),
                )
            )
        data.extend(COUNT_KEY)
        data.extend(struct.pack("<I", structural_count))
        data.extend(VERSION_KEY)
        data.extend(struct.pack("<I", versions[index]))
        data.extend(bytes(7))
    for channel_index, values in enumerate(channels, start=1):
        if marker_records is not None:
            encoded_markers = b"".join(
                struct.pack("<I", (marker_type << 24) | record_index)
                for marker_type, record_index in marker_records[channel_index - 1]
            )
            data.extend(MARKERS_DATA_PREFIX)
            data.extend(struct.pack("<I", len(encoded_markers)))
            data.extend(encoded_markers)
        payload, compressed = _gzip_payload(values)
        if payload_suffix:
            payload += payload_suffix
            compressed = gzip.compress(payload, mtime=0)
        compressed += gzip_trailing
        data.extend(RAW_DATA_KEY)
        data.extend(struct.pack("<I", len(compressed)))
        data.extend(compressed)
        data.extend(
            _metadata(
                len(payload) // 4,
                raw_size=raw_size_override,
                d_step=d_step,
                d_size=d_size_override,
                min_ticks=min_ticks,
            )
        )
        duplicate = compressed
        if duplicate_mismatch_channel == channel_index:
            _, duplicate = _gzip_payload((*values[:-1], values[-1] + 1.0))
        data.extend(PRM_DATA_KEY)
        data.extend(struct.pack("<I", len(duplicate)))
        data.extend(duplicate)
        data.extend(bytes(31))
        data.extend(DET_NAME_KEY)
        data.extend(labels[channel_index - 1].encode("utf-16-le"))
        data.extend(DET_NAME_FIXED_TAIL)
        if channel_index < len(channels):
            data.extend(b"\xffSYNTHETIC_CHANNEL_METADATA")
        else:
            data.extend(b"\x09Detectors")
    data.extend(FOOTER_MARKER)
    data.extend(footer_suffix)
    data.extend(trailing)
    return bytes(data)
