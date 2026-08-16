# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Canonical invariant checks that never reinterpret scientific values."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from ordifile.core.models import (
    MAX_CANONICAL_INTEGER_DECIMAL_DIGITS,
    DatasetBundle,
    FileStatus,
    InstrumentMetadata,
    Issue,
    MetadataEntry,
    PeakRecord,
    SampleRecord,
    SeriesKind,
    Severity,
    SignalSeries,
    SourceFile,
    integer_is_within_canonical_bound,
)
from ordifile.core.privacy import contains_machine_local_path, contains_uri_reference
from ordifile.core.workbook_text import (
    MAX_WORKBOOK_CELL_CHARACTERS,
    workbook_text_is_exact,
)

_CANONICAL_ISSUE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_ROW_LOCATOR = re.compile(r"[^:/\\?#\r\n]+:row:[0-9]+(?::column:[0-9]+)?\Z")
_CELL_LOCATOR = re.compile(r"sheet:[0-9]+:cell:[A-Z]{1,3}[1-9][0-9]*\Z")
_CANONICAL_LOCATOR = re.compile(r"canonical:[A-Za-z0-9_.-]+\Z")


def _is_unsafe_metadata_source(value: str) -> bool:
    """Allow relative logical provenance locators, never paths or URI authorities."""
    if contains_machine_local_path(value) or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        return True
    if any(
        pattern.fullmatch(value) is not None
        for pattern in (_ROW_LOCATOR, _CELL_LOCATOR, _CANONICAL_LOCATOR)
    ):
        return False
    return contains_uri_reference(value)


def validate_bundle_structure(bundle: object) -> tuple[Issue, ...]:
    """Validate immutable container and element types before source rebinding."""
    if type(bundle) is not DatasetBundle:
        return (
            Issue(
                "BUNDLE_TYPE_INVALID",
                "An adapter must return a DatasetBundle instance.",
                Severity.ERROR,
            ),
        )
    issues: list[Issue] = []
    expected: tuple[tuple[str, type[Any]], ...] = (
        ("sources", SourceFile),
        ("samples", SampleRecord),
        ("signals", SignalSeries),
        ("peaks", PeakRecord),
        ("metadata", MetadataEntry),
        ("warnings", Issue),
        ("errors", Issue),
    )
    for field, element_type in expected:
        value = getattr(bundle, field)
        if type(value) is not tuple:
            issues.append(
                Issue(
                    "CANONICAL_CONTAINER_TYPE_INVALID",
                    f"DatasetBundle.{field} must be an immutable tuple.",
                    Severity.ERROR,
                )
            )
            continue
        if any(type(item) is not element_type for item in value):
            issues.append(
                Issue(
                    "CANONICAL_ELEMENT_TYPE_INVALID",
                    f"DatasetBundle.{field} contains an invalid element type.",
                    Severity.ERROR,
                )
            )
    for field in ("warnings", "errors"):
        value = getattr(bundle, field)
        if type(value) is not tuple:
            continue
        for item in value:
            if type(item) is not Issue:
                continue
            if (
                type(item.code) is not str
                or type(item.message) is not str
                or type(item.severity) is not Severity
                or item.source is not None
                and type(item.source) is not str
                or type(item.context) is not tuple
                or any(
                    type(pair) is not tuple
                    or len(pair) != 2
                    or any(type(part) is not str for part in pair)
                    for pair in item.context
                )
            ):
                issues.append(
                    Issue(
                        "CANONICAL_ISSUE_INVALID",
                        f"DatasetBundle.{field} contains a malformed structured issue.",
                        Severity.ERROR,
                    )
                )
                break
            expected_severity = Severity.WARNING if field == "warnings" else Severity.ERROR
            if item.severity is not expected_severity:
                issues.append(
                    Issue(
                        "CANONICAL_ISSUE_SEVERITY_INVALID",
                        f"DatasetBundle.{field} contains an issue with inconsistent severity.",
                        Severity.ERROR,
                    )
                )
                break
            if _CANONICAL_ISSUE_CODE.fullmatch(item.code) is None:
                issues.append(
                    Issue(
                        "CANONICAL_ISSUE_CODE_INVALID",
                        f"DatasetBundle.{field} contains a non-stable issue code.",
                        Severity.ERROR,
                    )
                )
                break
            text_parts = (
                item.code,
                item.message,
                *(part for pair in item.context for part in pair),
            )
            if item.source is not None:
                text_parts = (*text_parts, item.source)
            if any(len(part) > MAX_WORKBOOK_CELL_CHARACTERS for part in text_parts):
                issues.append(
                    Issue(
                        "CANONICAL_ISSUE_CELL_LIMIT",
                        f"DatasetBundle.{field} contains issue text exceeding the mandatory "
                        "workbook cell limit.",
                        Severity.ERROR,
                    )
                )
                break
            if any(not workbook_text_is_exact(part) for part in text_parts):
                issues.append(
                    Issue(
                        "CANONICAL_ISSUE_TEXT_UNREPRESENTABLE",
                        f"DatasetBundle.{field} contains text that XLSX cannot preserve exactly.",
                        Severity.ERROR,
                    )
                )
                break
    return tuple(issues)


def validate_bundle(bundle: DatasetBundle) -> tuple[Issue, ...]:
    """Return structured invariant violations and non-destructive warnings."""
    structure_issues = validate_bundle_structure(bundle)
    if structure_issues:
        return structure_issues
    issues: list[Issue] = []
    if len(bundle.sources) != 1:
        issues.append(
            Issue(
                "SOURCE_COUNT_INVALID",
                "A v0.1 adapter must return exactly one source per input.",
                Severity.ERROR,
            )
        )
    if len(bundle.samples) != 1:
        issues.append(
            Issue(
                "SAMPLE_COUNT_INVALID",
                "A v0.1 adapter must return exactly one sample per input.",
                Severity.ERROR,
            )
        )
        return tuple(issues)
    sample = bundle.samples[0]

    def validate_text(
        value: object,
        field: str,
        source: str | None,
        *,
        optional: bool = True,
    ) -> None:
        if value is None and optional:
            return
        if type(value) is not str:
            safe_source = source if type(source) is str else None
            issues.append(
                Issue(
                    "CANONICAL_TEXT_TYPE_INVALID",
                    f"Canonical field {field!r} must be a string"
                    + (" or None." if optional else "."),
                    Severity.ERROR,
                    safe_source,
                )
            )
        elif not workbook_text_is_exact(value):
            issues.append(
                Issue(
                    "WORKBOOK_TEXT_UNREPRESENTABLE",
                    f"Canonical field {field!r} contains text that XLSX cannot preserve exactly.",
                    Severity.ERROR,
                    source,
                )
            )

    def validate_integer(value: object, field: str, source: str | None) -> None:
        if type(value) is int and not integer_is_within_canonical_bound(value):
            issues.append(
                Issue(
                    "INTEGER_LIMIT_EXCEEDED",
                    f"Canonical field {field!r} exceeds the supported "
                    f"{MAX_CANONICAL_INTEGER_DECIMAL_DIGITS}-decimal-digit integer limit.",
                    Severity.ERROR,
                    source,
                )
            )

    def validate_mandatory_text(
        value: object, field: str, source: str | None, *, optional: bool = True
    ) -> None:
        validate_text(value, field, source, optional=optional)
        if type(value) is str and len(value) > MAX_WORKBOOK_CELL_CHARACTERS:
            issues.append(
                Issue(
                    "WORKBOOK_CELL_TEXT_LIMIT",
                    f"Mandatory workbook field {field!r} exceeds the exact cell text limit.",
                    Severity.ERROR,
                    source,
                )
            )

    sample_id_value: object = sample.sample_id
    status_value: object = sample.status
    reliability_value: object = sample.acquired_at_reliable
    acquired_value: object = sample.acquired_at
    instrument_value: object = sample.instrument
    if type(sample_id_value) is not str:
        issues.append(
            Issue("SAMPLE_ID_TYPE_INVALID", "sample_id must be a string.", Severity.ERROR)
        )
    elif not sample_id_value.strip():
        issues.append(Issue("SAMPLE_ID_EMPTY", "sample_id cannot be empty.", Severity.ERROR))
    elif len(sample_id_value) > MAX_WORKBOOK_CELL_CHARACTERS:
        issues.append(
            Issue(
                "WORKBOOK_CELL_TEXT_LIMIT",
                "sample_id exceeds the mandatory workbook cell text limit.",
                Severity.ERROR,
                sample.source.relative_path,
            )
        )
    elif not workbook_text_is_exact(sample_id_value):
        issues.append(
            Issue(
                "WORKBOOK_TEXT_UNREPRESENTABLE",
                "sample_id contains text that XLSX cannot preserve exactly.",
                Severity.ERROR,
                sample.source.relative_path,
            )
        )
    if type(status_value) is not FileStatus:
        issues.append(
            Issue(
                "SAMPLE_STATUS_TYPE_INVALID",
                "sample.status must be a FileStatus value.",
                Severity.ERROR,
                sample.source.relative_path,
            )
        )
    if type(reliability_value) is not bool:
        issues.append(
            Issue(
                "ACQUIRED_AT_RELIABILITY_TYPE_INVALID",
                "acquired_at_reliable must be a boolean.",
                Severity.ERROR,
            )
        )
    if acquired_value is not None and type(acquired_value) is not datetime:
        issues.append(
            Issue(
                "ACQUIRED_AT_TYPE_INVALID",
                "acquired_at must be a datetime or None.",
                Severity.ERROR,
            )
        )
    elif reliability_value is True and (
        acquired_value is None
        or acquired_value.tzinfo is None
        or acquired_value.utcoffset() is None
    ):
        issues.append(
            Issue(
                "ACQUIRED_AT_RELIABILITY_INVALID",
                "acquired_at_reliable=True requires a timezone-aware acquisition timestamp.",
                Severity.ERROR,
                sample.source.relative_path,
            )
        )
    if sample.sequence is not None and (type(sample.sequence) is not int):
        issues.append(
            Issue(
                "SEQUENCE_TYPE_INVALID",
                "sample.sequence must be an integer or None.",
                Severity.ERROR,
                sample.source.relative_path,
            )
        )
    else:
        validate_integer(sample.sequence, "sample.sequence", sample.source.relative_path)
    if sample.runtime is not None and (type(sample.runtime) not in {int, float}):
        issues.append(
            Issue(
                "RUNTIME_TYPE_INVALID",
                "sample.runtime must be numeric or None.",
                Severity.ERROR,
                sample.source.relative_path,
            )
        )
    elif type(sample.runtime) is float and not math.isfinite(sample.runtime):
        issues.append(
            Issue(
                "RUNTIME_NONFINITE",
                "sample.runtime must be finite.",
                Severity.ERROR,
                sample.source.relative_path,
            )
        )
    else:
        validate_integer(sample.runtime, "sample.runtime", sample.source.relative_path)
    if type(instrument_value) is not InstrumentMetadata:
        issues.append(
            Issue(
                "INSTRUMENT_METADATA_TYPE_INVALID",
                "sample.instrument must be InstrumentMetadata.",
                Severity.ERROR,
                sample.source.relative_path,
            )
        )
    else:
        validate_mandatory_text(
            instrument_value.instrument_type,
            "sample.instrument.instrument_type",
            sample.source.relative_path,
        )
        validate_mandatory_text(
            instrument_value.vendor,
            "sample.instrument.vendor",
            sample.source.relative_path,
        )
    for field in ("channels", "detectors"):
        values = getattr(sample, field)
        if type(values) is not tuple:
            issues.append(
                Issue(
                    "CANONICAL_TUPLE_TYPE_INVALID",
                    f"sample.{field} must be an immutable tuple.",
                    Severity.ERROR,
                    sample.source.relative_path,
                )
            )
        elif any(type(value) is not str for value in values):
            issues.append(
                Issue(
                    "CANONICAL_TUPLE_ELEMENT_INVALID",
                    f"sample.{field} must contain only strings.",
                    Severity.ERROR,
                    sample.source.relative_path,
                )
            )
        elif any(not workbook_text_is_exact(value) for value in values):
            issues.append(
                Issue(
                    "WORKBOOK_TEXT_UNREPRESENTABLE",
                    f"sample.{field} contains text that XLSX cannot preserve exactly.",
                    Severity.ERROR,
                    sample.source.relative_path,
                )
            )
        elif len("; ".join(values)) > MAX_WORKBOOK_CELL_CHARACTERS:
            issues.append(
                Issue(
                    "WORKBOOK_CELL_TEXT_LIMIT",
                    f"Joined sample.{field} exceeds the mandatory workbook cell text limit.",
                    Severity.ERROR,
                    sample.source.relative_path,
                )
            )
    if (
        type(sample.channels) is tuple
        and type(sample.detectors) is tuple
        and all(type(value) is str for value in (*sample.detectors, *sample.channels))
        and len("; ".join((*sample.detectors, *sample.channels))) > MAX_WORKBOOK_CELL_CHARACTERS
    ):
        issues.append(
            Issue(
                "WORKBOOK_CELL_TEXT_LIMIT",
                "Joined detector_channels exceeds the mandatory workbook cell text limit.",
                Severity.ERROR,
                sample.source.relative_path,
            )
        )
    for peak in bundle.peaks:
        validate_text(peak.sample_id, "peak.sample_id", peak.source_file, optional=False)
        validate_text(peak.source_file, "peak.source_file", None, optional=False)
        for field in (
            "channel",
            "detector",
            "retention_time_unit",
            "compound",
            "compound_source",
        ):
            validate_text(getattr(peak, field), f"peak.{field}", peak.source_file)
        validate_text(peak.status, "peak.status", peak.source_file, optional=False)
        if (
            type(peak.sample_id) is str
            and type(sample.sample_id) is str
            and peak.sample_id != sample.sample_id
        ):
            issues.append(
                Issue(
                    "PEAK_SAMPLE_MISMATCH",
                    "A peak references a different sample_id.",
                    Severity.ERROR,
                    peak.source_file,
                )
            )
        if peak.peak_number is not None and (type(peak.peak_number) is not int):
            issues.append(
                Issue(
                    "PEAK_NUMBER_TYPE_INVALID",
                    "peak.peak_number must be an integer or None.",
                    Severity.ERROR,
                    peak.source_file,
                )
            )
        else:
            validate_integer(peak.peak_number, "peak.peak_number", peak.source_file)
        for field in ("retention_time", "area", "height"):
            value = getattr(peak, field)
            if value is not None and (type(value) not in {int, float}):
                issues.append(
                    Issue(
                        "PEAK_VALUE_TYPE_INVALID",
                        f"peak.{field} must be numeric or None.",
                        Severity.ERROR,
                        peak.source_file,
                    )
                )
            else:
                validate_integer(value, f"peak.{field}", peak.source_file)
    for signal in bundle.signals:
        validate_text(signal.sample_id, "signal.sample_id", signal.source_file, optional=False)
        validate_text(signal.source_file, "signal.source_file", None, optional=False)
        for field in ("channel", "detector", "x_unit", "y_unit"):
            validate_text(getattr(signal, field), f"signal.{field}", signal.source_file)
        for field in ("x_label", "y_label"):
            validate_text(
                getattr(signal, field), f"signal.{field}", signal.source_file, optional=False
            )
        if type(signal.series_kind) is not SeriesKind:
            issues.append(
                Issue(
                    "SIGNAL_SERIES_KIND_INVALID",
                    "signal.series_kind must be a supported SeriesKind value.",
                    Severity.ERROR,
                    signal.source_file,
                )
            )
        if (
            type(signal.sample_id) is str
            and type(sample.sample_id) is str
            and signal.sample_id != sample.sample_id
        ):
            issues.append(
                Issue(
                    "SIGNAL_SAMPLE_MISMATCH",
                    "A signal references a different sample_id.",
                    Severity.ERROR,
                    signal.source_file,
                )
            )
        coordinates_valid = True
        for field in ("x_values", "y_values"):
            values = getattr(signal, field)
            if type(values) is not tuple:
                coordinates_valid = False
                issues.append(
                    Issue(
                        "SIGNAL_TUPLE_TYPE_INVALID",
                        f"signal.{field} must be an immutable tuple.",
                        Severity.ERROR,
                        signal.source_file,
                    )
                )
                continue
            for value in values:
                if type(value) not in {int, float}:
                    coordinates_valid = False
                    issues.append(
                        Issue(
                            "SIGNAL_VALUE_TYPE_INVALID",
                            f"signal.{field} contains a non-numeric element.",
                            Severity.ERROR,
                            signal.source_file,
                        )
                    )
                    break
                validate_integer(value, f"signal.{field}", signal.source_file)
        if coordinates_valid and len(signal.x_values) != len(signal.y_values):
            issues.append(
                Issue(
                    "SIGNAL_LENGTH_MISMATCH",
                    "Signal x and y arrays must have the same length.",
                    Severity.ERROR,
                    signal.source_file,
                )
            )
    for entry in bundle.metadata:
        for field in ("sample_id", "source_file", "namespace", "key"):
            validate_text(
                getattr(entry, field), f"metadata.{field}", entry.source_file, optional=False
            )
        validate_text(entry.unit, "metadata.unit", entry.source_file)
        if (
            type(entry.sample_id) is str
            and type(sample.sample_id) is str
            and entry.sample_id != sample.sample_id
        ):
            issues.append(
                Issue(
                    "METADATA_SAMPLE_MISMATCH",
                    "A metadata entry references a different sample_id.",
                    Severity.ERROR,
                    entry.source_file,
                )
            )
        if type(entry.value) not in {type(None), str, bool, int, float, datetime}:
            issues.append(
                Issue(
                    "METADATA_VALUE_TYPE_INVALID",
                    "Metadata values must be None, text, boolean, bounded numeric, or datetime.",
                    Severity.ERROR,
                    entry.source_file,
                )
            )
        else:
            validate_integer(entry.value, "metadata.value", entry.source_file)
            if type(entry.value) is str and not workbook_text_is_exact(entry.value):
                issues.append(
                    Issue(
                        "WORKBOOK_TEXT_UNREPRESENTABLE",
                        "Metadata text cannot be preserved exactly in XLSX.",
                        Severity.ERROR,
                        entry.source_file,
                    )
                )
        entry_source: object = entry.source
        if entry_source is not None and type(entry_source) is not str:
            issues.append(
                Issue(
                    "METADATA_SOURCE_TYPE_INVALID",
                    "Metadata source must be a string or None.",
                    Severity.ERROR,
                    entry.source_file,
                )
            )
        elif type(entry_source) is str:
            if not workbook_text_is_exact(entry_source):
                issues.append(
                    Issue(
                        "WORKBOOK_TEXT_UNREPRESENTABLE",
                        "Metadata source cannot be preserved exactly in XLSX.",
                        Severity.ERROR,
                        entry.source_file,
                    )
                )
            if _is_unsafe_metadata_source(entry_source):
                issues.append(
                    Issue(
                        "METADATA_SOURCE_UNSAFE",
                        "Metadata source must be a relative logical locator without "
                        "control characters.",
                        Severity.ERROR,
                        entry.source_file,
                    )
                )
    return tuple(issues)
