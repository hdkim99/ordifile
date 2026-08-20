# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Qt background workers for read-only preview and workbook conversion."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ordifile import PeakTableFormat, PeakTableMapping, PeakTableMappingSet
from ordifile.core.models import BatchOutcome, ProgressEvent
from ordifile.desktop.models import (
    DesktopBatchReport,
    DesktopPeakTablePreviewReport,
    DesktopRequest,
)
from ordifile.desktop.services import convert_selection, inspect_selection, preview_peak_table


def _unexpected_worker_failure() -> DesktopBatchReport:
    """Return a fixed report without forwarding a background exception to Qt."""
    return DesktopBatchReport(
        BatchOutcome.FAILED,
        error_code="DESKTOP_WORKER_FAILED",
        error_message="The background operation stopped unexpectedly.",
    )


class PreviewWorker(QObject):
    """Run public batch inspection outside the UI thread."""

    progress = Signal(object)
    completed = Signal(object)
    finished = Signal()

    def __init__(
        self,
        inputs: tuple[Path, ...],
        sort: str,
        peak_table_mapping: PeakTableMapping | None = None,
        peak_table_mapping_set: PeakTableMappingSet | None = None,
    ) -> None:
        super().__init__()
        self._inputs = inputs
        self._sort = sort
        self._peak_table_mapping = peak_table_mapping
        self._peak_table_mapping_set = peak_table_mapping_set

    def _emit_progress(self, event: ProgressEvent) -> None:
        self.progress.emit(event)

    @Slot()
    def run(self) -> None:
        """Inspect the immutable request and always release the worker thread."""
        try:
            self.completed.emit(
                inspect_selection(
                    self._inputs,
                    sort=self._sort,
                    peak_table_mapping=self._peak_table_mapping,
                    peak_table_mapping_set=self._peak_table_mapping_set,
                    progress=self._emit_progress,
                )
            )
        except BaseException:
            self.completed.emit(_unexpected_worker_failure())
        finally:
            self.finished.emit()


class PeakTablePreviewWorker(QObject):
    """Read one bounded generic-table preview outside the UI thread."""

    completed = Signal(object)
    finished = Signal()

    def __init__(
        self,
        path: Path,
        source_format: PeakTableFormat,
        sheet: str | None = None,
    ) -> None:
        super().__init__()
        self._path = path
        self._source_format = source_format
        self._sheet = sheet

    @Slot()
    def run(self) -> None:
        """Call the public preview service and always release the worker thread."""
        try:
            self.completed.emit(
                preview_peak_table(self._path, self._source_format, sheet=self._sheet)
            )
        except BaseException:
            self.completed.emit(
                DesktopPeakTablePreviewReport(
                    error_code="DESKTOP_WORKER_FAILED",
                    error_message="The background preview stopped unexpectedly.",
                )
            )
        finally:
            self.finished.emit()


class ConversionWorker(QObject):
    """Run public conversion outside the UI thread."""

    progress = Signal(object)
    completed = Signal(object)
    finished = Signal()

    def __init__(self, request: DesktopRequest) -> None:
        super().__init__()
        self._request = request

    def _emit_progress(self, event: ProgressEvent) -> None:
        self.progress.emit(event)

    @Slot()
    def run(self) -> None:
        """Convert the immutable request and always release the worker thread."""
        try:
            self.completed.emit(convert_selection(self._request, progress=self._emit_progress))
        except BaseException:
            self.completed.emit(_unexpected_worker_failure())
        finally:
            self.finished.emit()
