# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Merge provenance-confirmed official Results into one native logical source."""

from __future__ import annotations

from dataclasses import replace

from ordifile.core.errors import OrdifileError
from ordifile.core.models import DatasetBundle, Issue

_DERIVED_METADATA_KEYS = frozenset(
    {
        "peak_table_status",
        "integration_marker_status",
        "processing_time_table_status",
        "processing_method_span_sha256",
        "stored_integration_type",
        "derived_peak_count",
        "derived_area_method_id",
        "derived_area_origin",
        "derived_area_equivalence_status",
        "scientific_semantics_evidence_gap",
    }
)
_DERIVED_WARNING_CODES = frozenset(
    {
        "YOUNGIN_PRM_AREA_ORDIFILE_DERIVED_EXPERIMENTAL",
        "YOUNGIN_PRM_DERIVED_AREA_UNAVAILABLE",
    }
)


def _rebind_issue(issue: Issue, source_file: str) -> Issue:
    return replace(issue, source=source_file)


def _is_derived_metadata(key: str) -> bool:
    return key in _DERIVED_METADATA_KEYS or key.endswith(
        (
            "_integration_marker_status",
            "_integration_marker_count",
            "_ignored_incomplete_marker_count",
            "_marker_candidate_count",
            "_processing_time_table_status",
            "_processing_time_table_excluded_candidate_count",
        )
    )


def merge_acquired_result(
    native: DatasetBundle,
    acquired: DatasetBundle,
) -> DatasetBundle:
    """Attach exact acquired peaks while preserving the native source and sample."""
    if len(native.sources) != 1 or len(native.samples) != 1:
        raise OrdifileError(
            "LOGICAL_SOURCE_NATIVE_INVALID",
            "The native bundle must contain exactly one source and sample.",
        )
    if len(acquired.sources) != 1 or len(acquired.samples) != 1:
        raise OrdifileError(
            "LOGICAL_SOURCE_RESULT_INVALID",
            "The acquired Result must contain exactly one source and sample.",
        )
    if native.peaks and any(peak.data_origin != "ordifile_marker_derived" for peak in native.peaks):
        raise OrdifileError(
            "LOGICAL_SOURCE_DIRECT_RESULT_PRESENT",
            "Automatic Result acquisition cannot replace or supplement source-explicit peaks.",
        )
    if acquired.signals:
        raise OrdifileError(
            "LOGICAL_SOURCE_RESULT_SIGNALS_UNEXPECTED",
            "An acquired Result adapter must not return scientific signals.",
        )
    if acquired.errors:
        raise OrdifileError(
            "LOGICAL_SOURCE_RESULT_ERRORS_PRESENT",
            "An acquired Result containing canonical errors cannot be merged.",
        )
    native_sample = native.samples[0]
    acquired_sample = acquired.samples[0]
    native_vendor = native_sample.instrument.vendor
    acquired_vendor = acquired_sample.instrument.vendor
    if (
        native_vendor is not None
        and acquired_vendor is not None
        and native_vendor.casefold() != acquired_vendor.casefold()
    ):
        raise OrdifileError(
            "LOGICAL_SOURCE_VENDOR_MISMATCH",
            "Native and acquired Result vendors do not match.",
        )
    sample_id = native_sample.sample_id
    source_file = native.sources[0].public_reference
    peaks = tuple(
        replace(peak, sample_id=sample_id, source_file=source_file) for peak in acquired.peaks
    )
    replacing_derived_rows = bool(native.peaks)
    native_metadata = (
        tuple(item for item in native.metadata if not _is_derived_metadata(item.key))
        if replacing_derived_rows
        else native.metadata
    )
    metadata = tuple(
        replace(item, sample_id=sample_id, source_file=source_file) for item in acquired.metadata
    )
    native_warnings = (
        tuple(issue for issue in native.warnings if issue.code not in _DERIVED_WARNING_CODES)
        if replacing_derived_rows
        else native.warnings
    )
    warnings = tuple(_rebind_issue(issue, source_file) for issue in acquired.warnings)
    return replace(
        native,
        peaks=peaks,
        metadata=(*native_metadata, *metadata),
        warnings=(*native_warnings, *warnings),
    )
