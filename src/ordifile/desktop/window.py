# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Accessible QtWidgets window for the offline Ordifile desktop workflow."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QThread, QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ordifile.core.models import BatchOutcome, ProgressEvent
from ordifile.desktop.models import DesktopBatchReport, DesktopRequest, InputSelectionModel
from ordifile.desktop.services import details_text, safe_display_name
from ordifile.desktop.workers import ConversionWorker, PreviewWorker

SORT_OPTIONS = (
    ("Automatic (recommended)", "auto"),
    ("Acquisition time", "acquired_at"),
    ("Sequence", "sequence"),
    ("Filename", "filename"),
    ("Input order", "input_order"),
)


def local_paths_from_urls(urls: Iterable[QUrl]) -> tuple[Path, ...]:
    """Keep only local file/folder drops; remote URLs are never opened."""
    paths: list[Path] = []
    for url in urls:
        if url.isLocalFile():
            local = url.toLocalFile()
            if local:
                paths.append(Path(local))
    return tuple(paths)


class MainWindow(QMainWindow):
    """Thin desktop layer over the stable public inspection and conversion APIs."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ordifile")
        self.resize(980, 680)
        self.setAcceptDrops(True)
        self._selection = InputSelectionModel()
        self._preview_thread: QThread | None = None
        self._preview_worker: PreviewWorker | None = None
        self._preview_inputs: tuple[Path, ...] | None = None
        self._preview_pending = False
        self._conversion_thread: QThread | None = None
        self._conversion_worker: ConversionWorker | None = None
        self._last_output: Path | None = None

        central = QWidget(self)
        root = QVBoxLayout(central)
        heading = QLabel("Convert scientific instrument data to one workbook")
        heading.setObjectName("headingLabel")
        heading.setAccessibleName("Ordifile desktop converter")
        root.addWidget(heading)
        privacy = QLabel("Offline processing only. Files remain on this computer.")
        privacy.setWordWrap(True)
        root.addWidget(privacy)

        input_buttons = QHBoxLayout()
        self.add_files_button = QPushButton("&Add Files…")
        self.add_files_button.setAccessibleName("Add files")
        self.add_folder_button = QPushButton("Add &Folder…")
        self.add_folder_button.setAccessibleName("Add folder")
        self.remove_button = QPushButton("&Remove Selected")
        self.remove_button.setAccessibleName("Remove selected inputs")
        self.clear_button = QPushButton("C&lear")
        self.clear_button.setAccessibleName("Clear all inputs")
        for button in (
            self.add_files_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
        ):
            input_buttons.addWidget(button)
        input_buttons.addStretch()
        root.addLayout(input_buttons)

        selected_label = QLabel("Selected &files and folders:")
        self.selection_list = QListWidget()
        self.selection_list.setObjectName("selectionList")
        self.selection_list.setAccessibleName("Selected files and folders")
        self.selection_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.selection_list.setMaximumHeight(90)
        selected_label.setBuddy(self.selection_list)
        root.addWidget(selected_label)
        root.addWidget(self.selection_list)

        detected_label = QLabel("&Detected files:")
        self.input_table = QTableWidget(0, 4)
        self.input_table.setObjectName("inputTable")
        self.input_table.setAccessibleName("Detected input files")
        self.input_table.setHorizontalHeaderLabels(("File", "Detected format", "Adapter", "Status"))
        self.input_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.input_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.input_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.input_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.input_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.input_table.setToolTip("Drop files or folders here, or use the Add buttons.")
        detected_label.setBuddy(self.input_table)
        root.addWidget(detected_label)
        root.addWidget(self.input_table, stretch=1)

        options = QGroupBox("Conversion options")
        option_grid = QGridLayout(options)
        sort_label = QLabel("&Sort:")
        self.sort_combo = QComboBox()
        self.sort_combo.setAccessibleName("Sort method")
        for label, value in SORT_OPTIONS:
            self.sort_combo.addItem(label, value)
        sort_label.setBuddy(self.sort_combo)
        option_grid.addWidget(sort_label, 0, 0)
        option_grid.addWidget(self.sort_combo, 0, 1, 1, 2)

        output_label = QLabel("&Output:")
        self.output_edit = QLineEdit(str(Path.cwd() / "Ordifile_Result.xlsx"))
        self.output_edit.setAccessibleName("Output workbook path")
        output_label.setBuddy(self.output_edit)
        self.output_button = QPushButton("&Browse…")
        self.output_button.setAccessibleName("Choose output workbook")
        option_grid.addWidget(output_label, 1, 0)
        option_grid.addWidget(self.output_edit, 1, 1)
        option_grid.addWidget(self.output_button, 1, 2)
        root.addWidget(options)

        actions = QHBoxLayout()
        self.convert_button = QPushButton("&Convert")
        self.convert_button.setAccessibleName("Convert selected inputs")
        self.convert_button.setDefault(True)
        self.convert_button.setEnabled(False)
        self.open_output_button = QPushButton("&Open Output")
        self.open_output_button.setAccessibleName("Open generated workbook")
        self.open_output_button.setEnabled(False)
        actions.addWidget(self.convert_button)
        actions.addWidget(self.open_output_button)
        actions.addStretch()
        root.addLayout(actions)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAccessibleName("Conversion progress")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)
        self.status_label = QLabel("Add files or folders to begin.")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAccessibleName("Conversion status")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.details = QPlainTextEdit()
        self.details.setObjectName("detailsText")
        self.details.setAccessibleName("Conversion details")
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(110)
        self.details.setPlainText("No conversion has run.")
        root.addWidget(self.details)
        self.setCentralWidget(central)

        self.add_files_button.clicked.connect(self._choose_files)
        self.add_folder_button.clicked.connect(self._choose_folder)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self._clear_inputs)
        self.output_button.clicked.connect(self._choose_output)
        self.convert_button.clicked.connect(self._start_conversion)
        self.open_output_button.clicked.connect(self._open_output)
        self.sort_combo.currentIndexChanged.connect(self._request_preview)

        self.setTabOrder(self.add_files_button, self.add_folder_button)
        self.setTabOrder(self.add_folder_button, self.selection_list)
        self.setTabOrder(self.selection_list, self.remove_button)
        self.setTabOrder(self.remove_button, self.clear_button)
        self.setTabOrder(self.clear_button, self.input_table)
        self.setTabOrder(self.input_table, self.sort_combo)
        self.setTabOrder(self.sort_combo, self.output_edit)
        self.setTabOrder(self.output_edit, self.output_button)
        self.setTabOrder(self.output_button, self.convert_button)
        self.setTabOrder(self.convert_button, self.open_output_button)

    @property
    def selected_paths(self) -> tuple[Path, ...]:
        """Expose immutable top-level selection for interface tests."""
        return self._selection.paths

    def add_paths(self, paths: Iterable[str | Path]) -> bool:
        """Add local files/folders and schedule authoritative public-API inspection."""
        if self._conversion_thread is not None:
            self.status_label.setText("Wait for the current conversion before changing inputs.")
            return False
        result = self._selection.add(paths)
        if not result.added:
            if result.duplicates:
                self.status_label.setText(f"Ignored {len(result.duplicates)} duplicate input(s).")
            return False
        self._render_queued_inputs()
        duplicate_note = (
            f"; ignored {len(result.duplicates)} duplicate(s)" if result.duplicates else ""
        )
        self.status_label.setText(f"Added {len(result.added)} input(s){duplicate_note}.")
        self._request_preview()
        return True

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt API
        """Accept local file/folder URLs only."""
        if (
            self._conversion_thread is None
            and event.mimeData().hasUrls()
            and local_paths_from_urls(event.mimeData().urls())
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt API
        """Add every local path from one drop without executing it."""
        paths = local_paths_from_urls(event.mimeData().urls())
        if paths and self.add_paths(paths):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _choose_files(self) -> None:
        paths, _filter = QFileDialog.getOpenFileNames(
            self,
            "Add scientific data files",
            str(Path.home()),
            "All files (*)",
        )
        if paths:
            self.add_paths(paths)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Add a folder", str(Path.home()), QFileDialog.Option.ShowDirsOnly
        )
        if path:
            self.add_paths((path,))

    def _choose_output(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Choose output workbook",
            self.output_edit.text(),
            "Excel workbook (*.xlsx)",
        )
        if path:
            output = Path(path)
            if output.suffix.casefold() != ".xlsx":
                output = output.with_suffix(".xlsx")
            self.output_edit.setText(str(output))

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.selection_list.selectedIndexes()})
        selected = self._selection.paths
        removable = [selected[row] for row in rows if row < len(selected)]
        if removable:
            self._selection.remove(removable)
            self._render_queued_inputs()
            self._request_preview()

    def _clear_inputs(self) -> None:
        self._selection.clear()
        self.selection_list.clear()
        self.input_table.setRowCount(0)
        self.status_label.setText("Input list cleared.")
        self.details.setPlainText("No inputs selected.")
        self.convert_button.setEnabled(False)

    def _sort_value(self) -> str:
        value = self.sort_combo.currentData()
        return value if isinstance(value, str) else "auto"

    def _render_queued_inputs(self) -> None:
        self.selection_list.clear()
        for path in self._selection.paths:
            self.selection_list.addItem(safe_display_name(path))
        self.input_table.setRowCount(len(self._selection.paths))
        for row, path in enumerate(self._selection.paths):
            values = (safe_display_name(path), "Pending core discovery", "—", "Queued")
            for column, value in enumerate(values):
                self.input_table.setItem(row, column, QTableWidgetItem(value))
        self.convert_button.setEnabled(bool(self._selection.paths))

    def _render_report(self, report: DesktopBatchReport) -> None:
        self.input_table.setRowCount(len(report.files))
        for row, item in enumerate(report.files):
            values = (item.source, item.format_name, item.adapter_id, item.status.value)
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if item.message:
                    cell.setToolTip(item.message)
                self.input_table.setItem(row, column, cell)

    def _request_preview(self, *_unused: object) -> None:
        if not self._selection.paths or self._conversion_thread is not None:
            return
        if self._preview_thread is not None:
            self._preview_pending = True
            return
        self._preview_pending = False
        self._preview_inputs = self._selection.paths
        self.convert_button.setEnabled(False)
        self.status_label.setText("Inspecting selected inputs…")
        thread = QThread(self)
        worker = PreviewWorker(self._selection.paths, self._sort_value())
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_preview_progress)
        worker.completed.connect(self._on_preview_complete)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._preview_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._preview_thread = thread
        self._preview_worker = worker
        thread.start()

    def _on_preview_progress(self, event: object) -> None:
        if isinstance(event, ProgressEvent):
            self._show_progress(event, inspecting=True)

    def _on_preview_complete(self, report: object) -> None:
        if not isinstance(report, DesktopBatchReport):
            return
        if self._preview_inputs != self._selection.paths:
            return
        if report.is_fatal_error:
            self.status_label.setText(
                f"Inspection failed [{report.error_code}]: {report.error_message}"
            )
        else:
            self._render_report(report)
            self.status_label.setText(
                f"Inspection complete: {len(report.files)} file(s), {report.failure_count} failed."
            )
        self.details.setPlainText(details_text(report))

    def _preview_finished(self) -> None:
        self._preview_thread = None
        self._preview_worker = None
        self._preview_inputs = None
        self.convert_button.setEnabled(bool(self._selection.paths))
        if self._preview_pending:
            self._request_preview()

    def _start_conversion(self) -> None:
        if self._conversion_thread is not None:
            return
        request = DesktopRequest(
            self._selection.paths,
            Path(self.output_edit.text()),
            self._sort_value(),
        )
        self._set_conversion_controls(False)
        self.open_output_button.setEnabled(False)
        self._last_output = None
        self.status_label.setText("Starting conversion…")
        self.details.setPlainText("Conversion is running.")
        thread = QThread(self)
        worker = ConversionWorker(request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_conversion_progress)
        worker.completed.connect(self._on_conversion_complete)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._conversion_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._conversion_thread = thread
        self._conversion_worker = worker
        thread.start()

    def _on_conversion_progress(self, event: object) -> None:
        if isinstance(event, ProgressEvent):
            self._show_progress(event, inspecting=False)

    def _show_progress(self, event: ProgressEvent, *, inspecting: bool) -> None:
        total = max(event.total, 1)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(min(event.completed, total))
        labels = {
            "discovery": "Discovering inputs",
            "processing": "Inspecting files" if inspecting else "Converting files",
            "export_start": "Writing workbook",
            "export_complete": "Workbook written",
        }
        label = labels.get(event.stage, "Processing")
        self.status_label.setText(f"{label}: {event.completed}/{event.total}")

    def _on_conversion_complete(self, report: object) -> None:
        if not isinstance(report, DesktopBatchReport):
            return
        if report.files:
            self._render_report(report)
        self.details.setPlainText(details_text(report))
        output_exists = report.output_path is not None and report.output_path.is_file()
        if output_exists:
            self._last_output = report.output_path
            self.open_output_button.setEnabled(True)
        if report.is_fatal_error:
            self.status_label.setText(
                f"Conversion failed [{report.error_code}]: {report.error_message}"
            )
        elif report.outcome is BatchOutcome.PARTIAL_SUCCESS:
            self.status_label.setText(
                f"Workbook created with partial success: {report.success_count} succeeded, "
                f"{report.failure_count} failed."
            )
        elif report.outcome is BatchOutcome.FAILED:
            suffix = " A diagnostic workbook was created." if output_exists else ""
            self.status_label.setText(
                f"No files converted successfully; {report.failure_count} failed.{suffix}"
            )
        else:
            self.status_label.setText(
                f"Conversion complete: {report.success_count} succeeded, "
                f"{report.warning_count} with warnings."
            )

    def _conversion_finished(self) -> None:
        self._conversion_thread = None
        self._conversion_worker = None
        self._set_conversion_controls(True)

    def _set_conversion_controls(self, enabled: bool) -> None:
        for widget in (
            self.add_files_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
            self.selection_list,
            self.input_table,
            self.sort_combo,
            self.output_edit,
            self.output_button,
            self.convert_button,
        ):
            widget.setEnabled(enabled)

    def _open_output(self) -> None:
        if self._last_output is None or not self._last_output.is_file():
            self.status_label.setText("The generated workbook is no longer available.")
            self.open_output_button.setEnabled(False)
            return
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output)))
        if not opened:
            self.status_label.setText("The workbook could not be opened by the desktop system.")

    def closeEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        """Do not destroy active workers; conversion has no unsafe cancellation path."""
        if self._conversion_thread is not None or self._preview_thread is not None:
            self.status_label.setText("Please wait for the current operation to finish.")
            if hasattr(event, "ignore"):
                event.ignore()
            return
        if hasattr(event, "accept"):
            event.accept()
