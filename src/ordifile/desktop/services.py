# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Framework-neutral desktop calls into the stable Ordifile public API."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping
from pathlib import Path

import ordifile
from ordifile import (
    ConversionPlan,
    ConversionPlanEntryStatus,
    ConversionPlanProblem,
    ConversionPlanReadiness,
    ConversionRecipe,
    PeakTableFormat,
    PeakTableImportSettings,
    PeakTableMapping,
    PeakTableMappingSet,
    PlanProgressEvent,
    summarize_conversion,
)
from ordifile import api as _ordifile_api
from ordifile.core.models import BatchOutcome, BatchResult, FileStatus, ProgressEvent, Severity
from ordifile.core.peak_mapping import peak_preview_display
from ordifile.desktop.models import (
    DesktopBatchReport,
    DesktopFileReport,
    DesktopInputStatus,
    DesktopPeakTablePreview,
    DesktopPeakTablePreviewReport,
    DesktopRequest,
    validate_request,
)

ProgressCallback = Callable[[ProgressEvent], None]
PlanProgressCallback = Callable[[PlanProgressEvent], None]

_STATUS_MAP: Mapping[FileStatus, DesktopInputStatus] = {
    FileStatus.SUCCESS: DesktopInputStatus.SUCCESS,
    FileStatus.WARNING: DesktopInputStatus.WARNING,
    FileStatus.FAILED: DesktopInputStatus.FAILED,
    FileStatus.DUPLICATE: DesktopInputStatus.DUPLICATE,
    FileStatus.SKIPPED: DesktopInputStatus.SKIPPED,
}

_PLAN_STATUS_MAP: Mapping[ConversionPlanEntryStatus, DesktopInputStatus] = {
    ConversionPlanEntryStatus.ROUTABLE: DesktopInputStatus.QUEUED,
    ConversionPlanEntryStatus.FAILED: DesktopInputStatus.FAILED,
    ConversionPlanEntryStatus.DUPLICATE: DesktopInputStatus.DUPLICATE,
    ConversionPlanEntryStatus.EXCLUDED_ARTIFACT: DesktopInputStatus.SKIPPED,
}

_PLAN_PROBLEM_MESSAGES: Mapping[ConversionPlanProblem, str] = {
    ConversionPlanProblem.NONE: "",
    ConversionPlanProblem.UNMAPPED_GENERIC_TABLE: (
        "A generic table needs an explicit peak-column mapping."
    ),
    ConversionPlanProblem.MAPPING_SCHEMA_DRIFT: (
        "A reusable mapping profile no longer matches this table exactly."
    ),
    ConversionPlanProblem.MAPPING_PROFILE_AMBIGUOUS: (
        "More than one reusable mapping profile matches this table."
    ),
    ConversionPlanProblem.WORKSHEET_AMBIGUOUS: (
        "More than one workbook sheet is eligible for mapping."
    ),
    ConversionPlanProblem.ADAPTER_AMBIGUOUS: "More than one exact adapter claims this input.",
    ConversionPlanProblem.UNSUPPORTED_FORMAT: "No supported input route was found.",
    ConversionPlanProblem.MALFORMED_INPUT: "The input structure is malformed.",
    ConversionPlanProblem.DUPLICATE_INPUT: "This input duplicates an earlier source.",
    ConversionPlanProblem.INPUT_DISCOVERY_FAILED: "The input could not be discovered safely.",
    ConversionPlanProblem.OUTPUT_CONFLICT: "The output target conflicts with the inputs.",
}


def _safe_text(value: object, *, limit: int = 500) -> str:
    """Render bounded single-line text without terminal or bidi controls."""
    text = str(value)
    rendered = "".join(
        character
        if character.isprintable()
        and unicodedata.category(character) not in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        else " "
        for character in text
    )
    return " ".join(rendered.split())[:limit]


def _structured_error(error: Exception) -> tuple[str, str]:
    """Keep public structured errors actionable without exposing tracebacks."""
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    if type(code) is str and type(message) is str:
        return _safe_text(code, limit=100) or "ORDIFILE_ERROR", _safe_text(message)
    return "UNEXPECTED_ERROR", "Unexpected internal error; no files were changed."


def presentation_error(error: Exception) -> tuple[str, str]:
    """Return structured, control-safe error text for local interface operations."""
    return _structured_error(error)


def safe_preview_text(value: str) -> str:
    """Return a bounded, visibly escaped local preview label."""
    return peak_preview_display(value)


def _interrupted_report() -> DesktopBatchReport:
    """Return a fixed report for non-ordinary termination inside a GUI worker."""
    return DesktopBatchReport(
        BatchOutcome.FAILED,
        error_code="OPERATION_INTERRUPTED",
        error_message="The operation was interrupted; review the selected output before retrying.",
    )


def safe_display_name(path: Path) -> str:
    """Return a bounded local basename without control or bidirectional characters."""
    return _safe_text(path.name or str(path)) or "Selected input"


def _descriptor_map() -> dict[str, tuple[str, str]]:
    """Return only fixture-tested formats exposed by the public registry API."""
    return {
        descriptor.adapter_id: (
            descriptor.display_name,
            descriptor.support_status.value.replace("_", " ").title(),
        )
        for descriptor in _ordifile_api.list_formats()
    }


def _file_reports(
    result: BatchResult,
    *,
    direct_input_count: int | None = None,
) -> tuple[DesktopFileReport, ...]:
    descriptors = _descriptor_map()
    reports: list[DesktopFileReport] = []
    for item in result.files:
        adapter_id = item.adapter_id or ""
        format_name, evidence = descriptors.get(adapter_id, ("Not detected", ""))
        if evidence and evidence.casefold() not in format_name.casefold():
            format_name = f"{format_name} ({evidence})"
        issue = next(
            (candidate for candidate in item.issues if candidate.severity is Severity.ERROR),
            next(iter(item.issues), None),
        )
        reports.append(
            DesktopFileReport(
                source=_safe_text(item.source.public_reference),
                format_name=_safe_text(format_name),
                adapter_id=_safe_text(adapter_id) or "—",
                status=_STATUS_MAP[item.status],
                message=(
                    ""
                    if issue is None
                    else f"[{_safe_text(issue.code)}] {_safe_text(issue.message)}"
                ),
                mapping_route=(
                    _safe_text(item.mapping_route, limit=100) if item.mapping_route else None
                ),
                mapping_profile_id=(
                    _safe_text(item.mapping_profile_id, limit=100)
                    if item.mapping_profile_id
                    else None
                ),
                mapping_diagnostics=item.mapping_diagnostics,
                review_input_index=(
                    item.source.input_order
                    if direct_input_count is not None
                    and 0 <= item.source.input_order < direct_input_count
                    else None
                ),
                source_sha256=item.source.sha256,
            )
        )
    return tuple(reports)


def _report(
    result: BatchResult,
    *,
    direct_input_count: int | None = None,
) -> DesktopBatchReport:
    return DesktopBatchReport(
        outcome=result.outcome,
        files=_file_reports(result, direct_input_count=direct_input_count),
        success_count=result.success_count,
        warning_count=result.warning_count,
        failure_count=result.failure_count,
        duplicate_count=result.duplicate_count,
        output_path=result.output_path,
        summary=summarize_conversion(result),
    )


def _plan_file_reports(
    plan: ConversionPlan,
    *,
    direct_input_count: int | None = None,
) -> tuple[DesktopFileReport, ...]:
    descriptors = _descriptor_map()
    reports: list[DesktopFileReport] = []
    for entry in plan.entries:
        adapter_id = entry.adapter_id or ""
        format_name, evidence = descriptors.get(adapter_id, ("Not detected", ""))
        if evidence and evidence.casefold() not in format_name.casefold():
            format_name = f"{format_name} ({evidence})"
        reports.append(
            DesktopFileReport(
                source=_safe_text(entry.source_id),
                format_name=_safe_text(format_name),
                adapter_id=_safe_text(adapter_id) or "—",
                status=_PLAN_STATUS_MAP[entry.status],
                message=_PLAN_PROBLEM_MESSAGES[entry.problem],
                mapping_route=entry.route.value,
                mapping_profile_id=(
                    _safe_text(entry.mapping_profile_id, limit=100)
                    if entry.mapping_profile_id
                    else None
                ),
                mapping_diagnostics=entry.mapping_diagnostics,
                review_input_index=(
                    entry.input_order
                    if direct_input_count is not None
                    and 0 <= entry.input_order < direct_input_count
                    else None
                ),
                source_sha256=entry.sha256,
                plan_status=entry.status,
                plan_route=entry.route,
                plan_problem=entry.problem,
            )
        )
    return tuple(reports)


def preflight_selection(
    request: DesktopRequest,
    *,
    progress: PlanProgressCallback | None = None,
) -> DesktopBatchReport:
    """Build a plan without constructing canonical rows or writing output."""
    direct_input_count = (
        len(request.inputs)
        if all(path.is_file() and not path.is_symlink() for path in request.inputs)
        else None
    )
    try:
        validate_request(request)
        if request.recipe is not None:
            plan = _ordifile_api.plan_recipe(
                request.inputs,
                request.output,
                recipe=request.recipe,
                progress=progress,
            )
        else:
            plan = _ordifile_api.plan_conversion(
                request.inputs,
                request.output,
                sort=request.sort,
                include_signals=True,
                on_error="continue",
                overwrite=False,
                sheet=request.sheet,
                peak_table_mapping=request.peak_table_mapping,
                peak_table_mapping_set=request.peak_table_mapping_set,
                progress=progress,
            )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        return _interrupted_report()
    except Exception as error:
        code, message = _structured_error(error)
        return DesktopBatchReport(BatchOutcome.FAILED, error_code=code, error_message=message)
    if direct_input_count is not None and len(plan.entries) != direct_input_count:
        direct_input_count = None
    outcome = {
        ConversionPlanReadiness.READY: BatchOutcome.SUCCESS,
        ConversionPlanReadiness.READY_WITH_KNOWN_FAILURES: BatchOutcome.PARTIAL_SUCCESS,
        ConversionPlanReadiness.BLOCKED: BatchOutcome.FAILED,
    }[plan.readiness]
    return DesktopBatchReport(
        outcome,
        files=_plan_file_reports(plan, direct_input_count=direct_input_count),
        success_count=plan.summary.routable,
        failure_count=plan.summary.failed,
        duplicate_count=plan.summary.duplicates,
        plan=plan,
    )


def convert_preflight_plan(
    plan: ConversionPlan,
    *,
    progress: ProgressCallback | None = None,
) -> DesktopBatchReport:
    """Execute the exact reviewed public plan after core-owned revalidation."""
    try:
        result = _ordifile_api.convert_plan(plan, progress=progress)
    except (KeyboardInterrupt, SystemExit, MemoryError):
        return _interrupted_report()
    except Exception as error:
        code, message = _structured_error(error)
        return DesktopBatchReport(BatchOutcome.FAILED, error_code=code, error_message=message)
    return _report(result)


def inspect_selection(
    inputs: tuple[Path, ...],
    *,
    sort: str,
    peak_table_mapping: PeakTableMapping | None = None,
    peak_table_mapping_set: PeakTableMappingSet | None = None,
    progress: ProgressCallback | None = None,
) -> DesktopBatchReport:
    """Discover and detect selected inputs without writing an artifact."""
    direct_input_count = (
        len(inputs) if all(path.is_file() and not path.is_symlink() for path in inputs) else None
    )
    try:
        result = _ordifile_api.inspect_inputs(
            inputs,
            sort=sort,
            peak_table_mapping=peak_table_mapping,
            peak_table_mapping_set=peak_table_mapping_set,
            progress=progress,
        )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        return _interrupted_report()
    except Exception as error:
        code, message = _structured_error(error)
        return DesktopBatchReport(BatchOutcome.FAILED, error_code=code, error_message=message)
    if direct_input_count is not None and len(result.files) != direct_input_count:
        direct_input_count = None
    return _report(result, direct_input_count=direct_input_count)


def convert_selection(
    request: DesktopRequest,
    *,
    progress: ProgressCallback | None = None,
) -> DesktopBatchReport:
    """Convert with the public API while preserving partial and all-failed outcomes."""
    direct_input_count = (
        len(request.inputs)
        if all(path.is_file() and not path.is_symlink() for path in request.inputs)
        else None
    )
    try:
        validate_request(request)
        if request.recipe is not None:
            result = _ordifile_api.convert_recipe(
                request.inputs,
                request.output,
                recipe=request.recipe,
                progress=progress,
            )
        else:
            result = _ordifile_api.convert(
                request.inputs,
                request.output,
                sort=request.sort,
                include_signals=True,
                on_error="continue",
                overwrite=False,
                sheet=request.sheet,
                peak_table_mapping=request.peak_table_mapping,
                peak_table_mapping_set=request.peak_table_mapping_set,
                progress=progress,
            )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        return _interrupted_report()
    except Exception as error:
        code, message = _structured_error(error)
        return DesktopBatchReport(BatchOutcome.FAILED, error_code=code, error_message=message)
    if direct_input_count is not None and len(result.files) != direct_input_count:
        direct_input_count = None
    return _report(result, direct_input_count=direct_input_count)


def preview_peak_table(
    path: Path,
    source_format: PeakTableFormat,
    *,
    sheet: str | None = None,
    import_settings: PeakTableImportSettings | None = None,
) -> DesktopPeakTablePreviewReport:
    """Read a bounded preview through the public API without parsing in the GUI."""
    try:
        available_worksheets: tuple[str, ...] = ()
        if source_format is PeakTableFormat.XLSX:
            available_worksheets = _ordifile_api.list_peak_table_worksheets(path)
            if sheet is None:
                if len(available_worksheets) != 1:
                    return DesktopPeakTablePreviewReport(
                        error_code="XLSX_SHEET_SELECTION_REQUIRED",
                        error_message="Choose one worksheet before loading the preview.",
                        available_worksheets=available_worksheets,
                    )
                sheet = available_worksheets[0]
        preview = _ordifile_api.preview_peak_table(
            path,
            source_format,
            sheet=sheet,
            import_settings=import_settings,
        )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        return DesktopPeakTablePreviewReport(
            error_code="OPERATION_INTERRUPTED",
            error_message="The preview operation was interrupted.",
        )
    except Exception as error:
        code, message = _structured_error(error)
        return DesktopPeakTablePreviewReport(error_code=code, error_message=message)
    return DesktopPeakTablePreviewReport(
        preview=DesktopPeakTablePreview(
            preview.source_format,
            tuple(preview.headers),
            tuple(tuple(str(cell) for cell in row) for row in preview.rows),
            preview.sheet,
            preview.source_sha256,
            preview.import_settings,
        ),
        available_worksheets=available_worksheets,
    )


def load_mapping(path: Path) -> PeakTableMapping:
    """Load a data-only mapping through the public package interface."""
    return ordifile.load_peak_table_mapping(path)


def save_mapping(mapping: PeakTableMapping, path: Path, *, overwrite: bool = False) -> None:
    """Save a data-only mapping through the public package interface."""
    ordifile.save_peak_table_mapping(mapping, path, overwrite=overwrite)


def load_mapping_set(path: Path) -> PeakTableMappingSet:
    """Load a data-only reusable mapping set through the public package interface."""
    return ordifile.load_peak_table_mapping_set(path)


def save_mapping_set(
    mapping_set: PeakTableMappingSet,
    path: Path,
    *,
    overwrite: bool = False,
) -> None:
    """Save a data-only reusable mapping set through the public package interface."""
    ordifile.save_peak_table_mapping_set(mapping_set, path, overwrite=overwrite)


def load_recipe(path: Path) -> ConversionRecipe:
    """Load a data-only conversion recipe through the public package interface."""
    return ordifile.load_conversion_recipe(path)


def save_recipe(recipe: ConversionRecipe, path: Path, *, overwrite: bool = False) -> None:
    """Save a data-only conversion recipe through the public package interface."""
    ordifile.save_conversion_recipe(recipe, path, overwrite=overwrite)


def details_text(report: DesktopBatchReport) -> str:
    """Build a readable, sanitized diagnostic without a Python traceback."""
    if report.is_fatal_error:
        return f"[{report.error_code}] {report.error_message}"
    details: list[str] = []
    if report.plan is not None and report.plan.output_issue_code is not None:
        details.append(
            f"[{_safe_text(report.plan.output_issue_code, limit=100)}] "
            "The output target blocks this plan."
        )
    details.extend(f"{item.source}: {item.message}" for item in report.files if item.message)
    if not details:
        return "No warnings or errors."
    return "\n".join(details)
