from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ordifile.core.models import DatasetBundle, PeakRecord, SampleRecord, SourceFile
from ordifile.core.validation import validate_bundle


def _bundle(peaks: tuple[PeakRecord, ...]) -> DatasetBundle:
    source = SourceFile(Path("source.xml"), "source.xml", "source.xml", 1, "a" * 64, None, 0)
    return DatasetBundle((source,), (SampleRecord("sample", source),), peaks=peaks)


def _peak(order: int | None, *, retention_time: float = 1.0) -> PeakRecord:
    return PeakRecord(
        "sample",
        "source.xml",
        channel="FID1A",
        detector="FID",
        retention_time=retention_time,
        retention_time_unit="min",
        area=10.0,
        status="experimental",
        observation_order=order,
        start_time=retention_time - 0.1,
        end_time=retention_time + 0.1,
        area_unit="pA*s",
        height_unit="pA",
    )


def test_generic_unordered_peak_stream_remains_valid() -> None:
    peak = PeakRecord("sample", "source.xml", retention_time=1.0, area=2.0)
    assert validate_bundle(_bundle((peak,))) == ()


def test_complete_contiguous_ordered_peak_stream_is_valid() -> None:
    assert validate_bundle(_bundle((_peak(1), _peak(2, retention_time=2.0)))) == ()


def test_secondary_retention_fields_are_tail_defaults_for_legacy_construction() -> None:
    peak = PeakRecord(
        "sample",
        "source.xml",
        "FID1A",
        "FID",
        1,
        1.0,
        "min",
        10.0,
        5.0,
        "A",
        "reported",
        "experimental",
        1,
        0.9,
        1.1,
        "pA*s",
        "pA",
    )

    assert peak.retention_time == 1.0
    assert peak.secondary_retention_time is None
    assert peak.secondary_retention_time_unit is None


def test_complete_two_dimensional_peak_stream_is_valid() -> None:
    peaks = tuple(
        replace(
            _peak(index, retention_time=float(index)),
            secondary_retention_time=index / 10,
            secondary_retention_time_unit="s",
        )
        for index in (1, 2)
    )

    assert validate_bundle(_bundle(peaks)) == ()


@pytest.mark.parametrize(
    ("peak", "code"),
    (
        (
            replace(_peak(1), secondary_retention_time=0.1),
            "PEAK_SECONDARY_RETENTION_PARTIAL",
        ),
        (
            replace(_peak(1), secondary_retention_time_unit="s"),
            "PEAK_SECONDARY_RETENTION_PARTIAL",
        ),
        (
            replace(
                _peak(1),
                secondary_retention_time=float("nan"),
                secondary_retention_time_unit="s",
            ),
            "PEAK_SECONDARY_RETENTION_VALUE_INVALID",
        ),
        (
            replace(
                _peak(1),
                secondary_retention_time=True,
                secondary_retention_time_unit="s",
            ),
            "PEAK_SECONDARY_RETENTION_VALUE_INVALID",
        ),
        (
            replace(
                _peak(1),
                secondary_retention_time=0.1,
                secondary_retention_time_unit="",
            ),
            "PEAK_SECONDARY_RETENTION_UNIT_INVALID",
        ),
        (
            replace(
                _peak(1),
                secondary_retention_time=10**1_001,
                secondary_retention_time_unit="s",
            ),
            "INTEGER_LIMIT_EXCEEDED",
        ),
    ),
)
def test_invalid_secondary_retention_coordinate_is_rejected(peak: PeakRecord, code: str) -> None:
    assert code in {issue.code for issue in validate_bundle(_bundle((peak,)))}


def test_peak_stream_cannot_mix_one_and_two_retention_dimensions() -> None:
    peaks = (
        _peak(1),
        replace(
            _peak(2, retention_time=2.0),
            secondary_retention_time=0.2,
            secondary_retention_time_unit="s",
        ),
    )

    assert "PEAK_RETENTION_DIMENSION_MIXED" in {
        issue.code for issue in validate_bundle(_bundle(peaks))
    }


def test_two_dimensional_stream_requires_source_observation_order() -> None:
    peak = replace(
        _peak(None),
        secondary_retention_time=0.1,
        secondary_retention_time_unit="s",
    )

    assert "PEAK_SECONDARY_RETENTION_ORDER_REQUIRED" in {
        issue.code for issue in validate_bundle(_bundle((peak,)))
    }


def test_two_dimensional_stream_rejects_partial_source_observation_order() -> None:
    peaks = (
        replace(
            _peak(1),
            secondary_retention_time=0.1,
            secondary_retention_time_unit="s",
        ),
        replace(
            _peak(None, retention_time=2.0),
            secondary_retention_time=0.2,
            secondary_retention_time_unit="s",
        ),
    )

    assert "PEAK_SECONDARY_RETENTION_ORDER_REQUIRED" in {
        issue.code for issue in validate_bundle(_bundle(peaks))
    }


def test_two_dimensional_stream_without_primary_rt_or_area_is_rejected() -> None:
    peak = PeakRecord(
        "sample",
        "source.xml",
        retention_time_unit="min",
        observation_order=None,
        secondary_retention_time=0.1,
        secondary_retention_time_unit="s",
    )
    codes = {issue.code for issue in validate_bundle(_bundle((peak,)))}

    assert "PEAK_SECONDARY_RETENTION_ORDER_REQUIRED" in codes
    assert "ORDERED_PEAK_VALUE_INVALID" in codes


@pytest.mark.parametrize("field", ("retention_time", "area"))
def test_ordered_peak_huge_integer_is_structured_failure(field: str) -> None:
    if field == "retention_time":
        peak = replace(
            _peak(1),
            retention_time=10**1_001,
            secondary_retention_time=0.1,
            secondary_retention_time_unit="s",
        )
    else:
        peak = replace(
            _peak(1),
            area=10**1_001,
            secondary_retention_time=0.1,
            secondary_retention_time_unit="s",
        )

    assert "INTEGER_LIMIT_EXCEEDED" in {issue.code for issue in validate_bundle(_bundle((peak,)))}


def test_different_streams_can_use_different_retention_dimensions() -> None:
    peaks = (
        _peak(1),
        replace(
            _peak(1, retention_time=2.0),
            channel="FID2A",
            secondary_retention_time=0.2,
            secondary_retention_time_unit="s",
        ),
    )

    assert validate_bundle(_bundle(peaks)) == ()


def test_secondary_retention_unit_must_be_consistent_per_stream() -> None:
    peaks = (
        replace(
            _peak(1),
            secondary_retention_time=0.1,
            secondary_retention_time_unit="s",
        ),
        replace(
            _peak(2, retention_time=2.0),
            secondary_retention_time=0.2,
            secondary_retention_time_unit="min",
        ),
    )

    assert "PEAK_SECONDARY_RETENTION_UNIT_INCONSISTENT" in {
        issue.code for issue in validate_bundle(_bundle(peaks))
    }


@pytest.mark.parametrize(
    ("peaks", "code"),
    (
        ((_peak(1), _peak(None, retention_time=2.0)), "PEAK_OBSERVATION_ORDER_PARTIAL"),
        ((_peak(2),), "PEAK_OBSERVATION_ORDER_INVALID"),
        ((_peak(1), _peak(1, retention_time=2.0)), "PEAK_OBSERVATION_ORDER_INVALID"),
        ((replace(_peak(1), retention_time=float("nan")),), "ORDERED_PEAK_VALUE_INVALID"),
        ((replace(_peak(1), area=float("inf")),), "ORDERED_PEAK_VALUE_INVALID"),
        ((replace(_peak(1), retention_time_unit=""),), "ORDERED_PEAK_UNIT_INVALID"),
        ((replace(_peak(1), area_unit=""),), "ORDERED_PEAK_UNIT_INVALID"),
        ((replace(_peak(1), start_time=2.0),), "PEAK_TIME_BOUNDARY_INVALID"),
    ),
)
def test_invalid_ordered_peak_stream_is_rejected(peaks: tuple[PeakRecord, ...], code: str) -> None:
    assert code in {issue.code for issue in validate_bundle(_bundle(peaks))}


def test_ordered_peak_units_must_be_consistent_per_stream() -> None:
    peaks = (_peak(1), replace(_peak(2, retention_time=2.0), area_unit="counts"))
    assert "ORDERED_PEAK_UNIT_INVALID" in {issue.code for issue in validate_bundle(_bundle(peaks))}


def test_ordered_peak_area_unit_can_be_consistently_unresolved() -> None:
    peaks = (
        replace(_peak(1), area_unit=None, height_unit=None),
        replace(_peak(2, retention_time=2.0), area_unit=None, height_unit=None),
    )
    assert validate_bundle(_bundle(peaks)) == ()


def test_ordered_peak_area_unit_cannot_mix_unresolved_and_explicit() -> None:
    peaks = (_peak(1), replace(_peak(2, retention_time=2.0), area_unit=None))
    assert "ORDERED_PEAK_UNIT_INVALID" in {issue.code for issue in validate_bundle(_bundle(peaks))}
