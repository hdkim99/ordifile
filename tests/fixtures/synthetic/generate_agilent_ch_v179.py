# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate structural ChemStation v179 test bytes without proprietary byte slices.

The container bytes are generated locally. Structural offsets, markers, version, and
producer text are independently recorded profile facts; sample, numeric, and payload
values are invented for the tests.
"""

from __future__ import annotations

import struct
from pathlib import Path

HEADER_BYTES = 6_144


def _ascii_pascal(header: bytearray, offset: int, value: str) -> None:
    raw = value.encode("ascii")
    header[offset] = len(raw)
    header[offset + 1 : offset + 1 + len(raw)] = raw


def _utf16_pascal(header: bytearray, offset: int, value: str) -> None:
    raw = value.encode("utf-16-le")
    header[offset] = len(value)
    header[offset + 1 : offset + 1 + len(raw)] = raw


def synthetic_v179_bytes(
    *,
    version_text: str = "179",
    numeric_version: int = 179,
    data_page: int = 13,
    start_ms: float = 0.0,
    end_ms: float | None = None,
    step_ms: float = 20.0,
    values: tuple[float, ...] = (10.0, 40.0, 90.0, 40.0, 10.0),
    stored_maximum: float | None = None,
    response_scale: float = 1.0 / 7680.0,
    response_unit: str = "pA",
    sample_text: str = "synthetic_sample",
    trailing: bytes = b"",
) -> bytes:
    """Return deterministic invented bytes matching the documented v179 structure."""
    header = bytearray(HEADER_BYTES)
    _ascii_pascal(header, 0, version_text)
    struct.pack_into(">I", header, 248, numeric_version)
    struct.pack_into(">I", header, 264, data_page)
    resolved_end = end_ms if end_ms is not None else start_ms + step_ms * (len(values) - 1)
    struct.pack_into(">f", header, 282, start_ms)
    struct.pack_into(">f", header, 286, resolved_end)
    struct.pack_into(">f", header, 290, max(values) if stored_maximum is None else stored_maximum)
    _utf16_pascal(header, 347, "GC DATA FILE")
    _utf16_pascal(header, 858, sample_text)
    _utf16_pascal(header, 2391, "01-Jan-26, 01:02:03")
    _utf16_pascal(header, 2492, "GCI")
    _utf16_pascal(header, 2533, "GC")
    _utf16_pascal(header, 2574, "SYNTHETIC.M")
    _utf16_pascal(header, 3089, "Asterix ChemStation")
    _utf16_pascal(header, 4172, response_unit)
    struct.pack_into(">d", header, 4724, 0.0)
    struct.pack_into(">d", header, 4732, response_scale)
    payload = struct.pack(f"<{len(values)}d", *values) if values else b""
    return bytes(header) + payload + trailing


def write_synthetic_v179(path: Path, **kwargs: object) -> Path:
    """Write one invented fixture and return its path."""
    path.write_bytes(synthetic_v179_bytes(**kwargs))  # type: ignore[arg-type]
    return path
