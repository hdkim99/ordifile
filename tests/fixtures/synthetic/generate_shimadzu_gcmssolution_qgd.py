# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate an invented structural QGD profile without proprietary byte slices."""

from __future__ import annotations

import struct
from collections.abc import Mapping
from pathlib import Path

from generate_cfb_v4 import SECTOR_BYTES, build_cfb_v4

SCAN_COUNT = 16_800
RT_START_MS = 240_000
RT_INTERVAL_MS = 200
SCAN_TARGET = 0x01D60000


def synthetic_qgd_streams(
    *,
    file_schema: str = "4.00",
    retention_times_ms: tuple[int, ...] | None = None,
    intensity_value_overrides: Mapping[int, int] | None = None,
    intensity_width_overrides: Mapping[int, int] | None = None,
    records_overrides: Mapping[int, tuple[tuple[int, int], ...]] | None = None,
    header_scan_overrides: Mapping[int, int] | None = None,
    header_rt_overrides: Mapping[int, int] | None = None,
    header_target_overrides: Mapping[int, int] | None = None,
    header_point_count_overrides: Mapping[int, int] | None = None,
    path_replacements: Mapping[tuple[str, ...], tuple[str, ...]] | None = None,
    trailing_ms_bytes: bytes = b"",
) -> dict[tuple[str, ...], bytes]:
    """Return deterministic invented streams for the exact Stage A profile."""
    retention = retention_times_ms or tuple(
        RT_START_MS + index * RT_INTERVAL_MS for index in range(SCAN_COUNT)
    )
    intensity_overrides = intensity_value_overrides or {}
    width_overrides = intensity_width_overrides or {}
    record_overrides = records_overrides or {}
    scan_overrides = header_scan_overrides or {}
    rt_overrides = header_rt_overrides or {}
    target_overrides = header_target_overrides or {}
    point_count_overrides = header_point_count_overrides or {}

    offsets: list[int] = []
    tic_values: list[int] = []
    ms_data = bytearray()
    for scan_index, retention_ms in enumerate(retention):
        offsets.append(len(ms_data))
        width = width_overrides.get(scan_index, 2)
        default_intensity = intensity_overrides.get(scan_index, 1_000 + scan_index % 1_000)
        records = record_overrides.get(scan_index, ((700, default_intensity),))
        tic_values.append(sum(intensity for _, intensity in records))
        encoded_count = point_count_overrides.get(scan_index, len(records))
        ms_data.extend(
            struct.pack(
                "<III2I2H2I",
                scan_overrides.get(scan_index, scan_index),
                rt_overrides.get(scan_index, retention_ms),
                target_overrides.get(scan_index, SCAN_TARGET),
                0,
                0,
                width,
                encoded_count,
                0,
                0,
            )
        )
        for mass_raw, intensity_raw in records:
            ms_data.extend(struct.pack("<H", mass_raw))
            ms_data.extend(intensity_raw.to_bytes(width, "little", signed=False))
    ms_data.extend(trailing_ms_bytes)

    file_property = bytearray(SECTOR_BYTES)
    struct.pack_into("<I", file_property, 0, 11)
    encoded_schema = file_schema.encode("ascii") + b"\x00"
    file_property[4 : 4 + len(encoded_schema)] = encoded_schema
    file_property[148:153] = b"4.11 "
    streams: dict[tuple[str, ...], bytes] = {
        ("File Property",): bytes(file_property),
        ("GCMS Raw Data", "Retention Time"): struct.pack(f"<{len(retention)}I", *retention),
        ("GCMS Raw Data", "TIC Data"): struct.pack(f"<{len(tic_values)}Q", *tic_values),
        ("GCMS Raw Data", "Spectrum Index"): struct.pack(f"<{len(offsets)}I", *offsets),
        ("GCMS Raw Data", "MS Raw Data"): bytes(ms_data),
    }
    for old, new in (path_replacements or {}).items():
        streams[new] = streams.pop(old)
    return streams


def synthetic_qgd_bytes(**kwargs: object) -> bytes:
    """Return one deterministic invented compound document."""
    return build_cfb_v4(synthetic_qgd_streams(**kwargs))  # type: ignore[arg-type]


def write_synthetic_qgd(path: Path, **kwargs: object) -> Path:
    """Write one invented structural fixture and return its path."""
    path.write_bytes(synthetic_qgd_bytes(**kwargs))
    return path
