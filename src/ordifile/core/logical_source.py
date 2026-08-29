# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Merge provenance-confirmed official Results into one native logical source."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from ordifile.core.discovery import is_chemstation_run_directory
from ordifile.core.errors import OrdifileError
from ordifile.core.models import DatasetBundle, FileResult, FileStatus, Issue, Severity

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


def _run_directory(path: Path, cache: dict[Path, bool]) -> Path | None:
    """Return the ChemStation run directory a path sits in, when there is one."""
    for parent in path.parents:
        if is_chemstation_run_directory(parent, cache):
            return parent
    return None


def _one_sample(bundle: DatasetBundle | None) -> bool:
    return bundle is not None and len(bundle.sources) == 1 and len(bundle.samples) == 1


def _is_signal_only(item: FileResult) -> bool:
    return (
        item.status in {FileStatus.SUCCESS, FileStatus.WARNING}
        and _one_sample(item.bundle)
        and item.bundle is not None
        and bool(item.bundle.signals)
        and not item.bundle.peaks
    )


def _is_mapped_peak_table(item: FileResult) -> bool:
    # Only a table the researcher's own mapping read can stand in as a run's peak table;
    # nothing about the container says which export that is.
    return (
        item.status in {FileStatus.SUCCESS, FileStatus.WARNING}
        and item.mapping_route is not None
        and _one_sample(item.bundle)
        and item.bundle is not None
        and bool(item.bundle.peaks)
        and not item.bundle.signals
    )


def _with_issue(item: FileResult, code: str, message: str) -> FileResult:
    return replace(
        item,
        issues=(
            *item.issues,
            Issue(code, message, Severity.WARNING, item.source.public_reference),
        ),
    )


def join_chemstation_runs(results: Sequence[FileResult]) -> tuple[FileResult, ...]:
    """Join each ChemStation run's signal and its mapped peak table into one source.

    The container does not say which of a run's exports is the peak table, and its
    filename is site-specific, so the researcher's own mapping decides: a run is joined
    only when exactly one file in it carries a signal and exactly one was read by that
    mapping.  Anything else is left as separate sources and reported.
    """
    cache: dict[Path, bool] = {}
    groups: dict[Path, list[int]] = {}
    for index, item in enumerate(results):
        run = _run_directory(item.source.path, cache)
        if run is not None:
            groups.setdefault(run, []).append(index)
    if not groups:
        return tuple(results)

    joined = list(results)
    for indexes in groups.values():
        signals = [index for index in indexes if _is_signal_only(joined[index])]
        tables = [index for index in indexes if _is_mapped_peak_table(joined[index])]
        if not signals or not tables:
            continue
        if len(signals) > 1 or len(tables) > 1:
            for index in signals:
                joined[index] = _with_issue(
                    joined[index],
                    "AGILENT_D_JOIN_AMBIGUOUS",
                    f"This ChemStation run holds {len(signals)} signal file(s) and "
                    f"{len(tables)} mapped peak table(s), so which pair belongs together "
                    "is not determined; they were kept as separate sources.",
                )
            continue
        signal_index, table_index = signals[0], tables[0]
        native = joined[signal_index].bundle
        acquired = joined[table_index].bundle
        if native is None or acquired is None:  # pragma: no cover - guarded above
            continue
        try:
            merged = merge_acquired_result(native, acquired)
        except OrdifileError as error:
            joined[signal_index] = _with_issue(
                joined[signal_index],
                "AGILENT_D_JOIN_REFUSED",
                f"This ChemStation run's signal and peak table could not be joined "
                f"({error.code}); they were kept as separate sources.",
            )
            continue
        joined[signal_index] = _with_issue(
            replace(joined[signal_index], bundle=merged),
            "AGILENT_D_RUN_JOINED",
            "The peak table this ChemStation run stores beside its signal was read with "
            "the supplied mapping and attached to this source.",
        )
        joined[table_index] = _with_issue(
            replace(joined[table_index], status=FileStatus.SKIPPED, bundle=None),
            "AGILENT_D_PEAK_TABLE_MERGED",
            "This peak table was attached to the signal of the ChemStation run that "
            "stores it, and is retained here for the audit trail.",
        )
    return tuple(joined)
