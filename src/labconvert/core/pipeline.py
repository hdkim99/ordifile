# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Failure-isolating discovery, detection, parsing, validation, and sorting pipeline."""

from __future__ import annotations

import math
import os
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path, PurePosixPath, PureWindowsPath

from labconvert.adapters.base import ParseOptions
from labconvert.adapters.registry import AdapterRegistry
from labconvert.core.detection import detect_adapter
from labconvert.core.discovery import discover_files, sha256_file
from labconvert.core.errors import LabConvertError
from labconvert.core.models import (
    BatchResult,
    ConversionOptions,
    DatasetBundle,
    FileResult,
    FileStatus,
    Issue,
    MetadataEntry,
    ProgressEvent,
    Severity,
    SortMode,
    SourceFile,
    integer_is_within_canonical_bound,
)
from labconvert.core.sorting import sort_file_results
from labconvert.core.validation import validate_bundle, validate_bundle_structure
from labconvert.core.workbook_text import (
    MAX_WORKBOOK_CELL_CHARACTERS,
    workbook_audit_display,
    workbook_cell_text_is_exact,
    workbook_text_is_exact,
)

# The warning threshold flags unusually large in-memory parser work. The 2 GiB hard
# boundary prevents a single v0.1 tabular input from monopolizing process address space;
# both remain overrideable constants for constrained deployments and tests.
WARN_INPUT_FILE_BYTES = 256 * 1024 * 1024
MAX_INPUT_FILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ERROR_DETAIL_ITEMS = 32
MAX_ERROR_DETAIL_KEY_CHARACTERS = 64
MAX_ERROR_DETAIL_VALUE_CHARACTERS = 512
_ADAPTER_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_EXTERNAL_LOCATOR = re.compile(
    r"(?P<url>[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"']+)"
    r"|(?P<windows>(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s<>\"']+)"
    r"|(?P<unc>(?<![\\])\\\\[^\\\s<>\"']+\\[^\s<>\"']+)"
    r"|(?P<posix>(?<![:/A-Za-z0-9_])/(?:[^\s<>\"']+))"
)
_ABSOLUTE_PATH_PLACEHOLDER = "[absolute-path-omitted]"


def _contains_absolute_path(value: str) -> bool:
    """Detect a machine-local path without treating URLs as local paths."""
    for match in _EXTERNAL_LOCATOR.finditer(value):
        url = match.group("url")
        if url is not None:
            if url.lower().startswith(("http://", "https://")):
                continue
            return True
        candidate = match.group(0)
        if match.group("windows") is not None or match.group("unc") is not None:
            if PureWindowsPath(candidate).is_absolute():
                return True
        elif PurePosixPath(candidate).is_absolute():
            return True
    return False


def _scrub_absolute_paths(value: str) -> str:
    """Omit an entire external value when any machine-local path is present.

    Whole-value omission is deliberately conservative: an unquoted path containing
    spaces has no reliable textual end delimiter, so token replacement could expose its
    tail. URLs and relative logical locators remain unchanged when no absolute path is
    present.
    """
    return _ABSOLUTE_PATH_PLACEHOLDER if _contains_absolute_path(value) else value


def _bundle_issue_has_private_path(bundle: DatasetBundle) -> bool:
    """Identify external adapter issue text that could expose a machine-local path."""
    for issue in (*bundle.warnings, *bundle.errors):
        text_parts = (issue.message, *(part for pair in issue.context for part in pair))
        if issue.source is not None:
            text_parts = (*text_parts, issue.source)
        if any(_contains_absolute_path(part) for part in text_parts):
            return True
    return False


def _safe_detail_text(value: object) -> str:
    """Serialize one error detail without invoking plugin-defined conversion hooks."""
    if type(value) is str:
        if len(value) > MAX_ERROR_DETAIL_VALUE_CHARACTERS:
            return "[text-omitted-too-long]"
        if not workbook_text_is_exact(value):
            return "[text-omitted-unrepresentable]"
        return _scrub_absolute_paths(value)
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        if not integer_is_within_canonical_bound(value):
            return "[integer-omitted-too-large]"
        rendered = str(value)
        if len(rendered) > MAX_ERROR_DETAIL_VALUE_CHARACTERS:
            return "[integer-omitted-too-long]"
        return rendered
    if type(value) is float:
        return repr(value) if math.isfinite(value) else "[nonfinite-float]"
    return "[unsupported-detail-type]"


def _safe_error_context(details: object) -> tuple[tuple[str, str], ...]:
    """Bound plugin-controlled error details to privacy-safe primitive context."""
    if type(details) is not dict:
        return (("details", "[unsupported-details-mapping]"),)
    context: list[tuple[str, str]] = []
    entries = islice(details.items(), MAX_ERROR_DETAIL_ITEMS + 1)
    for index, (key, value) in enumerate(entries, start=1):
        if index > MAX_ERROR_DETAIL_ITEMS:
            context.append(("details_truncated", "true"))
            break
        if (
            type(key) is str
            and 0 < len(key) <= MAX_ERROR_DETAIL_KEY_CHARACTERS
            and workbook_text_is_exact(key)
        ):
            safe_key = _scrub_absolute_paths(key)
        else:
            safe_key = f"detail_{index:03d}"
        context.append((safe_key, _safe_detail_text(value)))
    return tuple(context)


def _issue_from_error(error: Exception, source: SourceFile) -> Issue:
    safe_source = workbook_audit_display(source.relative_path)
    if isinstance(error, LabConvertError):
        if (
            type(error.code) is not str
            or _ADAPTER_ERROR_CODE.fullmatch(error.code) is None
            or type(error.message) is not str
            or not error.message
            or len(error.message) > MAX_ERROR_DETAIL_VALUE_CHARACTERS
            or not workbook_text_is_exact(error.message)
        ):
            return Issue(
                "ADAPTER_ERROR_INVALID",
                "The adapter raised a malformed structured error; unsafe details were omitted.",
                Severity.ERROR,
                safe_source,
            )
        return Issue(
            error.code,
            _scrub_absolute_paths(error.message),
            Severity.ERROR,
            safe_source,
            _safe_error_context(error.details),
        )
    error_type = type(error).__name__
    if len(error_type) > 80 or not workbook_text_is_exact(error_type):
        error_type = "ordinary exception"
    return Issue(
        "ADAPTER_UNEXPECTED_ERROR",
        f"The adapter raised an unexpected {error_type}; no scientific data "
        "was exported for this file.",
        Severity.ERROR,
        safe_source,
    )


def _bounded_file_issues(issues: tuple[Issue, ...], source_file: str) -> tuple[Issue, ...]:
    """Keep mandatory Import_Log aggregate cells within their exact XLSX boundary."""
    warnings = ";".join(issue.code for issue in issues if issue.severity is Severity.WARNING)
    errors = ";".join(issue.code for issue in issues if issue.severity is Severity.ERROR)
    messages = " | ".join(issue.message for issue in issues)
    if max(len(warnings), len(errors), len(messages)) <= MAX_WORKBOOK_CELL_CHARACTERS:
        return issues
    return (
        Issue(
            "WORKBOOK_AUDIT_CELL_LIMIT",
            "Per-file issue details exceeded a mandatory workbook audit cell and were "
            "replaced with this bounded error.",
            Severity.ERROR,
            source_file,
        ),
    )


def _bind_source(bundle: DatasetBundle, source: SourceFile) -> DatasetBundle:
    samples = tuple(replace(sample, source=source) for sample in bundle.samples)
    safe_reference = workbook_audit_display(source.relative_path)
    peaks = tuple(replace(peak, source_file=safe_reference) for peak in bundle.peaks)
    signals = tuple(replace(signal, source_file=safe_reference) for signal in bundle.signals)
    metadata = tuple(replace(entry, source_file=safe_reference) for entry in bundle.metadata)
    # Preserve adapter cardinality so validation can enforce the exactly-one v0.1 contract.
    sources = tuple(source for _adapter_source in bundle.sources)
    return replace(
        bundle,
        sources=sources,
        samples=samples,
        peaks=peaks,
        signals=signals,
        metadata=metadata,
    )


def _normalize_datetimes(
    bundle: DatasetBundle, source_file: str
) -> tuple[DatasetBundle, tuple[Issue, ...]]:
    """Replace validated datetime serialization hooks with hook-free built-in values."""
    sample = bundle.samples[0]
    acquired = sample.acquired_at
    issues: list[Issue] = []
    normalized_sample = sample
    metadata = list(bundle.metadata)
    if type(acquired) is datetime:
        try:
            serialized = acquired.isoformat()
            normalized = datetime.fromisoformat(serialized)
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception:
            issues.append(
                Issue(
                    "ACQUIRED_AT_SERIALIZATION_INVALID",
                    "acquired_at could not be serialized safely; the plugin file was excluded.",
                    Severity.ERROR,
                    source_file,
                )
            )
            normalized_sample = replace(
                sample,
                acquired_at=None,
                acquired_at_reliable=False,
            )
        else:
            if not workbook_cell_text_is_exact(serialized):
                issues.append(
                    Issue(
                        "ACQUIRED_AT_SERIALIZATION_INVALID",
                        "acquired_at serialization is not exactly representable in one workbook "
                        "cell.",
                        Severity.ERROR,
                        source_file,
                    )
                )
            else:
                reliable = sample.acquired_at_reliable
                if normalized.tzinfo is not None:
                    try:
                        normalized.utcoffset()
                        normalized.astimezone(UTC)
                    except (OverflowError, ValueError):
                        reliable = False
                        issues.append(
                            Issue(
                                "ACQUIRED_AT_UTC_RANGE_UNORDERABLE",
                                "acquired_at cannot be represented on the UTC timeline and was "
                                "excluded from acquisition-time sorting.",
                                Severity.WARNING,
                                source_file,
                            )
                        )
                        if type(sample.sample_id) is str:
                            metadata.append(
                                MetadataEntry(
                                    sample.sample_id,
                                    source_file,
                                    "core:timestamp_validation",
                                    "acquired_at_unorderable_raw",
                                    serialized,
                                    source="canonical:sample.acquired_at",
                                )
                            )
                normalized_sample = replace(
                    sample,
                    acquired_at=normalized,
                    acquired_at_reliable=reliable,
                )
    normalized_metadata: list[MetadataEntry] = []
    for entry in metadata:
        value = entry.value
        if type(value) is not datetime:
            normalized_metadata.append(entry)
            continue
        try:
            serialized_value = value.isoformat()
            normalized_value = datetime.fromisoformat(serialized_value)
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception:
            issues.append(
                Issue(
                    "METADATA_DATETIME_SERIALIZATION_INVALID",
                    "A Metadata datetime could not be serialized safely; the plugin file was "
                    "excluded.",
                    Severity.ERROR,
                    source_file,
                )
            )
            continue
        if not workbook_cell_text_is_exact(serialized_value):
            issues.append(
                Issue(
                    "METADATA_DATETIME_SERIALIZATION_INVALID",
                    "A Metadata datetime is not exactly representable in one workbook cell.",
                    Severity.ERROR,
                    source_file,
                )
            )
            continue
        normalized_metadata.append(replace(entry, value=normalized_value))
    return (
        replace(bundle, samples=(normalized_sample,), metadata=tuple(normalized_metadata)),
        tuple(issues),
    )


def run_pipeline(
    inputs: Sequence[str | os.PathLike[str]],
    registry: AdapterRegistry,
    *,
    recursive: bool = False,
    extensions: Iterable[str] | None = None,
    sort: SortMode | str = SortMode.AUTO,
    forced_adapter: str | None = None,
    parse_options: ParseOptions | None = None,
    on_error: str = "continue",
    progress: Callable[[ProgressEvent], None] | None = None,
    artifact_output: os.PathLike[str] | None = None,
) -> BatchResult:
    """Process each discovered file independently and preserve every outcome."""
    if on_error not in {"continue", "stop"}:
        raise LabConvertError("ON_ERROR_INVALID", "on_error must be 'continue' or 'stop'.")
    try:
        requested_sort = sort if isinstance(sort, SortMode) else SortMode(sort)
    except ValueError as error:
        choices = ", ".join(mode.value for mode in SortMode)
        raise LabConvertError("SORT_MODE_INVALID", f"sort must be one of: {choices}.") from error
    if forced_adapter is not None:
        registry.get(forced_adapter)
    options = ParseOptions() if parse_options is None else parse_options
    normalized_extensions = None if extensions is None else tuple(extensions)
    processed: list[FileResult] = []
    stopped = False
    discovered_files = discover_files(
        inputs,
        recursive=recursive,
        extensions=normalized_extensions,
        warn_file_bytes=WARN_INPUT_FILE_BYTES,
        max_file_bytes=MAX_INPUT_FILE_BYTES,
        artifact_output=None if artifact_output is None else Path(artifact_output),
    )
    if progress is not None:
        progress(ProgressEvent("discovery", len(discovered_files), len(discovered_files)))
    total_files = len(discovered_files)

    def report_processed(item: FileResult, completed: int) -> None:
        if progress is not None:
            progress(
                ProgressEvent(
                    "processing",
                    completed,
                    total_files,
                    workbook_audit_display(item.source.relative_path),
                    item.status,
                )
            )

    for completed, discovered in enumerate(discovered_files, start=1):
        source = discovered.source
        display_source = workbook_audit_display(source.relative_path)
        discovery_issues = discovered.issues
        if display_source != source.relative_path:
            discovery_issues = (
                *discovery_issues,
                Issue(
                    "SOURCE_DISPLAY_ESCAPED",
                    "Unsafe source identity code points were reversibly escaped for workbook "
                    "audit fields; the input file and its SHA-256 were not changed.",
                    Severity.WARNING,
                    display_source,
                ),
            )
        if any(issue.code == "LABCONVERT_ARTIFACT_EXCLUDED" for issue in discovery_issues):
            result = FileResult(source, FileStatus.SKIPPED, issues=discovery_issues)
            processed.append(result)
            report_processed(result, completed)
            continue
        if source.duplicate_of is not None:
            result = FileResult(source, FileStatus.DUPLICATE, issues=discovery_issues)
            processed.append(result)
            report_processed(result, completed)
            continue
        if any(issue.severity is Severity.ERROR for issue in discovery_issues):
            result = FileResult(source, FileStatus.FAILED, issues=discovery_issues)
            processed.append(result)
            stopped = stopped or on_error == "stop"
            report_processed(result, completed)
            continue
        if stopped:
            result = FileResult(
                source,
                FileStatus.SKIPPED,
                issues=(
                    Issue(
                        "SKIPPED_AFTER_FAILURE",
                        "Parsing was not attempted because on_error='stop' stopped the batch.",
                        Severity.WARNING,
                        display_source,
                    ),
                ),
            )
            processed.append(result)
            report_processed(result, completed)
            continue
        selected_adapter_id: str | None = None
        selected_adapter_version: str | None = None
        probes: tuple[tuple[str, float, str], ...] = ()
        try:
            detection = detect_adapter(source.path, registry, forced_adapter=forced_adapter)
            probes = tuple(
                (adapter_id, probe.confidence, probe.reason)
                for adapter_id, probe in detection.probes
            )
            selected_adapter_id = detection.adapter.adapter_id
            selected_adapter_version = detection.adapter.adapter_version
            source = replace(source, detected_format=detection.adapter.adapter_id)
            parsed_bundle = detection.adapter.parse(source.path, options)
            structure_issues = validate_bundle_structure(parsed_bundle)
            if not structure_issues and _bundle_issue_has_private_path(parsed_bundle):
                structure_issues = (
                    Issue(
                        "CANONICAL_ISSUE_PRIVATE_PATH",
                        "An adapter issue contained a machine-local absolute path; the plugin "
                        "file was excluded and the private text was omitted.",
                        Severity.ERROR,
                        display_source,
                    ),
                )
            bundle = None if structure_issues else _bind_source(parsed_bundle, source)
            datetime_issues: tuple[Issue, ...] = ()
            if bundle is not None and len(bundle.samples) == 1:
                bundle, datetime_issues = _normalize_datetimes(bundle, display_source)
            try:
                post_parse_sha256 = sha256_file(source.path)
            except (OSError, UnicodeError) as error:
                raise LabConvertError(
                    "INPUT_INTEGRITY_CHECK_FAILED",
                    "Input integrity could not be verified after parsing "
                    f"({type(error).__name__}).",
                ) from error
            if source.sha256 != post_parse_sha256:
                issue = Issue(
                    "INPUT_CHANGED_DURING_PARSE",
                    "Input content changed between discovery and the post-parse integrity check; "
                    "parsed scientific data was excluded from output.",
                    Severity.ERROR,
                    display_source,
                )
                result = FileResult(
                    source,
                    FileStatus.FAILED,
                    detection.adapter.adapter_id,
                    detection.adapter.adapter_version,
                    bundle,
                    (*discovery_issues, issue),
                    probes=probes,
                )
                processed.append(result)
                stopped = stopped or on_error == "stop"
            elif structure_issues:
                result = FileResult(
                    source,
                    FileStatus.FAILED,
                    detection.adapter.adapter_id,
                    detection.adapter.adapter_version,
                    None,
                    (*discovery_issues, *structure_issues),
                    probes=probes,
                )
                processed.append(result)
                stopped = stopped or on_error == "stop"
            else:
                assert bundle is not None
                validation = validate_bundle(bundle)
                issues = _bounded_file_issues(
                    (
                        *discovery_issues,
                        *bundle.warnings,
                        *bundle.errors,
                        *datetime_issues,
                        *validation,
                    ),
                    display_source,
                )
                if any(issue.severity is Severity.ERROR for issue in issues):
                    result = FileResult(
                        source,
                        FileStatus.FAILED,
                        detection.adapter.adapter_id,
                        detection.adapter.adapter_version,
                        bundle,
                        issues,
                        probes=probes,
                    )
                    processed.append(result)
                    stopped = stopped or on_error == "stop"
                else:
                    status = FileStatus.WARNING if issues else FileStatus.SUCCESS
                    result = FileResult(
                        source,
                        status,
                        detection.adapter.adapter_id,
                        detection.adapter.adapter_version,
                        bundle,
                        issues,
                        probes=probes,
                    )
                    processed.append(result)
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception as error:  # per-file boundary isolates ordinary plugin/parser failures
            result = FileResult(
                source,
                FileStatus.FAILED,
                selected_adapter_id,
                selected_adapter_version,
                issues=_bounded_file_issues(
                    (*discovery_issues, _issue_from_error(error, source)), display_source
                ),
                probes=probes,
            )
            processed.append(result)
            stopped = stopped or on_error == "stop"
        report_processed(result, completed)
    ordered, decision = sort_file_results(tuple(processed), requested_sort)
    return BatchResult(
        ordered,
        decision,
        options=ConversionOptions(
            recursive=recursive,
            extensions=tuple(str(item) for item in normalized_extensions or ()),
            sort=requested_sort,
            adapter=forced_adapter,
            sheet=options.sheet,
            include_hidden_sheets=options.include_hidden_sheets,
            on_error=on_error,
        ),
    )
