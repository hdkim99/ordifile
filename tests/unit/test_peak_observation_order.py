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
