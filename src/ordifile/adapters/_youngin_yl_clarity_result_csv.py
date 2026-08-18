# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded reader for one owner-provenance YL-Clarity Result Table profile."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import Any

MAX_RESULT_CSV_BYTES = 32 * 1024 * 1024
MAX_RESULT_CSV_LINES = 100_000
MAX_LINE_CHARACTERS = 32_767
MAX_NUMERIC_LEXEME_CHARACTERS = 128
MAX_PEAKS_PER_SIGNAL = 100_000
MAX_SIGNALS = 32

RESULT_HEADERS = (
    "Signal No.",
    "Signal Name",
    "Peak No.",
    "Reten. time [min]",
    "Area [mV.s]",
    "Height [mV]",
    "Area [%]",
    "Height [%]",
    "W05 [min]",
)
RESULT_HEADER_LINE = "\t".join(RESULT_HEADERS)
_FAMILY_PREFIX = b"Signal No.\tSignal Name\tPeak No.\t"
_METADATA_FIELD_COUNTS = (4, 5, 2, 4, 34, 5, 7, 2)
_COMPOUND_HEADER = (
    "",
    "",
    "",
    "",
    "",
    "Reten. Time [min]",
    "Response",
    "Amount [N/A]",
    "Amount% [%]",
    "Peak Type",
    "Compound Name",
)
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")
_POSITIVE_INTEGER = re.compile(r"[1-9][0-9]*\Z")
_SIGNAL_NAMES = frozenset(("FID", "TCD"))


class YoungInResultCsvStructureError(Exception):
    """Privacy-safe structural failure translated by the public adapter."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True, slots=True)
class YoungInResultPeak:
    """One exact source-order peak row."""

    signal_number: int
    signal_name: str
    peak_number: int
    observation_order: int
    retention_time_text: str
    retention_time: float
    area_text: str
    area: float
    height_text: str
    height: float
    area_percent_text: str
    area_percent: float
    height_percent_text: str
    height_percent: float
    width_05_text: str
    width_05: float


@dataclass(frozen=True, slots=True)
class YoungInResultSignal:
    """One signal section, including an explicit no-peak state."""

    signal_number: int
    signal_name: str
    peaks: tuple[YoungInResultPeak, ...]
    no_peaks_reported: bool


@dataclass(frozen=True, slots=True)
class YoungInResultCsvData:
    """Allowlisted scientific and structural facts from the exact export."""

    signals: tuple[YoungInResultSignal, ...]
    peaks: tuple[YoungInResultPeak, ...]
    source_size: int
    source_sha256: str
    line_count: int


def _fail(code: str, message: str, **details: Any) -> YoungInResultCsvStructureError:
    return YoungInResultCsvStructureError(code, message, **details)


def _read_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            if size < len(RESULT_HEADER_LINE) or size > MAX_RESULT_CSV_BYTES:
                raise _fail(
                    "YOUNGIN_RESULT_CSV_SIZE_INVALID",
                    "The Result Table export size is outside the supported bounded profile.",
                    size_bytes=size,
                    maximum_bytes=MAX_RESULT_CSV_BYTES,
                )
            data = stream.read(MAX_RESULT_CSV_BYTES + 1)
            extra = stream.read(1)
    except YoungInResultCsvStructureError:
        raise
    except OSError as error:
        raise _fail("INPUT_READ_FAILED", "The Result Table input could not be read.") from error
    if len(data) > MAX_RESULT_CSV_BYTES or extra or len(data) != size:
        raise _fail(
            "YOUNGIN_RESULT_CSV_SIZE_CHANGED",
            "The Result Table input size changed during its bounded read.",
        )
    return data


def has_result_csv_family_identity(path: Path) -> bool:
    """Return whether a bounded first row identifies the observed Result Table family."""
    try:
        with path.open("rb") as stream:
            prefix = stream.read(4 * 1024)
    except OSError:
        return False
    first_line = prefix.split(b"\r\n", 1)[0]
    return first_line.startswith(_FAMILY_PREFIX) and b"Reten. time" in first_line


def _lines(data: bytes) -> tuple[str, ...]:
    if data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data:
        raise _fail(
            "YOUNGIN_RESULT_CSV_ENCODING_UNSUPPORTED",
            "The exact Result Table profile requires unmarked CP949-compatible text.",
        )
    line_count = data.count(b"\r\n")
    if line_count > MAX_RESULT_CSV_LINES:
        raise _fail(
            "YOUNGIN_RESULT_CSV_LINE_LIMIT",
            "The Result Table input exceeds the bounded line limit.",
            maximum_lines=MAX_RESULT_CSV_LINES,
        )
    remainder = data.replace(b"\r\n", b"")
    if b"\r" in remainder or b"\n" in remainder or not data.endswith(b"\r\n\r\n"):
        raise _fail(
            "YOUNGIN_RESULT_CSV_LINE_ENDING_INVALID",
            "The exact Result Table profile requires complete CRLF records.",
        )
    try:
        text = data.decode("cp949", errors="strict")
    except UnicodeDecodeError as error:
        raise _fail(
            "YOUNGIN_RESULT_CSV_ENCODING_UNSUPPORTED",
            "The exact Result Table profile requires CP949-compatible text.",
        ) from error
    lines = tuple(text.split("\r\n")[:-1])
    if len(lines) != line_count:
        raise _fail(
            "YOUNGIN_RESULT_CSV_LINE_ENDING_INVALID",
            "The Result Table records could not be split without loss.",
        )
    for line in lines:
        if len(line) > MAX_LINE_CHARACTERS or any(
            ord(character) < 32 and character != "\t" for character in line
        ):
            raise _fail(
                "YOUNGIN_RESULT_CSV_TEXT_INVALID",
                "A Result Table record exceeds its bound or contains an unsupported control.",
            )
    return lines


def _positive_integer(text: str, *, field: str, maximum: int) -> int:
    if len(text) > MAX_NUMERIC_LEXEME_CHARACTERS or _POSITIVE_INTEGER.fullmatch(text) is None:
        raise _fail(
            "YOUNGIN_RESULT_CSV_INTEGER_INVALID",
            "A Result Table integer is outside the supported grammar.",
            field=field,
        )
    value = int(text)
    if value > maximum:
        raise _fail(
            "YOUNGIN_RESULT_CSV_INTEGER_INVALID",
            "A Result Table integer exceeds its bounded range.",
            field=field,
            maximum=maximum,
        )
    return value


def _decimal(text: str, *, field: str, nonnegative: bool = True) -> tuple[Decimal, float]:
    if len(text) > MAX_NUMERIC_LEXEME_CHARACTERS or _DECIMAL.fullmatch(text) is None:
        raise _fail(
            "YOUNGIN_RESULT_CSV_NUMBER_INVALID",
            "A Result Table numeric field is outside the supported decimal grammar.",
            field=field,
        )
    try:
        exact = Decimal(text)
        value = float(exact)
    except (InvalidOperation, OverflowError, ValueError) as error:
        raise _fail(
            "YOUNGIN_RESULT_CSV_NUMBER_INVALID",
            "A Result Table numeric field is invalid.",
            field=field,
        ) from error
    if not exact.is_finite() or not isfinite(value):
        raise _fail(
            "YOUNGIN_RESULT_CSV_NUMBER_INVALID",
            "A Result Table numeric field must be finite.",
            field=field,
        )
    if Decimal(str(value)) != exact:
        raise _fail(
            "YOUNGIN_RESULT_CSV_LOSSY_FLOAT",
            "A Result Table numeric field cannot be represented exactly by the canonical model.",
            field=field,
        )
    if nonnegative and exact < 0:
        raise _fail(
            "YOUNGIN_RESULT_CSV_RESPONSE_INVALID",
            "A Result Table response or time field must be nonnegative.",
            field=field,
        )
    return exact, value


def _section_identity(fields: list[str]) -> tuple[int, str]:
    signal_number = _positive_integer(fields[0], field="signal_number", maximum=MAX_SIGNALS)
    signal_name = fields[1]
    if signal_name not in _SIGNAL_NAMES:
        raise _fail(
            "YOUNGIN_RESULT_CSV_SIGNAL_UNSUPPORTED",
            "The Result Table signal name is outside the observed exact profile.",
            signal_number=signal_number,
        )
    return signal_number, signal_name


def _parse_peak(
    fields: list[str],
    *,
    signal_number: int,
    signal_name: str,
    observation_order: int,
) -> tuple[YoungInResultPeak, tuple[Decimal, Decimal]]:
    if len(fields) != len(RESULT_HEADERS):
        raise _fail(
            "YOUNGIN_RESULT_CSV_PEAK_ROW_INVALID",
            "A Result Table peak row does not match the exact column count.",
            observation_order=observation_order,
        )
    row_signal_number, row_signal_name = _section_identity(fields)
    if (row_signal_number, row_signal_name) != (signal_number, signal_name):
        raise _fail(
            "YOUNGIN_RESULT_CSV_SIGNAL_MISMATCH",
            "A Result Table peak row changed signal identity within its section.",
            observation_order=observation_order,
        )
    peak_number = _positive_integer(fields[2], field="peak_number", maximum=MAX_PEAKS_PER_SIGNAL)
    if peak_number != observation_order:
        raise _fail(
            "YOUNGIN_RESULT_CSV_PEAK_ORDER_INVALID",
            "Source peak numbers must be contiguous and preserve section row order.",
            observation_order=observation_order,
        )
    retention_exact, retention_time = _decimal(fields[3], field="retention_time")
    area_exact, area = _decimal(fields[4], field="area")
    height_exact, height = _decimal(fields[5], field="height")
    _area_percent_exact, area_percent = _decimal(fields[6], field="area_percent")
    _height_percent_exact, height_percent = _decimal(fields[7], field="height_percent")
    _width_exact, width_05 = _decimal(fields[8], field="width_05")
    peak = YoungInResultPeak(
        signal_number,
        signal_name,
        peak_number,
        observation_order,
        fields[3],
        retention_time,
        fields[4],
        area,
        fields[5],
        height,
        fields[6],
        area_percent,
        fields[7],
        height_percent,
        fields[8],
        width_05,
    )
    del retention_exact
    return peak, (area_exact, height_exact)


def _parse_total(
    fields: list[str],
    *,
    signal_number: int,
    signal_name: str,
    area_sum: Decimal,
    height_sum: Decimal,
) -> None:
    if (
        len(fields) != len(RESULT_HEADERS)
        or fields[2] != ""
        or fields[3] != "Total"
        or fields[8] != ""
        or _section_identity(fields) != (signal_number, signal_name)
    ):
        raise _fail(
            "YOUNGIN_RESULT_CSV_TOTAL_INVALID",
            "The Result Table Total row does not match its signal section.",
            signal_number=signal_number,
        )
    total_area, _ = _decimal(fields[4], field="total_area")
    total_height, _ = _decimal(fields[5], field="total_height")
    _decimal(fields[6], field="total_area_percent")
    _decimal(fields[7], field="total_height_percent")
    if total_area != area_sum or total_height != height_sum:
        raise _fail(
            "YOUNGIN_RESULT_CSV_TOTAL_MISMATCH",
            "A Result Table Total does not match the exact source peak responses.",
            signal_number=signal_number,
        )


def _parse_signals(lines: tuple[str, ...]) -> tuple[tuple[YoungInResultSignal, ...], int]:
    cursor = 0
    signals: list[YoungInResultSignal] = []
    while cursor < len(lines) and lines[cursor] == RESULT_HEADER_LINE:
        cursor += 1
        if cursor >= len(lines):
            raise _fail(
                "YOUNGIN_RESULT_CSV_SECTION_TRUNCATED",
                "A Result Table signal section is truncated after its header.",
            )
        fields = lines[cursor].split("\t")
        if len(fields) < 3:
            raise _fail(
                "YOUNGIN_RESULT_CSV_SECTION_INVALID",
                "A Result Table signal section has no valid first row.",
            )
        signal_number, signal_name = _section_identity(fields)
        expected_number = len(signals) + 1
        if signal_number != expected_number or any(
            item.signal_name == signal_name for item in signals
        ):
            raise _fail(
                "YOUNGIN_RESULT_CSV_SIGNAL_ORDER_INVALID",
                "Signal sections must be sequential and uniquely named.",
                expected_signal_number=expected_number,
            )

        if fields[2] == "No peak to report":
            if len(fields) != 25 or any(fields[3:]):
                raise _fail(
                    "YOUNGIN_RESULT_CSV_NO_PEAK_ROW_INVALID",
                    "The explicit no-peak row is outside the observed exact profile.",
                    signal_number=signal_number,
                )
            peaks: tuple[YoungInResultPeak, ...] = ()
            no_peaks_reported = True
            cursor += 1
        else:
            parsed: list[YoungInResultPeak] = []
            area_sum = Decimal(0)
            height_sum = Decimal(0)
            while cursor < len(lines):
                fields = lines[cursor].split("\t")
                if len(fields) == len(RESULT_HEADERS) and fields[3] == "Total":
                    break
                peak, exact_responses = _parse_peak(
                    fields,
                    signal_number=signal_number,
                    signal_name=signal_name,
                    observation_order=len(parsed) + 1,
                )
                parsed.append(peak)
                if len(parsed) > MAX_PEAKS_PER_SIGNAL:
                    raise _fail(
                        "YOUNGIN_RESULT_CSV_PEAK_LIMIT",
                        "A Result Table signal exceeds the bounded peak limit.",
                        signal_number=signal_number,
                    )
                area_sum += exact_responses[0]
                height_sum += exact_responses[1]
                cursor += 1
            if not parsed or cursor >= len(lines):
                raise _fail(
                    "YOUNGIN_RESULT_CSV_TOTAL_MISSING",
                    "A populated Result Table signal requires one Total row.",
                    signal_number=signal_number,
                )
            _parse_total(
                lines[cursor].split("\t"),
                signal_number=signal_number,
                signal_name=signal_name,
                area_sum=area_sum,
                height_sum=height_sum,
            )
            peaks = tuple(parsed)
            no_peaks_reported = False
            cursor += 1
        if cursor >= len(lines) or lines[cursor] != "":
            raise _fail(
                "YOUNGIN_RESULT_CSV_SECTION_TERMINATOR_MISSING",
                "A Result Table signal section is missing its blank terminator.",
                signal_number=signal_number,
            )
        cursor += 1
        signals.append(YoungInResultSignal(signal_number, signal_name, peaks, no_peaks_reported))
        if len(signals) > MAX_SIGNALS:
            raise _fail(
                "YOUNGIN_RESULT_CSV_SIGNAL_LIMIT",
                "The Result Table exceeds the bounded signal limit.",
                maximum_signals=MAX_SIGNALS,
            )
    if not signals:
        raise _fail(
            "YOUNGIN_RESULT_CSV_HEADER_INVALID",
            "The exact Result Table header was not found at the start of the export.",
        )
    observed_profile = tuple(
        (item.signal_number, item.signal_name, bool(item.peaks), item.no_peaks_reported)
        for item in signals
    )
    if observed_profile not in {
        ((1, "TCD", True, False),),
        ((1, "FID", False, True), (2, "TCD", True, False)),
    }:
        raise _fail(
            "YOUNGIN_RESULT_CSV_PROFILE_UNSUPPORTED",
            "The signal-section combination is outside the two owner-validated profiles.",
        )
    return tuple(signals), cursor


def _validate_private_trailer(lines: tuple[str, ...], cursor: int, *, signal_count: int) -> None:
    """Validate shape only; privacy-bearing metadata values never leave this reader."""
    for block_index in range(signal_count):
        for expected_count in _METADATA_FIELD_COUNTS:
            if cursor >= len(lines) or len(lines[cursor].split("\t")) != expected_count:
                raise _fail(
                    "YOUNGIN_RESULT_CSV_TRAILER_INVALID",
                    "The private metadata trailer is outside the observed bounded shape.",
                    metadata_block=block_index + 1,
                )
            cursor += 1
        if cursor + 1 >= len(lines) or lines[cursor : cursor + 2] != ("", ""):
            raise _fail(
                "YOUNGIN_RESULT_CSV_TRAILER_INVALID",
                "A private metadata block is missing its exact separator.",
                metadata_block=block_index + 1,
            )
        cursor += 2
    if cursor + 2 >= len(lines):
        raise _fail(
            "YOUNGIN_RESULT_CSV_TRAILER_TRUNCATED",
            "The Result Table trailer is incomplete.",
        )
    report_header = lines[cursor].split("\t")
    if (
        len(report_header) != 11
        or report_header[:2] != ["", ""]
        or any(not value for value in report_header[2:5])
        or any(report_header[5:])
    ):
        raise _fail(
            "YOUNGIN_RESULT_CSV_TRAILER_INVALID",
            "The final report header is outside the observed bounded shape.",
        )
    if tuple(lines[cursor + 1].split("\t")) != _COMPOUND_HEADER:
        raise _fail(
            "YOUNGIN_RESULT_CSV_COMPOUND_HEADER_INVALID",
            "The empty compound table header is outside the observed exact profile.",
        )
    if lines[cursor + 2 :] != ("",):
        raise _fail(
            "YOUNGIN_RESULT_CSV_TRAILER_INVALID",
            "Unexpected rows follow the observed empty compound table.",
        )


def read_result_csv(path: Path) -> YoungInResultCsvData:
    """Read one observed Result Table export without exposing private trailer values."""
    data = _read_bytes(path)
    lines = _lines(data)
    signals, cursor = _parse_signals(lines)
    _validate_private_trailer(lines, cursor, signal_count=len(signals))
    peaks = tuple(peak for signal in signals for peak in signal.peaks)
    return YoungInResultCsvData(
        signals,
        peaks,
        len(data),
        hashlib.sha256(data).hexdigest(),
        len(lines),
    )
