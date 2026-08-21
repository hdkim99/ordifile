from __future__ import annotations

from pathlib import Path

from ordifile import ConversionResultSummary, summarize_conversion
from ordifile.core.models import (
    BatchResult,
    DatasetBundle,
    FileResult,
    FileStatus,
    PeakRecord,
    SampleRecord,
    SeriesKind,
    SignalSeries,
    SortDecision,
    SortMode,
    SourceFile,
)


def _source(order: int) -> SourceFile:
    return SourceFile(
        path=Path(f"/private/input-{order}.csv"),
        relative_path=f"input-{order}.csv",
        name=f"input-{order}.csv",
        size=1,
        sha256=f"{order:064x}",
        modified_at=None,
        input_order=order,
        public_id=f"source-{order:064x}",
    )


def _bundle(source: SourceFile, *, sample_id: str) -> DatasetBundle:
    return DatasetBundle(
        sources=(source,),
        samples=(SampleRecord(sample_id, source),),
        peaks=(PeakRecord(sample_id, source.name, retention_time=1.0, area=2.0),),
        signals=(
            SignalSeries(sample_id, source.name, None, None, (1.0,), (2.0,)),
            SignalSeries(
                sample_id,
                source.name,
                None,
                None,
                (1.0,),
                (2.0,),
                series_kind=SeriesKind.DECODED_RECORDS,
            ),
        ),
    )


def test_conversion_summary_counts_only_included_canonical_records() -> None:
    success_source = _source(1)
    warning_source = _source(2)
    failed_source = _source(3)
    skipped_source = _source(4)
    duplicate_source = _source(5)
    result = BatchResult(
        (
            FileResult(
                success_source,
                FileStatus.SUCCESS,
                bundle=_bundle(success_source, sample_id="private-a"),
            ),
            FileResult(
                warning_source,
                FileStatus.WARNING,
                bundle=_bundle(warning_source, sample_id="private-b"),
            ),
            FileResult(
                failed_source,
                FileStatus.FAILED,
                bundle=_bundle(failed_source, sample_id="excluded"),
            ),
            FileResult(skipped_source, FileStatus.SKIPPED),
            FileResult(duplicate_source, FileStatus.DUPLICATE),
        ),
        SortDecision(SortMode.AUTO, SortMode.INPUT_ORDER, "test"),
    )

    assert summarize_conversion(result) == ConversionResultSummary(
        total_sources=5,
        converted_sources=2,
        warning_sources=1,
        failed_sources=1,
        skipped_sources=1,
        duplicate_sources=1,
        sample_records=2,
        peak_records=2,
        scientific_signal_series=2,
        structural_record_series=2,
    )


def test_conversion_summary_contains_no_identifiers_or_scientific_values() -> None:
    source = _source(1)
    result = BatchResult(
        (
            FileResult(
                source, FileStatus.SUCCESS, bundle=_bundle(source, sample_id="private-sample")
            ),
        ),
        SortDecision(SortMode.AUTO, SortMode.INPUT_ORDER, "test"),
    )

    rendered = repr(summarize_conversion(result))
    assert "private" not in rendered
    assert str(source.path) not in rendered
    assert "1.0" not in rendered
    assert "2.0" not in rendered


def test_conversion_summary_scales_linearly_for_large_batch() -> None:
    files = []
    for order in range(1, 501):
        source = _source(order)
        files.append(
            FileResult(
                source,
                FileStatus.SUCCESS,
                bundle=_bundle(source, sample_id=f"sample-{order}"),
            )
        )
    result = BatchResult(
        tuple(files),
        SortDecision(SortMode.AUTO, SortMode.INPUT_ORDER, "test"),
    )

    summary = summarize_conversion(result)

    assert summary.total_sources == 500
    assert summary.converted_sources == 500
    assert summary.sample_records == 500
    assert summary.peak_records == 500
    assert summary.scientific_signal_series == 500
    assert summary.structural_record_series == 500
