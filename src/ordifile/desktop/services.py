# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Framework-neutral desktop calls into the stable Ordifile public API."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping
from pathlib import Path

import ordifile
from ordifile import PeakTableFormat, PeakTableMapping
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

_STATUS_MAP: Mapping[FileStatus, DesktopInputStatus] = {
    FileStatus.SUCCESS: DesktopInputStatus.SUCCESS,
    FileStatus.WARNING: DesktopInputStatus.WARNING,
    FileStatus.FAILED: DesktopInputStatus.FAILED,
    FileStatus.DUPLICATE: DesktopInputStatus.DUPLICATE,
    FileStatus.SKIPPED: DesktopInputStatus.SKIPPED,
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


def _file_reports(result: BatchResult) -> tuple[DesktopFileReport, ...]:
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
            )
        )
    return tuple(reports)


def _report(result: BatchResult) -> DesktopBatchReport:
    return DesktopBatchReport(
        outcome=result.outcome,
        files=_file_reports(result),
        success_count=result.success_count,
        warning_count=result.warning_count,
        failure_count=result.failure_count,
        duplicate_count=result.duplicate_count,
        output_path=result.output_path,
    )


def inspect_selection(
    inputs: tuple[Path, ...],
    *,
    sort: str,
    peak_table_mapping: PeakTableMapping | None = None,
    progress: ProgressCallback | None = None,
) -> DesktopBatchReport:
    """Discover and detect selected inputs without writing an artifact."""
    try:
        result = _ordifile_api.inspect_inputs(
            inputs,
            sort=sort,
            peak_table_mapping=peak_table_mapping,
            progress=progress,
        )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        return _interrupted_report()
    except Exception as error:
        code, message = _structured_error(error)
        return DesktopBatchReport(BatchOutcome.FAILED, error_code=code, error_message=message)
    return _report(result)


def convert_selection(
    request: DesktopRequest,
    *,
    progress: ProgressCallback | None = None,
) -> DesktopBatchReport:
    """Convert with the public API while preserving partial and all-failed outcomes."""
    try:
        validate_request(request)
        result = _ordifile_api.convert(
            request.inputs,
            request.output,
            sort=request.sort,
            on_error="continue",
            overwrite=False,
            peak_table_mapping=request.peak_table_mapping,
            progress=progress,
        )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        return _interrupted_report()
    except Exception as error:
        code, message = _structured_error(error)
        return DesktopBatchReport(BatchOutcome.FAILED, error_code=code, error_message=message)
    return _report(result)


def preview_peak_table(
    path: Path,
    source_format: PeakTableFormat,
    *,
    sheet: str | None = None,
) -> DesktopPeakTablePreviewReport:
    """Read a bounded preview through the public API without parsing in the GUI."""
    try:
        preview = _ordifile_api.preview_peak_table(path, source_format, sheet=sheet)
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
        )
    )


def load_mapping(path: Path) -> PeakTableMapping:
    """Load a data-only mapping through the public package interface."""
    return ordifile.load_peak_table_mapping(path)


def save_mapping(mapping: PeakTableMapping, path: Path, *, overwrite: bool = False) -> None:
    """Save a data-only mapping through the public package interface."""
    ordifile.save_peak_table_mapping(mapping, path, overwrite=overwrite)


def details_text(report: DesktopBatchReport) -> str:
    """Build a readable, sanitized diagnostic without a Python traceback."""
    if report.is_fatal_error:
        return f"[{report.error_code}] {report.error_message}"
    details = [item.message for item in report.files if item.message]
    if not details:
        return "No warnings or errors."
    return "\n".join(f"{item.source}: {item.message}" for item in report.files if item.message)
