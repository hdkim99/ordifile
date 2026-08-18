# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Qt background workers for read-only preview and workbook conversion."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ordifile.core.models import BatchOutcome, ProgressEvent
from ordifile.desktop.models import DesktopBatchReport, DesktopRequest
from ordifile.desktop.services import convert_selection, inspect_selection


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

    def __init__(self, inputs: tuple[Path, ...], sort: str) -> None:
        super().__init__()
        self._inputs = inputs
        self._sort = sort

    def _emit_progress(self, event: ProgressEvent) -> None:
        self.progress.emit(event)

    @Slot()
    def run(self) -> None:
        """Inspect the immutable request and always release the worker thread."""
        try:
            self.completed.emit(
                inspect_selection(self._inputs, sort=self._sort, progress=self._emit_progress)
            )
        except BaseException:
            self.completed.emit(_unexpected_worker_failure())
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
