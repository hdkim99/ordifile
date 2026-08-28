from __future__ import annotations

import pytest

from ordifile.adapters._youngin_yl_clarity_prm_derived_peaks import (
    _RESOLUTION_VISIT_BUDGET_MAXIMUM,
    _RESOLUTION_VISIT_BUDGET_PER_SAMPLE,
    _descend_to_group_end,
    _resolution_visit_budget,
    derive_marker_peaks,
)
from ordifile.adapters._youngin_yl_clarity_prm_markers import PrmPeakWindow

# 60 s/min divided by the validated 600 records/min sampling metadata.
DT_SECONDS = 0.1


def _derive(values, windows, **kwargs):
    return derive_marker_peaks(
        values,
        windows,
        d_step=1,
        min_ticks=600.0,
        threshold=kwargs.pop("threshold", 0.1),
        **kwargs,
    )


def test_single_group_area_height_and_stored_response_apex_are_deterministic() -> None:
    values = (0.0, 1.0, 3.0, 1.0, 0.0)
    windows = (PrmPeakWindow(0, 2, 4, 0, 4),)

    peaks = _derive(values, windows)

    assert len(peaks) == 1
    assert (peaks[0].start_index, peaks[0].retention_index, peaks[0].end_index) == (0, 2, 4)
    assert peaks[0].area == pytest.approx(5.0 * DT_SECONDS)
    assert peaks[0].height == pytest.approx(3.0)


def test_sloping_baseline_is_a_straight_line_between_group_contacts() -> None:
    values = (0.0, 4.0, 2.0)
    windows = (PrmPeakWindow(0, 1, 2, 0, 2),)

    peaks = _derive(values, windows)

    # Baseline 0 -> 2 over two intervals; the response is corrected at each interval centre.
    assert peaks[0].area == pytest.approx(((0.0 - 0.5) + (4.0 - 1.5)) * DT_SECONDS)
    assert peaks[0].height == pytest.approx(4.0 - 1.0)


def test_fused_peaks_share_one_baseline_and_split_at_the_stored_response_minimum() -> None:
    values = (0.0, 2.0, 0.5, 3.0, 0.0)
    windows = (
        PrmPeakWindow(0, 1, 2, 0, 4),
        PrmPeakWindow(2, 3, 4, 0, 4),
    )

    peaks = _derive(values, windows)

    assert tuple(item.retention_index for item in peaks) == (1, 3)
    assert tuple((item.start_index, item.end_index) for item in peaks) == ((0, 2), (2, 4))
    assert tuple(item.area for item in peaks) == pytest.approx((0.2, 0.35))


def test_baseline_contact_between_apexes_starts_an_independent_group() -> None:
    values = (0.0, 3.0, -1.0, 3.0, 0.0)
    windows = (
        PrmPeakWindow(0, 1, 2, 0, 4),
        PrmPeakWindow(2, 3, 4, 0, 4),
    )

    peaks = _derive(values, windows)

    assert tuple((item.start_index, item.end_index) for item in peaks) == ((0, 2), (2, 4))
    # Each group carries its own straight baseline instead of one line across the cluster.
    assert tuple(item.area for item in peaks) == pytest.approx((0.4, 0.3))


def test_retention_time_uses_the_stored_response_maximum_not_the_stored_apex() -> None:
    values = (0.0, 5.0, 4.0, 0.0)
    windows = (PrmPeakWindow(0, 2, 3, 0, 3),)

    peaks = _derive(values, windows)

    assert peaks[0].retention_index == 1
    assert peaks[0].area == pytest.approx(9.0 * DT_SECONDS)


def test_excluded_candidates_do_not_change_the_remaining_geometry() -> None:
    values = (0.0, 2.0, 0.5, 3.0, 0.0)
    windows = (
        PrmPeakWindow(0, 1, 2, 0, 4),
        PrmPeakWindow(2, 3, 4, 0, 4),
    )

    complete = _derive(values, windows)
    reduced = _derive(values, windows, excluded_window_offsets=frozenset({0}))

    assert len(reduced) == 1
    assert reduced[0] == complete[1]


def test_group_end_walk_stops_at_a_response_larger_than_the_threshold() -> None:
    values = (0.0, 5.0, 0.4, 0.3, 0.35)

    assert _descend_to_group_end(values, 0, 4, 0.1) == 3
    assert _descend_to_group_end(values, 0, 4, 10.0) == 0


def test_invalid_time_metadata_is_rejected() -> None:
    with pytest.raises(ValueError, match="time metadata"):
        derive_marker_peaks(
            (0.0, 1.0, 0.0),
            (PrmPeakWindow(0, 1, 2, 0, 2),),
            d_step=0,
            min_ticks=600.0,
            threshold=0.1,
        )


def test_invalid_threshold_is_rejected() -> None:
    with pytest.raises(ValueError, match="threshold"):
        derive_marker_peaks(
            (0.0, 1.0, 0.0),
            (PrmPeakWindow(0, 1, 2, 0, 2),),
            d_step=1,
            min_ticks=600.0,
            threshold=-1.0,
        )


def test_retention_index_outside_its_partition_fails_closed() -> None:
    # The stored apex sits before a baseline contact, so the group narrows to a partition
    # that no longer contains the stored-response maximum the row would report.
    values = (0.0, 3.0, -1.0, 5.0, 0.0)
    windows = (PrmPeakWindow(0, 1, 4, 0, 4),)

    with pytest.raises(ValueError, match="retention index lies outside"):
        _derive(values, windows)


def _dense_baseline_separated_cluster(count: int):
    """One stored cluster in which every neighbouring apex pair is baseline separated."""
    values: list[float] = []
    for index in range(count):
        values += [-1.0 * index, 5.0, -1.0 * index - 0.5]
    signal = tuple(values)
    windows = tuple(
        PrmPeakWindow(3 * index, 3 * index + 1, 3 * index + 2, 0, len(signal) - 1)
        for index in range(count)
    )
    return signal, windows


def test_resolution_visit_budget_pins_both_constants() -> None:
    # Below the crossover the per-sample multiplier decides the budget, at and above it the
    # absolute maximum does.  Changing either constant changes one of these three values.
    crossover = _RESOLUTION_VISIT_BUDGET_MAXIMUM // _RESOLUTION_VISIT_BUDGET_PER_SAMPLE

    assert _resolution_visit_budget(crossover - 1) == 1024 * (crossover - 1)
    assert _resolution_visit_budget(crossover) == 32_000_000
    assert _resolution_visit_budget(crossover + 1) == 32_000_000
    assert crossover == 31_250


def test_sample_budget_admits_exactly_its_densest_cluster() -> None:
    # 2,041 baseline-separated groups is the densest single cluster the budget admits.  A
    # recursive solver overflows the interpreter stack far below this, so this also pins that
    # the resolution is iterative.
    signal, windows = _dense_baseline_separated_cluster(2_041)

    peaks = _derive(signal, windows)

    assert len(peaks) == 2_041
    assert all(peak.start_index <= peak.retention_index <= peak.end_index for peak in peaks)


def test_non_positive_area_fails_closed() -> None:
    # Response minus baseline is zero at every sample except the apex, so the peak is not
    # negative, yet the left-edge/midpoint summation over a sloping baseline totals below zero.
    values = (-3.0, -2.0, -1.0, 0.0, 3.0, 2.0)
    windows = (PrmPeakWindow(0, 4, 5, 0, 5),)

    with pytest.raises(ValueError, match="not strictly positive"):
        _derive(values, windows)


def test_group_resolution_one_group_over_its_sample_budget_fails_closed() -> None:
    # One group denser than the admitted maximum is rejected, so the two tests together pin
    # the budget rather than merely bracketing it.
    signal, windows = _dense_baseline_separated_cluster(2_042)

    with pytest.raises(ValueError, match="bounded sample budget"):
        _derive(signal, windows)


def test_non_positive_area_is_checked_before_candidates_are_excluded() -> None:
    # The first peak sits on a rising baseline and totals below zero; the second is positive.
    # Excluding the first must not hide it, so the channel still fails closed.
    values = (-3.0, -2.0, -1.0, 0.0, 3.0, 2.05, 9.0, 4.0)
    windows = (
        PrmPeakWindow(0, 4, 5, 0, 7),
        PrmPeakWindow(5, 6, 7, 0, 7),
    )

    with pytest.raises(ValueError, match="not strictly positive"):
        _derive(values, windows, excluded_window_offsets=frozenset({0}))

    with pytest.raises(ValueError, match="not strictly positive"):
        _derive(values, windows)


def test_unordered_stored_apexes_fail_closed() -> None:
    values = (0.0, 2.0, 0.5, 3.0, 0.0)
    windows = (
        PrmPeakWindow(0, 2, 2, 0, 4),
        PrmPeakWindow(2, 2, 4, 0, 4),
    )

    with pytest.raises(ValueError, match="stored apex"):
        _derive(values, windows)


@pytest.mark.parametrize(
    "window",
    (
        PrmPeakWindow(0, 1, 2, -1, 2),
        PrmPeakWindow(0, 1, 2, 0, 3),
        PrmPeakWindow(0, 1, 2, 2, 1),
        PrmPeakWindow(0, 3, 2, 0, 2),
    ),
)
def test_invalid_cluster_and_stored_apex_bounds_are_rejected(window: PrmPeakWindow) -> None:
    with pytest.raises(ValueError, match="marker window"):
        _derive((0.0, 1.0, 0.0), (window,))
