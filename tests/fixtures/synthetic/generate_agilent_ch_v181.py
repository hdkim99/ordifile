# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate structural ChemStation v181 test bytes without proprietary byte slices.

The container bytes are generated locally. Structural offsets, markers, version, and
producer text are independently recorded profile facts; sample, numeric, and payload
values are invented for the tests.
"""

from __future__ import annotations

import struct
from pathlib import Path

SyntheticRecord = tuple[str, int]


def _ascii_pascal(header: bytearray, offset: int, value: str) -> None:
    raw = value.encode("ascii")
    header[offset] = len(raw)
    header[offset + 1 : offset + 1 + len(raw)] = raw


def _utf16_pascal(header: bytearray, offset: int, value: str) -> None:
    raw = value.encode("utf-16-le")
    header[offset] = len(value)
    header[offset + 1 : offset + 1 + len(raw)] = raw


def synthetic_v181_bytes(
    *,
    version_text: str = "181",
    numeric_version: int = 181,
    data_page: int = 13,
    records: tuple[SyntheticRecord, ...] = (
        ("absolute", 100),
        ("relative", 0),
    ),
    trailing: bytes = b"",
) -> bytes:
    """Return deterministic invented bytes matching the documented structure."""
    header = bytearray(6_144)
    _ascii_pascal(header, 0, version_text)
    struct.pack_into(">I", header, 248, numeric_version)
    struct.pack_into(">I", header, 264, data_page)
    struct.pack_into(">I", header, 278, 17)
    struct.pack_into(">f", header, 282, 12.5)
    struct.pack_into(">f", header, 286, 34.5)
    _utf16_pascal(header, 347, "GC DATA FILE")
    _utf16_pascal(header, 858, "synthetic_sample")
    _utf16_pascal(header, 2391, "01-Jan-26, 01:02:03")
    _utf16_pascal(header, 2492, "FID1A")
    _utf16_pascal(header, 2533, "GC")
    _utf16_pascal(header, 2574, "SYNTHETIC.M")
    _utf16_pascal(header, 3089, "Asterix ChemStation")
    struct.pack_into(">H", header, 4122, 10_000)
    struct.pack_into(">H", header, 4124, 50_000)
    _utf16_pascal(header, 4172, "raw")
    struct.pack_into(">d", header, 4724, 0.0)
    struct.pack_into(">d", header, 4732, 0.5)
    payload = bytearray()
    for kind, value in records:
        if kind == "absolute":
            if not -(2**47) <= value <= 2**47 - 1:
                raise ValueError("synthetic absolute value must fit the signed-high/u32 layout")
            high = value >> 32
            low = value & 0xFFFFFFFF
            payload.extend(struct.pack(">hhI", 0x7FFF, high, low))
        elif kind == "relative":
            payload.extend(struct.pack(">h", value))
        else:
            raise ValueError(f"unknown synthetic record kind: {kind}")
    return bytes(header + payload + trailing)


def write_synthetic_v181(path: Path, **kwargs: object) -> Path:
    """Write one invented fixture and return its path."""
    path.write_bytes(synthetic_v181_bytes(**kwargs))  # type: ignore[arg-type]
    return path
