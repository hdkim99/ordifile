# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Independently implemented decoder for ChemStation ``.CH`` v179 signals.

Version 179 shares the v181 header family and differs only in its payload: an
uncompressed little-endian binary64 array instead of compressed records. The
retention-time construction below is validated against paired vendor report exports;
see ``docs/research/agilent-chemstation-ch-v179-investigation.md``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from ordifile.adapters._agilent_ch_v181_records import (
    HEADER_BYTES,
    ChV181StructureError,
    V181Header,
    parse_v181_header,
)

EXPECTED_VERSION = 179
POINT_BYTES = 8
MAX_DECODED_POINTS = 2_000_000
MAX_CH_FILE_BYTES = 64 * 1024 * 1024

# Big-endian float32 run boundaries in milliseconds, and the big-endian float64 response
# scale, all inside the shared header.
START_MS_OFFSET = 282
END_MS_OFFSET = 286
SIGNAL_MAXIMUM_OFFSET = 290
RESPONSE_SCALE_OFFSET = 4732

MILLISECONDS_PER_MINUTE = 60_000.0


@dataclass(frozen=True, slots=True)
class DecodedV179Signal:
    """One uncompressed v179 signal with its file-derived axis."""

    header: V179Header
    values: tuple[float, ...]
    point_count: int
    step_ms: float


@dataclass(frozen=True, slots=True)
class V179Header:
    """Structural header facts plus the fields that carry the axis and scale."""

    shared: V181Header
    start_ms: float
    end_ms: float
    stored_maximum: float
    response_scale: float
    response_unit: str


def _fail(code: str, message: str, **details: object) -> ChV181StructureError:
    return ChV181StructureError(code, message, **details)


def _be_f32(data: bytes, offset: int) -> float:
    return float(struct.unpack_from(">f", data, offset)[0])


def _be_f64(data: bytes, offset: int) -> float:
    return float(struct.unpack_from(">d", data, offset)[0])


def read_v179_signal(path: Path) -> DecodedV179Signal:
    """Read one exact v179 signal, or fail closed with a structured reason."""
    try:
        file_size = path.stat().st_size
    except OSError as error:
        raise _fail(
            "AGILENT_CH_HEADER_INVALID",
            "The input could not be inspected safely.",
        ) from error
    if file_size > MAX_CH_FILE_BYTES:
        raise _fail(
            "AGILENT_CH_FILE_TOO_LARGE",
            "The source exceeds the bounded reader size.",
            file_size=file_size,
            maximum=MAX_CH_FILE_BYTES,
        )
    try:
        data = path.read_bytes()
    except OSError as error:
        raise _fail("AGILENT_CH_HEADER_INVALID", "The input could not be read.") from error

    shared = parse_v181_header(data[:HEADER_BYTES], file_size, expected_version=EXPECTED_VERSION)

    payload = data[HEADER_BYTES:]
    if len(payload) % POINT_BYTES:
        raise _fail(
            "AGILENT_CH_PAYLOAD_INVALID",
            "The v179 payload is not a whole number of stored values.",
            payload_bytes=len(payload),
        )
    point_count = len(payload) // POINT_BYTES
    if point_count < 2:
        raise _fail(
            "AGILENT_CH_PAYLOAD_INVALID",
            "The v179 payload carries fewer than two stored values.",
            point_count=point_count,
        )
    if point_count > MAX_DECODED_POINTS:
        raise _fail(
            "AGILENT_CH_PAYLOAD_INVALID",
            "The v179 payload exceeds the bounded point count.",
            point_count=point_count,
            maximum=MAX_DECODED_POINTS,
        )
    values = struct.unpack_from(f"<{point_count}d", payload, 0)
    if any(not isfinite(value) for value in values):
        raise _fail("AGILENT_CH_PAYLOAD_INVALID", "A stored value is not finite.")

    start_ms = _be_f32(data, START_MS_OFFSET)
    end_ms = _be_f32(data, END_MS_OFFSET)
    stored_maximum = _be_f32(data, SIGNAL_MAXIMUM_OFFSET)
    response_scale = _be_f64(data, RESPONSE_SCALE_OFFSET)
    for offset, value in (
        (START_MS_OFFSET, start_ms),
        (END_MS_OFFSET, end_ms),
        (SIGNAL_MAXIMUM_OFFSET, stored_maximum),
        (RESPONSE_SCALE_OFFSET, response_scale),
    ):
        if not isfinite(value):
            raise _fail(
                "AGILENT_CH_HEADER_INVALID",
                "A required numeric header field is not finite.",
                offset=offset,
            )
    if not end_ms > start_ms:
        raise _fail(
            "AGILENT_CH_TIME_AXIS_INVALID",
            "The stored run boundaries do not increase.",
            start_ms=start_ms,
            end_ms=end_ms,
        )
    if not response_scale > 0.0:
        raise _fail(
            "AGILENT_CH_RESPONSE_SCALE_INVALID",
            "The stored response scale is not positive.",
            offset=RESPONSE_SCALE_OFFSET,
        )
    # The stored maximum is an independent check that the payload was read correctly.
    decoded_maximum = max(values)
    if abs(decoded_maximum - stored_maximum) > abs(decoded_maximum) * 1e-6 + 1e-9:
        raise _fail(
            "AGILENT_CH_PAYLOAD_INVALID",
            "The decoded maximum does not match the value stored in the header.",
            stored=stored_maximum,
            decoded=decoded_maximum,
        )

    step_ms = (end_ms - start_ms) / (point_count - 1)
    header = V179Header(
        shared=shared,
        start_ms=start_ms,
        end_ms=end_ms,
        stored_maximum=stored_maximum,
        response_scale=response_scale,
        response_unit=shared.raw_unit_lexeme,
    )
    return DecodedV179Signal(header, values, point_count, step_ms)


def retention_times(decoded: DecodedV179Signal) -> tuple[float, ...]:
    """Return the file-derived retention axis in minutes."""
    return tuple(
        (decoded.header.start_ms + index * decoded.step_ms) / MILLISECONDS_PER_MINUTE
        for index in range(decoded.point_count)
    )


def scaled_responses(decoded: DecodedV179Signal) -> tuple[float, ...]:
    """Return stored values in the unit the header declares, using its stored scale."""
    scale = decoded.header.response_scale
    return tuple(value * scale for value in decoded.values)
