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
from ordifile.adapters.generic_xlsx import (
    list_xlsx_peak_table_worksheets,
    preview_xlsx_peak_table,
)
from ordifile.adapters.registry import (
    MAX_EXTENSION_FILTER_MANIFEST_CHARACTERS,
    MAX_EXTENSION_FILTERS,
    AdapterRegistry,
    create_registry,
    normalize_extension_token,
)
from ordifile.core.discovery import paths_alias, sha256_file
from ordifile.core.errors import ExportError, OrdifileError
from ordifile.core.models import (
    BatchResult,
    ConversionExecutionMode,
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
    MAX_PEAK_PREVIEW_ROWS,
    PeakTableFormat,
    PeakTableImportSettings,
    PeakTableMapping,
    PeakTableMappingSet,
    PeakTablePreview,
    PeakTableTextEncoding,
)
from ordifile.core.pipeline import run_pipeline
from ordifile.core.planning import (
    ConversionPlan,
    PlanProgressEvent,
    build_conversion_plan,
    output_binding,
    plan_bindings,
)
from ordifile.core.recipe import ConversionRecipe
from ordifile.core.routing import InputRouteExpectation
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


def _require_conversion_recipe(value: object, *, optional: bool = True) -> None:
    if value is None and optional:
        return
    if type(value) is not ConversionRecipe:
        raise OrdifileError(
            "OPTION_TYPE_INVALID",
            "recipe must be a ConversionRecipe.",
        )


def _apply_conversion_recipe(
    recipe: ConversionRecipe | None,
    *,
    recursive: bool,
    extensions: Iterable[str] | None,
    sort: SortMode | str,
    include_signals: bool,
    adapter: str | None,
    sheet: str | None,
    include_hidden_sheets: bool,
    peak_table_mapping: PeakTableMapping | None,
    peak_table_mapping_set: PeakTableMappingSet | None,
    on_error: str,
    overwrite: bool,
    sidecar_mode: str,
) -> tuple[
    bool,
    Iterable[str] | None,
    SortMode | str,
    bool,
    str | None,
    str | None,
    bool,
    PeakTableMapping | None,
    PeakTableMappingSet | None,
    str,
    bool,
    str,
]:
    """Apply one recipe only when no behavior option competes with it."""
    _require_conversion_recipe(recipe)
    if recipe is None:
        return (
            recursive,
            extensions,
            sort,
            include_signals,
            adapter,
            sheet,
            include_hidden_sheets,
            peak_table_mapping,
            peak_table_mapping_set,
            on_error,
            overwrite,
            sidecar_mode,
        )
    conflicts = (
        recursive
        or extensions is not None
        or sort not in {SortMode.AUTO, SortMode.AUTO.value}
        or include_signals
        or adapter is not None
        or sheet is not None
        or include_hidden_sheets
        or peak_table_mapping is not None
        or peak_table_mapping_set is not None
        or on_error != "continue"
        or overwrite
        or sidecar_mode != "error"
    )
    if conflicts:
        raise OrdifileError(
            "CONVERSION_RECIPE_OPTION_CONFLICT",
            "A recipe cannot be combined with separate behavior or overwrite options.",
        )
    return (
        recipe.recursive,
        recipe.extensions or None,
        recipe.sort,
        recipe.include_signals,
        recipe.adapter,
        recipe.sheet,
        recipe.include_hidden_sheets,
        recipe.peak_table_mapping,
        recipe.peak_table_mapping_set,
        recipe.on_error,
        False,
        recipe.sidecar_mode,
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


def _public_sheet_option(
    mapping: PeakTableMapping | None,
    sheet: str | None,
    *,
    recipe_active: bool = False,
) -> str | None:
    """Return a fixed marker instead of a private mapped or Recipe worksheet title."""
    if sheet is not None and (mapping is not None or recipe_active):
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
    import_settings: PeakTableImportSettings | None = None,
) -> PeakTablePreview:
    """Read a bounded local header/row preview through existing generic readers."""
    if type(source_format) is not PeakTableFormat:
        raise OrdifileError("OPTION_TYPE_INVALID", "source_format must be a PeakTableFormat value.")
    if type(row_limit) is not int or row_limit < 1 or row_limit > MAX_PEAK_PREVIEW_ROWS:
        raise OrdifileError(
            "PEAK_MAPPING_PREVIEW_LIMIT_INVALID",
            f"row_limit must be from 1 through {MAX_PEAK_PREVIEW_ROWS}.",
        )
    _require_optional_text("sheet", sheet)
    if import_settings is not None and type(import_settings) is not PeakTableImportSettings:
        raise OrdifileError(
            "OPTION_TYPE_INVALID",
            "import_settings must be a PeakTableImportSettings value or None.",
        )
    settings = import_settings or PeakTableImportSettings()
    if (
        source_format is PeakTableFormat.XLSX
        and settings.text_encoding is not PeakTableTextEncoding.UTF8
    ):
        raise OrdifileError(
            "PEAK_MAPPING_IMPORT_SETTINGS_INVALID",
            "Text encoding is available only for delimited peak tables.",
        )
    candidate = Path(path)
    if candidate.is_symlink():
        raise OrdifileError("SYMLINK_REJECTED", "Peak-table preview does not follow symlinks.")
    if not candidate.is_file():
        raise OrdifileError("INSPECT_REQUIRES_FILE", "Peak-table preview requires one file.")
    try:
        before = candidate.stat()
    except OSError as error:
        raise OrdifileError(
            "PEAK_MAPPING_PREVIEW_READ_FAILED",
            "The peak-table preview source could not be inspected safely.",
        ) from error
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
        preview = preview_xlsx_peak_table(
            candidate,
            sheet=sheet,
            row_limit=row_limit,
            import_settings=settings,
        )
    else:
        if sheet is not None:
            raise OrdifileError(
                "PEAK_MAPPING_SHEET_INVALID", "sheet is available only for XLSX mappings."
            )
        preview = preview_delimited_peak_table(
            candidate,
            source_format,
            row_limit=row_limit,
            import_settings=settings,
        )
    try:
        source_sha256 = sha256_file(candidate)
        after = candidate.stat()
    except OSError as error:
        raise OrdifileError(
            "PEAK_MAPPING_PREVIEW_READ_FAILED",
            "The peak-table preview source could not be read safely.",
        ) from error
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise OrdifileError(
            "PEAK_MAPPING_PREVIEW_SOURCE_CHANGED",
            "The peak-table preview source changed while it was being inspected.",
        )
    return replace(preview, source_sha256=source_sha256)


def list_peak_table_worksheets(
    path: str | os.PathLike[str],
    *,
    include_hidden: bool = False,
) -> tuple[str, ...]:
    """List audited XLSX worksheet titles for explicit local selection."""
    _require_bool("include_hidden", include_hidden)
    candidate = Path(path)
    if candidate.is_symlink():
        raise OrdifileError("SYMLINK_REJECTED", "Worksheet selection does not follow symlinks.")
    if not candidate.is_file() or candidate.suffix.casefold() != ".xlsx":
        raise OrdifileError(
            "PEAK_MAPPING_FORMAT_MISMATCH",
            "Worksheet selection requires one XLSX file.",
        )
    worksheets = list_xlsx_peak_table_worksheets(
        candidate,
        include_hidden=include_hidden,
    )
    if not worksheets:
        raise OrdifileError(
            "XLSX_NO_VISIBLE_SHEET",
            "The workbook has no visible worksheet available for mapping.",
        )
    return worksheets


def inspect_file(
    path: str | os.PathLike[str],
    *,
    adapter: str | None = None,
    sheet: str | None = None,
    include_hidden_sheets: bool = False,
    peak_table_mapping: PeakTableMapping | None = None,
    peak_table_mapping_set: PeakTableMappingSet | None = None,
    experimental_derived_area: bool = False,
    registry: AdapterRegistry | None = None,
) -> InspectionResult:
    """Detect, parse, and validate one file without writing an output."""
    _require_bool("include_hidden_sheets", include_hidden_sheets)
    _require_bool("experimental_derived_area", experimental_derived_area)
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
            experimental_derived_area=experimental_derived_area,
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
    experimental_derived_area: bool = False,
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
    _require_bool("experimental_derived_area", experimental_derived_area)
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
            experimental_derived_area=experimental_derived_area,
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
                experimental_derived_area=experimental_derived_area,
            ),
        )
    )


def _convert_impl(
    inputs: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
    output: str | os.PathLike[str] = "Ordifile_Result.xlsx",
    *,
    recursive: bool = False,
    extensions: Iterable[str] | None = None,
    sort: SortMode | str = SortMode.AUTO,
    include_signals: bool = False,
    experimental_derived_area: bool = False,
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
    expected_sources: tuple[tuple[str, int, str | None, int | None, tuple[str, ...]], ...]
    | None = None,
    expected_routes: tuple[InputRouteExpectation | None, ...] | None = None,
    expected_registry_signature: tuple[tuple[str, str, str], ...] | None = None,
    expected_output_binding: object | None = None,
    conversion_plan_schema_version: int | None = None,
    conversion_plan_public_summary_sha256: str | None = None,
    conversion_recipe_schema_version: int | None = None,
    conversion_recipe_public_fingerprint_sha256: str | None = None,
) -> BatchResult:
    """Batch-convert inputs into one ordered Excel workbook."""
    _require_bool("recursive", recursive)
    _require_bool("include_signals", include_signals)
    _require_bool("experimental_derived_area", experimental_derived_area)
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
        preserve_exact_adapter_precedence=conversion_recipe_schema_version is not None,
        parse_options=ParseOptions(
            sheet=sheet,
            worksheet_provenance=(
                MAPPED_XLSX_SHEET_MARKER
                if conversion_recipe_schema_version is not None and sheet is not None
                else None
            ),
            include_hidden_sheets=include_hidden_sheets,
            include_mapping_semantic_sha256=(conversion_recipe_schema_version is None),
            peak_table_mapping=peak_table_mapping,
            peak_table_mapping_set=peak_table_mapping_set,
            experimental_derived_area=experimental_derived_area,
        ),
        on_error=on_error,
        progress=progress,
        artifact_output=output_path,
        expected_sources=expected_sources,
        expected_routes=expected_routes,
        expected_registry_signature=expected_registry_signature,
    )
    if not result.files:
        raise OrdifileError(
            "NO_DISCOVERED_FILES", "No files remained after discovery and extension filtering."
        )
    if expected_sources is not None and any(
        issue.code in {"INPUT_CHANGED_DURING_PARSE", "INPUT_INTEGRITY_CHECK_FAILED"}
        for item in result.files
        for issue in item.issues
    ):
        raise OrdifileError(
            "CONVERSION_PLAN_STALE",
            "An input changed during planned conversion; no workbook was written.",
        )
    if (
        expected_output_binding is not None
        and output_binding(output_path) != expected_output_binding
    ):
        raise OrdifileError(
            "CONVERSION_PLAN_STALE",
            "The output target changed after conversion preflight; no workbook was written.",
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
            sheet=_public_sheet_option(
                peak_table_mapping,
                sheet,
                recipe_active=conversion_recipe_schema_version is not None,
            ),
            include_hidden_sheets=include_hidden_sheets,
            on_error=on_error,
            overwrite=overwrite,
            sidecar_mode=sidecar_mode,
            output_name=output_path.name,
            peak_table_mapping_sha256=(
                peak_table_mapping.semantic_sha256
                if peak_table_mapping is not None and conversion_recipe_schema_version is None
                else None
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
            execution_mode=(
                ConversionExecutionMode.REVALIDATED_PREFLIGHT
                if conversion_plan_public_summary_sha256 is not None
                else ConversionExecutionMode.DIRECT
            ),
            conversion_plan_schema_version=conversion_plan_schema_version,
            conversion_plan_public_summary_sha256=conversion_plan_public_summary_sha256,
            conversion_recipe_schema_version=conversion_recipe_schema_version,
            conversion_recipe_public_fingerprint_sha256=(
                conversion_recipe_public_fingerprint_sha256
            ),
            experimental_derived_area=experimental_derived_area,
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


def plan_conversion(
    inputs: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
    output: str | os.PathLike[str] = "Ordifile_Result.xlsx",
    *,
    recursive: bool = False,
    extensions: Iterable[str] | None = None,
    sort: SortMode | str = SortMode.AUTO,
    include_signals: bool = False,
    experimental_derived_area: bool = False,
    adapter: str | None = None,
    sheet: str | None = None,
    include_hidden_sheets: bool = False,
    peak_table_mapping: PeakTableMapping | None = None,
    peak_table_mapping_set: PeakTableMappingSet | None = None,
    on_error: str = "continue",
    overwrite: bool = False,
    sidecar_mode: str = "error",
    progress: Callable[[PlanProgressEvent], None] | None = None,
    registry: AdapterRegistry | None = None,
) -> ConversionPlan:
    """Build a route-only immutable plan without canonical rows or output artifacts."""
    return _plan_conversion_impl(
        inputs,
        output,
        recursive=recursive,
        extensions=extensions,
        sort=sort,
        include_signals=include_signals,
        experimental_derived_area=experimental_derived_area,
        adapter=adapter,
        sheet=sheet,
        include_hidden_sheets=include_hidden_sheets,
        peak_table_mapping=peak_table_mapping,
        peak_table_mapping_set=peak_table_mapping_set,
        on_error=on_error,
        overwrite=overwrite,
        sidecar_mode=sidecar_mode,
        progress=progress,
        registry=registry,
        recipe=None,
    )


def plan_recipe(
    inputs: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
    output: str | os.PathLike[str] = "Ordifile_Result.xlsx",
    *,
    recipe: ConversionRecipe,
    experimental_derived_area: bool = False,
    progress: Callable[[PlanProgressEvent], None] | None = None,
    registry: AdapterRegistry | None = None,
) -> ConversionPlan:
    """Build a conversion plan from one validated local Recipe and runtime paths."""
    _require_conversion_recipe(recipe, optional=False)
    return _plan_conversion_impl(
        inputs,
        output,
        experimental_derived_area=experimental_derived_area,
        progress=progress,
        registry=registry,
        recipe=recipe,
    )


def _plan_conversion_impl(
    inputs: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
    output: str | os.PathLike[str] = "Ordifile_Result.xlsx",
    *,
    recursive: bool = False,
    extensions: Iterable[str] | None = None,
    sort: SortMode | str = SortMode.AUTO,
    include_signals: bool = False,
    experimental_derived_area: bool = False,
    adapter: str | None = None,
    sheet: str | None = None,
    include_hidden_sheets: bool = False,
    peak_table_mapping: PeakTableMapping | None = None,
    peak_table_mapping_set: PeakTableMappingSet | None = None,
    on_error: str = "continue",
    overwrite: bool = False,
    sidecar_mode: str = "error",
    progress: Callable[[PlanProgressEvent], None] | None = None,
    registry: AdapterRegistry | None = None,
    recipe: ConversionRecipe | None = None,
) -> ConversionPlan:
    """Shared implementation for direct and Recipe-backed preflight."""
    (
        recursive,
        extensions,
        sort,
        include_signals,
        adapter,
        sheet,
        include_hidden_sheets,
        peak_table_mapping,
        peak_table_mapping_set,
        on_error,
        overwrite,
        sidecar_mode,
    ) = _apply_conversion_recipe(
        recipe,
        recursive=recursive,
        extensions=extensions,
        sort=sort,
        include_signals=include_signals,
        adapter=adapter,
        sheet=sheet,
        include_hidden_sheets=include_hidden_sheets,
        peak_table_mapping=peak_table_mapping,
        peak_table_mapping_set=peak_table_mapping_set,
        on_error=on_error,
        overwrite=overwrite,
        sidecar_mode=sidecar_mode,
    )
    _require_bool("recursive", recursive)
    _require_bool("include_signals", include_signals)
    _require_bool("experimental_derived_area", experimental_derived_area)
    _require_bool("include_hidden_sheets", include_hidden_sheets)
    _require_bool("overwrite", overwrite)
    if overwrite:
        raise OrdifileError(
            "CONVERSION_PLAN_OVERWRITE_UNSUPPORTED",
            "Conversion preflight requires a new output target; use direct conversion for an "
            "explicit overwrite.",
        )
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
    if progress is not None and not callable(progress):
        raise OrdifileError("OPTION_TYPE_INVALID", "progress must be callable or None.")
    if not isinstance(output, (str, os.PathLike)):
        raise OrdifileError("OPTION_TYPE_INVALID", "output must be a filesystem path.")
    requested_sort = _normalize_sort(sort)
    normalized_extensions = _normalize_extensions(extensions)
    normalized = _inputs(inputs)
    if not normalized:
        raise OrdifileError("NO_INPUTS", "At least one input path is required.")
    active = create_registry() if registry is None else registry
    if adapter is not None:
        active.get(adapter)
    return build_conversion_plan(
        normalized,
        output,
        active,
        recursive=recursive,
        extensions=normalized_extensions,
        sort=requested_sort.value,
        include_signals=include_signals,
        experimental_derived_area=experimental_derived_area,
        adapter=adapter,
        sheet=sheet,
        include_hidden_sheets=include_hidden_sheets,
        peak_table_mapping=peak_table_mapping,
        peak_table_mapping_set=peak_table_mapping_set,
        on_error=on_error,
        overwrite=overwrite,
        sidecar_mode=sidecar_mode,
        recipe_schema_version=recipe.schema_version if recipe is not None else None,
        recipe_public_fingerprint_sha256=(
            recipe.public_fingerprint_sha256 if recipe is not None else None
        ),
        recipe_semantic_sha256=recipe.semantic_sha256 if recipe is not None else None,
        progress=progress,
    )


def convert_plan(
    plan: ConversionPlan,
    *,
    progress: Callable[[ProgressEvent], None] | None = None,
    registry: AdapterRegistry | None = None,
) -> BatchResult:
    """Revalidate one reviewed same-process plan, then execute the existing converter."""
    if type(plan) is not ConversionPlan:
        raise OrdifileError("CONVERSION_PLAN_INVALID", "plan must be a ConversionPlan.")
    _require_registry(registry)
    if progress is not None and not callable(progress):
        raise OrdifileError("OPTION_TYPE_INVALID", "progress must be callable or None.")
    if not plan.is_executable:
        raise OrdifileError(
            "CONVERSION_PLAN_BLOCKED",
            "The reviewed plan is blocked; refresh preflight after resolving its failures.",
        )
    bindings = plan_bindings(plan)
    active = create_registry() if registry is None else registry
    try:
        fresh = build_conversion_plan(
            bindings.inputs,
            bindings.output,
            active,
            recursive=bindings.recursive,
            extensions=bindings.extensions,
            sort=bindings.sort,
            include_signals=bindings.include_signals,
            experimental_derived_area=bindings.experimental_derived_area,
            adapter=bindings.adapter,
            sheet=bindings.sheet,
            include_hidden_sheets=bindings.include_hidden_sheets,
            peak_table_mapping=bindings.peak_table_mapping,
            peak_table_mapping_set=bindings.peak_table_mapping_set,
            on_error=bindings.on_error,
            overwrite=bindings.overwrite,
            sidecar_mode=bindings.sidecar_mode,
            recipe_schema_version=bindings.recipe_schema_version,
            recipe_public_fingerprint_sha256=bindings.recipe_public_fingerprint_sha256,
            recipe_semantic_sha256=bindings.recipe_semantic_sha256,
        )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except Exception as error:
        raise OrdifileError(
            "CONVERSION_PLAN_STALE",
            "Inputs or conversion configuration changed; refresh preflight before converting.",
        ) from error
    fresh_bindings = plan_bindings(fresh)
    if fresh.public_summary_sha256 != plan.public_summary_sha256 or fresh_bindings != bindings:
        raise OrdifileError(
            "CONVERSION_PLAN_STALE",
            "Inputs or conversion configuration changed; refresh preflight before converting.",
        )
    expected_sources = tuple(
        (
            os.path.abspath(os.fspath(source.path)),
            source.size,
            source.sha256,
            source.duplicate_of,
            source.issue_codes,
        )
        for source in fresh_bindings.sources
    )
    expected_routes = tuple(source.route_expectation for source in fresh_bindings.sources)
    try:
        return _convert_impl(
            fresh_bindings.inputs,
            fresh_bindings.output,
            recursive=fresh_bindings.recursive,
            extensions=fresh_bindings.extensions,
            sort=fresh_bindings.sort,
            include_signals=fresh_bindings.include_signals,
            experimental_derived_area=fresh_bindings.experimental_derived_area,
            adapter=fresh_bindings.adapter,
            sheet=fresh_bindings.sheet,
            include_hidden_sheets=fresh_bindings.include_hidden_sheets,
            peak_table_mapping=fresh_bindings.peak_table_mapping,
            peak_table_mapping_set=fresh_bindings.peak_table_mapping_set,
            on_error=fresh_bindings.on_error,
            overwrite=fresh_bindings.overwrite,
            sidecar_mode=fresh_bindings.sidecar_mode,
            progress=progress,
            registry=active,
            expected_sources=expected_sources,
            expected_routes=expected_routes,
            expected_registry_signature=fresh_bindings.registry_signature,
            expected_output_binding=fresh_bindings.output_snapshot,
            conversion_plan_schema_version=plan.schema_version,
            conversion_plan_public_summary_sha256=plan.public_summary_sha256,
            conversion_recipe_schema_version=bindings.recipe_schema_version,
            conversion_recipe_public_fingerprint_sha256=(bindings.recipe_public_fingerprint_sha256),
        )
    except ExportError as error:
        if error.code in {
            "OUTPUT_COLLISION",
            "OUTPUT_EXISTS",
            "SIDECAR_EXISTS",
        }:
            raise OrdifileError(
                "CONVERSION_PLAN_STALE",
                "The output target changed after preflight; no existing artifact was replaced.",
            ) from error
        raise


def convert(
    inputs: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
    output: str | os.PathLike[str] = "Ordifile_Result.xlsx",
    *,
    recursive: bool = False,
    extensions: Iterable[str] | None = None,
    sort: SortMode | str = SortMode.AUTO,
    include_signals: bool = False,
    experimental_derived_area: bool = False,
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
    conversion_plan: ConversionPlan | None = None,
) -> BatchResult:
    """Batch-convert inputs into one ordered Excel workbook."""
    if conversion_plan is not None:
        if type(conversion_plan) is not ConversionPlan:
            raise OrdifileError(
                "CONVERSION_PLAN_INVALID", "conversion_plan must be a ConversionPlan or None."
            )
        _require_registry(registry)
        active = create_registry() if registry is None else registry
        current = plan_conversion(
            inputs,
            output,
            recursive=recursive,
            extensions=extensions,
            sort=sort,
            include_signals=include_signals,
            experimental_derived_area=experimental_derived_area,
            adapter=adapter,
            sheet=sheet,
            include_hidden_sheets=include_hidden_sheets,
            peak_table_mapping=peak_table_mapping,
            peak_table_mapping_set=peak_table_mapping_set,
            on_error=on_error,
            overwrite=overwrite,
            sidecar_mode=sidecar_mode,
            registry=active,
        )
        if current.public_summary_sha256 != conversion_plan.public_summary_sha256 or plan_bindings(
            current
        ) != plan_bindings(conversion_plan):
            raise OrdifileError(
                "CONVERSION_PLAN_STALE",
                "The conversion request changed after preflight; refresh the plan.",
            )
        return convert_plan(conversion_plan, progress=progress, registry=active)
    return _convert_impl(
        inputs,
        output,
        recursive=recursive,
        extensions=extensions,
        sort=sort,
        include_signals=include_signals,
        experimental_derived_area=experimental_derived_area,
        adapter=adapter,
        sheet=sheet,
        include_hidden_sheets=include_hidden_sheets,
        peak_table_mapping=peak_table_mapping,
        peak_table_mapping_set=peak_table_mapping_set,
        on_error=on_error,
        overwrite=overwrite,
        sidecar_mode=sidecar_mode,
        progress=progress,
        registry=registry,
    )


def convert_recipe(
    inputs: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
    output: str | os.PathLike[str] = "Ordifile_Result.xlsx",
    *,
    recipe: ConversionRecipe,
    experimental_derived_area: bool = False,
    progress: Callable[[ProgressEvent], None] | None = None,
    registry: AdapterRegistry | None = None,
    conversion_plan: ConversionPlan | None = None,
) -> BatchResult:
    """Preflight, revalidate, and convert with one strict local Recipe."""
    _require_conversion_recipe(recipe, optional=False)
    if conversion_plan is not None and type(conversion_plan) is not ConversionPlan:
        raise OrdifileError(
            "CONVERSION_PLAN_INVALID", "conversion_plan must be a ConversionPlan or None."
        )
    _require_registry(registry)
    active = create_registry() if registry is None else registry
    current = plan_recipe(
        inputs,
        output,
        recipe=recipe,
        experimental_derived_area=experimental_derived_area,
        registry=active,
    )
    if conversion_plan is None:
        conversion_plan = current
    elif current.public_summary_sha256 != conversion_plan.public_summary_sha256 or plan_bindings(
        current
    ) != plan_bindings(conversion_plan):
        raise OrdifileError(
            "CONVERSION_PLAN_STALE",
            "The conversion request changed after preflight; refresh the plan.",
        )
    return convert_plan(conversion_plan, progress=progress, registry=active)
