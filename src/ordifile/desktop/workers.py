# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Qt background workers for read-only preview and workbook conversion."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ordifile import ConversionPlan, PeakTableFormat, PeakTableImportSettings
from ordifile.core.models import BatchOutcome, ProgressEvent
from ordifile.desktop.models import (
    DesktopBatchReport,
    DesktopPeakTablePreviewReport,
    DesktopRequest,
)
from ordifile.desktop.services import (
    convert_preflight_plan,
    preflight_selection,
    preview_peak_table,
)


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
        request: DesktopRequest,
    ) -> None:
        super().__init__()
        self._request = request

    def _emit_progress(self, event: object) -> None:
        self.progress.emit(event)

    @Slot()
    def run(self) -> None:
        """Inspect the immutable request and always release the worker thread."""
        try:
            self.completed.emit(preflight_selection(self._request, progress=self._emit_progress))
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
        import_settings: PeakTableImportSettings | None = None,
    ) -> None:
        super().__init__()
        self._path = path
        self._source_format = source_format
        self._sheet = sheet
        self._import_settings = import_settings

    @Slot()
    def run(self) -> None:
        """Call the public preview service and always release the worker thread."""
        try:
            self.completed.emit(
                preview_peak_table(
                    self._path,
                    self._source_format,
                    sheet=self._sheet,
                    import_settings=self._import_settings,
                )
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

    def __init__(self, plan: ConversionPlan) -> None:
        super().__init__()
        self._plan = plan

    def _emit_progress(self, event: ProgressEvent) -> None:
        self.progress.emit(event)

    @Slot()
    def run(self) -> None:
        """Convert the immutable request and always release the worker thread."""
        try:
            self.completed.emit(convert_preflight_plan(self._plan, progress=self._emit_progress))
        except BaseException:
            self.completed.emit(_unexpected_worker_failure())
        finally:
            self.finished.emit()
