# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate an invented structural LCD TTFL profile without proprietary byte slices."""

from __future__ import annotations

import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from generate_cfb_v4 import SECTOR_BYTES, build_cfb_v4

CHANNEL_HEADER_BYTES = 768
CHANNEL_RECORD_BYTES = 16
INDEX_RECORD_BYTES = 16
BASE_STEP_MS = 400
LONG_STEP_MS = 900


def _file_property(schema: str, *, as_xml: bool = False) -> bytes:
    payload = bytearray(SECTOR_BYTES)
    if as_xml:
        payload[0:4] = b"\x1f\x00\x00\x04"
        encoded = schema.encode("ascii").hex().upper().encode("ascii")
        body = b'<?xml version="1.0"?>\r\n<FileProperty><szVersion>@StoX@' + encoded
        body += b"</szVersion></FileProperty>"
        payload[4 : 4 + len(body)] = body
        return bytes(payload)
    struct.pack_into("<I", payload, 0, 11)
    encoded_schema = schema.encode("ascii") + b"\x00"
    payload[4 : 4 + len(encoded_schema)] = encoded_schema
    return bytes(payload)


def synthetic_lcd_streams(
    *,
    file_schema: str = "3.00",
    scan_count: int = 1_024,
    second_channel_scans: Sequence[int] | None = (10, 50, 90, 300),
    retention_times_ms: Sequence[int] | None = None,
    channel_declared_overrides: Mapping[int, int] | None = None,
    index_previous_overrides: Mapping[int, int] | None = None,
    index_scan_overrides: Mapping[int, int] | None = None,
    secondary_exceeds_primary_at: int | None = None,
    use_tlm_storage: bool = False,
    tlm_architecture: bool = False,
    tlm_tic_bytes: bytes | None = None,
    xml_file_property: bool = False,
    extra_streams: Mapping[tuple[str, ...], bytes] | None = None,
) -> dict[tuple[str, ...], bytes]:
    """Return deterministic invented streams for the validated TTFL profile."""
    second = sorted(set(second_channel_scans if second_channel_scans is not None else ()))
    if retention_times_ms is None:
        times: list[int] = []
        clock = 0
        for index in range(scan_count):
            times.append(clock)
            clock += LONG_STEP_MS if index in set(second) else BASE_STEP_MS
    else:
        times = list(retention_times_ms)

    # One index record per stored spectrum, ordered by scan, chained per channel.
    records: list[tuple[int, int]] = [(scan, 0) for scan in range(scan_count)]
    records += [(scan, 1) for scan in second]
    records.sort(key=lambda item: (item[0], item[1]))
    last_of: dict[int, int] = {}
    index_blob = bytearray()
    offset = 0
    for position, (scan, channel) in enumerate(records):
        previous = last_of.get(channel, -1)
        last_of[channel] = position
        index_blob += struct.pack(
            "<Qii",
            offset,
            index_scan_overrides.get(position, scan) if index_scan_overrides else scan,
            index_previous_overrides.get(position, previous)
            if index_previous_overrides
            else previous,
        )
        offset += 64

    def channel_stream(slot: int, first_scan: int, last_scan: int) -> bytes:
        declared = last_scan - first_scan + 1
        if channel_declared_overrides and slot in channel_declared_overrides:
            declared = channel_declared_overrides[slot]
        blob = bytearray(CHANNEL_HEADER_BYTES)
        struct.pack_into("<Q", blob, 0, declared)
        struct.pack_into("<Q", blob, 260, declared)
        for position in range(declared):
            primary = 1_000 + (position * 37) % 5_000
            secondary = primary // 2
            if secondary_exceeds_primary_at == position and slot == 0:
                secondary = primary + 1
            blob += struct.pack("<QII", primary, secondary, 0)
        return bytes(blob)

    if tlm_architecture:
        tic = (
            tlm_tic_bytes
            if tlm_tic_bytes is not None
            else b"".join(
                struct.pack("<Q", 500 + (index * 13) % 900) for index in range(len(times))
            )
        )
        return {
            ("File Property",): _file_property(file_schema, as_xml=xml_file_property),
            ("TLM Raw Data", "Retention Time"): struct.pack(f"<{len(times)}I", *times),
            ("TLM Raw Data", "TIC Data"): tic,
        }
    streams: dict[tuple[str, ...], bytes] = {
        ("File Property",): _file_property(file_schema, as_xml=xml_file_property),
        ("TTFL Raw Data", "Retention Time"): struct.pack(f"<{len(times)}I", *times),
        ("TTFL Raw Data", "Data Index"): bytes(index_blob),
        ("TTFL Raw Data", "MS Raw Data"): bytes(max(offset, SECTOR_BYTES)),
        ("TTFL Raw Data", "TIC Data 0"): channel_stream(0, 0, scan_count - 1),
    }
    for slot in range(1, 32):
        streams[("TTFL Raw Data", f"TIC Data {slot}")] = b""
    if second:
        streams[("TTFL Raw Data", "TIC Data 1")] = channel_stream(1, second[0], second[-1])
    if use_tlm_storage:
        streams[("TLM Raw Data", "TIC Data")] = bytes(SECTOR_BYTES)
    streams.update(extra_streams or {})
    return streams


def synthetic_lcd_bytes(**kwargs: Any) -> bytes:
    """Return one deterministic invented compound document."""
    streams = {
        path: payload for path, payload in synthetic_lcd_streams(**kwargs).items() if payload
    }
    return build_cfb_v4(streams)


def write_synthetic_lcd(path: Path, **kwargs: Any) -> Path:
    """Write one invented structural fixture and return its path."""
    path.write_bytes(synthetic_lcd_bytes(**kwargs))
    return path
