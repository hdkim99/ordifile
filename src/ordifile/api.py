# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Stable public API used by the CLI and future GUI."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ordifile.adapters._delimited import preview_delimited_peak_table
from ordifile.adapters.base import AdapterDescriptor, ParseOptions
from ordifile.adapters.generic_xlsx import preview_xlsx_peak_table
from ordifile.adapters.registry import (
    MAX_EXTENSION_FILTER_MANIFEST_CHARACTERS,
    MAX_EXTENSION_FILTERS,
    AdapterRegistry,
    create_registry,
    normalize_extension_token,
)
from ordifile.core.discovery import paths_alias
from ordifile.core.errors import ExportError, OrdifileError
from ordifile.core.models import (
    BatchResult,
    ConversionOptions,
    DatasetBundle,
    FileResult,
    InspectionResult,
    ProgressEvent,
    Severity,
    SortMode,
    SourceFile,
)
from ordifile.core.peak_mapping import (
    MAPPED_XLSX_SHEET_MARKER,
    PeakTableFormat,
    PeakTableMapping,
    PeakTableMappingSet,
    PeakTablePreview,
)
from ordifile.core.pipeline import run_pipeline
from ordifile.exporters.excel import ExcelExporter


@dataclass(frozen=True, slots=True)
class FormatReport:
    """Installed adapter descriptors plus privacy-safe plugin load diagnostics."""

    descriptors: tuple[AdapterDescriptor, ...]
    load_errors: tuple[str, ...]


def _public_api_source(source: SourceFile) -> SourceFile:
    """Remove a privacy-policy source path from a public API return value."""
    if source.public_id is None:
        return source
    reference = source.public_reference
    return replace(
        source,
        path=Path(reference),
        relative_path=reference,
        name=reference,
    )


def _public_api_bundle(bundle: DatasetBundle | None) -> DatasetBundle | None:
    """Rebind nested source records to their public-only API representation."""
    if bundle is None:
        return None
    sources = tuple(_public_api_source(source) for source in bundle.sources)
    source_by_order = {source.input_order: source for source in sources}
    samples = tuple(
        replace(
            sample,
            source=source_by_order.get(
                sample.source.input_order,
                _public_api_source(sample.source),
            ),
        )
        for sample in bundle.samples
    )
    return replace(bundle, sources=sources, samples=samples)


def _public_api_file_result(result: FileResult) -> FileResult:
    """Return one result without privacy-policy filesystem names or paths."""
    return replace(
        result,
        source=_public_api_source(result.source),
        bundle=_public_api_bundle(result.bundle),
    )


def _public_api_batch_result(result: BatchResult) -> BatchResult:
    """Return a batch safe for callers while leaving generic provenance unchanged."""
    return replace(
        result,
        files=tuple(_public_api_file_result(item) for item in result.files),
    )


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise OrdifileError("OPTION_TYPE_INVALID", f"{name} must be an exact boolean value.")


def _require_optional_text(name: str, value: object) -> None:
    if value is not None and type(value) is not str:
        raise OrdifileError("OPTION_TYPE_INVALID", f"{name} must be text or None.")


def _require_registry(registry: object) -> None:
    if registry is not None and type(registry) is not AdapterRegistry:
        raise OrdifileError("OPTION_TYPE_INVALID", "registry must be an AdapterRegistry or None.")


def _require_peak_mapping(value: object) -> None:
    if value is not None and type(value) is not PeakTableMapping:
        raise OrdifileError(
            "OPTION_TYPE_INVALID",
            "peak_table_mapping must be a PeakTableMapping or None.",
        )


def _require_peak_mapping_set(value: object) -> None:
    if value is not None and type(value) is not PeakTableMappingSet:
        raise OrdifileError(
            "OPTION_TYPE_INVALID",
            "peak_table_mapping_set must be a PeakTableMappingSet or None.",
        )


def _validate_peak_mapping_options(
    mapping: PeakTableMapping | None,
    mapping_set: PeakTableMappingSet | None = None,
    *,
    sheet: str | None,
    include_hidden_sheets: bool = False,
) -> None:
    """Reject XLSX-only options for mapped text before discovery begins."""
    if (
        mapping is not None
        and mapping.source_format is not PeakTableFormat.XLSX
        and sheet is not None
    ):
        raise OrdifileError(
            "PEAK_MAPPING_SHEET_INVALID",
            "sheet is available only for XLSX peak-table mappings.",
        )
    if mapping is not None and mapping_set is not None:
        raise OrdifileError(
            "PEAK_MAPPING_OPTION_CONFLICT",
            "peak_table_mapping and peak_table_mapping_set are mutually exclusive.",
        )
    if mapping_set is not None and (sheet is not None or include_hidden_sheets):
        raise OrdifileError(
            "PEAK_MAPPING_SET_SHEET_CONFLICT",
            "Mapping profiles own XLSX worksheet selection; sheet options cannot be combined.",
        )


def _public_sheet_option(mapping: PeakTableMapping | None, sheet: str | None) -> str | None:
    """Return a fixed marker instead of a private mapped worksheet title."""
    if mapping is not None and sheet is not None:
        return MAPPED_XLSX_SHEET_MARKER
    return sheet


def _inputs(
    values: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
) -> tuple[str | os.PathLike[str], ...]:
    if isinstance(values, (str, os.PathLike)):
        return (values,)
    return tuple(values)


def _normalize_sort(sort: SortMode | str) -> SortMode:
    if type(sort) not in {str, SortMode}:
        raise OrdifileError("SORT_MODE_INVALID", "sort must be a supported text sort mode.")
    try:
        return SortMode(sort)
    except ValueError as error:
        choices = ", ".join(mode.value for mode in SortMode)
        raise OrdifileError("SORT_MODE_INVALID", f"sort must be one of: {choices}.") from error


def _normalize_extensions(extensions: Iterable[str] | None) -> tuple[str, ...] | None:
    if extensions is None:
        return None
    if type(extensions) is str:
        raise OrdifileError(
            "OPTION_TYPE_INVALID", "extensions must be an iterable of text values, not text."
        )
    try:
        normalized_extensions = tuple(extensions)
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except Exception as error:
        raise OrdifileError(
            "OPTION_TYPE_INVALID", "extensions must be an iterable of text values."
        ) from error
    if any(type(item) is not str for item in normalized_extensions):
        raise OrdifileError(
            "OPTION_TYPE_INVALID", "extensions must contain only exact text values."
        )
    if len(normalized_extensions) > MAX_EXTENSION_FILTERS:
        raise OrdifileError(
            "EXTENSIONS_INVALID",
            f"extensions supports at most {MAX_EXTENSION_FILTERS} stable filters.",
        )
    stable_extensions: list[str] = []
    for item in normalized_extensions:
        stable = normalize_extension_token(item)
        if stable is None:
            raise OrdifileError(
                "EXTENSIONS_INVALID",
                "Each extension must be a nonempty dotted or undotted ASCII token with at "
                "most 32 characters after the optional leading dot, without controls or "
                "path separators.",
            )
        stable_extensions.append(stable)
    if len(set(stable_extensions)) != len(stable_extensions):
        raise OrdifileError(
            "EXTENSIONS_INVALID",
            "extensions must not contain duplicate case-insensitive filters.",
        )
    if len("; ".join(stable_extensions)) > MAX_EXTENSION_FILTER_MANIFEST_CHARACTERS:
        raise OrdifileError(
            "EXTENSIONS_INVALID",
            "The normalized extension filter list exceeds the bounded Manifest option.",
        )
    return tuple(stable_extensions)


def list_formats(*, registry: AdapterRegistry | None = None) -> tuple[AdapterDescriptor, ...]:
    """List fixture-tested adapters with explicit evidence status."""
    return tuple(
        descriptor
        for descriptor in get_format_report(registry=registry).descriptors
        if descriptor.tested_fixture
    )


def get_format_report(*, registry: AdapterRegistry | None = None) -> FormatReport:
    """List installed formats without silently hiding external plugin load failures."""
    _require_registry(registry)
    active = create_registry() if registry is None else registry
    return FormatReport(active.descriptors(), active.load_errors)


def preview_peak_table(
    path: str | os.PathLike[str],
    source_format: PeakTableFormat,
    *,
    sheet: str | None = None,
    row_limit: int = 5,
) -> PeakTablePreview:
    """Read a bounded local header/row preview through existing generic readers."""
    if type(source_format) is not PeakTableFormat:
        raise OrdifileError("OPTION_TYPE_INVALID", "source_format must be a PeakTableFormat value.")
    _require_optional_text("sheet", sheet)
    candidate = Path(path)
    if candidate.is_symlink():
        raise OrdifileError("SYMLINK_REJECTED", "Peak-table preview does not follow symlinks.")
    if not candidate.is_file():
        raise OrdifileError("INSPECT_REQUIRES_FILE", "Peak-table preview requires one file.")
    suffixes = {
        PeakTableFormat.CSV: frozenset((".csv",)),
        PeakTableFormat.TSV: frozenset((".tsv", ".txt")),
        PeakTableFormat.SEMICOLON: frozenset((".txt",)),
        PeakTableFormat.XLSX: frozenset((".xlsx",)),
    }
    if candidate.suffix.casefold() not in suffixes[source_format]:
        raise OrdifileError(
            "PEAK_MAPPING_FORMAT_MISMATCH",
            "The input extension does not match the selected audited source format.",
        )
    if source_format is PeakTableFormat.XLSX:
        return preview_xlsx_peak_table(candidate, sheet=sheet, row_limit=row_limit)
    if sheet is not None:
        raise OrdifileError(
            "PEAK_MAPPING_SHEET_INVALID", "sheet is available only for XLSX mappings."
        )
    return preview_delimited_peak_table(candidate, source_format, row_limit=row_limit)


def inspect_file(
    path: str | os.PathLike[str],
    *,
    adapter: str | None = None,
    sheet: str | None = None,
    include_hidden_sheets: bool = False,
    peak_table_mapping: PeakTableMapping | None = None,
    peak_table_mapping_set: PeakTableMappingSet | None = None,
    registry: AdapterRegistry | None = None,
) -> InspectionResult:
    """Detect, parse, and validate one file without writing an output."""
    _require_bool("include_hidden_sheets", include_hidden_sheets)
    _require_optional_text("adapter", adapter)
    _require_optional_text("sheet", sheet)
    _require_registry(registry)
    _require_peak_mapping(peak_table_mapping)
    _require_peak_mapping_set(peak_table_mapping_set)
    _validate_peak_mapping_options(
        peak_table_mapping,
        peak_table_mapping_set,
        sheet=sheet,
        include_hidden_sheets=include_hidden_sheets,
    )
    if adapter is not None and (
        peak_table_mapping is not None or peak_table_mapping_set is not None
    ):
        raise OrdifileError(
            "PEAK_MAPPING_ADAPTER_CONFLICT",
            "adapter and peak_table_mapping cannot be selected together.",
        )
    candidate = Path(path)
    if candidate.is_symlink():
        raise OrdifileError(
            "SYMLINK_REJECTED",
            "inspect_file does not follow symbolic links; provide the target explicitly.",
        )
    if not candidate.exists():
        raise OrdifileError("INPUT_NOT_FOUND", "The input path does not exist.")
    if not candidate.is_file():
        raise OrdifileError(
            "INSPECT_REQUIRES_FILE", "inspect_file requires exactly one regular file."
        )
    active = create_registry() if registry is None else registry
    result = run_pipeline(
        (path,),
        active,
        forced_adapter=adapter,
        parse_options=ParseOptions(
            sheet=sheet,
            include_hidden_sheets=include_hidden_sheets,
            peak_table_mapping=peak_table_mapping,
            peak_table_mapping_set=peak_table_mapping_set,
        ),
    )
    if len(result.files) != 1:
        raise OrdifileError("INSPECT_REQUIRES_FILE", "inspect_file requires one regular file.")
    file_result = result.files[0]
    discovery_error_codes = {
        "INPUT_NOT_FOUND",
        "INPUT_DISCOVERY_FAILED",
        "INPUT_READ_FAILED",
        "INPUT_RESOLVE_FAILED",
        "INPUT_SIZE_LIMIT",
        "INPUT_TYPE_UNSUPPORTED",
        "SYMLINK_REJECTED",
    }
    discovery_errors = [
        issue
        for issue in file_result.issues
        if issue.severity is Severity.ERROR and issue.code in discovery_error_codes
    ]
    if discovery_errors:
        issue = discovery_errors[0]
        raise OrdifileError(issue.code, issue.message)
    public_file_result = _public_api_file_result(file_result)
    return InspectionResult(public_file_result, public_file_result.probes)


def inspect_inputs(
    inputs: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
    *,
    recursive: bool = False,
    extensions: Iterable[str] | None = None,
    sort: SortMode | str = SortMode.AUTO,
    adapter: str | None = None,
    sheet: str | None = None,
    include_hidden_sheets: bool = False,
    peak_table_mapping: PeakTableMapping | None = None,
    peak_table_mapping_set: PeakTableMappingSet | None = None,
    progress: Callable[[ProgressEvent], None] | None = None,
    registry: AdapterRegistry | None = None,
) -> BatchResult:
    """Discover and inspect a batch without creating output artifacts.

    The returned paths follow the same privacy-safe public identity policy as
    :func:`convert`. A later conversion intentionally reads and validates the inputs
    again so the preview cannot authorize stale or changed scientific data.
    """
    _require_bool("recursive", recursive)
    _require_bool("include_hidden_sheets", include_hidden_sheets)
    _require_optional_text("adapter", adapter)
    _require_optional_text("sheet", sheet)
    _require_registry(registry)
    _require_peak_mapping(peak_table_mapping)
    _require_peak_mapping_set(peak_table_mapping_set)
    _validate_peak_mapping_options(
        peak_table_mapping,
        peak_table_mapping_set,
        sheet=sheet,
        include_hidden_sheets=include_hidden_sheets,
    )
    if adapter is not None and (
        peak_table_mapping is not None or peak_table_mapping_set is not None
    ):
        raise OrdifileError(
            "PEAK_MAPPING_ADAPTER_CONFLICT",
            "adapter and peak_table_mapping cannot be selected together.",
        )
    requested_sort = _normalize_sort(sort)
    normalized_extensions = _normalize_extensions(extensions)
    if progress is not None and not callable(progress):
        raise OrdifileError("OPTION_TYPE_INVALID", "progress must be callable or None.")
    normalized = _inputs(inputs)
    if not normalized:
        raise OrdifileError("NO_INPUTS", "At least one input path is required.")
    active = create_registry() if registry is None else registry
    result = run_pipeline(
        normalized,
        active,
        recursive=recursive,
        extensions=normalized_extensions,
        sort=requested_sort,
        forced_adapter=adapter,
        parse_options=ParseOptions(
            sheet=sheet,
            include_hidden_sheets=include_hidden_sheets,
            peak_table_mapping=peak_table_mapping,
            peak_table_mapping_set=peak_table_mapping_set,
        ),
        on_error="continue",
        progress=progress,
    )
    if not result.files:
        raise OrdifileError(
            "NO_DISCOVERED_FILES", "No files remained after discovery and extension filtering."
        )
    return _public_api_batch_result(
        replace(
            result,
            options=ConversionOptions(
                recursive=recursive,
                extensions=normalized_extensions or (),
                sort=result.sort.requested,
                adapter=adapter,
                sheet=_public_sheet_option(peak_table_mapping, sheet),
                include_hidden_sheets=include_hidden_sheets,
                peak_table_mapping_sha256=(
                    peak_table_mapping.semantic_sha256 if peak_table_mapping is not None else None
                ),
                peak_table_mapping_schema_version=(
                    peak_table_mapping.schema_version if peak_table_mapping is not None else None
                ),
                peak_table_source_format=(
                    peak_table_mapping.source_format.value
                    if peak_table_mapping is not None
                    else None
                ),
                peak_table_mapping_set_id=(
                    peak_table_mapping_set.set_id if peak_table_mapping_set is not None else None
                ),
                peak_table_mapping_set_schema_version=(
                    peak_table_mapping_set.schema_version
                    if peak_table_mapping_set is not None
                    else None
                ),
                peak_table_mapping_set_fingerprint=(
                    peak_table_mapping_set.structural_fingerprint_sha256
                    if peak_table_mapping_set is not None
                    else None
                ),
                peak_table_mapping_set_profile_count=(
                    len(peak_table_mapping_set.profiles)
                    if peak_table_mapping_set is not None
                    else None
                ),
            ),
        )
    )


def convert(
    inputs: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
    output: str | os.PathLike[str] = "Ordifile_Result.xlsx",
    *,
    recursive: bool = False,
    extensions: Iterable[str] | None = None,
    sort: SortMode | str = SortMode.AUTO,
    include_signals: bool = False,
    adapter: str | None = None,
    sheet: str | None = None,
    include_hidden_sheets: bool = False,
    peak_table_mapping: PeakTableMapping | None = None,
    peak_table_mapping_set: PeakTableMappingSet | None = None,
    on_error: str = "continue",
    overwrite: bool = False,
    sidecar_mode: str = "error",
    progress: Callable[[ProgressEvent], None] | None = None,
    registry: AdapterRegistry | None = None,
) -> BatchResult:
    """Batch-convert inputs into one ordered Excel workbook."""
    _require_bool("recursive", recursive)
    _require_bool("include_signals", include_signals)
    _require_bool("include_hidden_sheets", include_hidden_sheets)
    _require_bool("overwrite", overwrite)
    _require_optional_text("adapter", adapter)
    _require_optional_text("sheet", sheet)
    _require_registry(registry)
    _require_peak_mapping(peak_table_mapping)
    _require_peak_mapping_set(peak_table_mapping_set)
    _validate_peak_mapping_options(
        peak_table_mapping,
        peak_table_mapping_set,
        sheet=sheet,
        include_hidden_sheets=include_hidden_sheets,
    )
    if adapter is not None and (
        peak_table_mapping is not None or peak_table_mapping_set is not None
    ):
        raise OrdifileError(
            "PEAK_MAPPING_ADAPTER_CONFLICT",
            "adapter and peak_table_mapping cannot be selected together.",
        )
    if type(on_error) is not str or on_error not in {"continue", "stop"}:
        raise OrdifileError("ON_ERROR_INVALID", "on_error must be 'continue' or 'stop'.")
    if type(sidecar_mode) is not str or sidecar_mode not in {"error", "csv"}:
        raise OrdifileError("SIDECAR_MODE_INVALID", "sidecar_mode must be 'error' or 'csv'.")
    requested_sort = _normalize_sort(sort)
    if progress is not None and not callable(progress):
        raise OrdifileError("OPTION_TYPE_INVALID", "progress must be callable or None.")
    if not isinstance(output, (str, os.PathLike)):
        raise OrdifileError("OPTION_TYPE_INVALID", "output must be a filesystem path.")
    normalized_extensions = _normalize_extensions(extensions)
    normalized = _inputs(inputs)
    if not normalized:
        raise OrdifileError("NO_INPUTS", "At least one input path is required.")
    output_path = Path(output)
    for raw_input in normalized:
        candidate = Path(raw_input)
        if candidate.is_file() and paths_alias(candidate, output_path):
            raise ExportError(
                "OUTPUT_IS_INPUT",
                "The output workbook aliases an explicit input file; inputs are read-only.",
            )
    active = create_registry() if registry is None else registry
    result = run_pipeline(
        normalized,
        active,
        recursive=recursive,
        extensions=normalized_extensions,
        sort=requested_sort,
        forced_adapter=adapter,
        parse_options=ParseOptions(
            sheet=sheet,
            include_hidden_sheets=include_hidden_sheets,
            peak_table_mapping=peak_table_mapping,
            peak_table_mapping_set=peak_table_mapping_set,
        ),
        on_error=on_error,
        progress=progress,
        artifact_output=output_path,
    )
    if not result.files:
        raise OrdifileError(
            "NO_DISCOVERED_FILES", "No files remained after discovery and extension filtering."
        )
    if on_error == "stop" and result.failure_count:
        failed = next(item for item in result.files if item.status.value == "failed")
        issue = next(
            (item for item in failed.issues if item.severity is Severity.ERROR),
            None,
        )
        details = {
            "source_file": failed.source.public_reference,
            "error_code": issue.code if issue is not None else "UNKNOWN_FILE_FAILURE",
            "message": (
                issue.message
                if issue is not None
                else "The failed file did not provide a structured error message."
            ),
        }
        if failed.adapter_id is not None:
            details["adapter"] = failed.adapter_id
        raise OrdifileError(
            "BATCH_FILE_FAILURE",
            "Conversion stopped after the first file failure; no workbook was written.",
            details=details,
        )
    result = replace(
        result,
        options=ConversionOptions(
            recursive=recursive,
            extensions=tuple(str(item) for item in normalized_extensions or ()),
            sort=result.sort.requested,
            include_signals=include_signals,
            adapter=adapter,
            sheet=_public_sheet_option(peak_table_mapping, sheet),
            include_hidden_sheets=include_hidden_sheets,
            on_error=on_error,
            overwrite=overwrite,
            sidecar_mode=sidecar_mode,
            output_name=output_path.name,
            peak_table_mapping_sha256=(
                peak_table_mapping.semantic_sha256 if peak_table_mapping is not None else None
            ),
            peak_table_mapping_schema_version=(
                peak_table_mapping.schema_version if peak_table_mapping is not None else None
            ),
            peak_table_source_format=(
                peak_table_mapping.source_format.value if peak_table_mapping is not None else None
            ),
            peak_table_mapping_set_id=(
                peak_table_mapping_set.set_id if peak_table_mapping_set is not None else None
            ),
            peak_table_mapping_set_schema_version=(
                peak_table_mapping_set.schema_version
                if peak_table_mapping_set is not None
                else None
            ),
            peak_table_mapping_set_fingerprint=(
                peak_table_mapping_set.structural_fingerprint_sha256
                if peak_table_mapping_set is not None
                else None
            ),
            peak_table_mapping_set_profile_count=(
                len(peak_table_mapping_set.profiles) if peak_table_mapping_set is not None else None
            ),
        ),
    )
    if progress is not None:
        progress(ProgressEvent("export_start", 0, 1, output_path.name))
    exported = ExcelExporter().export(
        result,
        output_path,
        overwrite=overwrite,
        include_signals=include_signals,
        sidecar_mode=sidecar_mode,
    )
    if progress is not None:
        progress(ProgressEvent("export_complete", 1, 1, output_path.name))
    return _public_api_batch_result(exported)
