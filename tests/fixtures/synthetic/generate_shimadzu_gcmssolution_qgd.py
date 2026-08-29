# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate an invented structural QGD profile without proprietary byte slices."""

from __future__ import annotations

import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from generate_cfb_v4 import SECTOR_BYTES, build_cfb_v4

SCAN_COUNT = 16_800
RT_START_MS = 240_000
RT_INTERVAL_MS = 200
SCAN_TARGET = 0x01D60000
SPECTRUM_INDEX_U64_TAG = b"\x01\x00"
PEAK_RECORD_BYTES = 208


def synthetic_mc_peak_record(
    *,
    retention_ms: int,
    start_ms: int,
    end_ms: int,
    area: float,
    height: float,
    area_percent: float,
    name: bytes = b"",
    trailing_name_bytes: bytes = b"",
) -> bytes:
    """Return one invented 208-byte mass-chromatogram peak record."""
    record = bytearray(PEAK_RECORD_BYTES)
    struct.pack_into("<i", record, 4, retention_ms)
    struct.pack_into("<d", record, 8, area)
    struct.pack_into("<d", record, 16, height)
    struct.pack_into("<i", record, 40, start_ms)
    struct.pack_into("<i", record, 44, end_ms)
    struct.pack_into("<d", record, 72, area_percent)
    encoded = name + b"\x00" + trailing_name_bytes
    record[80 : 80 + len(encoded)] = encoded[: PEAK_RECORD_BYTES - 80]
    return bytes(record)


def synthetic_mc_peak_streams(
    peaks: tuple[Mapping[str, Any], ...],
) -> tuple[bytes, bytes]:
    """Return an invented ``MC Peak Table`` payload and its ``MC Peak Info`` header."""
    total = sum(float(peak["area"]) for peak in peaks) or 1.0
    table = b"".join(
        synthetic_mc_peak_record(
            retention_ms=int(peak["retention_ms"]),
            start_ms=int(peak["start_ms"]),
            end_ms=int(peak["end_ms"]),
            area=float(peak["area"]),
            height=float(peak["height"]),
            area_percent=(
                float(peak["area_percent"])
                if "area_percent" in peak
                else 100.0 * float(peak["area"]) / total
            ),
            name=bytes(peak.get("name", b"")),
            trailing_name_bytes=bytes(peak.get("trailing_name_bytes", b"")),
        )
        for peak in peaks
    )
    # Real documents store a 112-byte header; the synthetic builder only emits regular
    # CFB sectors, so the invented header is padded to one sector.
    info = bytearray(SECTOR_BYTES)
    struct.pack_into("<I", info, 0, len(peaks))
    return table, bytes(info)


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
    spectrum_index_width: int = 4,
    scan_number_field: bool = False,
    header_scan_number_overrides: Mapping[int, int] | None = None,
    mc_peaks: tuple[Mapping[str, Any], ...] | None = None,
    mc_peak_table_override: bytes | None = None,
    mc_peak_info_override: bytes | None = None,
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
    scan_number_overrides = header_scan_number_overrides or {}

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
                scan_number_overrides.get(scan_index, scan_index + 1 if scan_number_field else 0),
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
        ("GCMS Raw Data", "Spectrum Index"): (
            struct.pack(f"<{len(offsets)}I", *offsets)
            if spectrum_index_width == 4
            else SPECTRUM_INDEX_U64_TAG + struct.pack(f"<{len(offsets)}Q", *offsets)
        ),
        ("GCMS Raw Data", "MS Raw Data"): bytes(ms_data),
    }
    if mc_peaks is not None or mc_peak_table_override is not None:
        table, info = synthetic_mc_peak_streams(mc_peaks) if mc_peaks is not None else (b"", b"")
        streams[("GCMS Data Processing", "MC Peak Table")] = (
            mc_peak_table_override if mc_peak_table_override is not None else table
        )
        streams[("GCMS Data Processing", "MC Peak Info")] = (
            mc_peak_info_override if mc_peak_info_override is not None else info
        )
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
