from __future__ import annotations

import hashlib
import math
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from statistics import median
from zipfile import ZipFile, ZipInfo

import pytest

from ordifile.adapters._youngin_yl_clarity_prm_binary import read_prm
from ordifile.adapters.base import ParseOptions
from ordifile.adapters.youngin_yl_clarity_prm_raw import YoungInYlClarityPrmRawAdapter
from ordifile.core.models import DatasetBundle, SignalSeries

EXPECTED_ARCHIVE_SIZE = 907_058
EXPECTED_ARCHIVE_SHA256 = "0846fe27ffae90f67f05a2ae191a3bc2e7b9dcc894e9441648d5ad1c0453efd0"
EXPECTED_MEMBER_COUNT = 8
EXPECTED_EXPANDED_BYTES = 2_597_121
EXPECTED_PAIRS = 2
EXPECTED_STREAMS = 4
EXPECTED_SIGNAL_POINTS = 52_700
EXPECTED_RESULT_ROWS = 25
EXPECTED_BOUNDARY_ROWS = 25
EXPECTED_DERIVED_ROWS = 18
EXPECTED_AREA_EXACT_BY_DECIMAL_PLACES = {2: 9, 3: 5, 4: 0}
EXPECTED_AREA_WITHIN_1_PERCENT = 13
EXPECTED_AREA_WITHIN_5_PERCENT = 13
EXPECTED_AREA_MEDIAN_RELATIVE_ERROR = 0.0011490070117224072
EXPECTED_AREA_P90_RELATIVE_ERROR = 0.13691660391767188
EXPECTED_AREA_MAX_RELATIVE_ERROR = 0.3126668575000758
EXPECTED_OFFICIAL_BOUNDARY_EXACT_BY_DECIMAL_PLACES = {2: 16, 3: 7, 4: 0}
MAX_MEMBER_BYTES = 800_000
MAX_COMPRESSION_RATIO = 6.0
PRINTED_SIGNAL_HALF_UNIT = Decimal("0.00005001")
AREA_QUANTA = {2: Decimal("0.01"), 3: Decimal("0.001"), 4: Decimal("0.0001")}
TIME_LEXEME = re.compile(r"[0-9]+\.[0-9]{5}")
SIGNAL_LEXEME = re.compile(r"-?[0-9]+\.[0-9]{4}")
BOUNDARY_AREA_LEXEME = re.compile(r"[0-9]+\.[0-9]{3}")


@dataclass(frozen=True, slots=True)
class _ResultRow:
    detector: str
    peak_number: int
    retention_time: Decimal
    area: Decimal


@dataclass(frozen=True, slots=True)
class _BoundaryRow:
    detector: str
    peak_number: int
    retention_time: Decimal
    start_time: Decimal
    end_time: Decimal
    area: Decimal


@dataclass(frozen=True, slots=True)
class _Export:
    curves: tuple[tuple[tuple[Decimal, Decimal], ...], ...]
    rows: tuple[_ResultRow, ...]
    boundaries: tuple[_BoundaryRow, ...]


def _archive() -> Path:
    value = os.environ.get("ORDIFILE_YOUNGIN_9_0_NONFIXED_ARCHIVE")
    if not value:
        raise AssertionError("ORDIFILE_YOUNGIN_9_0_NONFIXED_ARCHIVE is required")
    return Path(value)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_member(info: ZipInfo) -> bool:
    pure = PurePosixPath(info.filename)
    mode = (info.external_attr >> 16) & 0xFFFF
    return (
        not info.is_dir()
        and not (info.flag_bits & 0x1)
        and "\\" not in info.filename
        and not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in pure.parts)
        and (mode == 0 or stat.S_ISREG(mode))
    )


def _curve_blocks(data: bytes) -> tuple[tuple[tuple[Decimal, Decimal], ...], ...]:
    lines = data.decode("cp949", errors="strict").splitlines()
    blocks: list[tuple[tuple[Decimal, Decimal], ...]] = []
    for index, line in enumerate(lines):
        if line != "Time [min]\tVoltage [mV]":
            continue
        rows: list[tuple[Decimal, Decimal]] = []
        for candidate in lines[index + 1 :]:
            fields = candidate.split("\t")
            if len(fields) != 2:
                break
            if (
                TIME_LEXEME.fullmatch(fields[0]) is None
                or SIGNAL_LEXEME.fullmatch(fields[1]) is None
            ):
                raise AssertionError("curve precision changed")
            try:
                rows.append((Decimal(fields[0]), Decimal(fields[1])))
            except InvalidOperation as error:
                raise AssertionError("curve contains a non-numeric row") from error
        if rows:
            blocks.append(tuple(rows))
    return tuple(blocks)


def _boundary_rows(data: bytes) -> tuple[_BoundaryRow, ...]:
    lines = data.decode("cp949", errors="strict").splitlines()
    sections: list[tuple[int, Decimal, Decimal, Decimal, Decimal]] = []
    all_signals: list[tuple[str, int, Decimal, Decimal]] = []
    boundary_header = (
        "Primary File",
        "Date",
        "Time",
        "Peak No.",
        "Reten. Time [min]",
        "Start Time [min]",
        "End Time [min]",
    )
    signal_header = (
        "Primary File",
        "Date",
        "Time",
        "Peak No.",
        "Signal",
        "Signal Name",
        "Reten. Time [min]",
    )
    for index, line in enumerate(lines):
        fields = tuple(line.split("\t"))
        if fields[: len(boundary_header)] == boundary_header:
            for candidate in lines[index + 1 :]:
                values = candidate.split("\t")
                if len(values) < 9 or not values[3].strip().isdigit():
                    break
                if BOUNDARY_AREA_LEXEME.fullmatch(values[7].strip()) is None:
                    raise AssertionError(
                        "boundary-table Area is not an exact nonnegative 3dp lexeme"
                    )
                try:
                    sections.append(
                        (
                            int(values[3]),
                            Decimal(values[4]),
                            Decimal(values[5]),
                            Decimal(values[6]),
                            Decimal(values[7]),
                        )
                    )
                except InvalidOperation as error:
                    raise AssertionError("boundary row contains a non-numeric value") from error
        elif fields[: len(signal_header)] == signal_header:
            for candidate in lines[index + 1 :]:
                values = candidate.split("\t")
                if (
                    len(values) < 8
                    or not values[3].strip().isdigit()
                    or values[5].strip() not in {"FID", "TCD"}
                ):
                    break
                if BOUNDARY_AREA_LEXEME.fullmatch(values[7].strip()) is None:
                    raise AssertionError("signal Area is not an exact nonnegative 3dp lexeme")
                try:
                    all_signals.append(
                        (
                            values[5].strip(),
                            int(values[3]),
                            Decimal(values[6]),
                            Decimal(values[7]),
                        )
                    )
                except InvalidOperation as error:
                    raise AssertionError("signal row contains a non-numeric value") from error

    boundaries: list[_BoundaryRow] = []
    for peak_number, retention_time, start_time, end_time, area in sections:
        matches = tuple(
            (detector, candidate_area)
            for detector, candidate_number, candidate_rt, candidate_area in all_signals
            if candidate_number == peak_number
            and candidate_rt == retention_time
            and candidate_area == area
        )
        assert len(matches) == 1
        boundaries.append(
            _BoundaryRow(
                matches[0][0],
                peak_number,
                retention_time,
                start_time,
                end_time,
                area,
            )
        )
    return tuple(boundaries)


def _signal_matches_curve(signal: SignalSeries, curve: tuple[tuple[Decimal, Decimal], ...]) -> bool:
    return len(signal.x_values) == len(curve) == len(signal.y_values) and all(
        Decimal(format(x_value, ".5f")) == time
        and abs(Decimal(str(y_value)) - response) <= PRINTED_SIGNAL_HALF_UNIT
        for x_value, y_value, (time, response) in zip(
            signal.x_values,
            signal.y_values,
            curve,
            strict=True,
        )
    )


def _bundle_matches(bundle: DatasetBundle, export: _Export) -> bool:
    return len(bundle.signals) == len(export.curves) and all(
        _signal_matches_curve(signal, curve)
        for signal, curve in zip(bundle.signals, export.curves, strict=True)
    )


def _quantized_matches(candidate: float, official: Decimal) -> dict[int, bool]:
    return {
        places: Decimal.from_float(candidate).quantize(quantum, rounding=ROUND_HALF_EVEN)
        == official.quantize(quantum, rounding=ROUND_HALF_EVEN)
        for places, quantum in AREA_QUANTA.items()
    }


def _derived_errors(
    bundle: DatasetBundle, rows: tuple[_ResultRow, ...]
) -> tuple[list[float], dict[int, int]]:
    by_detector = {
        detector: tuple(peak for peak in bundle.peaks if peak.detector == detector)
        for detector in {row.detector for row in rows}
    }
    positions = {detector: 0 for detector in by_detector}
    errors: list[float] = []
    exact = {places: 0 for places in AREA_QUANTA}
    for row in rows:
        peaks = by_detector[row.detector]
        position = positions[row.detector]
        while (
            position < len(peaks)
            and Decimal(format(peaks[position].retention_time or 0.0, ".3f")) != row.retention_time
        ):
            position += 1
        assert position < len(peaks)
        peak = peaks[position]
        positions[row.detector] = position + 1
        assert peak.area is None
        assert peak.calculated_area is not None
        assert peak.derivation_method_id == (
            "youngin-prm-marker-timetable-hybrid-contact-envelope-v3"
        )
        for places, matched in _quantized_matches(peak.calculated_area, row.area).items():
            exact[places] += matched
        errors.append(float(abs(Decimal(str(peak.calculated_area)) - row.area) / abs(row.area)))
    assert all(positions[detector] == len(peaks) for detector, peaks in by_detector.items())
    return errors, exact


def _display_index(signal: SignalSeries, displayed_time: Decimal) -> int:
    matches = tuple(
        index
        for index, value in enumerate(signal.x_values)
        if Decimal(format(value, ".3f")) == displayed_time
    )
    assert len(matches) == 1
    return matches[0]


def _official_boundary_area(signal: SignalSeries, row: _BoundaryRow) -> float:
    start = _display_index(signal, row.start_time)
    end = _display_index(signal, row.end_time)
    assert start < end
    left = signal.y_values[start]
    right = signal.y_values[end]
    corrected = tuple(
        max(
            0.0,
            signal.y_values[index] - (left + (right - left) * (index - start) / (end - start)),
        )
        for index in range(start, end + 1)
    )
    dt_seconds = (signal.x_values[1] - signal.x_values[0]) * 60.0
    return math.fsum(
        (first + second) * 0.5 * dt_seconds
        for first, second in zip(corrected, corrected[1:], strict=False)
    )


def test_nonfixed_owner_archive_fixes_expanded_scientific_and_area_evidence() -> None:
    archive = _archive()
    data = archive.read_bytes()
    assert len(data) == EXPECTED_ARCHIVE_SIZE
    assert _sha256(data) == EXPECTED_ARCHIVE_SHA256

    prm_data: list[bytes] = []
    exports: list[_Export] = []
    suffix_counts: dict[str, int] = {}
    with ZipFile(archive) as source:
        infos = source.infolist()
        assert len(infos) == EXPECTED_MEMBER_COUNT
        assert sum(info.file_size for info in infos) == EXPECTED_EXPANDED_BYTES
        assert source.testzip() is None
        assert all(_safe_member(info) for info in infos)
        assert all(
            info.file_size <= MAX_MEMBER_BYTES
            and info.compress_size > 0
            and info.file_size / info.compress_size <= MAX_COMPRESSION_RATIO
            for info in infos
        )
        assert len({info.filename.casefold() for info in infos}) == EXPECTED_MEMBER_COUNT
        for info in infos:
            member = source.read(info)
            suffix = PurePosixPath(info.filename).suffix.casefold()
            suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
            if suffix == ".prm":
                prm_data.append(member)
            elif suffix == ".csv":
                boundaries = _boundary_rows(member)
                exports.append(
                    _Export(
                        _curve_blocks(member),
                        tuple(
                            _ResultRow(
                                row.detector,
                                row.peak_number,
                                row.retention_time,
                                row.area,
                            )
                            for row in boundaries
                        ),
                        boundaries,
                    )
                )
            elif suffix != ".png":
                raise AssertionError("archive contains an unexpected member type")
    assert suffix_counts == {".prm": 2, ".csv": 2, ".png": 4}

    used_exports: set[int] = set()
    histories: list[int] = []
    stream_count = 0
    signal_points = 0
    result_rows = 0
    boundary_rows = 0
    derived_rows = 0
    area_errors: list[float] = []
    exact = {places: 0 for places in AREA_QUANTA}
    official_boundary_exact = {places: 0 for places in AREA_QUANTA}
    fail_closed_history_count = 0
    with tempfile.TemporaryDirectory(prefix="ordifile-nonfixed-regression-") as directory:
        root = Path(directory)
        for member in prm_data:
            source_path = root / f"source-{_sha256(member)}.prm"
            source_path.write_bytes(member)
            decoded = read_prm(source_path)
            histories.append(decoded.history_count)
            bundle = YoungInYlClarityPrmRawAdapter().parse(
                source_path,
                ParseOptions(experimental_derived_area=True),
            )
            matches = [
                index
                for index, export in enumerate(exports)
                if index not in used_exports and _bundle_matches(bundle, export)
            ]
            assert len(matches) == 1
            selected = matches[0]
            used_exports.add(selected)
            export = exports[selected]
            stream_count += len(bundle.signals)
            signal_points += sum(len(signal.y_values) for signal in bundle.signals)
            result_rows += len(export.rows)
            boundary_rows += len(export.boundaries)
            derived_rows += len(bundle.peaks)

            if bundle.peaks:
                errors, derived_exact = _derived_errors(bundle, export.rows)
                area_errors.extend(errors)
                for places, count in derived_exact.items():
                    exact[places] += count
            else:
                assert decoded.history_count == 4
                statuses = {
                    entry.value
                    for entry in bundle.metadata
                    if entry.key.endswith("processing_time_table_status")
                }
                assert "time_table_opcode_unsupported" in statuses
                assert len(bundle.signals) == 2
                fail_closed_history_count += 1

            signals = {signal.detector: signal for signal in bundle.signals}
            for boundary in export.boundaries:
                candidate = _official_boundary_area(signals[boundary.detector], boundary)
                for places, is_match in _quantized_matches(candidate, boundary.area).items():
                    official_boundary_exact[places] += is_match

    assert len(used_exports) == EXPECTED_PAIRS
    assert sorted(histories) == [2, 4]
    assert fail_closed_history_count == 1
    assert stream_count == EXPECTED_STREAMS
    assert signal_points == EXPECTED_SIGNAL_POINTS
    assert result_rows == EXPECTED_RESULT_ROWS
    assert boundary_rows == EXPECTED_BOUNDARY_ROWS
    assert derived_rows == EXPECTED_DERIVED_ROWS
    assert len(area_errors) == EXPECTED_DERIVED_ROWS
    assert exact == EXPECTED_AREA_EXACT_BY_DECIMAL_PLACES
    assert sum(error <= 0.01 for error in area_errors) == EXPECTED_AREA_WITHIN_1_PERCENT
    assert sum(error <= 0.05 for error in area_errors) == EXPECTED_AREA_WITHIN_5_PERCENT
    assert median(area_errors) == pytest.approx(EXPECTED_AREA_MEDIAN_RELATIVE_ERROR)
    ordered = sorted(area_errors)
    assert ordered[math.floor(0.9 * (len(ordered) - 1))] == pytest.approx(
        EXPECTED_AREA_P90_RELATIVE_ERROR
    )
    assert max(area_errors) == pytest.approx(EXPECTED_AREA_MAX_RELATIVE_ERROR)
    assert official_boundary_exact == EXPECTED_OFFICIAL_BOUNDARY_EXACT_BY_DECIMAL_PLACES
    assert _sha256(archive.read_bytes()) == EXPECTED_ARCHIVE_SHA256
