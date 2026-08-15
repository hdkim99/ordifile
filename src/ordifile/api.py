# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Stable public API used by the CLI and future GUI."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ordifile.adapters.base import AdapterDescriptor, ParseOptions
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
    InspectionResult,
    ProgressEvent,
    Severity,
    SortMode,
)
from ordifile.core.pipeline import run_pipeline
from ordifile.exporters.excel import ExcelExporter


@dataclass(frozen=True, slots=True)
class FormatReport:
    """Installed adapter descriptors plus privacy-safe plugin load diagnostics."""

    descriptors: tuple[AdapterDescriptor, ...]
    load_errors: tuple[str, ...]


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise OrdifileError("OPTION_TYPE_INVALID", f"{name} must be an exact boolean value.")


def _require_optional_text(name: str, value: object) -> None:
    if value is not None and type(value) is not str:
        raise OrdifileError("OPTION_TYPE_INVALID", f"{name} must be text or None.")


def _require_registry(registry: object) -> None:
    if registry is not None and type(registry) is not AdapterRegistry:
        raise OrdifileError("OPTION_TYPE_INVALID", "registry must be an AdapterRegistry or None.")


def _inputs(
    values: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
) -> tuple[str | os.PathLike[str], ...]:
    if isinstance(values, (str, os.PathLike)):
        return (values,)
    return tuple(values)


def list_formats(*, registry: AdapterRegistry | None = None) -> tuple[AdapterDescriptor, ...]:
    """List verified built-in and installed external adapter capabilities."""
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


def inspect_file(
    path: str | os.PathLike[str],
    *,
    adapter: str | None = None,
    sheet: str | None = None,
    include_hidden_sheets: bool = False,
    registry: AdapterRegistry | None = None,
) -> InspectionResult:
    """Detect, parse, and validate one file without writing an output."""
    _require_bool("include_hidden_sheets", include_hidden_sheets)
    _require_optional_text("adapter", adapter)
    _require_optional_text("sheet", sheet)
    _require_registry(registry)
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
        parse_options=ParseOptions(sheet, include_hidden_sheets),
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
    return InspectionResult(file_result, file_result.probes)


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
    if type(on_error) is not str or on_error not in {"continue", "stop"}:
        raise OrdifileError("ON_ERROR_INVALID", "on_error must be 'continue' or 'stop'.")
    if type(sidecar_mode) is not str or sidecar_mode not in {"error", "csv"}:
        raise OrdifileError("SIDECAR_MODE_INVALID", "sidecar_mode must be 'error' or 'csv'.")
    if type(sort) not in {str, SortMode}:
        raise OrdifileError("SORT_MODE_INVALID", "sort must be a supported text sort mode.")
    try:
        SortMode(sort)
    except ValueError as error:
        choices = ", ".join(mode.value for mode in SortMode)
        raise OrdifileError("SORT_MODE_INVALID", f"sort must be one of: {choices}.") from error
    if progress is not None and not callable(progress):
        raise OrdifileError("OPTION_TYPE_INVALID", "progress must be callable or None.")
    if not isinstance(output, (str, os.PathLike)):
        raise OrdifileError("OPTION_TYPE_INVALID", "output must be a filesystem path.")
    if extensions is not None:
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
        normalized_extensions = tuple(stable_extensions)
    else:
        normalized_extensions = None
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
        sort=sort,
        forced_adapter=adapter,
        parse_options=ParseOptions(sheet, include_hidden_sheets),
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
            "source_file": failed.source.relative_path,
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
            sheet=sheet,
            include_hidden_sheets=include_hidden_sheets,
            on_error=on_error,
            overwrite=overwrite,
            sidecar_mode=sidecar_mode,
            output_name=output_path.name,
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
    return exported
