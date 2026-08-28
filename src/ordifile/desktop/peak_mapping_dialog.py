# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Explicit, user-confirmed generic peak-table mapping dialog."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ordifile import (
    ColumnSelector,
    PeakTableFormat,
    PeakTableImportSettings,
    PeakTableMapping,
    PeakTableTextEncoding,
)
from ordifile.desktop.models import DesktopPeakTablePreview, DesktopPeakTablePreviewReport
from ordifile.desktop.services import presentation_error, safe_display_name, safe_preview_text
from ordifile.desktop.workers import PeakTablePreviewWorker

_FORMAT_LABELS = {
    PeakTableFormat.CSV: "CSV (comma-separated)",
    PeakTableFormat.TSV: "TSV (tab-separated)",
    PeakTableFormat.SEMICOLON: "TXT (semicolon-separated)",
    PeakTableFormat.XLSX: "XLSX workbook",
}

_ENCODING_LABELS = {
    PeakTableTextEncoding.UTF8: "UTF-8 / UTF-8 with BOM",
    PeakTableTextEncoding.CP949: "Korean Windows (CP949)",
    PeakTableTextEncoding.WINDOWS_1252: "Western Windows (1252)",
    PeakTableTextEncoding.UTF16: "UTF-16 with BOM",
}

_COLUMN_FIELDS = (
    ("height_column", "Height"),
    ("compound_name_column", "Compound name"),
    ("peak_name_column", "Peak name"),
    ("peak_index_column", "Peak index"),
    ("detector_column", "Detector"),
    ("channel_column", "Channel"),
    ("sample_id_column", "Sample ID"),
    ("run_id_column", "Run ID"),
    ("acquisition_time_column", "Acquisition time"),
    ("start_time_column", "Start time"),
    ("end_time_column", "End time"),
    ("secondary_retention_time_column", "Secondary retention time"),
)


def formats_for_path(path: Path) -> tuple[PeakTableFormat, ...]:
    """Return only mapped containers supported for this filename extension."""
    return {
        ".csv": (PeakTableFormat.CSV,),
        ".tsv": (PeakTableFormat.TSV,),
        ".txt": (PeakTableFormat.TSV, PeakTableFormat.SEMICOLON),
        ".xlsx": (PeakTableFormat.XLSX,),
    }.get(path.suffix.casefold(), ())


class PeakMappingDialog(QDialog):
    """Map exact table columns without guessing scientific meaning."""

    def __init__(
        self,
        source: Path,
        *,
        mapping: PeakTableMapping | None = None,
        parent: QWidget | None = None,
        auto_preview: bool = True,
        review_mode: bool = False,
        sheet: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review Mapping" if review_mode else "Map Peak Columns")
        self.resize(900, 700)
        self.setModal(True)
        self._source = source
        self._sheet = sheet
        self._review_mode = review_mode
        self._initial_mapping = mapping
        self._mapping: PeakTableMapping | None = None
        self._preview: DesktopPeakTablePreview | None = None
        self._confirmation_snapshot: DesktopPeakTablePreview | None = None
        self._confirmation_accept_pending = False
        self._confirming = False
        self._preview_thread: QThread | None = None
        self._preview_worker: PeakTablePreviewWorker | None = None

        root = QVBoxLayout(self)
        explanation = QLabel(
            (
                "Only source columns whose label and position are unchanged are restored. "
                "Review unresolved roles explicitly; Ordifile does not infer replacements."
            )
            if review_mode
            else (
                "Select the retention-time and area columns explicitly. Ordifile does not "
                "infer vendor semantics or units from this table."
            )
        )
        explanation.setWordWrap(True)
        root.addWidget(explanation)
        source_label = QLabel(f"Preview source: {safe_display_name(source)}")
        source_label.setAccessibleName("Peak mapping preview source")
        root.addWidget(source_label)

        format_row = QHBoxLayout()
        format_label = QLabel("Source &format:")
        self.format_combo = QComboBox()
        self.format_combo.setAccessibleName("Generic table source format")
        for source_format in formats_for_path(source):
            self.format_combo.addItem(_FORMAT_LABELS[source_format], source_format.value)
        format_label.setBuddy(self.format_combo)
        self.reload_button = QPushButton("&Load Preview")
        self.reload_button.setAccessibleName("Load bounded table preview")
        format_row.addWidget(format_label)
        format_row.addWidget(self.format_combo, stretch=1)
        format_row.addWidget(self.reload_button)
        root.addLayout(format_row)

        self.table_options_button = QPushButton("&Table Options")
        self.table_options_button.setCheckable(True)
        self.table_options_button.setAccessibleName("Show explicit table import options")
        root.addWidget(self.table_options_button)
        self.table_options_container = QWidget()
        table_options_form = QFormLayout(self.table_options_container)
        self.encoding_combo = QComboBox()
        self.encoding_combo.setAccessibleName("Text encoding")
        for encoding, label in _ENCODING_LABELS.items():
            self.encoding_combo.addItem(label, encoding.value)
        self.header_row_spin = QSpinBox()
        self.header_row_spin.setAccessibleName("Header row")
        # 0 declares that the source carries no header record; column roles then bind to
        # one-based positional labels instead of header text.
        self.header_row_spin.setRange(0, 100)
        self.header_row_spin.setValue(1)
        self.header_row_spin.setSpecialValueText("No header record")
        self.worksheet_combo = QComboBox()
        self.worksheet_combo.setAccessibleName("Mapped XLSX worksheet")
        self.worksheet_combo.addItem("Choose a worksheet", None)
        table_options_form.addRow("Text &encoding:", self.encoding_combo)
        table_options_form.addRow("&Header row:", self.header_row_spin)
        table_options_form.addRow("&Worksheet:", self.worksheet_combo)
        table_options_help = QLabel(
            "Choose how to read the table structure. These settings do not assign RT, Area, "
            "units, or vendor identity."
        )
        table_options_help.setWordWrap(True)
        table_options_form.addRow(table_options_help)
        self.table_options_container.setVisible(False)
        root.addWidget(self.table_options_container)

        self.preview_status = QLabel("Preview has not been loaded.")
        self.preview_status.setAccessibleName("Peak table preview status")
        self.preview_status.setWordWrap(True)
        root.addWidget(self.preview_status)
        self.preview_table = QTableWidget(0, 0)
        self.preview_table.setAccessibleName("Peak table preview rows")
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        root.addWidget(self.preview_table, stretch=1)

        mapping_scroll = QScrollArea()
        mapping_scroll.setAccessibleName("Peak mapping fields")
        mapping_scroll.setWidgetResizable(True)
        mapping_scroll.setMaximumHeight(320)
        self.mapping_container = QWidget()
        mapping_layout = QVBoxLayout(self.mapping_container)

        required = QGroupBox("Required mapping")
        required_form = QFormLayout(required)
        self.retention_time_combo = self._column_combo("Retention time column")
        self.area_combo = self._column_combo("Area column")
        self.retention_time_unit_edit = QLineEdit()
        self.retention_time_unit_edit.setAccessibleName("Retention time unit")
        self.area_unit_edit = QLineEdit()
        self.area_unit_edit.setAccessibleName("Area unit")
        self.area_unit_edit.setPlaceholderText("Optional; leave blank if unresolved")
        required_form.addRow("&Retention time:", self.retention_time_combo)
        required_form.addRow("RT &unit:", self.retention_time_unit_edit)
        required_form.addRow("&Area:", self.area_combo)
        required_form.addRow("Area u&nit:", self.area_unit_edit)
        mapping_layout.addWidget(required)

        optional = QGroupBox("Optional mapped columns")
        optional_form = QFormLayout(optional)
        self.optional_combos: dict[str, QComboBox] = {}
        for field_name, label in _COLUMN_FIELDS:
            combo = self._column_combo(f"{label} column")
            self.optional_combos[field_name] = combo
            optional_form.addRow(f"{label}:", combo)
        self.height_unit_edit = QLineEdit()
        self.height_unit_edit.setAccessibleName("Height unit")
        self.secondary_retention_time_unit_edit = QLineEdit()
        self.secondary_retention_time_unit_edit.setAccessibleName("Secondary retention time unit")
        self.manufacturer_edit = QLineEdit()
        self.manufacturer_edit.setAccessibleName("User-supplied manufacturer")
        self.manufacturer_edit.setPlaceholderText("Optional; recorded as user-supplied")
        self.software_edit = QLineEdit()
        self.software_edit.setAccessibleName("User-supplied software")
        self.software_edit.setPlaceholderText("Optional; recorded as user-supplied")
        optional_form.addRow("Height unit:", self.height_unit_edit)
        optional_form.addRow("Secondary RT unit:", self.secondary_retention_time_unit_edit)
        optional_form.addRow("Manufacturer:", self.manufacturer_edit)
        optional_form.addRow("Software:", self.software_edit)
        mapping_layout.addWidget(optional)
        mapping_scroll.setWidget(self.mapping_container)
        root.addWidget(mapping_scroll)

        self.validation_label = QLabel("Load a preview, then select RT and Area columns.")
        self.validation_label.setAccessibleName("Peak mapping validation status")
        self.validation_label.setWordWrap(True)
        root.addWidget(self.validation_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        assert apply_button is not None
        assert cancel_button is not None
        self.apply_button = apply_button
        self.cancel_button = cancel_button
        self.apply_button.setText("Apply Mapping")
        self.apply_button.setAccessibleName("Apply explicit peak mapping")
        self.apply_button.setEnabled(False)
        root.addWidget(self.buttons)

        self.reload_button.clicked.connect(self.load_preview)
        self.format_combo.currentIndexChanged.connect(self._format_changed)
        self.table_options_button.toggled.connect(self.table_options_container.setVisible)
        self.encoding_combo.currentIndexChanged.connect(self._table_options_changed)
        self.header_row_spin.valueChanged.connect(self._table_options_changed)
        self.worksheet_combo.currentIndexChanged.connect(self._worksheet_changed)
        self.buttons.accepted.connect(self._accept_mapping)
        self.buttons.rejected.connect(self.reject)
        self.retention_time_combo.currentIndexChanged.connect(self._update_validity)
        self.area_combo.currentIndexChanged.connect(self._update_validity)
        self.retention_time_unit_edit.textChanged.connect(self._update_validity)
        self.height_unit_edit.textChanged.connect(self._update_validity)
        self.secondary_retention_time_unit_edit.textChanged.connect(self._update_validity)
        for combo in self.optional_combos.values():
            combo.currentIndexChanged.connect(self._update_validity)

        focus_widgets: tuple[QWidget, ...] = (
            self.format_combo,
            self.table_options_button,
            self.encoding_combo,
            self.header_row_spin,
            self.worksheet_combo,
            self.reload_button,
            self.preview_table,
            self.retention_time_combo,
            self.retention_time_unit_edit,
            self.area_combo,
            self.area_unit_edit,
            *self.optional_combos.values(),
            self.height_unit_edit,
            self.secondary_retention_time_unit_edit,
            self.manufacturer_edit,
            self.software_edit,
            self.apply_button,
            self.cancel_button,
        )
        for current, following in pairwise(focus_widgets):
            self.setTabOrder(current, following)

        if mapping is not None:
            index = self._find_data_index(self.format_combo, mapping.source_format.value)
            if index >= 0:
                self.format_combo.setCurrentIndex(index)
            self._restore_import_settings(mapping.import_settings)
        self._update_table_option_availability()
        if self.format_combo.count() == 0:
            self.preview_status.setText(
                "This file extension is not available for explicit peak-table mapping."
            )
            self.reload_button.setEnabled(False)
        elif auto_preview:
            self.load_preview()

    @staticmethod
    def _column_combo(accessible_name: str) -> QComboBox:
        combo = QComboBox()
        combo.setAccessibleName(accessible_name)
        combo.addItem("Not mapped", None)
        return combo

    @property
    def mapping(self) -> PeakTableMapping | None:
        """Return the immutable mapping after the dialog is accepted."""
        return self._mapping

    @property
    def preview_worksheet_title(self) -> str | None:
        """Return the locally previewed XLSX worksheet title after user review."""
        if self._preview is None or self._preview.source_format is not PeakTableFormat.XLSX:
            return None
        return self._preview.sheet

    @property
    def preview_source_sha256(self) -> str | None:
        """Return the local source snapshot identity produced by the preview worker."""
        return None if self._preview is None else self._preview.source_sha256

    def _source_format(self) -> PeakTableFormat | None:
        value = self.format_combo.currentData()
        try:
            return PeakTableFormat(value) if isinstance(value, str) else None
        except ValueError:
            return None

    def _import_settings(self) -> PeakTableImportSettings:
        raw_encoding = self.encoding_combo.currentData()
        encoding = (
            PeakTableTextEncoding(raw_encoding)
            if isinstance(raw_encoding, str)
            else PeakTableTextEncoding.UTF8
        )
        if self._source_format() is PeakTableFormat.XLSX:
            encoding = PeakTableTextEncoding.UTF8
        return PeakTableImportSettings(encoding, self.header_row_spin.value())

    def _restore_import_settings(self, settings: PeakTableImportSettings) -> None:
        encoding_index = self._find_data_index(
            self.encoding_combo,
            settings.text_encoding.value,
        )
        self.encoding_combo.blockSignals(True)
        if encoding_index >= 0:
            self.encoding_combo.setCurrentIndex(encoding_index)
        self.encoding_combo.blockSignals(False)
        self.header_row_spin.blockSignals(True)
        self.header_row_spin.setValue(settings.header_row)
        self.header_row_spin.blockSignals(False)

    def _selected_worksheet(self) -> str | None:
        value = self.worksheet_combo.currentData()
        return value if isinstance(value, str) else self._sheet

    def _populate_worksheets(self, worksheets: tuple[str, ...]) -> None:
        selected = self._selected_worksheet()
        self.worksheet_combo.blockSignals(True)
        self.worksheet_combo.clear()
        self.worksheet_combo.addItem("Choose a worksheet", None)
        for title in worksheets:
            self.worksheet_combo.addItem(safe_preview_text(title), title)
        index = self._find_data_index(self.worksheet_combo, selected)
        if index < 0 and len(worksheets) == 1:
            index = 1
        self.worksheet_combo.setCurrentIndex(max(0, index))
        self.worksheet_combo.blockSignals(False)
        current = self.worksheet_combo.currentData()
        self._sheet = current if isinstance(current, str) else None

    def _update_table_option_availability(self) -> None:
        is_xlsx = self._source_format() is PeakTableFormat.XLSX
        self.encoding_combo.setEnabled(not is_xlsx)
        self.worksheet_combo.setEnabled(is_xlsx)

    def _clear_preview_for_option_change(self, message: str) -> None:
        if self._preview_thread is not None:
            return
        self._preview = None
        self.preview_table.clear()
        self.preview_table.setRowCount(0)
        self.preview_table.setColumnCount(0)
        self._populate_column_combos(())
        self.preview_status.setText(message)
        self._update_validity()

    def _table_options_changed(self, _value: int) -> None:
        self._clear_preview_for_option_change(
            "Table options changed. Load the bounded preview again."
        )

    def _worksheet_changed(self, _index: int) -> None:
        value = self.worksheet_combo.currentData()
        self._sheet = value if isinstance(value, str) else None
        self._clear_preview_for_option_change(
            "Worksheet selection changed. Load the bounded preview again."
        )

    @staticmethod
    def _find_data_index(combo: QComboBox, expected: object) -> int:
        """Find Python item data without relying on QVariant equality conversion."""
        for index in range(combo.count()):
            if combo.itemData(index) == expected:
                return index
        return -1

    def _format_changed(self, _index: int) -> None:
        if self._source_format() is not PeakTableFormat.XLSX:
            self._sheet = None
        self._update_table_option_availability()
        self._preview = None
        self.preview_table.clear()
        self.preview_table.setRowCount(0)
        self.preview_table.setColumnCount(0)
        self._populate_column_combos(())
        self.preview_status.setText("Source format changed. Load the preview again.")
        self._update_validity()

    def load_preview(self) -> None:
        """Start a bounded public-API preview outside the UI thread."""
        source_format = self._source_format()
        if source_format is None or self._preview_thread is not None:
            return
        self._preview = None
        self.preview_table.clear()
        self.preview_table.setRowCount(0)
        self.preview_table.setColumnCount(0)
        self._populate_column_combos(())
        self._update_validity()
        self.reload_button.setEnabled(False)
        self.format_combo.setEnabled(False)
        self.table_options_button.setEnabled(False)
        self.table_options_container.setEnabled(False)
        self.preview_status.setText("Loading bounded preview…")
        self._start_preview_worker(source_format)

    def _start_preview_worker(self, source_format: PeakTableFormat) -> None:
        thread = QThread(self)
        worker = PeakTablePreviewWorker(
            self._source,
            source_format,
            self._selected_worksheet(),
            self._import_settings(),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_preview_complete)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._preview_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._preview_thread = thread
        self._preview_worker = worker
        thread.start()

    def _on_preview_complete(self, result: object) -> None:
        if self._confirming:
            self._on_confirmation_complete(result)
            return
        if not isinstance(result, DesktopPeakTablePreviewReport):
            return
        if result.available_worksheets:
            self._populate_worksheets(result.available_worksheets)
        if result.is_error or result.preview is None:
            self._preview = None
            self.preview_status.setText(
                f"Preview failed [{result.error_code}]: {result.error_message}"
            )
            self._populate_column_combos(())
            if result.error_code == "XLSX_SHEET_SELECTION_REQUIRED":
                self.table_options_button.setChecked(True)
                self.worksheet_combo.setFocus()
            self._update_validity()
        else:
            self.set_preview(result.preview)

    def _preview_finished(self) -> None:
        accept_pending = self._confirmation_accept_pending
        self._preview_thread = None
        self._preview_worker = None
        self._confirming = False
        self._confirmation_snapshot = None
        self._confirmation_accept_pending = False
        self.reload_button.setEnabled(self.format_combo.count() > 0)
        self.format_combo.setEnabled(True)
        self.table_options_button.setEnabled(True)
        self.table_options_container.setEnabled(True)
        self._update_table_option_availability()
        self.mapping_container.setEnabled(True)
        if accept_pending:
            self.accept()
        else:
            self._update_validity()
            if (
                self._source_format() is PeakTableFormat.XLSX
                and self.table_options_button.isChecked()
                and self._preview is None
                and self.worksheet_combo.count() > 1
            ):
                self.worksheet_combo.setFocus()

    def _on_confirmation_complete(self, result: object) -> None:
        snapshot = self._confirmation_snapshot
        if (
            snapshot is None
            or not isinstance(result, DesktopPeakTablePreviewReport)
            or result.is_error
            or result.preview is None
        ):
            self._mapping = None
            self.preview_status.setText(
                "Source recheck failed; reload the preview before applying this repair."
            )
            return
        current = result.preview
        if (
            current.source_format is not snapshot.source_format
            or current.headers != snapshot.headers
            or current.sheet != snapshot.sheet
            or current.import_settings != snapshot.import_settings
            or current.source_sha256 is None
            or current.source_sha256 != snapshot.source_sha256
            or self._source_format() is not snapshot.source_format
            or self._import_settings() != snapshot.import_settings
            or self._selected_worksheet() != snapshot.sheet
        ):
            self._mapping = None
            self.preview_status.setText(
                "Source or table options changed after preview; reload and review the mapping "
                "again."
            )
            return
        self._preview = current
        self._confirmation_accept_pending = True

    def set_preview(self, preview: DesktopPeakTablePreview) -> None:
        """Render a public bounded preview; exposed for deterministic interface tests."""
        if preview.source_format is not self._source_format():
            self.preview_status.setText("Preview format does not match the selected source format.")
            self._preview = None
            self._populate_column_combos(())
            self._update_validity()
            return
        if preview.import_settings != self._import_settings():
            self.preview_status.setText("Preview table options do not match the current selection.")
            self._preview = None
            self._populate_column_combos(())
            self._update_validity()
            return
        if preview.source_format is PeakTableFormat.XLSX and preview.sheet is not None:
            if self._find_data_index(self.worksheet_combo, preview.sheet) < 0:
                self._populate_worksheets((preview.sheet,))
            index = self._find_data_index(self.worksheet_combo, preview.sheet)
            self.worksheet_combo.blockSignals(True)
            self.worksheet_combo.setCurrentIndex(index)
            self.worksheet_combo.blockSignals(False)
            self._sheet = preview.sheet
        self._preview = preview
        self.preview_table.clear()
        self.preview_table.setColumnCount(len(preview.headers))
        self.preview_table.setHorizontalHeaderLabels(preview.headers)
        self.preview_table.setRowCount(len(preview.rows))
        for row_index, row in enumerate(preview.rows):
            for column_index, value in enumerate(row[: len(preview.headers)]):
                self.preview_table.setItem(row_index, column_index, QTableWidgetItem(value))
        if not self._populate_column_combos(preview.headers):
            self._preview = None
            self.preview_status.setText(
                "Preview headers cannot be mapped safely; use nonempty plain-text headers."
            )
            self._update_validity()
            return
        sheet = f" from sheet {safe_preview_text(preview.sheet)}" if preview.sheet else ""
        self.preview_status.setText(
            f"Preview loaded{sheet}: {len(preview.headers)} column(s), "
            f"{len(preview.rows)} preview row(s)."
        )
        if self._initial_mapping is not None:
            self._restore_mapping(self._initial_mapping)
            self._initial_mapping = None
        self._update_validity()

    def _populate_column_combos(self, headers: tuple[str, ...]) -> bool:
        valid = True
        try:
            selectors = tuple(
                ColumnSelector(header, index) for index, header in enumerate(headers, start=1)
            )
        except Exception:
            valid = False
            selectors = ()
        combos = (self.retention_time_combo, self.area_combo, *self.optional_combos.values())
        for combo in combos:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Not mapped", None)
            for selector in selectors:
                combo.addItem(
                    f"{selector.label} (column {selector.index})",
                    selector,
                )
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        return valid

    def _restore_mapping(self, mapping: PeakTableMapping) -> None:
        if self._preview is None or mapping.source_format is not self._preview.source_format:
            return
        field_combos = {
            "retention_time_column": self.retention_time_combo,
            "area_column": self.area_combo,
            **self.optional_combos,
        }
        for field_name, combo in field_combos.items():
            selector = getattr(mapping, field_name)
            if selector is None:
                continue
            expected = mapping.declared_headers
            observed = self._preview.headers
            if (
                selector.index > len(observed)
                or observed[selector.index - 1] != selector.label
                or expected[: selector.index].count(selector.label)
                != observed[: selector.index].count(selector.label)
            ):
                continue
            index = self._find_data_index(combo, selector)
            if index >= 0:
                combo.setCurrentIndex(index)
        self.retention_time_unit_edit.setText(mapping.retention_time_unit)
        self.area_unit_edit.setText(mapping.area_unit or "")
        self.height_unit_edit.setText(mapping.height_unit or "")
        self.secondary_retention_time_unit_edit.setText(mapping.secondary_retention_time_unit or "")
        self.manufacturer_edit.setText(mapping.manufacturer or "")
        self.software_edit.setText(mapping.software or "")
        self._restore_import_settings(mapping.import_settings)

    @staticmethod
    def _optional_text(edit: QLineEdit) -> str | None:
        value = edit.text().strip()
        return value or None

    def _selected_columns(self) -> tuple[ColumnSelector, ...]:
        values = (
            self.retention_time_combo.currentData(),
            self.area_combo.currentData(),
            *(combo.currentData() for combo in self.optional_combos.values()),
        )
        return tuple(value for value in values if isinstance(value, ColumnSelector))

    def _validation_message(self) -> str | None:
        if self._preview is None:
            return "Load a preview before applying a mapping."
        retention = self.retention_time_combo.currentData()
        area = self.area_combo.currentData()
        if not isinstance(retention, ColumnSelector) or not isinstance(area, ColumnSelector):
            return "Select both Retention Time and Area columns."
        if not self.retention_time_unit_edit.text().strip():
            return "Enter the retention-time unit explicitly."
        selected = self._selected_columns()
        if len({item.index for item in selected}) != len(selected):
            return "Each semantic role must use a different source column."
        height = self.optional_combos["height_column"].currentData()
        if not isinstance(height, ColumnSelector) and self.height_unit_edit.text().strip():
            return "Select a Height column before entering a height unit."
        secondary = self.optional_combos["secondary_retention_time_column"].currentData()
        if isinstance(secondary, ColumnSelector) != bool(
            self.secondary_retention_time_unit_edit.text().strip()
        ):
            return "Select Secondary RT and enter its unit together."
        return None

    def _update_validity(self, *_unused: object) -> None:
        message = self._validation_message()
        self.apply_button.setEnabled(message is None)
        self.validation_label.setText(
            "Ready. Mapped meanings are user-declared and are not vendor-verified."
            if message is None
            else message
        )

    def _accept_mapping(self) -> None:
        if self._validation_message() is not None or self._preview is None:
            self._update_validity()
            return
        retention = self.retention_time_combo.currentData()
        area = self.area_combo.currentData()
        source_format = self._source_format()
        assert isinstance(retention, ColumnSelector)
        assert isinstance(area, ColumnSelector)
        assert source_format is not None
        optional_values = {
            name: (value if isinstance((value := combo.currentData()), ColumnSelector) else None)
            for name, combo in self.optional_combos.items()
        }
        selected_positions = {item.index for item in self._selected_columns()}
        ignored = tuple(
            ColumnSelector(header, index)
            for index, header in enumerate(self._preview.headers, start=1)
            if index not in selected_positions
        )
        try:
            self._mapping = PeakTableMapping(
                retention_time_column=retention,
                area_column=area,
                retention_time_unit=self.retention_time_unit_edit.text().strip(),
                source_format=source_format,
                area_unit=self._optional_text(self.area_unit_edit),
                height_column=optional_values["height_column"],
                height_unit=self._optional_text(self.height_unit_edit),
                peak_name_column=optional_values["peak_name_column"],
                compound_name_column=optional_values["compound_name_column"],
                peak_index_column=optional_values["peak_index_column"],
                detector_column=optional_values["detector_column"],
                channel_column=optional_values["channel_column"],
                sample_id_column=optional_values["sample_id_column"],
                run_id_column=optional_values["run_id_column"],
                acquisition_time_column=optional_values["acquisition_time_column"],
                start_time_column=optional_values["start_time_column"],
                end_time_column=optional_values["end_time_column"],
                secondary_retention_time_column=optional_values["secondary_retention_time_column"],
                secondary_retention_time_unit=self._optional_text(
                    self.secondary_retention_time_unit_edit
                ),
                manufacturer=self._optional_text(self.manufacturer_edit),
                software=self._optional_text(self.software_edit),
                ignored_columns=ignored,
                import_settings=self._import_settings(),
            )
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception as error:
            self._mapping = None
            code, message = presentation_error(error)
            self.validation_label.setText(f"Mapping could not be applied [{code}]: {message}")
            return
        if not self._review_mode:
            self.accept()
            return
        if self._preview.source_sha256 is None:
            self._mapping = None
            self.preview_status.setText(
                "Source identity is unavailable; reload before applying this repair."
            )
            return
        self._confirmation_snapshot = self._preview
        self._confirming = True
        self.reload_button.setEnabled(False)
        self.format_combo.setEnabled(False)
        self.table_options_button.setEnabled(False)
        self.table_options_container.setEnabled(False)
        self.mapping_container.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.preview_status.setText("Rechecking the unchanged local source before repair…")
        self._start_preview_worker(source_format)

    def reject(self) -> None:
        """Keep the dialog alive until its bounded background preview has finished."""
        if self._preview_thread is not None:
            self.preview_status.setText("Please wait for the bounded preview to finish.")
            return
        super().reject()
