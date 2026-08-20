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
from pathlib import Path

from ordifile.adapters.base import DetectionResult, ParseOptions, SourceIdentityPolicy
from ordifile.adapters.registry import AdapterRegistry
from ordifile.core.detection import SOURCE_IDENTITY_PROBE_REASON, DetectionOutcome, detect_adapter
from ordifile.core.discovery import discover_files, sha256_file
from ordifile.core.errors import DetectionError, OrdifileError
from ordifile.core.models import (
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
from ordifile.core.peak_mapping import MAPPED_XLSX_SHEET_MARKER, PeakTableFormat
from ordifile.core.privacy import contains_machine_local_path, scrub_machine_local_paths
from ordifile.core.sorting import sort_file_results
from ordifile.core.validation import validate_bundle, validate_bundle_structure
from ordifile.core.workbook_text import (
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
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SOURCE_IDENTITY_ADAPTER_ERROR_MESSAGE = "Adapter error details withheld by source identity policy."
SOURCE_IDENTITY_UNEXPECTED_ERROR_MESSAGE = (
    "The adapter raised an unexpected error; identifying details were withheld by "
    "source identity policy."
)


def _source_identity_policy_before_detection(
    path: Path,
    registry: AdapterRegistry,
    forced_adapter: str | None,
) -> SourceIdentityPolicy:
    """Return the most private policy known without inspecting source content."""
    if forced_adapter is not None:
        return registry.get(forced_adapter).descriptor.source_identity_policy
    suffix = path.suffix.casefold()
    owners = tuple(
        adapter
        for adapter in registry.adapters()
        if suffix in {extension.casefold() for extension in adapter.descriptor.extensions}
    )
    if owners and any(
        adapter.descriptor.source_identity_policy is SourceIdentityPolicy.SHA256_ALIAS
        for adapter in owners
    ):
        return SourceIdentityPolicy.SHA256_ALIAS
    return SourceIdentityPolicy.RELATIVE_PATH


def _sha256_alias_owner_ids_before_detection(
    path: Path,
    registry: AdapterRegistry,
    forced_adapter: str | None,
) -> frozenset[str]:
    """Return suffix owners whose probe evidence requires selective redaction."""
    if forced_adapter is not None:
        adapter = registry.get(forced_adapter)
        if adapter.descriptor.source_identity_policy is SourceIdentityPolicy.SHA256_ALIAS:
            return frozenset((adapter.adapter_id,))
        return frozenset()
    suffix = path.suffix.casefold()
    return frozenset(
        adapter.adapter_id
        for adapter in registry.adapters()
        if adapter.descriptor.source_identity_policy is SourceIdentityPolicy.SHA256_ALIAS
        and suffix in {extension.casefold() for extension in adapter.descriptor.extensions}
    )


def _apply_source_identity(source: SourceFile, policy: SourceIdentityPolicy) -> SourceFile:
    """Create a core-owned alias and disregard any adapter-provided public identity."""
    if policy is SourceIdentityPolicy.RELATIVE_PATH:
        return replace(source, public_id=None)
    public_id = (
        f"source-{source.sha256}"
        if type(source.sha256) is str and _SHA256.fullmatch(source.sha256) is not None
        else f"source-input-{source.input_order + 1:06d}"
    )
    return replace(source, public_id=public_id)


def _rebind_issue_sources(issues: tuple[Issue, ...], source: SourceFile) -> tuple[Issue, ...]:
    """Replace adapter or discovery source labels with the core public reference."""
    reference = workbook_audit_display(source.public_reference)
    return tuple(replace(issue, source=reference) for issue in issues)


def _redact_all_probe_reasons(
    probes: tuple[tuple[str, float, str], ...],
) -> tuple[tuple[str, float, str], ...]:
    """Withhold every probe reason when provisional private identity remains effective."""
    return tuple(
        (adapter_id, confidence, SOURCE_IDENTITY_PROBE_REASON)
        for adapter_id, confidence, _reason in probes
    )


def _bundle_issue_has_private_path(bundle: DatasetBundle) -> bool:
    """Identify external adapter issue text that could expose a machine-local path."""
    for issue in (*bundle.warnings, *bundle.errors):
        text_parts = (issue.message, *(part for pair in issue.context for part in pair))
        if issue.source is not None:
            text_parts = (*text_parts, issue.source)
        if any(contains_machine_local_path(part) for part in text_parts):
            return True
    return False


def _safe_detail_text(value: object) -> str:
    """Serialize one error detail without invoking plugin-defined conversion hooks."""
    if type(value) is str:
        if len(value) > MAX_ERROR_DETAIL_VALUE_CHARACTERS:
            return "[text-omitted-too-long]"
        if not workbook_text_is_exact(value):
            return "[text-omitted-unrepresentable]"
        return scrub_machine_local_paths(value)
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
            safe_key = scrub_machine_local_paths(key)
        else:
            safe_key = f"detail_{index:03d}"
        context.append((safe_key, _safe_detail_text(value)))
    return tuple(context)


def _issue_from_error(
    error: Exception,
    source: SourceFile,
    *,
    redact_details: bool = False,
) -> Issue:
    safe_source = workbook_audit_display(source.public_reference)
    if isinstance(error, OrdifileError):
        if redact_details:
            if type(error.code) is not str or _ADAPTER_ERROR_CODE.fullmatch(error.code) is None:
                return Issue(
                    "ADAPTER_ERROR_INVALID",
                    "The adapter raised a malformed structured error; identifying details "
                    "were withheld.",
                    Severity.ERROR,
                    safe_source,
                )
            return Issue(
                error.code,
                SOURCE_IDENTITY_ADAPTER_ERROR_MESSAGE,
                Severity.ERROR,
                safe_source,
            )
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
            scrub_machine_local_paths(error.message),
            Severity.ERROR,
            safe_source,
            _safe_error_context(error.details),
        )
    if redact_details:
        return Issue(
            "ADAPTER_UNEXPECTED_ERROR",
            SOURCE_IDENTITY_UNEXPECTED_ERROR_MESSAGE,
            Severity.ERROR,
            safe_source,
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
    safe_reference = workbook_audit_display(source.public_reference)
    peaks = tuple(replace(peak, source_file=safe_reference) for peak in bundle.peaks)
    signals = tuple(replace(signal, source_file=safe_reference) for signal in bundle.signals)
    metadata = tuple(replace(entry, source_file=safe_reference) for entry in bundle.metadata)
    warnings = tuple(replace(issue, source=safe_reference) for issue in bundle.warnings)
    errors = tuple(replace(issue, source=safe_reference) for issue in bundle.errors)
    # Preserve adapter cardinality so validation can enforce the exactly-one v0.1 contract.
    sources = tuple(source for _adapter_source in bundle.sources)
    return replace(
        bundle,
        sources=sources,
        samples=samples,
        peaks=peaks,
        signals=signals,
        metadata=metadata,
        warnings=warnings,
        errors=errors,
    )


def _bind_mapped_fallback_sample(bundle: DatasetBundle, source: SourceFile) -> DatasetBundle:
    """Replace the non-identifying parser placeholder with the SHA-derived source alias."""
    new_id = workbook_audit_display(source.public_reference)
    return replace(
        bundle,
        samples=(replace(bundle.samples[0], sample_id=new_id),),
        peaks=tuple(replace(peak, sample_id=new_id) for peak in bundle.peaks),
        metadata=tuple(replace(entry, sample_id=new_id) for entry in bundle.metadata),
    )


def _mapped_adapter_id(path: Path, source_format: PeakTableFormat) -> str:
    """Select one existing audited generic reader without content inference."""
    suffix = path.suffix.casefold()
    contracts = {
        PeakTableFormat.CSV: ("generic_csv", frozenset((".csv",))),
        PeakTableFormat.TSV: ("generic_tsv", frozenset((".tsv", ".txt"))),
        PeakTableFormat.SEMICOLON: ("generic_semicolon", frozenset((".txt",))),
        PeakTableFormat.XLSX: ("generic_xlsx", frozenset((".xlsx",))),
    }
    adapter_id, extensions = contracts[source_format]
    if suffix not in extensions:
        raise DetectionError(
            "PEAK_MAPPING_FORMAT_MISMATCH",
            "The input extension does not match the mapping's audited source format.",
        )
    return adapter_id


def _adapter_source_integrity_issue(bundle: DatasetBundle, source: SourceFile) -> Issue | None:
    """Reject a bounded adapter read that does not match discovery provenance."""
    if len(bundle.sources) != 1:
        return None
    adapter_source = bundle.sources[0]
    if adapter_source.sha256 is None:
        return None
    if (
        type(adapter_source.sha256) is not str
        or _SHA256.fullmatch(adapter_source.sha256) is None
        or type(adapter_source.size) is not int
        or adapter_source.size < 0
    ):
        return Issue(
            "ADAPTER_SOURCE_INTEGRITY_INVALID",
            "The adapter returned malformed source integrity metadata; parsed data was excluded.",
            Severity.ERROR,
            workbook_audit_display(source.public_reference),
        )
    if adapter_source.sha256 != source.sha256 or adapter_source.size != source.size:
        return Issue(
            "INPUT_CHANGED_DURING_PARSE",
            "The adapter's bounded read did not match discovery provenance; parsed data was "
            "excluded from output.",
            Severity.ERROR,
            workbook_audit_display(source.public_reference),
        )
    return None


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
        raise OrdifileError("ON_ERROR_INVALID", "on_error must be 'continue' or 'stop'.")
    try:
        requested_sort = sort if isinstance(sort, SortMode) else SortMode(sort)
    except ValueError as error:
        choices = ", ".join(mode.value for mode in SortMode)
        raise OrdifileError("SORT_MODE_INVALID", f"sort must be one of: {choices}.") from error
    if forced_adapter is not None:
        registry.get(forced_adapter)
    options = ParseOptions() if parse_options is None else parse_options
    if forced_adapter is not None and options.peak_table_mapping is not None:
        raise OrdifileError(
            "PEAK_MAPPING_ADAPTER_CONFLICT",
            "adapter and peak_table_mapping cannot be selected together.",
        )
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
                    workbook_audit_display(item.source.public_reference),
                    item.status,
                )
            )

    for completed, discovered in enumerate(discovered_files, start=1):
        sha256_alias_owner_ids = _sha256_alias_owner_ids_before_detection(
            discovered.source.path, registry, forced_adapter
        )
        initial_policy = (
            SourceIdentityPolicy.SHA256_ALIAS
            if options.peak_table_mapping is not None
            else _source_identity_policy_before_detection(
                discovered.source.path, registry, forced_adapter
            )
        )
        source = _apply_source_identity(discovered.source, initial_policy)
        artifact_excluded = any(
            issue.code == "ORDIFILE_ARTIFACT_EXCLUDED" for issue in discovered.issues
        )
        if artifact_excluded:
            # Core-owned output artifacts are already classified before adapter
            # detection and retain their ordinary audit names instead of inheriting a
            # shared-extension vendor privacy policy.
            source = _apply_source_identity(
                discovered.source,
                SourceIdentityPolicy.RELATIVE_PATH,
            )
        display_source = workbook_audit_display(source.public_reference)
        discovery_issues = _rebind_issue_sources(discovered.issues, source)
        if display_source != source.public_reference:
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
        if artifact_excluded:
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
            mapping_applied = False
            parse_for_adapter = options
            if options.peak_table_mapping is None:
                detection = detect_adapter(
                    source.path,
                    registry,
                    forced_adapter=forced_adapter,
                    redact_adapter_ids=sha256_alias_owner_ids,
                    redact_error_reasons=initial_policy is SourceIdentityPolicy.SHA256_ALIAS,
                )
            else:
                try:
                    automatic = detect_adapter(
                        source.path,
                        registry,
                        redact_adapter_ids=sha256_alias_owner_ids,
                        redact_error_reasons=True,
                    )
                except DetectionError as error:
                    if error.code != "FORMAT_NOT_DETECTED":
                        raise
                    automatic = None
                generic_ids = {
                    "generic_csv",
                    "generic_tsv",
                    "generic_semicolon",
                    "generic_xlsx",
                }
                if automatic is not None and automatic.adapter.adapter_id not in generic_ids:
                    detection = automatic
                    parse_for_adapter = replace(options, peak_table_mapping=None)
                else:
                    mapped_id = _mapped_adapter_id(
                        source.path, options.peak_table_mapping.source_format
                    )
                    mapped_adapter = registry.get(mapped_id)
                    detection = DetectionOutcome(
                        mapped_adapter,
                        (
                            (
                                mapped_id,
                                DetectionResult(
                                    True,
                                    1.0,
                                    "Explicit user mapping selected an audited generic container.",
                                ),
                            ),
                        ),
                    )
                    mapping_applied = True
            selected_adapter_id = detection.adapter.adapter_id
            selected_adapter_version = detection.adapter.adapter_version
            selected_adapter_policy = detection.adapter.descriptor.source_identity_policy
            if mapping_applied:
                selected_adapter_policy = SourceIdentityPolicy.SHA256_ALIAS
            selected_policy = selected_adapter_policy
            if initial_policy is SourceIdentityPolicy.SHA256_ALIAS:
                selected_policy = SourceIdentityPolicy.SHA256_ALIAS
            probes = tuple(
                (
                    adapter_id,
                    probe.confidence,
                    probe.reason,
                )
                for adapter_id, probe in detection.probes
            )
            if selected_adapter_policy is SourceIdentityPolicy.SHA256_ALIAS:
                probes = _redact_all_probe_reasons(probes)
            source = replace(
                _apply_source_identity(source, selected_policy),
                detected_format=detection.adapter.adapter_id,
            )
            discovery_issues = _rebind_issue_sources(discovery_issues, source)
            display_source = workbook_audit_display(source.public_reference)
            if options.peak_table_mapping is not None and not mapping_applied:
                discovery_issues = (
                    *discovery_issues,
                    Issue(
                        "PEAK_MAPPING_NOT_APPLIED_EXACT_PROFILE",
                        "The explicit mapping was not applied because an exact-profile adapter "
                        "owned this input.",
                        Severity.WARNING,
                        display_source,
                    ),
                )
            parsed_bundle = detection.adapter.parse(source.path, parse_for_adapter)
            structure_issues = validate_bundle_structure(parsed_bundle)
            if not structure_issues:
                adapter_integrity_issue = _adapter_source_integrity_issue(parsed_bundle, source)
                if adapter_integrity_issue is not None:
                    structure_issues = (adapter_integrity_issue,)
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
            structure_issues = _rebind_issue_sources(structure_issues, source)
            bundle = None if structure_issues else _bind_source(parsed_bundle, source)
            if (
                bundle is not None
                and mapping_applied
                and options.peak_table_mapping is not None
                and options.peak_table_mapping.sample_id_column is None
            ):
                bundle = _bind_mapped_fallback_sample(bundle, source)
            datetime_issues: tuple[Issue, ...] = ()
            if bundle is not None and len(bundle.samples) == 1:
                bundle, datetime_issues = _normalize_datetimes(bundle, display_source)
            try:
                post_parse_sha256 = sha256_file(source.path)
            except (OSError, UnicodeError) as error:
                raise OrdifileError(
                    "INPUT_INTEGRITY_CHECK_FAILED",
                    "Input integrity could not be verified after parsing "
                    f"({type(error).__name__}).",
                ) from error
            if source.sha256 != post_parse_sha256:
                if initial_policy is SourceIdentityPolicy.SHA256_ALIAS:
                    probes = _redact_all_probe_reasons(probes)
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
                    None,
                    (*discovery_issues, issue),
                    probes=probes,
                )
                processed.append(result)
                stopped = stopped or on_error == "stop"
            elif structure_issues:
                if initial_policy is SourceIdentityPolicy.SHA256_ALIAS:
                    probes = _redact_all_probe_reasons(probes)
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
                    if initial_policy is SourceIdentityPolicy.SHA256_ALIAS:
                        probes = _redact_all_probe_reasons(probes)
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
                    if selected_adapter_policy is SourceIdentityPolicy.RELATIVE_PATH:
                        source = replace(
                            _apply_source_identity(
                                discovered.source,
                                SourceIdentityPolicy.RELATIVE_PATH,
                            ),
                            detected_format=detection.adapter.adapter_id,
                        )
                        bundle = _bind_source(bundle, source)
                        issues = _rebind_issue_sources(issues, source)
                        restored_display = workbook_audit_display(source.public_reference)
                        if restored_display != source.public_reference:
                            issues = _bounded_file_issues(
                                (
                                    *issues,
                                    Issue(
                                        "SOURCE_DISPLAY_ESCAPED",
                                        "Unsafe source identity code points were reversibly "
                                        "escaped for workbook audit fields; the input file and "
                                        "its SHA-256 were not changed.",
                                        Severity.WARNING,
                                        restored_display,
                                    ),
                                ),
                                restored_display,
                            )
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
            if initial_policy is SourceIdentityPolicy.SHA256_ALIAS:
                probes = _redact_all_probe_reasons(probes)
            result = FileResult(
                source,
                FileStatus.FAILED,
                selected_adapter_id,
                selected_adapter_version,
                issues=_bounded_file_issues(
                    (
                        *discovery_issues,
                        _issue_from_error(
                            error,
                            source,
                            redact_details=source.public_id is not None,
                        ),
                    ),
                    display_source,
                ),
                probes=probes,
            )
            processed.append(result)
            stopped = stopped or on_error == "stop"
        result = replace(result, issues=_rebind_issue_sources(result.issues, result.source))
        processed[-1] = result
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
            sheet=(
                MAPPED_XLSX_SHEET_MARKER
                if options.peak_table_mapping is not None and options.sheet is not None
                else options.sheet
            ),
            include_hidden_sheets=options.include_hidden_sheets,
            on_error=on_error,
            peak_table_mapping_sha256=(
                options.peak_table_mapping.semantic_sha256
                if options.peak_table_mapping is not None
                else None
            ),
            peak_table_mapping_schema_version=(
                options.peak_table_mapping.schema_version
                if options.peak_table_mapping is not None
                else None
            ),
            peak_table_source_format=(
                options.peak_table_mapping.source_format.value
                if options.peak_table_mapping is not None
                else None
            ),
        ),
    )
