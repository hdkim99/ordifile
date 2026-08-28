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

from ordifile.adapters.base import ParseOptions
from ordifile.adapters.youngin_yl_clarity_prm_raw import YoungInYlClarityPrmRawAdapter
from ordifile.core.models import DatasetBundle, SignalSeries

EXPECTED_ARCHIVE_SIZE = 1_155_037
EXPECTED_ARCHIVE_SHA256 = "5b0e44072ae0ca3a733bcb21515773f616d6eb1d2171886b4f299baf552e1568"
EXPECTED_MEMBER_COUNT = 20
EXPECTED_EXPANDED_BYTES = 5_684_379
EXPECTED_PAIRS = 10
EXPECTED_STREAMS = 10
EXPECTED_SIGNAL_POINTS = 119_790
EXPECTED_DERIVED_CANDIDATES = 28
EXPECTED_RESULT_ROWS = 38
EXPECTED_FAIL_CLOSED_ROWS = 10
EXPECTED_AREA_EXACT_BY_DECIMAL_PLACES = {2: 28, 3: 26, 4: 28}
EXPECTED_AREA_WITHIN_1_PERCENT = 28
EXPECTED_AREA_WITHIN_5_PERCENT = 28
EXPECTED_AREA_MEDIAN_RELATIVE_ERROR = 1.4620226185290704e-08
EXPECTED_AREA_P90_RELATIVE_ERROR = 1.3000537304618472e-06
EXPECTED_AREA_MAX_RELATIVE_ERROR = 6.049179949147435e-06
MAX_MEMBER_BYTES = 1_000_000
MAX_COMPRESSION_RATIO = 10.0
PRINTED_SIGNAL_HALF_UNIT = Decimal("0.00005001")
AREA_QUANTA = {2: Decimal("0.01"), 3: Decimal("0.001"), 4: Decimal("0.0001")}
TIME_LEXEME = re.compile(r"[0-9]+\.[0-9]{5}")
SIGNAL_LEXEME = re.compile(r"-?[0-9]+\.[0-9]{4}")


@dataclass(frozen=True, slots=True)
class _ResultRow:
    detector: str
    retention_time: Decimal
    area_text: str
    area: Decimal


@dataclass(frozen=True, slots=True)
class _CurveBlock:
    header: str
    lexemes: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _Export:
    curves: tuple[_CurveBlock, ...]
    rows: tuple[_ResultRow, ...]


def _archive() -> Path:
    value = os.environ.get("ORDIFILE_YOUNGIN_9_0_AREA_ARCHIVE")
    if not value:
        raise AssertionError("ORDIFILE_YOUNGIN_9_0_AREA_ARCHIVE is required")
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


def _curve_blocks(data: bytes) -> tuple[_CurveBlock, ...]:
    lines = data.decode("cp949", errors="strict").splitlines()
    blocks: list[_CurveBlock] = []
    for index, line in enumerate(lines):
        if not line.startswith("Time [min]\t"):
            continue
        rows: list[tuple[str, str]] = []
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
                Decimal(fields[0])
                Decimal(fields[1])
            except InvalidOperation:
                break
            rows.append((fields[0], fields[1]))
        if rows:
            blocks.append(_CurveBlock(line, tuple(rows)))
    return tuple(blocks)


def _result_rows(data: bytes) -> tuple[_ResultRow, ...]:
    rows: list[_ResultRow] = []
    for line in data.decode("cp949", errors="strict").splitlines():
        fields = line.split("\t")
        if (
            len(fields) < 9
            or not fields[3].strip().isdigit()
            or fields[4].strip() not in {"FID", "TCD"}
            or not fields[5].strip().isdigit()
        ):
            continue
        area_text = fields[7].strip()
        if re.fullmatch(r"[0-9]+\.[0-9]{4}", area_text) is None:
            raise AssertionError("official Result Area is not an exact nonnegative 4dp lexeme")
        try:
            official_area = Decimal(area_text)
            if not official_area.is_finite():
                raise AssertionError("official Result Area is not finite")
            rows.append(_ResultRow(fields[4].strip(), Decimal(fields[6]), area_text, official_area))
        except InvalidOperation as error:
            raise AssertionError("composite Result row contains a non-numeric value") from error
    return tuple(rows)


def _signal_matches(signal: SignalSeries, curve: _CurveBlock) -> bool:
    return len(signal.x_values) == len(signal.y_values) == len(curve.lexemes) and all(
        Decimal(format(x_value, ".5f")) == Decimal(time_text)
        and abs(Decimal(str(y_value)) - Decimal(response_text)) <= PRINTED_SIGNAL_HALF_UNIT
        for x_value, y_value, (time_text, response_text) in zip(
            signal.x_values, signal.y_values, curve.lexemes, strict=True
        )
    )


def _bundle_matches(bundle: DatasetBundle, export: _Export) -> bool:
    # One owner-controlled legacy export repeats its sole full curve block verbatim.
    # Collapse only exact duplicates; a distinct extra curve remains a pairing failure.
    distinct_curves = tuple(dict.fromkeys(export.curves))
    return len(bundle.signals) == len(distinct_curves) and all(
        _signal_matches(signal, curve)
        for signal, curve in zip(bundle.signals, distinct_curves, strict=True)
    )


def _derived_errors(
    bundle: DatasetBundle, rows: tuple[_ResultRow, ...]
) -> tuple[list[float], dict[int, int], int]:
    by_detector = {
        detector: tuple(peak for peak in bundle.peaks if peak.detector == detector)
        for detector in {row.detector for row in rows}
    }
    positions = {detector: 0 for detector in by_detector}
    errors: list[float] = []
    skipped = 0
    exact_by_decimal_places = {places: 0 for places in AREA_QUANTA}
    for row in rows:
        peaks = by_detector[row.detector]
        if not peaks:
            # The channel failed closed; its official rows are recorded as not compared.
            skipped += 1
            continue
        position = positions[row.detector]
        while (
            position < len(peaks)
            and Decimal(format(peaks[position].retention_time or 0.0, ".3f")) != row.retention_time
        ):
            position += 1
        assert position < len(peaks), "an official Result RT lacks its PRM marker candidate"
        peak = peaks[position]
        positions[row.detector] = position + 1
        assert peak.calculated_area is not None and row.area != 0
        for places, quantum in AREA_QUANTA.items():
            rendered = Decimal.from_float(float(peak.calculated_area)).quantize(
                quantum, rounding=ROUND_HALF_EVEN
            )
            official = row.area.quantize(quantum, rounding=ROUND_HALF_EVEN)
            exact_by_decimal_places[places] += rendered == official
        errors.append(float(abs(Decimal(str(peak.calculated_area)) - row.area) / abs(row.area)))
    assert all(
        positions[detector] == len(peaks) for detector, peaks in by_detector.items() if peaks
    )
    return errors, exact_by_decimal_places, skipped


def test_owner_area_archive_preserves_all_paired_result_residuals() -> None:
    archive = _archive()
    data = archive.read_bytes()
    assert len(data) == EXPECTED_ARCHIVE_SIZE
    assert _sha256(data) == EXPECTED_ARCHIVE_SHA256

    prm_data: list[bytes] = []
    exports: list[_Export] = []
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
            if suffix == ".prm":
                prm_data.append(member)
            elif suffix == ".csv":
                exports.append(_Export(_curve_blocks(member), _result_rows(member)))
            else:
                raise AssertionError("archive contains an unexpected member type")

    used_exports: set[int] = set()
    stream_count = 0
    signal_points = 0
    derived_candidates = 0
    area_errors: list[float] = []
    fail_closed_rows = 0
    exact_area_by_decimal_places = {places: 0 for places in AREA_QUANTA}
    with tempfile.TemporaryDirectory(prefix="ordifile-area-regression-") as directory:
        root = Path(directory)
        for member in prm_data:
            source_path = root / f"source-{_sha256(member)}.prm"
            source_path.write_bytes(member)
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
            stream_count += len(bundle.signals)
            signal_points += sum(len(signal.y_values) for signal in bundle.signals)
            derived_candidates += len(bundle.peaks)
            errors, exact, skipped = _derived_errors(bundle, exports[selected].rows)
            fail_closed_rows += skipped
            area_errors.extend(errors)
            for places, count in exact.items():
                exact_area_by_decimal_places[places] += count

    assert len(used_exports) == EXPECTED_PAIRS
    assert stream_count == EXPECTED_STREAMS
    assert signal_points == EXPECTED_SIGNAL_POINTS
    assert derived_candidates == EXPECTED_DERIVED_CANDIDATES
    assert fail_closed_rows == EXPECTED_FAIL_CLOSED_ROWS
    assert len(area_errors) + fail_closed_rows == EXPECTED_RESULT_ROWS
    assert exact_area_by_decimal_places == EXPECTED_AREA_EXACT_BY_DECIMAL_PLACES
    assert sum(error <= 0.01 for error in area_errors) == EXPECTED_AREA_WITHIN_1_PERCENT
    assert sum(error <= 0.05 for error in area_errors) == EXPECTED_AREA_WITHIN_5_PERCENT
    assert median(area_errors) == pytest.approx(EXPECTED_AREA_MEDIAN_RELATIVE_ERROR)
    ordered = sorted(area_errors)
    assert ordered[math.floor(0.9 * (len(ordered) - 1))] == pytest.approx(
        EXPECTED_AREA_P90_RELATIVE_ERROR
    )
    assert max(area_errors) == pytest.approx(EXPECTED_AREA_MAX_RELATIVE_ERROR)
    assert _sha256(archive.read_bytes()) == EXPECTED_ARCHIVE_SHA256
