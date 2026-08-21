# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Deterministic post-conversion counts derived only from canonical records."""

from __future__ import annotations

from dataclasses import dataclass

from ordifile.core.models import BatchResult, FileStatus, SeriesKind

CONVERSION_RESULT_SUMMARY_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ConversionResultSummary:
    """Count-only completion summary shared by workbook, CLI, and desktop."""

    total_sources: int
    converted_sources: int
    warning_sources: int
    failed_sources: int
    skipped_sources: int
    duplicate_sources: int
    sample_records: int
    peak_records: int
    scientific_signal_series: int
    structural_record_series: int


def summarize_conversion(result: BatchResult) -> ConversionResultSummary:
    """Return exact counts without copying identifiers or scientific values."""
    sample_records = 0
    peak_records = 0
    scientific_signal_series = 0
    structural_record_series = 0
    for item in result.files:
        if item.status not in {FileStatus.SUCCESS, FileStatus.WARNING} or item.bundle is None:
            continue
        sample_records += len(item.bundle.samples)
        peak_records += len(item.bundle.peaks)
        for series in item.bundle.signals:
            if series.series_kind is SeriesKind.SCIENTIFIC_SIGNAL:
                scientific_signal_series += 1
            elif series.series_kind is SeriesKind.DECODED_RECORDS:
                structural_record_series += 1
    return ConversionResultSummary(
        total_sources=len(result.files),
        converted_sources=result.success_count,
        warning_sources=result.warning_count,
        failed_sources=result.failure_count,
        skipped_sources=sum(item.status is FileStatus.SKIPPED for item in result.files),
        duplicate_sources=result.duplicate_count,
        sample_records=sample_records,
        peak_records=peak_records,
        scientific_signal_series=scientific_signal_series,
        structural_record_series=structural_record_series,
    )
