# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded clean-room reader for one exact ChromaTOF 4.72 GCxGC result profile."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import Any

from ordifile.core.workbook_text import MAX_WORKBOOK_CELL_CHARACTERS, workbook_text_is_exact

MAX_RESULT_BYTES = 32 * 1024 * 1024
MAX_RESULT_LINES = 100_001
MAX_LINE_CHARACTERS = 32_767
MAX_NUMERIC_LEXEME_CHARACTERS = 128
MAX_PEAKS = 100_000
MAX_SPECTRUM_PAIRS = 10_000

RESULT_HEADERS = (
    "Name",
    "1st Dimension Time (s)",
    "2nd Dimension Time (s)",
    "Area",
    "Height",
    "Spectra",
    "wb1",
    "wb2",
    "Retention Index",
)
RESULT_HEADER_LINE = "\t".join(RESULT_HEADERS)
_FAMILY_MARKERS = frozenset(RESULT_HEADERS)
_RARE_FAMILY_MARKERS = frozenset(("1st Dimension Time (s)", "2nd Dimension Time (s)", "wb1", "wb2"))
_MINIMUM_FAMILY_MARKERS = 5
_DECIMAL = re.compile(r"[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")
_SPECTRUM = re.compile(r"[1-9][0-9]*:[0-9]+(?: [1-9][0-9]*:[0-9]+)*\Z")


class LecoGcgcResultStructureError(Exception):
    """Privacy-safe structural failure translated by the public adapter."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True, slots=True)
class LecoGcgcResultPeak:
    """One source-order row from the exact nine-column result table."""

    observation_order: int
    source_row: int
    name: str
    retention_time_text: str
    retention_time: float
    secondary_retention_time_text: str
    secondary_retention_time: float
    area_text: str
    area: float
    height_text: str
    height: float
    spectra: str
    wb1_text: str
    wb2_text: str
    retention_index_text: str


@dataclass(frozen=True, slots=True)
class LecoGcgcResultData:
    """Allowlisted profile data and immutable source identity."""

    peaks: tuple[LecoGcgcResultPeak, ...]
    source_size: int
    source_sha256: str
    line_count: int


def _fail(code: str, message: str, **details: Any) -> LecoGcgcResultStructureError:
    return LecoGcgcResultStructureError(code, message, **details)


def _read_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            if size < len(RESULT_HEADER_LINE) or size > MAX_RESULT_BYTES:
                raise _fail(
                    "LECO_GCGC_RESULT_SIZE_INVALID",
                    "The GCxGC result size is outside the supported bounded profile.",
                    size_bytes=size,
                    maximum_bytes=MAX_RESULT_BYTES,
                )
            data = stream.read(MAX_RESULT_BYTES + 1)
            extra = stream.read(1)
    except LecoGcgcResultStructureError:
        raise
    except OSError as error:
        raise _fail("INPUT_READ_FAILED", "The GCxGC result input could not be read.") from error
    if len(data) > MAX_RESULT_BYTES or extra or len(data) != size:
        raise _fail(
            "LECO_GCGC_RESULT_SIZE_CHANGED",
            "The GCxGC result size changed during its bounded read.",
        )
    return data


def has_gcgc_result_family_identity(path: Path) -> bool:
    """Return whether a bounded first row identifies the observed result family."""
    try:
        with path.open("rb") as stream:
            prefix = stream.read(16 * 1024)
    except OSError:
        return False
    if not prefix or b"\x00" in prefix:
        return False
    first_line = prefix.splitlines()[0] if prefix.splitlines() else b""
    try:
        headers = first_line.decode("ascii", errors="strict").split("\t")
    except UnicodeDecodeError:
        return False
    header_set = set(headers)
    return bool(
        _RARE_FAMILY_MARKERS & header_set
        and len(_FAMILY_MARKERS & header_set) >= _MINIMUM_FAMILY_MARKERS
    )


def _lines(data: bytes) -> tuple[str, ...]:
    if data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data:
        raise _fail(
            "LECO_GCGC_RESULT_ENCODING_UNSUPPORTED",
            "The exact GCxGC result profile requires unmarked single-byte ASCII text.",
        )
    line_count = data.count(b"\r\n")
    if line_count > MAX_RESULT_LINES:
        raise _fail(
            "LECO_GCGC_RESULT_LINE_LIMIT",
            "The GCxGC result input exceeds the bounded line limit.",
            maximum_lines=MAX_RESULT_LINES,
        )
    remainder = data.replace(b"\r\n", b"")
    if b"\r" in remainder or b"\n" in remainder or not data.endswith(b"\r\n"):
        raise _fail(
            "LECO_GCGC_RESULT_LINE_ENDING_INVALID",
            "The exact GCxGC result profile requires complete CRLF records.",
        )
    try:
        text = data.decode("ascii", errors="strict")
    except UnicodeDecodeError as error:
        raise _fail(
            "LECO_GCGC_RESULT_ENCODING_UNSUPPORTED",
            "The exact GCxGC result profile requires single-byte ASCII text.",
        ) from error
    lines = tuple(text.split("\r\n")[:-1])
    if len(lines) != line_count:
        raise _fail(
            "LECO_GCGC_RESULT_LINE_ENDING_INVALID",
            "The GCxGC result records could not be split without loss.",
        )
    for line in lines:
        if len(line) > MAX_LINE_CHARACTERS or any(
            ord(character) < 32 and character != "\t" for character in line
        ):
            raise _fail(
                "LECO_GCGC_RESULT_TEXT_INVALID",
                "A GCxGC result record exceeds its bound or contains an unsupported control.",
            )
    return lines


def _decimal(text: str, *, field: str, source_row: int) -> tuple[str, float]:
    if len(text) > MAX_NUMERIC_LEXEME_CHARACTERS or _DECIMAL.fullmatch(text) is None:
        raise _fail(
            "LECO_GCGC_RESULT_NUMBER_INVALID",
            "A GCxGC result numeric field is outside the supported decimal grammar.",
            field=field,
            source_row=source_row,
        )
    try:
        exact = Decimal(text)
        value = float(exact)
    except (InvalidOperation, OverflowError, ValueError) as error:
        raise _fail(
            "LECO_GCGC_RESULT_NUMBER_INVALID",
            "A GCxGC result numeric field is invalid.",
            field=field,
            source_row=source_row,
        ) from error
    if not exact.is_finite() or not isfinite(value) or exact < 0:
        raise _fail(
            "LECO_GCGC_RESULT_NUMBER_INVALID",
            "A GCxGC result numeric field must be finite and nonnegative.",
            field=field,
            source_row=source_row,
        )
    if Decimal(str(value)) != exact:
        raise _fail(
            "LECO_GCGC_RESULT_LOSSY_FLOAT",
            "A GCxGC result numeric field cannot be represented exactly by the canonical model.",
            field=field,
            source_row=source_row,
        )
    return text, value


def _decimal_lexeme(text: str, *, field: str, source_row: int) -> str:
    """Validate an auxiliary decimal that remains exact source text in Metadata."""
    if len(text) > MAX_NUMERIC_LEXEME_CHARACTERS or _DECIMAL.fullmatch(text) is None:
        raise _fail(
            "LECO_GCGC_RESULT_NUMBER_INVALID",
            "A GCxGC result numeric field is outside the supported decimal grammar.",
            field=field,
            source_row=source_row,
        )
    try:
        exact = Decimal(text)
    except InvalidOperation as error:
        raise _fail(
            "LECO_GCGC_RESULT_NUMBER_INVALID",
            "A GCxGC result numeric field is invalid.",
            field=field,
            source_row=source_row,
        ) from error
    if not exact.is_finite() or exact < 0:
        raise _fail(
            "LECO_GCGC_RESULT_NUMBER_INVALID",
            "A GCxGC result numeric field must be finite and nonnegative.",
            field=field,
            source_row=source_row,
        )
    return text


def _source_text(text: str, *, field: str, source_row: int) -> str:
    if (
        not text
        or text != text.strip()
        or len(text) > MAX_WORKBOOK_CELL_CHARACTERS
        or not workbook_text_is_exact(text)
    ):
        raise _fail(
            "LECO_GCGC_RESULT_FIELD_INVALID",
            "A GCxGC result text field is empty or outside the exact workbook boundary.",
            field=field,
            source_row=source_row,
        )
    return text


def _peak(fields: list[str], *, observation_order: int) -> LecoGcgcResultPeak:
    source_row = observation_order + 1
    if len(fields) != len(RESULT_HEADERS):
        raise _fail(
            "LECO_GCGC_RESULT_ROW_INVALID",
            "A GCxGC result row does not match the exact column count.",
            source_row=source_row,
        )
    name = _source_text(fields[0], field="name", source_row=source_row)
    retention_text, retention_time = _decimal(
        fields[1], field="retention_time", source_row=source_row
    )
    secondary_text, secondary_retention_time = _decimal(
        fields[2], field="secondary_retention_time", source_row=source_row
    )
    area_text, area = _decimal(fields[3], field="area", source_row=source_row)
    height_text, height = _decimal(fields[4], field="height", source_row=source_row)
    spectra = _source_text(fields[5], field="spectra", source_row=source_row)
    if _SPECTRUM.fullmatch(spectra) is None or len(spectra.split(" ")) > MAX_SPECTRUM_PAIRS:
        raise _fail(
            "LECO_GCGC_RESULT_SPECTRUM_INVALID",
            "A GCxGC result spectrum is outside the observed integer-pair grammar.",
            source_row=source_row,
        )
    wb1_text = _decimal_lexeme(fields[6], field="wb1", source_row=source_row)
    wb2_text = _decimal_lexeme(fields[7], field="wb2", source_row=source_row)
    retention_index_text = _decimal_lexeme(
        fields[8], field="retention_index", source_row=source_row
    )
    return LecoGcgcResultPeak(
        observation_order,
        source_row,
        name,
        retention_text,
        retention_time,
        secondary_text,
        secondary_retention_time,
        area_text,
        area,
        height_text,
        height,
        spectra,
        wb1_text,
        wb2_text,
        retention_index_text,
    )


def read_gcgc_result(path: Path) -> LecoGcgcResultData:
    """Read one immutable, exact-profile result table without inferring missing values."""
    data = _read_bytes(path)
    lines = _lines(data)
    if not lines or lines[0] != RESULT_HEADER_LINE:
        raise _fail(
            "LECO_GCGC_RESULT_HEADER_INVALID",
            "The GCxGC result header does not match the exact observed profile.",
        )
    if len(lines) == 1:
        raise _fail(
            "LECO_GCGC_RESULT_EMPTY",
            "The GCxGC result table contains no peak rows.",
        )
    if len(lines) - 1 > MAX_PEAKS:
        raise _fail(
            "LECO_GCGC_RESULT_PEAK_LIMIT",
            "The GCxGC result table exceeds the bounded peak limit.",
            maximum_peaks=MAX_PEAKS,
        )
    peaks = tuple(
        _peak(line.split("\t"), observation_order=index)
        for index, line in enumerate(lines[1:], start=1)
    )
    return LecoGcgcResultData(
        peaks,
        len(data),
        hashlib.sha256(data).hexdigest(),
        len(lines),
    )
