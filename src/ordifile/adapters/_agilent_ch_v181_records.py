# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Independently implemented decoder for ChemStation ``.CH`` v181 records.

This module exposes byte-level facts only. It deliberately does not assign retention
time, physical intensity, detector, or unit semantics to candidate header fields.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

HEADER_BYTES = 6_144
EXPECTED_VERSION = 181
EXPECTED_DATA_PAGE = 13
ABSOLUTE_RECORD_MARKER = 0x7FFF
MAX_DECODED_RECORDS = 2_000_000
MIN_I64 = -(2**63)
MAX_I64 = 2**63 - 1


class ChV181StructureError(Exception):
    """Bounded structural error translated by the public adapter."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True, slots=True)
class V181Header:
    """Observed header fields without unsupported scientific interpretations."""

    version: int
    payload_offset: int
    family_marker: str
    sample_text: str
    acquisition_local_text: str
    header_text_2492: str
    header_text_2533: str
    method_text: str
    software_text: str
    raw_unit_lexeme: str
    header_f32_0282: float
    header_f32_0286: float
    header_u16_4122: int
    header_u16_4124: int
    header_f64_4724: float
    header_f64_4732: float
    raw_text_bytes_hex: tuple[tuple[str, str], ...]
    raw_numeric_bytes_hex: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class DecodedV181Records:
    """Lossless candidate decoded-record stream and structural counts."""

    header: V181Header
    values: tuple[int, ...]
    absolute_record_count: int
    ordinary_record_count: int
    nonzero_ordinary_record_count: int
    final_zero_ordinary_record: bool
    trailing_byte_count: int


def _u16(data: bytes, offset: int) -> int:
    return int(struct.unpack_from(">H", data, offset)[0])


def _u32(data: bytes, offset: int) -> int:
    return int(struct.unpack_from(">I", data, offset)[0])


def _f32(data: bytes, offset: int) -> float:
    return float(struct.unpack_from(">f", data, offset)[0])


def _f64(data: bytes, offset: int) -> float:
    return float(struct.unpack_from(">d", data, offset)[0])


def _ascii_pascal(data: bytes, offset: int, *, required: bool = False) -> str:
    length = data[offset]
    end = offset + 1 + length
    if end > len(data):
        raise ChV181StructureError(
            "AGILENT_CH_TEXT_ENCODING_INVALID",
            "A bounded ASCII header field extends beyond the header.",
            offset=offset,
        )
    try:
        value = data[offset + 1 : end].decode("ascii", errors="strict")
    except UnicodeDecodeError as error:
        raise ChV181StructureError(
            "AGILENT_CH_TEXT_ENCODING_INVALID",
            "A bounded ASCII header field is not valid ASCII.",
            offset=offset,
        ) from error
    if required and not value:
        raise ChV181StructureError(
            "AGILENT_CH_HEADER_INVALID",
            "A required header marker is empty.",
            offset=offset,
        )
    return value


def _utf16le_pascal_raw(data: bytes, offset: int) -> bytes:
    characters = data[offset]
    end = offset + 1 + characters * 2
    if end > len(data):
        raise ChV181StructureError(
            "AGILENT_CH_TEXT_ENCODING_INVALID",
            "A bounded UTF-16LE header field extends beyond the header.",
            offset=offset,
        )
    return data[offset + 1 : end]


def _utf16le_pascal(data: bytes, offset: int, *, required: bool = False) -> str:
    raw = _utf16le_pascal_raw(data, offset)
    try:
        value = raw.decode("utf-16-le", errors="strict")
    except UnicodeDecodeError as error:
        raise ChV181StructureError(
            "AGILENT_CH_TEXT_ENCODING_INVALID",
            "A bounded UTF-16LE header field is malformed.",
            offset=offset,
        ) from error
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ChV181StructureError(
            "AGILENT_CH_TEXT_ENCODING_INVALID",
            "A bounded UTF-16LE header field contains an isolated surrogate.",
            offset=offset,
        )
    if required and not value:
        raise ChV181StructureError(
            "AGILENT_CH_HEADER_INVALID",
            "A required header marker is empty.",
            offset=offset,
        )
    return value


def parse_v181_header(
    data: bytes, file_size: int, *, expected_version: int = EXPECTED_VERSION
) -> V181Header:
    """Validate the exact supported header family and return structural facts.

    The header family is shared with internal version 179, which differs only in how its
    record payload is stored, so the accepted version is a parameter.
    """
    if len(data) < HEADER_BYTES:
        raise ChV181StructureError(
            "AGILENT_CH_HEADER_TRUNCATED",
            f"The header family requires at least {HEADER_BYTES} header bytes.",
            expected=HEADER_BYTES,
            actual=len(data),
        )
    ascii_version = _ascii_pascal(data, 0, required=True)
    if ascii_version != str(expected_version):
        raise ChV181StructureError(
            "AGILENT_CH_VERSION_UNSUPPORTED",
            "The internal version text does not exactly match the supported profile.",
            offset=0,
            actual=ascii_version,
            expected=str(expected_version),
        )
    text_version = expected_version
    numeric_version = _u32(data, 248)
    if text_version != numeric_version:
        raise ChV181StructureError(
            "AGILENT_CH_VERSION_CONFLICT",
            "The two bounded internal version fields disagree.",
            text_version=text_version,
            numeric_version=numeric_version,
        )
    if numeric_version != expected_version:
        raise ChV181StructureError(
            "AGILENT_CH_VERSION_UNSUPPORTED",
            "The internal version is not the one this reader accepts.",
            actual=numeric_version,
            expected=expected_version,
        )
    family_marker = _utf16le_pascal(data, 347, required=True)
    if family_marker != "GC DATA FILE":
        raise ChV181StructureError(
            "AGILENT_CH_HEADER_INVALID",
            "The required GC data marker is absent.",
            offset=347,
        )
    data_page = _u32(data, 264)
    payload_offset = (data_page - 1) * 512 if data_page else -1
    if data_page != EXPECTED_DATA_PAGE or payload_offset != HEADER_BYTES:
        raise ChV181StructureError(
            "AGILENT_CH_PAYLOAD_OFFSET_INVALID",
            "The data-page field does not identify the supported payload boundary.",
            data_page=data_page,
            payload_offset=payload_offset,
        )
    if file_size <= payload_offset:
        raise ChV181StructureError(
            "AGILENT_CH_PAYLOAD_MISSING",
            "The file has no record payload after the validated header.",
            payload_offset=payload_offset,
            file_size=file_size,
        )
    software_text = _utf16le_pascal(data, 3089)
    if software_text != "Asterix ChemStation":
        raise ChV181StructureError(
            "AGILENT_CH_HEADER_INVALID",
            "The bounded producer text does not exactly match the validated profile.",
            offset=3089,
        )
    text_fields = (
        ("sample_text", _utf16le_pascal_raw(data, 858)),
        ("acquisition_local_text", _utf16le_pascal_raw(data, 2391)),
        ("header_text_2492", _utf16le_pascal_raw(data, 2492)),
        ("header_text_2533", _utf16le_pascal_raw(data, 2533)),
        ("method_text", _utf16le_pascal_raw(data, 2574)),
        ("software_text", _utf16le_pascal_raw(data, 3089)),
        ("unit_lexeme", _utf16le_pascal_raw(data, 4172)),
    )
    header_f32_0282 = _f32(data, 282)
    header_f32_0286 = _f32(data, 286)
    header_f64_4724 = _f64(data, 4724)
    header_f64_4732 = _f64(data, 4732)
    numeric_fields = (
        ("header_f32_0282", data[282:286]),
        ("header_f32_0286", data[286:290]),
        ("header_f64_4724", data[4724:4732]),
        ("header_f64_4732", data[4732:4740]),
    )
    for offset, value in (
        (282, header_f32_0282),
        (286, header_f32_0286),
        (4724, header_f64_4724),
        (4732, header_f64_4732),
    ):
        if not isfinite(value):
            raise ChV181StructureError(
                "AGILENT_CH_HEADER_INVALID",
                "A candidate numeric header field is not finite.",
                offset=offset,
            )
    return V181Header(
        version=numeric_version,
        payload_offset=payload_offset,
        family_marker=family_marker,
        sample_text=_utf16le_pascal(data, 858),
        acquisition_local_text=_utf16le_pascal(data, 2391),
        header_text_2492=_utf16le_pascal(data, 2492),
        header_text_2533=_utf16le_pascal(data, 2533),
        method_text=_utf16le_pascal(data, 2574),
        software_text=software_text,
        raw_unit_lexeme=_utf16le_pascal(data, 4172),
        header_f32_0282=header_f32_0282,
        header_f32_0286=header_f32_0286,
        header_u16_4122=_u16(data, 4122),
        header_u16_4124=_u16(data, 4124),
        header_f64_4724=header_f64_4724,
        header_f64_4732=header_f64_4732,
        raw_text_bytes_hex=tuple((name, raw.hex()) for name, raw in text_fields),
        raw_numeric_bytes_hex=tuple((name, raw.hex()) for name, raw in numeric_fields),
    )


def decode_v181_records(path: Path) -> DecodedV181Records:
    """Decode every complete candidate record in source order without scaling."""
    try:
        file_size = path.stat().st_size
        with path.open("rb") as stream:
            header_bytes = stream.read(HEADER_BYTES)
            header = parse_v181_header(header_bytes, file_size)
            stream.seek(header.payload_offset)
            values: list[int] = []
            absolute_count = 0
            ordinary_count = 0
            nonzero_ordinary_count = 0
            current: int | None = None
            delta = 0
            final_zero_ordinary_record = False
            while True:
                raw_word = stream.read(2)
                if not raw_word:
                    break
                if len(raw_word) != 2:
                    raise ChV181StructureError(
                        "AGILENT_CH_FILE_LENGTH_MISMATCH",
                        "The record payload ends with one unmatched byte.",
                        offset=stream.tell() - len(raw_word),
                    )
                word = struct.unpack(">h", raw_word)[0]
                if word == ABSOLUTE_RECORD_MARKER:
                    absolute = stream.read(6)
                    if len(absolute) != 6:
                        raise ChV181StructureError(
                            "AGILENT_CH_PAYLOAD_TRUNCATED",
                            "An absolute record marker is missing its six-byte value.",
                            offset=stream.tell() - len(absolute) - 2,
                        )
                    high, low = struct.unpack(">hI", absolute)
                    current = high * 2**32 + low
                    delta = 0
                    absolute_count += 1
                    final_zero_ordinary_record = False
                else:
                    if current is None:
                        raise ChV181StructureError(
                            "AGILENT_CH_HEADER_INVALID",
                            "The payload begins with a relative record before an absolute value.",
                            offset=header.payload_offset,
                        )
                    delta += word
                    current += delta
                    ordinary_count += 1
                    if word != 0:
                        nonzero_ordinary_count += 1
                    final_zero_ordinary_record = word == 0
                if current < MIN_I64 or current > MAX_I64:
                    raise ChV181StructureError(
                        "AGILENT_CH_INTEGER_OVERFLOW",
                        "Decoded record arithmetic exceeds the signed 64-bit boundary.",
                        record_index=len(values),
                    )
                values.append(current)
                if len(values) > MAX_DECODED_RECORDS:
                    raise ChV181StructureError(
                        "AGILENT_CH_RECORD_LIMIT",
                        "Decoded record count exceeds the adapter safety limit.",
                        limit=MAX_DECODED_RECORDS,
                    )
    except ChV181StructureError:
        raise
    except OSError as error:
        raise ChV181StructureError(
            "INPUT_READ_FAILED",
            f"Could not read the input ({type(error).__name__}).",
        ) from error
    if not values:
        raise ChV181StructureError(
            "AGILENT_CH_PAYLOAD_MISSING",
            "The validated payload contains no complete records.",
        )
    return DecodedV181Records(
        header=header,
        values=tuple(values),
        absolute_record_count=absolute_count,
        ordinary_record_count=ordinary_count,
        nonzero_ordinary_record_count=nonzero_ordinary_count,
        final_zero_ordinary_record=final_zero_ordinary_record,
        trailing_byte_count=0,
    )
