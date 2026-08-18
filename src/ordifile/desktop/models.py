# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Presentation state for the optional desktop interface."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

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


@dataclass(frozen=True, slots=True)
class DesktopFileReport:
    """One privacy-safe discovered-file result for the input table."""

    source: str
    format_name: str
    adapter_id: str
    status: DesktopInputStatus
    message: str = ""


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
