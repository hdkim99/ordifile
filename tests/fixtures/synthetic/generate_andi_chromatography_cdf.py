# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate an invented ANDI chromatography netCDF-3 file from the public format."""

from __future__ import annotations

import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

NC_CHAR = 2
NC_FLOAT = 5
_NC_DIMENSION = 0x0A
_NC_VARIABLE = 0x0B
_NC_ATTRIBUTE = 0x0C
_ABSENT = 0x00
_NAME_WIDTH = 32


def _pad(payload: bytes) -> bytes:
    return payload + b"\x00" * (-len(payload) % 4)


def _name(text: str) -> bytes:
    encoded = text.encode("ascii")
    return struct.pack(">I", len(encoded)) + _pad(encoded)


def _attributes(items: Mapping[str, str]) -> bytes:
    if not items:
        return struct.pack(">II", _ABSENT, 0)
    blob = struct.pack(">II", _NC_ATTRIBUTE, len(items))
    for key, value in items.items():
        encoded = value.encode("ascii")
        blob += _name(key) + struct.pack(">II", NC_CHAR, len(encoded)) + _pad(encoded)
    return blob


def synthetic_cdf_bytes(
    *,
    point_count: int = 64,
    peak_count: int = 3,
    sampling_interval: float = 0.5,
    delay_time: float = 0.0,
    retention_unit: str | None = "time in seconds",
    detector_unit: str | None = "uV",
    uniform_flag: tuple[str, str] | None = ("uniform_sampling_flag", "Y"),
    peak_retention_times: Sequence[float] | None = None,
    peak_heights: Sequence[float] | None = None,
    peak_names: Sequence[str] | None = None,
    peak_start_times: Sequence[float] | None = None,
    peak_end_times: Sequence[float] | None = None,
    record_count: int = 0,
    version: int = 1,
    omit_ordinate: bool = False,
    global_attributes: Mapping[str, str] | None = None,
) -> bytes:
    """Return one deterministic invented ANDI chromatography document."""
    retention = list(
        peak_retention_times
        if peak_retention_times is not None
        else [(index + 1) * 4.0 for index in range(peak_count)]
    )
    heights = list(
        peak_heights if peak_heights is not None else [10.0 + i for i in range(peak_count)]
    )
    labels = list(
        peak_names if peak_names is not None else [f"Compound {i}" for i in range(peak_count)]
    )

    dimensions: list[tuple[str, int]] = [("point_number", point_count), ("peak_number", peak_count)]
    if labels:
        dimensions.append(("_name_string", _NAME_WIDTH))

    attributes: dict[str, str] = {
        "aia_template_revision": "1.0",
        "netcdf_revision": "2.0",
        "dataset_completeness": "C1+C2",
        "dataset_origin": "Synthetic Instruments",
        "detector_name": "Synthetic detector",
        "sample_name": "synthetic-sample",
    }
    if retention_unit is not None:
        attributes["retention_unit"] = retention_unit
    if detector_unit is not None:
        attributes["detector_unit"] = detector_unit
    attributes.update(global_attributes or {})

    scalars: list[tuple[str, float]] = [
        ("actual_sampling_interval", sampling_interval),
        ("actual_delay_time", delay_time),
        ("actual_run_time_length", (point_count - 1) * sampling_interval),
    ]

    variables: list[tuple[str, tuple[int, ...], int, int, bytes, Mapping[str, str]]] = []
    for name, value in scalars:
        variables.append((name, (), NC_FLOAT, 1, struct.pack(">f", value), {}))
    if not omit_ordinate:
        ordinate = b"".join(struct.pack(">f", 100.0 + (index % 17)) for index in range(point_count))
        variables.append(
            (
                "ordinate_values",
                (0,),
                NC_FLOAT,
                point_count,
                ordinate,
                dict([uniform_flag]) if uniform_flag else {},
            )
        )
    if peak_count:
        variables.append(
            (
                "peak_retention_time",
                (1,),
                NC_FLOAT,
                peak_count,
                b"".join(struct.pack(">f", value) for value in retention),
                {},
            )
        )
        variables.append(
            (
                "peak_area",
                (1,),
                NC_FLOAT,
                peak_count,
                b"".join(struct.pack(">f", 1_000.0 + index) for index in range(peak_count)),
                {},
            )
        )
        variables.append(
            (
                "peak_height",
                (1,),
                NC_FLOAT,
                peak_count,
                b"".join(struct.pack(">f", value) for value in heights),
                {},
            )
        )
        for name, source in (
            ("peak_start_time", peak_start_times),
            ("peak_end_time", peak_end_times),
        ):
            if source is not None:
                variables.append(
                    (
                        name,
                        (1,),
                        NC_FLOAT,
                        peak_count,
                        b"".join(struct.pack(">f", value) for value in source),
                        {},
                    )
                )
        if labels:
            blob = b"".join(
                label.encode("ascii")[:_NAME_WIDTH].ljust(_NAME_WIDTH, b"\x00") for label in labels
            )
            variables.append(("peak_name", (1, 2), NC_CHAR, peak_count * _NAME_WIDTH, blob, {}))

    header = b"CDF" + bytes([version]) + struct.pack(">I", record_count)
    header += struct.pack(">II", _NC_DIMENSION, len(dimensions))
    for name, length in dimensions:
        header += _name(name) + struct.pack(">I", length)
    header += _attributes(attributes)
    header += struct.pack(">II", _NC_VARIABLE, len(variables))

    offset_width = 4 if version == 1 else 8
    fixed = b""
    for name, dims, nc_type, _, _, var_attrs in variables:
        fixed += _name(name) + struct.pack(">I", len(dims))
        fixed += b"".join(struct.pack(">I", value) for value in dims)
        fixed += _attributes(var_attrs)
        fixed += struct.pack(">II", nc_type, 0) + b"\x00" * offset_width
    begin = len(header) + len(fixed)

    body = b""
    offsets: list[int] = []
    for _, _, _, _, payload, _ in variables:
        offsets.append(begin + len(body))
        body += _pad(payload)

    for index, (name, dims, nc_type, _, payload, var_attrs) in enumerate(variables):
        header += _name(name) + struct.pack(">I", len(dims))
        header += b"".join(struct.pack(">I", value) for value in dims)
        header += _attributes(var_attrs)
        size = len(_pad(payload))
        header += struct.pack(">II", nc_type, size)
        header += (
            struct.pack(">I", offsets[index]) if version == 1 else struct.pack(">Q", offsets[index])
        )
    return header + body


def write_synthetic_cdf(path: Path, **kwargs: Any) -> Path:
    """Write one invented ANDI chromatography fixture and return its path."""
    path.write_bytes(synthetic_cdf_bytes(**kwargs))
    return path
