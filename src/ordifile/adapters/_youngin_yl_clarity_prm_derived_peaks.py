# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Deterministic marker-assisted chromatographic calculations for YoungIn PRM."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ordifile.adapters._youngin_yl_clarity_prm_markers import PrmPeakWindow

DERIVATION_METHOD_ID_V2 = "youngin-prm-marker-timetable-lower-envelope-v2"
DERIVATION_METHOD_ID_V3 = "youngin-prm-marker-timetable-hybrid-contact-envelope-v3"
DERIVATION_ORIGIN = "ordifile_marker_derived"


@dataclass(frozen=True, slots=True)
class DerivedPrmPeak:
    """One Ordifile-derived peak using stored partitions and raw PRM signal."""

    retention_index: int
    start_index: int
    end_index: int
    area: float
    boundary_rule: str


def _cross(first: tuple[int, float], second: tuple[int, float], third: tuple[int, float]) -> float:
    return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (
        third[0] - first[0]
    )


def _lower_envelope(
    values: tuple[float, ...], start_index: int, end_index: int
) -> tuple[tuple[int, float], ...]:
    anchors: list[tuple[int, float]] = []
    for index in range(start_index, end_index + 1):
        point = (index, values[index])
        while len(anchors) >= 2 and _cross(anchors[-2], anchors[-1], point) <= 0.0:
            anchors.pop()
        anchors.append(point)
    return tuple(anchors)


def _baseline_values(
    anchors: tuple[tuple[int, float], ...], start_index: int, end_index: int
) -> tuple[float, ...]:
    baseline: list[float] = []
    segment = 0
    for index in range(start_index, end_index + 1):
        while segment + 1 < len(anchors) - 1 and index > anchors[segment + 1][0]:
            segment += 1
        left_index, left_value = anchors[segment]
        right_index, right_value = anchors[min(segment + 1, len(anchors) - 1)]
        if right_index == left_index:
            baseline.append(left_value)
        else:
            fraction = (index - left_index) / (right_index - left_index)
            baseline.append(left_value + fraction * (right_value - left_value))
    return tuple(baseline)


def _numeric_bound(value: float, baseline: float) -> float:
    scale = max(abs(value), abs(baseline), 1.0)
    return 8.0 * math.ulp(scale)


def _is_envelope_contact(value: float, baseline: float) -> bool:
    """Return whether two binary64 calculations describe the same hull contact."""
    difference = value - baseline
    bound = _numeric_bound(value, baseline)
    if difference < -bound:
        raise ValueError("the calculated baseline crosses the stored signal")
    return abs(difference) <= bound


def _corrected_response(value: float, baseline: float) -> float:
    difference = value - baseline
    bound = _numeric_bound(value, baseline)
    if difference < -bound:
        raise ValueError("the calculated baseline crosses the stored signal")
    return 0.0 if abs(difference) <= bound else difference


def _single_peak_base_to_base_bounds(
    values: tuple[float, ...],
    baseline: tuple[float, ...],
    window: PrmPeakWindow,
    retention_index: int,
) -> tuple[int, int]:
    """Narrow one independent marker cluster to its adjacent baseline contacts."""
    start_index = window.start_index
    end_index = window.end_index
    for index in range(retention_index - 1, window.start_index - 1, -1):
        if _is_envelope_contact(values[index], baseline[index - window.cluster_start_index]):
            start_index = index
            break
    for index in range(retention_index + 1, window.end_index + 1):
        if _is_envelope_contact(values[index], baseline[index - window.cluster_start_index]):
            end_index = index
            break
    if not start_index < retention_index < end_index:
        raise ValueError("a single-peak baseline lacks distinct contacts around its apex")
    return start_index, end_index


def derive_marker_peaks(
    values: tuple[float, ...],
    windows: tuple[PrmPeakWindow, ...],
    *,
    d_step: int,
    min_ticks: float,
    refine_single_peak_clusters: bool = False,
    original_single_peak_clusters: frozenset[tuple[int, int]] | None = None,
) -> tuple[DerivedPrmPeak, ...]:
    """Calculate peak RT indices and lower-envelope trapezoidal Areas.

    Stored markers provide every candidate partition.  For the evidence-bounded 9.0 Legacy
    mode, a cluster containing exactly one marker peak may be narrowed to the adjacent lower-
    envelope contacts before applying a straight base-to-base trapezoid.  The function never
    searches for a new apex or uses an external Result table.
    """
    if d_step <= 0 or not math.isfinite(min_ticks) or min_ticks <= 0:
        raise ValueError("time metadata must be finite and positive")
    if not windows:
        return ()
    if refine_single_peak_clusters and original_single_peak_clusters is None:
        raise ValueError("original marker cluster cardinality is required for refinement")
    single_peak_clusters = original_single_peak_clusters or frozenset()
    if any(
        window.start_index < 0
        or window.end_index >= len(values)
        or window.start_index > window.end_index
        or not window.start_index <= window.stored_apex_index <= window.end_index
        or window.cluster_start_index < 0
        or window.cluster_end_index >= len(values)
        or window.cluster_start_index > window.cluster_end_index
        or window.cluster_start_index > window.start_index
        or window.cluster_end_index < window.end_index
        for window in windows
    ):
        raise ValueError("marker window lies outside the signal")

    dt_seconds = 60.0 * d_step / min_ticks
    baseline_cache: dict[tuple[int, int], tuple[float, ...]] = {}
    derived: list[DerivedPrmPeak] = []
    for window in windows:
        cluster = (window.cluster_start_index, window.cluster_end_index)
        baseline = baseline_cache.get(cluster)
        if baseline is None:
            anchors = _lower_envelope(values, *cluster)
            baseline = _baseline_values(anchors, *cluster)
            baseline_cache[cluster] = baseline

        retention_index = max(
            range(window.start_index, window.end_index + 1),
            key=values.__getitem__,
        )
        start_index = window.start_index
        end_index = window.end_index
        boundary_rule = "cluster_envelope_partition"
        if refine_single_peak_clusters and cluster in single_peak_clusters:
            start_index, end_index = _single_peak_base_to_base_bounds(
                values,
                baseline,
                window,
                retention_index,
            )
            boundary_rule = "adjacent_contact_straight_baseline"
            left_value = values[start_index]
            right_value = values[end_index]
            baseline = tuple(
                left_value
                + (right_value - left_value) * (index - start_index) / (end_index - start_index)
                for index in range(start_index, end_index + 1)
            )
            baseline_offset = start_index
        else:
            baseline_offset = window.cluster_start_index
        corrected = tuple(
            _corrected_response(values[index], baseline[index - baseline_offset])
            for index in range(start_index, end_index + 1)
        )
        area = math.fsum(
            (left + right) * 0.5 * dt_seconds
            for left, right in zip(corrected, corrected[1:], strict=False)
        )
        derived.append(
            DerivedPrmPeak(
                retention_index,
                start_index,
                end_index,
                area,
                boundary_rule,
            )
        )
    return tuple(derived)
