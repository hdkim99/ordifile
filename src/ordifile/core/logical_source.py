# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Merge provenance-confirmed official Results into one native logical source."""

from __future__ import annotations

from dataclasses import replace

from ordifile.core.errors import OrdifileError
from ordifile.core.models import DatasetBundle, Issue


def _rebind_issue(issue: Issue, source_file: str) -> Issue:
    return replace(issue, source=source_file)


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
    if native.peaks:
        raise OrdifileError(
            "LOGICAL_SOURCE_DIRECT_RESULT_PRESENT",
            "Automatic Result acquisition cannot replace or supplement direct peaks.",
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
    metadata = tuple(
        replace(item, sample_id=sample_id, source_file=source_file) for item in acquired.metadata
    )
    warnings = tuple(_rebind_issue(issue, source_file) for issue in acquired.warnings)
    return replace(
        native,
        peaks=peaks,
        metadata=(*native.metadata, *metadata),
        warnings=(*native.warnings, *warnings),
    )
