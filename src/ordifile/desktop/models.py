# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Presentation state for the optional desktop interface."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ordifile import (
    ConversionPlan,
    ConversionPlanEntryStatus,
    ConversionPlanProblem,
    ConversionPlanRoute,
    ConversionRecipe,
    ConversionResultSummary,
    PeakMappingDriftDiagnostic,
    PeakTableFormat,
    PeakTableImportSettings,
    PeakTableMapping,
    PeakTableMappingSet,
)
from ordifile.core.models import BatchOutcome


class DesktopInputStatus(StrEnum):
    """User-facing status of one discovered input."""

    QUEUED = "Queued"
    SUCCESS = "Success"
    WARNING = "Warning"
    FAILED = "Failed"
    DUPLICATE = "Duplicate"
    SKIPPED = "Skipped"


@dataclass(frozen=True, slots=True)
class AddInputsResult:
    """Paths accepted by the selection model and lexical duplicates ignored."""

    added: tuple[Path, ...]
    duplicates: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class DesktopRequest:
    """One immutable conversion request sent to a background worker."""

    inputs: tuple[Path, ...]
    output: Path
    sort: str = "auto"
    peak_table_mapping: PeakTableMapping | None = None
    peak_table_mapping_set: PeakTableMappingSet | None = None
    recipe: ConversionRecipe | None = None
    sheet: str | None = None


@dataclass(frozen=True, slots=True)
class DesktopPeakTablePreview:
    """Bounded table preview safe to pass from a worker to the UI thread."""

    source_format: PeakTableFormat
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    sheet: str | None = None
    source_sha256: str | None = None
    import_settings: PeakTableImportSettings = PeakTableImportSettings()


@dataclass(frozen=True, slots=True)
class DesktopPeakTablePreviewReport:
    """Successful bounded preview or one structured presentation-safe failure."""

    preview: DesktopPeakTablePreview | None = None
    error_code: str | None = None
    error_message: str | None = None
    available_worksheets: tuple[str, ...] = ()

    @property
    def is_error(self) -> bool:
        """Return whether the preview could not be produced."""
        return self.error_code is not None


@dataclass(frozen=True, slots=True)
class DesktopFileReport:
    """One privacy-safe discovered-file result for the input table."""

    source: str
    format_name: str
    adapter_id: str
    status: DesktopInputStatus
    message: str = ""
    mapping_route: str | None = None
    mapping_profile_id: str | None = None
    mapping_diagnostics: tuple[PeakMappingDriftDiagnostic, ...] = ()
    review_input_index: int | None = None
    source_sha256: str | None = None
    plan_status: ConversionPlanEntryStatus | None = None
    plan_route: ConversionPlanRoute | None = None
    plan_problem: ConversionPlanProblem | None = None


@dataclass(frozen=True, slots=True)
class DesktopBatchReport:
    """Preview or conversion result safe to pass between worker and UI threads."""

    outcome: BatchOutcome
    files: tuple[DesktopFileReport, ...] = ()
    success_count: int = 0
    warning_count: int = 0
    failure_count: int = 0
    duplicate_count: int = 0
    output_path: Path | None = None
    error_code: str | None = None
    error_message: str | None = None
    plan: ConversionPlan | None = None
    summary: ConversionResultSummary | None = None

    @property
    def is_fatal_error(self) -> bool:
        """Return whether the public API rejected the whole request."""
        return self.error_code is not None


class RequestValidationError(ValueError):
    """A bounded local request problem found before a worker is started."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _path_key(path: Path) -> str:
    """Return a platform-aware lexical key without resolving symbolic links."""
    return os.path.normcase(os.path.abspath(os.fspath(path)))


class InputSelectionModel:
    """Ordered top-level file/folder selection without reimplementing discovery."""

    def __init__(self) -> None:
        self._paths: dict[str, Path] = {}

    @property
    def paths(self) -> tuple[Path, ...]:
        """Return selected paths in user-supplied order."""
        return tuple(self._paths.values())

    def add(self, values: Iterable[str | os.PathLike[str]]) -> AddInputsResult:
        """Add paths once using lexical aliases; core discovery remains authoritative."""
        added: list[Path] = []
        duplicates: list[Path] = []
        for value in values:
            path = Path(value)
            key = _path_key(path)
            if key in self._paths:
                duplicates.append(path)
                continue
            self._paths[key] = path
            added.append(path)
        return AddInputsResult(tuple(added), tuple(duplicates))

    def remove(self, values: Iterable[str | os.PathLike[str]]) -> None:
        """Remove top-level paths while preserving all remaining order."""
        for value in values:
            self._paths.pop(_path_key(Path(value)), None)

    def clear(self) -> None:
        """Clear all selected top-level paths."""
        self._paths.clear()


def validate_request(request: DesktopRequest) -> None:
    """Reject obvious UI mistakes; the public API performs authoritative validation."""
    if not request.inputs:
        raise RequestValidationError("NO_INPUTS", "Add at least one file or folder.")
    if request.output.suffix.casefold() != ".xlsx":
        raise RequestValidationError(
            "OUTPUT_EXTENSION_INVALID", "Choose an output filename ending in .xlsx."
        )
    if not request.output.parent.exists() or not request.output.parent.is_dir():
        raise RequestValidationError(
            "OUTPUT_DIRECTORY_MISSING", "Choose an existing output folder."
        )
    if request.output.is_dir():
        raise RequestValidationError("OUTPUT_IS_DIRECTORY", "Choose an output workbook file.")
    supported_sorts = {"auto", "acquired_at", "sequence", "filename", "input_order"}
    if request.sort not in supported_sorts:
        raise RequestValidationError("SORT_MODE_INVALID", "Choose a supported sort method.")
    if request.peak_table_mapping is not None and request.peak_table_mapping_set is not None:
        raise RequestValidationError(
            "PEAK_MAPPING_MODE_CONFLICT",
            "Choose either one explicit mapping or a reusable mapping set, not both.",
        )
    if request.sheet is not None and (
        request.peak_table_mapping is None
        or request.peak_table_mapping.source_format is not PeakTableFormat.XLSX
        or request.peak_table_mapping_set is not None
    ):
        raise RequestValidationError(
            "PEAK_MAPPING_SHEET_INVALID",
            "A selected worksheet requires one explicit XLSX peak mapping.",
        )
    if request.recipe is not None and (
        request.sort != "auto"
        or request.peak_table_mapping is not None
        or request.peak_table_mapping_set is not None
        or request.sheet is not None
    ):
        raise RequestValidationError(
            "CONVERSION_RECIPE_OPTION_CONFLICT",
            "A conversion recipe cannot be combined with separate desktop behavior settings.",
        )
