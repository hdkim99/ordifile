from __future__ import annotations

import pytest

from ordifile.adapters._youngin_yl_clarity_prm_derived_peaks import (
    _corrected_response,
    derive_marker_peaks,
)
from ordifile.adapters._youngin_yl_clarity_prm_markers import PrmPeakWindow


def test_lower_envelope_area_and_raw_apex_are_deterministic() -> None:
    values = (0.0, 1.0, 3.0, 1.0, 0.0)
    windows = (PrmPeakWindow(0, 1, 4, 0, 4),)

    peaks = derive_marker_peaks(values, windows, d_step=1, min_ticks=600.0)

    assert len(peaks) == 1
    assert peaks[0].retention_index == 2
    assert peaks[0].area == pytest.approx(0.5)


def test_cluster_lower_envelope_is_shared_across_valley_partitions() -> None:
    values = (0.0, 2.0, 0.5, 3.0, 0.0)
    windows = (
        PrmPeakWindow(0, 1, 2, 0, 4),
        PrmPeakWindow(2, 3, 4, 0, 4),
    )

    peaks = derive_marker_peaks(values, windows, d_step=1, min_ticks=600.0)

    assert tuple(item.retention_index for item in peaks) == (1, 3)
    assert tuple(item.area for item in peaks) == pytest.approx((0.225, 0.325))


def test_single_peak_cluster_can_use_adjacent_base_to_base_contacts() -> None:
    values = (0.0, 0.0, 2.0, 0.0, 0.0)
    windows = (PrmPeakWindow(0, 2, 4, 0, 4),)

    peaks = derive_marker_peaks(
        values,
        windows,
        d_step=1,
        min_ticks=600.0,
        refine_single_peak_clusters=True,
        original_single_peak_clusters=frozenset({(0, 4)}),
    )

    assert len(peaks) == 1
    assert (peaks[0].start_index, peaks[0].retention_index, peaks[0].end_index) == (1, 2, 3)
    assert peaks[0].area == pytest.approx(0.2)


def test_single_peak_refinement_does_not_split_shared_clusters() -> None:
    values = (0.0, 2.0, 0.5, 3.0, 0.0)
    windows = (
        PrmPeakWindow(0, 1, 2, 0, 4),
        PrmPeakWindow(2, 3, 4, 0, 4),
    )

    peaks = derive_marker_peaks(
        values,
        windows,
        d_step=1,
        min_ticks=600.0,
        refine_single_peak_clusters=True,
        original_single_peak_clusters=frozenset(),
    )

    assert tuple(item.area for item in peaks) == pytest.approx((0.225, 0.325))


def test_refinement_requires_original_cluster_cardinality() -> None:
    with pytest.raises(ValueError, match="cluster cardinality"):
        derive_marker_peaks(
            (0.0, 1.0, 0.0),
            (PrmPeakWindow(0, 1, 2, 0, 2),),
            d_step=1,
            min_ticks=600.0,
            refine_single_peak_clusters=True,
        )


def test_meaningful_baseline_crossing_fails_closed() -> None:
    with pytest.raises(ValueError, match="baseline crosses"):
        _corrected_response(1.0, 2.0)


def test_invalid_time_metadata_is_rejected() -> None:
    with pytest.raises(ValueError, match="time metadata"):
        derive_marker_peaks(
            (0.0, 1.0, 0.0),
            (PrmPeakWindow(0, 1, 2, 0, 2),),
            d_step=0,
            min_ticks=600.0,
        )


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
        derive_marker_peaks(
            (0.0, 1.0, 0.0),
            (window,),
            d_step=1,
            min_ticks=600.0,
        )
