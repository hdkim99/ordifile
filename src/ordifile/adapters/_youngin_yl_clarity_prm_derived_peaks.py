# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Deterministic marker-assisted chromatographic calculations for YoungIn PRM.

The stored marker stream describes peak partitions.  This module turns those
partitions into peak groups, one straight baseline per group, and an Area, using
only the PRM file itself.  No vendor library, Result table or composite export is
read at runtime.

The Area summation is not the general trapezoidal rule.  It is the
controlled-corpus-derived form that pairs the response at the left edge of each
interval with the baseline at the centre of that interval; see
`docs/research/youngin-yl-clarity-prm-derived-area-investigation.md`.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ordifile.adapters._youngin_yl_clarity_prm_markers import PrmPeakWindow

DERIVATION_METHOD_ID_V4 = "youngin-prm-marker-group-baseline-v4"
DERIVATION_ORIGIN = "ordifile_marker_derived"

BOUNDARY_RULE_GROUP_BASELINE = "marker_group_straight_baseline"

# Resolving one stored cluster re-scans a sample range per peak group, so an adversarial or
# corrupt marker stream can ask for quadratic work while still satisfying the bounded marker
# reader.  Every scan is charged against a budget, which makes the work deterministic rather
# than merely finite.  The cost of one cluster is about `groups * span / 2` visits, so the
# per-sample multiplier is in effect a ceiling of roughly `2 * multiplier` baseline-separated
# groups inside a single stored cluster.  The owner-controlled corpus needs at most 3.22 visits
# per stored sample, so this leaves a wide margin for legitimate chromatograms.  The absolute
# maximum keeps a very long channel from stalling a conversion before it fails closed.
_RESOLUTION_VISIT_BUDGET_PER_SAMPLE = 1024
_RESOLUTION_VISIT_BUDGET_MAXIMUM = 32_000_000


def _resolution_visit_budget(sample_count: int) -> int:
    """Return the sample-scan budget one channel of `sample_count` samples may spend."""
    return min(
        _RESOLUTION_VISIT_BUDGET_PER_SAMPLE * sample_count,
        _RESOLUTION_VISIT_BUDGET_MAXIMUM,
    )


@dataclass(frozen=True, slots=True)
class DerivedPrmPeak:
    """One Ordifile-derived peak using stored partitions and the stored PRM response.

    `height` is calculated for internal verification against owner-controlled
    exports.  It is not published as a product field.
    """

    retention_index: int
    start_index: int
    end_index: int
    area: float
    height: float
    boundary_rule: str


def _lower_hull(values: Sequence[float], start: int, end: int) -> list[int]:
    """Return the indices of the lower convex hull of the stored response samples."""
    hull: list[int] = []
    for index in range(start, end + 1):
        while len(hull) >= 2:
            left, middle = hull[-2], hull[-1]
            cross = (middle - left) * (values[index] - values[left]) - (
                values[middle] - values[left]
            ) * (index - left)
            if cross <= 0.0:
                hull.pop()
            else:
                break
        hull.append(index)
    return hull


def _argmin(values: Sequence[float], start: int, end: int) -> int:
    if end < start:
        start, end = end, start
    best = start
    for index in range(start + 1, end + 1):
        if values[index] < values[best]:
            best = index
    return best


def _descend_to_group_end(
    values: Sequence[float], lower_bound: int, marker: int, threshold: float
) -> int:
    """Walk back from a stored valley through stored-response noise no larger than threshold."""
    best = marker
    for index in range(marker - 1, lower_bound - 1, -1):
        if values[index] < values[best]:
            best = index
        elif values[index] - values[best] > threshold:
            break
    return best


def _resolve_groups(
    values: Sequence[float],
    apexes: Sequence[int],
    valleys: Sequence[int],
    retention_indices: Sequence[int],
    cluster_start: int,
    cluster_end: int,
    threshold: float,
    budget: list[int],
) -> list[tuple[int, int, int, float, float]]:
    """Resolve one stored marker cluster into peak groups without recursion.

    A stored cluster of `n` apexes resolves into at most `n` groups, so the explicit
    pending stack is bounded by `2 * n - 1` entries.  Working iteratively keeps a long
    chromatogram from exhausting the interpreter stack, and `budget` bounds the total
    sample scanning so that the work is deterministic rather than merely finite.
    """

    def spend(visits: int) -> None:
        budget[0] -= visits
        if budget[0] < 0:
            raise ValueError("marker group resolution exceeded its bounded sample budget")

    collected: list[tuple[int, int, int, float, float]] = []
    pending: list[tuple[int, int, int, int]] = [(0, len(apexes), cluster_start, cluster_end)]
    remaining_steps = 2 * len(apexes)
    while pending:
        remaining_steps -= 1
        if remaining_steps < 0:
            raise ValueError("marker group resolution exceeded its bounded step count")
        low, high, start, end = pending.pop()

        # 1. Narrow the group to the baseline contacts adjacent to its outer apexes.
        while True:
            spend(end - start + 1)
            hull = _lower_hull(values, start, end)
            first = start
            for index in hull:
                if index <= apexes[low]:
                    first = index
                else:
                    break
            last = end
            for index in hull:
                if index >= apexes[high - 1]:
                    last = index
                    break
            if first == start and last == end:
                break
            start, end = first, last
            if start >= end:
                raise ValueError("a marker group collapsed to an empty partition")

        # 2. Split at the first remaining baseline contact that separates two apexes.
        # `hull` is the narrowed group's own hull, so it is reused instead of recomputed.
        split: int | None = None
        for contact in hull:
            if not start < contact < end:
                continue
            position = bisect_left(apexes, contact, low, high) - 1
            if low <= position < high - 1 and apexes[position] < contact < apexes[position + 1]:
                split = position
                break
        if split is not None:
            marker = min(max(valleys[split], apexes[split]), apexes[split + 1])
            spend(max(marker - apexes[split], 0))
            left_end = _descend_to_group_end(values, apexes[split], marker, threshold)
            pending.append((low, split + 1, start, left_end))
            pending.append((split + 1, high, marker, end))
            continue

        # 3. One baseline group: a straight line between its two contacts.
        boundaries = [start]
        for position in range(low + 1, high):
            spend(apexes[position] - apexes[position - 1] + 1)
            boundaries.append(_argmin(values, apexes[position - 1], apexes[position]))
        boundaries.append(end)

        span = end - start
        left_value = values[start]
        slope = 0.0 if span <= 0 else (values[end] - left_value) / span

        for offset in range(high - low):
            peak_start = boundaries[offset]
            peak_end = boundaries[offset + 1]
            retention_index = retention_indices[low + offset]
            if peak_start >= peak_end:
                raise ValueError("a derived peak partition is empty")
            if not peak_start <= retention_index <= peak_end:
                raise ValueError(
                    "a derived retention index lies outside its calculated peak partition"
                )
            collected.append(
                (
                    retention_index,
                    peak_start,
                    peak_end,
                    math.fsum(
                        values[index] - (left_value + slope * (index + 0.5 - start))
                        for index in range(peak_start, peak_end)
                    ),
                    values[retention_index] - (left_value + slope * (retention_index - start)),
                )
            )
    return collected


def _cluster_windows(
    windows: Sequence[PrmPeakWindow],
) -> Iterable[tuple[int, tuple[PrmPeakWindow, ...]]]:
    first = 0
    current: list[PrmPeakWindow] = []
    for offset, window in enumerate(windows):
        cluster = (window.cluster_start_index, window.cluster_end_index)
        if current and cluster != (
            current[0].cluster_start_index,
            current[0].cluster_end_index,
        ):
            yield first, tuple(current)
            first = offset
            current = []
        current.append(window)
    if current:
        yield first, tuple(current)


def derive_marker_peaks(
    values: tuple[float, ...],
    windows: tuple[PrmPeakWindow, ...],
    *,
    d_step: int,
    min_ticks: float,
    threshold: float,
    excluded_window_offsets: frozenset[int] = frozenset(),
) -> tuple[DerivedPrmPeak, ...]:
    """Calculate peak retention indices, boundaries and Areas.

    Stored markers provide every candidate partition and every stored apex.  Peak
    groups are resolved from the lower convex hull of the stored response series, each group
    carries one straight baseline between its own contacts, and fused peaks inside a
    group are separated at the stored-response minimum between neighbouring stored apexes.
    The
    function never searches outside a stored marker partition, never runs whole-curve peak
    detection, and never reads an external Result table.  Inside a stored partition it does
    take the stored-response maximum, which is what the retention time reports.

    It fails closed rather than returning a partition that does not contain its own retention
    index, an Area that is not strictly positive, or a resolution that exceeds its bounded
    sample budget.
    """
    if d_step <= 0 or not math.isfinite(min_ticks) or min_ticks <= 0:
        raise ValueError("time metadata must be finite and positive")
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError("the stored response threshold must be finite and non-negative")
    if not windows:
        return ()
    if any(
        window.start_index < 0
        or window.end_index >= len(values)
        or window.start_index > window.end_index
        or not window.start_index <= window.stored_apex_index <= window.end_index
        or window.cluster_start_index < 0
        or window.cluster_end_index >= len(values)
        or window.cluster_start_index > window.start_index
        or window.cluster_end_index < window.end_index
        for window in windows
    ):
        raise ValueError("marker window lies outside the signal")

    dt_seconds = 60.0 * d_step / min_ticks
    budget = [_resolution_visit_budget(len(values))]
    derived: list[DerivedPrmPeak] = []
    for first_offset, cluster in _cluster_windows(windows):
        retention_indices = [
            max(range(window.start_index, window.end_index + 1), key=values.__getitem__)
            for window in cluster
        ]
        apexes = [window.stored_apex_index for window in cluster]
        if any(left >= right for left, right in zip(apexes, apexes[1:], strict=False)):
            raise ValueError("stored apex markers are not strictly ordered")
        valleys = [window.end_index for window in cluster[:-1]]
        collected = _resolve_groups(
            values,
            apexes,
            valleys,
            retention_indices,
            cluster[0].cluster_start_index,
            cluster[-1].cluster_end_index,
            threshold,
            budget,
        )
        collected.sort(key=lambda item: item[0])
        if len(collected) != len(cluster):
            raise ValueError("a marker cluster did not resolve into one peak per apex")
        for offset, (retention_index, start, end, area, height) in enumerate(collected):
            scaled_area = area * dt_seconds
            # Every official Area in the owner-controlled corpus is positive, and the smallest
            # Area this calculation reproduces there is 0.489.  A non-positive result is
            # therefore outside the evidence, not a small peak, so the channel fails closed.
            if not math.isfinite(scaled_area) or scaled_area <= 0.0:
                raise ValueError("a calculated peak Area is not strictly positive")
            if first_offset + offset in excluded_window_offsets:
                continue
            derived.append(
                DerivedPrmPeak(
                    retention_index,
                    start,
                    end,
                    scaled_area,
                    height,
                    BOUNDARY_RULE_GROUP_BASELINE,
                )
            )
    return tuple(derived)
