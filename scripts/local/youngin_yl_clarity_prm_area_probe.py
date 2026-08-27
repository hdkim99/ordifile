#!/usr/bin/env python3
# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Compare local-only PRM-derived Areas with same-run composite Result exports.

Only aggregate counts and error statistics are printed. Source names, paths, measured
arrays, and row values are deliberately excluded from the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
import tempfile
from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from statistics import median
from zipfile import ZipFile, ZipInfo

from ordifile.adapters._youngin_yl_clarity_prm_binary import read_prm
from ordifile.adapters._youngin_yl_clarity_prm_derived_peaks import derive_marker_peaks
from ordifile.adapters._youngin_yl_clarity_prm_markers import (
    PrmPeakWindow,
    build_peak_windows,
    read_prm_markers,
)
from ordifile.adapters.base import ParseOptions
from ordifile.adapters.youngin_yl_clarity_prm_raw import YoungInYlClarityPrmRawAdapter
from ordifile.core.models import DatasetBundle, SignalSeries

MAX_ARCHIVE_MEMBERS = 100
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100.0
SIGNAL_PRINTED_BOUND = Decimal("0.00005001")
AREA_PRINTED_HALF_QUANTUM = Decimal("0.00005")
AREA_PRECISION_QUANTA = {
    2: Decimal("0.01"),
    3: Decimal("0.001"),
    4: Decimal("0.0001"),
}
_TIME_LEXEME = re.compile(r"[0-9]+\.[0-9]{5}")
_SIGNAL_LEXEME = re.compile(r"-?[0-9]+\.[0-9]{4}")
_AREA_LEXEME = re.compile(r"[0-9]+\.[0-9]{4}")
_BOUNDARY_AREA_LEXEME = re.compile(r"[0-9]+\.[0-9]{3}")


@dataclass(frozen=True, slots=True)
class _ResultRow:
    detector: str
    peak_number: int
    retention_time: Decimal
    area: Decimal
    area_text: str
    height: Decimal
    area_percent: Decimal
    height_percent: Decimal
    width_at_half_height: Decimal


@dataclass(frozen=True, slots=True)
class _BoundaryRow:
    detector: str
    peak_number: int
    retention_time: Decimal
    start_time: Decimal
    end_time: Decimal
    area: Decimal
    height: Decimal


@dataclass(frozen=True, slots=True)
class _CurveBlock:
    header: str
    lexemes: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _Export:
    digest: str
    curves: tuple[_CurveBlock, ...]
    rows: tuple[_ResultRow, ...]
    boundaries: tuple[_BoundaryRow, ...]


@dataclass(slots=True)
class _Stratum:
    rows: int = 0
    exact_at_4dp: int = 0
    within_1_percent: int = 0
    within_5_percent: int = 0
    relative_errors: list[float] | None = None

    def __post_init__(self) -> None:
        if self.relative_errors is None:
            self.relative_errors = []


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
                _TIME_LEXEME.fullmatch(fields[0]) is None
                or _SIGNAL_LEXEME.fullmatch(fields[1]) is None
            ):
                raise ValueError("a full-curve row does not use the expected numeric precision")
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
    lines = data.decode("cp949", errors="strict").splitlines()
    rows: list[_ResultRow] = []
    for line in lines:
        fields = line.split("\t")
        if (
            len(fields) < 12
            or not fields[3].strip().isdigit()
            or fields[4].strip() not in {"FID", "TCD"}
            or not fields[5].strip().isdigit()
        ):
            continue
        if _AREA_LEXEME.fullmatch(fields[7].strip()) is None:
            raise ValueError("a Result Area is not an exact nonnegative four-decimal lexeme")
        try:
            rows.append(
                _ResultRow(
                    fields[4].strip(),
                    int(fields[5]),
                    Decimal(fields[6]),
                    Decimal(fields[7]),
                    fields[7],
                    Decimal(fields[8]),
                    Decimal(fields[9]),
                    Decimal(fields[10]),
                    Decimal(fields[11]),
                )
            )
        except InvalidOperation as error:
            raise ValueError("a composite Result row is not numeric") from error
    return tuple(rows)


def _boundary_rows(data: bytes) -> tuple[_BoundaryRow, ...]:
    """Read displayed non-fixed Result boundaries and bind them by scientific values."""
    lines = data.decode("cp949", errors="strict").splitlines()
    section_rows: list[tuple[int, Decimal, Decimal, Decimal, Decimal, Decimal]] = []
    all_signal_rows: list[tuple[str, int, Decimal, Decimal]] = []
    boundary_header = (
        "Primary File",
        "Date",
        "Time",
        "Peak No.",
        "Reten. Time [min]",
        "Start Time [min]",
        "End Time [min]",
    )
    all_signal_header = (
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
                if _BOUNDARY_AREA_LEXEME.fullmatch(values[7].strip()) is None:
                    raise ValueError(
                        "a boundary-table Area is not an exact nonnegative three-decimal lexeme"
                    )
                try:
                    section_rows.append(
                        (
                            int(values[3]),
                            Decimal(values[4]),
                            Decimal(values[5]),
                            Decimal(values[6]),
                            Decimal(values[7]),
                            Decimal(values[8]),
                        )
                    )
                except InvalidOperation as error:
                    raise ValueError("a non-fixed Result boundary row is not numeric") from error
        elif fields[: len(all_signal_header)] == all_signal_header:
            for candidate in lines[index + 1 :]:
                values = candidate.split("\t")
                if (
                    len(values) < 8
                    or not values[3].strip().isdigit()
                    or values[5].strip() not in {"FID", "TCD"}
                ):
                    break
                if _BOUNDARY_AREA_LEXEME.fullmatch(values[7].strip()) is None:
                    raise ValueError(
                        "an All Signals Area is not an exact nonnegative three-decimal lexeme"
                    )
                try:
                    all_signal_rows.append(
                        (
                            values[5].strip(),
                            int(values[3]),
                            Decimal(values[6]),
                            Decimal(values[7]),
                        )
                    )
                except InvalidOperation as error:
                    raise ValueError("a non-fixed All Signals row is not numeric") from error

    boundaries: list[_BoundaryRow] = []
    for peak_number, retention_time, start_time, end_time, area, height in section_rows:
        matches = tuple(
            (detector, candidate_area)
            for detector, candidate_number, candidate_rt, candidate_area in all_signal_rows
            if candidate_number == peak_number
            and candidate_rt == retention_time
            and candidate_area == area
        )
        if len(matches) != 1:
            raise ValueError("a non-fixed Result boundary row has ambiguous signal identity")
        boundaries.append(
            _BoundaryRow(
                matches[0][0],
                peak_number,
                retention_time,
                start_time,
                end_time,
                area,
                height,
            )
        )
    return tuple(boundaries)


def _signal_matches_curve(signal: SignalSeries, curve: _CurveBlock) -> bool:
    if len(signal.x_values) != len(curve.lexemes) or len(signal.y_values) != len(curve.lexemes):
        return False
    for x_value, y_value, (time_text, response_text) in zip(
        signal.x_values,
        signal.y_values,
        curve.lexemes,
        strict=True,
    ):
        time = Decimal(time_text)
        response = Decimal(response_text)
        if Decimal(format(x_value, ".5f")) != time:
            return False
        if abs(Decimal(str(y_value)) - response) > SIGNAL_PRINTED_BOUND:
            return False
    return True


def _distinct_curve_blocks(curves: tuple[_CurveBlock, ...]) -> tuple[_CurveBlock, ...]:
    """Collapse only blocks with identical header and original numeric lexemes."""
    return tuple(dict.fromkeys(curves))


def _bundle_matches_export(bundle: DatasetBundle, export: _Export) -> bool:
    # One legacy composite export repeats the same full curve block verbatim.  Collapse
    # only byte-for-byte/numerically identical blocks; any distinct extra curve still
    # prevents a confirmed pairing.
    distinct_curves = _distinct_curve_blocks(export.curves)
    return len(bundle.signals) == len(distinct_curves) and all(
        _signal_matches_curve(signal, curve)
        for signal, curve in zip(bundle.signals, distinct_curves, strict=True)
    )


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.floor(fraction * (len(ordered) - 1))]


def _trapezoidal_area(
    values: tuple[float, ...], start: int, end: int, *, baseline_mode: str
) -> float:
    if end <= start:
        return 0.0
    if baseline_mode == "window_linear":
        left = values[start]
        right = values[end]
        corrected = tuple(
            max(0.0, values[index] - (left + (right - left) * (index - start) / (end - start)))
            for index in range(start, end + 1)
        )
    elif baseline_mode == "endpoint_minimum":
        baseline = min(values[start], values[end])
        corrected = tuple(max(0.0, values[index] - baseline) for index in range(start, end + 1))
    elif baseline_mode == "zero":
        corrected = tuple(max(0.0, values[index]) for index in range(start, end + 1))
    else:
        raise ValueError(f"unknown baseline mode: {baseline_mode}")
    return math.fsum(
        (left + right) * 0.5 for left, right in zip(corrected, corrected[1:], strict=False)
    )


def _validate_archive(path: Path) -> tuple[list[bytes], list[_Export]]:
    prm_data: list[bytes] = []
    exports: list[_Export] = []
    with ZipFile(path) as archive:
        infos = archive.infolist()
        if not infos or len(infos) > MAX_ARCHIVE_MEMBERS or archive.testzip() is not None:
            raise ValueError("archive member/CRC validation failed")
        if sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES:
            raise ValueError("archive expanded-size bound failed")
        if len({info.filename.casefold() for info in infos}) != len(infos):
            raise ValueError("archive has duplicate member paths")
        for info in infos:
            if (
                not _safe_member(info)
                or info.file_size > MAX_MEMBER_BYTES
                or info.compress_size < 1
                or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise ValueError("archive member safety validation failed")
            data = archive.read(info)
            suffix = PurePosixPath(info.filename).suffix.casefold()
            if suffix == ".prm":
                prm_data.append(data)
            elif suffix == ".csv":
                exports.append(
                    _Export(
                        _sha256(data),
                        _curve_blocks(data),
                        _result_rows(data),
                        _boundary_rows(data),
                    )
                )
            elif suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
                # Privacy-safe settings screenshots may accompany an owner oracle.  They
                # are inspected separately and are never part of the numeric comparison.
                continue
            else:
                raise ValueError("archive contains an unexpected member type")
    return prm_data, exports


def _probe(paths: tuple[Path, ...]) -> dict[str, object]:
    pair_count = 0
    unmatched_prms = 0
    official_rows = 0
    rt_matches = 0
    derived_candidates = 0
    exact_area_by_decimal_places = {places: 0 for places in AREA_PRECISION_QUANTA}
    within_half_quantum_by_decimal_places = {places: 0 for places in AREA_PRECISION_QUANTA}
    within_area_printed_half_quantum = 0
    calculated_area_above_official = 0
    calculated_area_below_official = 0
    within_one_percent = 0
    within_five_percent = 0
    relative_errors: list[float] = []
    profile_counts: dict[str, int] = {}
    detector_rows: dict[str, int] = {}
    strata: dict[str, _Stratum] = {}
    candidate_mode_errors: dict[str, list[float]] = {
        "window_linear": [],
        "endpoint_minimum": [],
        "zero": [],
    }
    candidate_mode_exact = {
        mode: {places: 0 for places in AREA_PRECISION_QUANTA} for mode in candidate_mode_errors
    }
    feature_errors: dict[str, list[float]] = {}
    archive_hashes: list[str] = []
    official_boundary_rows = 0
    boundary_rows_aligned = 0
    boundary_start_printed_matches = 0
    boundary_end_printed_matches = 0
    boundary_start_nearest_record_matches = 0
    boundary_end_nearest_record_matches = 0
    boundary_candidate_rows = 0
    boundary_candidate_exact = {places: 0 for places in AREA_PRECISION_QUANTA}
    boundary_candidate_errors: list[float] = []
    boundary_start_record_offsets: Counter[int] = Counter()
    boundary_end_record_offsets: Counter[int] = Counter()

    with tempfile.TemporaryDirectory(prefix="ordifile-youngin-area-") as directory:
        temporary_root = Path(directory)
        for archive_index, path in enumerate(paths):
            archive_bytes = path.read_bytes()
            archive_hashes.append(_sha256(archive_bytes))
            prm_data, exports = _validate_archive(path)
            used_exports: set[int] = set()
            for prm_index, data in enumerate(prm_data):
                source_digest = _sha256(data)
                source = temporary_root / f"source-{archive_index}-{prm_index}-{source_digest}.prm"
                source.write_bytes(data)
                bundle = YoungInYlClarityPrmRawAdapter().parse(
                    source,
                    ParseOptions(experimental_derived_area=True),
                )
                decoded = read_prm(source)
                marker_decode = read_prm_markers(
                    source,
                    expected_sha256=decoded.source_sha256,
                    layout=decoded.current_revision_layout,
                    record_counts=tuple(channel.record_count for channel in decoded.channels),
                )
                windows_by_detector: dict[str, tuple[PrmPeakWindow, ...]] = {}
                if marker_decode.status == "matched":
                    for channel, markers in zip(
                        decoded.channels, marker_decode.channels, strict=True
                    ):
                        windows_by_detector[channel.stored_detector_label] = build_peak_windows(
                            markers
                        ).windows
                candidates = [
                    index
                    for index, export in enumerate(exports)
                    if index not in used_exports and _bundle_matches_export(bundle, export)
                ]
                if len(candidates) != 1:
                    unmatched_prms += 1
                    continue
                export_index = candidates[0]
                used_exports.add(export_index)
                export = exports[export_index]
                pair_count += 1
                profile = next(
                    str(entry.value) for entry in bundle.metadata if entry.key == "producer_version"
                )
                profile_counts[profile] = profile_counts.get(profile, 0) + 1
                derived_candidates += len(bundle.peaks)
                comparison_rows = export.rows or tuple(
                    _ResultRow(
                        row.detector,
                        row.peak_number,
                        row.retention_time,
                        row.area,
                        format(row.area, "f"),
                        row.height,
                        Decimal(0),
                        Decimal(0),
                        Decimal(0),
                    )
                    for row in export.boundaries
                )
                official_boundary_rows += len(export.boundaries)
                by_detector = {
                    detector: tuple(peak for peak in bundle.peaks if peak.detector == detector)
                    for detector in {row.detector for row in comparison_rows}
                }
                positions = {detector: 0 for detector in by_detector}
                for row in comparison_rows:
                    official_rows += 1
                    detector_rows[row.detector] = detector_rows.get(row.detector, 0) + 1
                    peaks = by_detector[row.detector]
                    position = positions[row.detector]
                    while (
                        position < len(peaks)
                        and Decimal(format(peaks[position].retention_time or 0.0, ".3f"))
                        != row.retention_time
                    ):
                        position += 1
                    if position == len(peaks):
                        positions[row.detector] = position
                        continue
                    peak = peaks[position]
                    positions[row.detector] = position + 1
                    rt_matches += 1
                    if peak.calculated_area is None:
                        continue
                    derived_area = Decimal(str(peak.calculated_area))
                    difference = abs(derived_area - row.area)
                    stratum_key = f"{profile}|{row.detector}"
                    stratum = strata.setdefault(stratum_key, _Stratum())
                    stratum.rows += 1
                    for places, quantum in AREA_PRECISION_QUANTA.items():
                        rounded_binary64 = Decimal.from_float(float(peak.calculated_area)).quantize(
                            quantum,
                            rounding=ROUND_HALF_EVEN,
                        )
                        rounded_official = row.area.quantize(quantum, rounding=ROUND_HALF_EVEN)
                        if rounded_binary64 == rounded_official:
                            exact_area_by_decimal_places[places] += 1
                            if places == 4:
                                stratum.exact_at_4dp += 1
                        if difference <= quantum / 2:
                            within_half_quantum_by_decimal_places[places] += 1
                    if difference <= AREA_PRINTED_HALF_QUANTUM:
                        within_area_printed_half_quantum += 1
                    if derived_area > row.area:
                        calculated_area_above_official += 1
                    elif derived_area < row.area:
                        calculated_area_below_official += 1
                    if row.area != 0:
                        relative = float(difference / abs(row.area))
                        relative_errors.append(relative)
                        stratum_errors = stratum.relative_errors
                        assert stratum_errors is not None
                        stratum_errors.append(relative)
                        if relative <= 0.01:
                            within_one_percent += 1
                            stratum.within_1_percent += 1
                        if relative <= 0.05:
                            within_five_percent += 1
                            stratum.within_5_percent += 1
                        windows = windows_by_detector.get(row.detector, ())
                        matching_windows = tuple(
                            window
                            for window in windows
                            if peak.start_time is not None
                            and peak.end_time is not None
                            and window.start_index == round(peak.start_time * 600)
                            and window.end_index == round(peak.end_time * 600)
                        )
                        if len(matching_windows) == 1:
                            window = matching_windows[0]
                            cluster_size = sum(
                                candidate.cluster_start_index == window.cluster_start_index
                                and candidate.cluster_end_index == window.cluster_end_index
                                for candidate in windows
                            )
                            feature_errors.setdefault(f"cluster_size={cluster_size}", []).append(
                                relative
                            )
                            feature_errors.setdefault(
                                "raw_apex_matches_marker="
                                f"{peak.retention_time == window.stored_apex_index / 600}",
                                [],
                            ).append(relative)
                        matching_signal = next(
                            signal for signal in bundle.signals if signal.detector == row.detector
                        )
                        matching_channel = next(
                            channel
                            for channel in decoded.channels
                            if channel.stored_detector_label == row.detector
                        )
                        boundary_matches = tuple(
                            boundary
                            for boundary in export.boundaries
                            if boundary.detector == row.detector
                            and boundary.peak_number == row.peak_number
                            and boundary.retention_time == row.retention_time
                            and boundary.area == row.area
                        )
                        if len(boundary_matches) == 1 and len(matching_windows) == 1:
                            boundary = boundary_matches[0]
                            window = matching_windows[0]
                            boundary_rows_aligned += 1
                            dt_minutes = Decimal(matching_channel.d_step_candidate) / Decimal(
                                str(matching_channel.min_ticks_candidate)
                            )
                            marker_start = Decimal(window.start_index) * dt_minutes
                            marker_end = Decimal(window.end_index) * dt_minutes
                            if (
                                marker_start.quantize(Decimal("0.001"), rounding=ROUND_HALF_EVEN)
                                == boundary.start_time
                            ):
                                boundary_start_printed_matches += 1
                            if (
                                marker_end.quantize(Decimal("0.001"), rounding=ROUND_HALF_EVEN)
                                == boundary.end_time
                            ):
                                boundary_end_printed_matches += 1
                            start_index = int(
                                (boundary.start_time / dt_minutes).to_integral_value(
                                    rounding=ROUND_HALF_EVEN
                                )
                            )
                            end_index = int(
                                (boundary.end_time / dt_minutes).to_integral_value(
                                    rounding=ROUND_HALF_EVEN
                                )
                            )
                            if start_index == window.start_index:
                                boundary_start_nearest_record_matches += 1
                            if end_index == window.end_index:
                                boundary_end_nearest_record_matches += 1
                            boundary_start_record_offsets[start_index - window.start_index] += 1
                            boundary_end_record_offsets[end_index - window.end_index] += 1
                            if (
                                window.cluster_start_index <= start_index <= end_index
                                and end_index <= window.cluster_end_index
                            ):
                                candidate_window = PrmPeakWindow(
                                    start_index,
                                    window.stored_apex_index,
                                    end_index,
                                    window.cluster_start_index,
                                    window.cluster_end_index,
                                )
                                candidate_peak = derive_marker_peaks(
                                    matching_signal.y_values,
                                    (candidate_window,),
                                    d_step=matching_channel.d_step_candidate,
                                    min_ticks=matching_channel.min_ticks_candidate,
                                )[0]
                                candidate_float = candidate_peak.area
                                candidate = Decimal(str(candidate_float))
                                boundary_candidate_rows += 1
                                if row.area != 0:
                                    boundary_candidate_errors.append(
                                        float(abs(candidate - row.area) / abs(row.area))
                                    )
                                for places, quantum in AREA_PRECISION_QUANTA.items():
                                    if Decimal.from_float(candidate_float).quantize(
                                        quantum,
                                        rounding=ROUND_HALF_EVEN,
                                    ) == row.area.quantize(quantum, rounding=ROUND_HALF_EVEN):
                                        boundary_candidate_exact[places] += 1
                        if peak.start_time is not None and peak.end_time is not None:
                            start = round(peak.start_time * 600)
                            end = round(peak.end_time * 600)
                            for mode, errors in candidate_mode_errors.items():
                                candidate_float = _trapezoidal_area(
                                    matching_signal.y_values,
                                    start,
                                    end,
                                    baseline_mode=mode,
                                ) * (
                                    (matching_signal.x_values[1] - matching_signal.x_values[0])
                                    * 60.0
                                )
                                candidate = Decimal(str(candidate_float))
                                errors.append(float(abs(candidate - row.area) / abs(row.area)))
                                for places, quantum in AREA_PRECISION_QUANTA.items():
                                    if Decimal.from_float(candidate_float).quantize(
                                        quantum,
                                        rounding=ROUND_HALF_EVEN,
                                    ) == row.area.quantize(quantum, rounding=ROUND_HALF_EVEN):
                                        candidate_mode_exact[mode][places] += 1

    stratum_report: dict[str, dict[str, object]] = {}
    for key, stratum in sorted(strata.items()):
        errors = stratum.relative_errors or []
        stratum_report[key] = {
            "rows": stratum.rows,
            "exact_at_4dp": stratum.exact_at_4dp,
            "within_1_percent": stratum.within_1_percent,
            "within_5_percent": stratum.within_5_percent,
            "median_relative_error": median(errors) if errors else None,
            "p90_relative_error": _percentile(errors, 0.9),
            "max_relative_error": max(errors) if errors else None,
        }

    return {
        "schema": "ordifile-youngin-prm-derived-area-probe-v1",
        "archive_count": len(paths),
        "archive_sha256": sorted(archive_hashes),
        "confirmed_pair_count": pair_count,
        "unmatched_prm_count": unmatched_prms,
        "profile_pair_counts": dict(sorted(profile_counts.items())),
        "official_result_rows": official_rows,
        "detector_result_rows": dict(sorted(detector_rows.items())),
        "derived_candidate_rows": derived_candidates,
        "retention_time_matches_at_3dp": rt_matches,
        "area_exact_by_decimal_places": exact_area_by_decimal_places,
        "area_within_half_quantum_by_decimal_places": within_half_quantum_by_decimal_places,
        "area_exact_at_4dp": exact_area_by_decimal_places[4],
        "area_within_printed_half_quantum": within_area_printed_half_quantum,
        "calculated_area_above_official": calculated_area_above_official,
        "calculated_area_below_official": calculated_area_below_official,
        "area_within_1_percent": within_one_percent,
        "area_within_5_percent": within_five_percent,
        "area_median_relative_error": (median(relative_errors) if relative_errors else None),
        "area_p90_relative_error": _percentile(relative_errors, 0.9),
        "area_max_relative_error": max(relative_errors) if relative_errors else None,
        "area_strata": stratum_report,
        "candidate_baseline_modes": {
            mode: {
                "rows": len(errors),
                "exact_by_decimal_places": candidate_mode_exact[mode],
                "within_1_percent": sum(error <= 0.01 for error in errors),
                "within_5_percent": sum(error <= 0.05 for error in errors),
                "median_relative_error": median(errors) if errors else None,
                "p90_relative_error": _percentile(errors, 0.9),
                "max_relative_error": max(errors) if errors else None,
            }
            for mode, errors in candidate_mode_errors.items()
        },
        "feature_errors": {
            feature: {
                "rows": len(errors),
                "within_1_percent": sum(error <= 0.01 for error in errors),
                "within_5_percent": sum(error <= 0.05 for error in errors),
                "median_relative_error": median(errors) if errors else None,
                "p90_relative_error": _percentile(errors, 0.9),
                "max_relative_error": max(errors) if errors else None,
            }
            for feature, errors in sorted(feature_errors.items())
        },
        "official_boundary_rows": official_boundary_rows,
        "boundary_rows_aligned": boundary_rows_aligned,
        "boundary_start_printed_matches": boundary_start_printed_matches,
        "boundary_end_printed_matches": boundary_end_printed_matches,
        "boundary_start_nearest_record_matches": boundary_start_nearest_record_matches,
        "boundary_end_nearest_record_matches": boundary_end_nearest_record_matches,
        "boundary_start_record_offset_counts": dict(sorted(boundary_start_record_offsets.items())),
        "boundary_end_record_offset_counts": dict(sorted(boundary_end_record_offsets.items())),
        "boundary_candidate_rows": boundary_candidate_rows,
        "boundary_candidate_exact_by_decimal_places": boundary_candidate_exact,
        "boundary_candidate_median_relative_error": (
            median(boundary_candidate_errors) if boundary_candidate_errors else None
        ),
        "boundary_candidate_p90_relative_error": _percentile(boundary_candidate_errors, 0.9),
        "boundary_candidate_max_relative_error": (
            max(boundary_candidate_errors) if boundary_candidate_errors else None
        ),
        "runtime_result_csv_dependency": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare local YoungIn PRM marker-derived Areas with composite oracles."
    )
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    report = _probe(tuple(args.archives))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
