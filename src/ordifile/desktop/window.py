# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Accessible QtWidgets window for the offline Ordifile desktop workflow."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QThread, QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ordifile import (
    ConversionPlan,
    ConversionPlanEntryStatus,
    ConversionPlanOutputDisposition,
    ConversionPlanProblem,
    ConversionPlanReadiness,
    ConversionPlanRoute,
    ConversionRecipe,
    PeakMappingDriftCategory,
    PeakMappingDriftDiagnostic,
    PeakTableFormat,
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
    PeakTablePreview,
    PlanProgressEvent,
    clone_peak_table_mapping_profile,
)
from ordifile.core.models import BatchOutcome, ProgressEvent, SortMode
from ordifile.desktop.models import (
    DesktopBatchReport,
    DesktopFileReport,
    DesktopRequest,
    InputSelectionModel,
)
from ordifile.desktop.peak_mapping_dialog import PeakMappingDialog, formats_for_path
from ordifile.desktop.recipe_dialog import RecipeManagerDialog
from ordifile.desktop.recipe_library import (
    RecipeLibrary,
    RecipeLibraryError,
    normalize_recipe_name,
)
from ordifile.desktop.services import (
    details_text,
    load_mapping,
    load_mapping_set,
    presentation_error,
    safe_display_name,
    safe_preview_text,
    save_mapping,
    save_mapping_set,
)
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

    def __init__(self, *, recipe_library: RecipeLibrary | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Ordifile")
        self.resize(980, 680)
        self.setAcceptDrops(True)
        self._selection = InputSelectionModel()
        self._preview_thread: QThread | None = None
        self._preview_worker: PreviewWorker | None = None
        self._preview_request: DesktopRequest | None = None
        self._preview_generation: int | None = None
        self._preflight_generation = 0
        self._preview_pending = False
        self._conversion_thread: QThread | None = None
        self._conversion_worker: ConversionWorker | None = None
        self._last_output: Path | None = None
        self._peak_table_mapping: PeakTableMapping | None = None
        self._peak_table_mapping_sheet: str | None = None
        self._peak_table_mapping_set: PeakTableMappingSet | None = None
        self._conversion_recipe: ConversionRecipe | None = None
        self._recipe_baseline_sha256: str | None = None
        self._active_recipe_id: str | None = None
        self._recipe_library = recipe_library
        self._recipe_library_available = True
        self._recipe_manager_dialog: RecipeManagerDialog | None = None
        self._displayed_files: tuple[DesktopFileReport, ...] = ()
        self._displayed_inputs: tuple[Path, ...] = ()
        self._displayed_mapping_set: PeakTableMappingSet | None = None
        self._displayed_plan: ConversionPlan | None = None
        self._displayed_request: DesktopRequest | None = None
        self._displayed_generation: int | None = None
        self._recipe_library_error: RecipeLibraryError | None = None
        if self._recipe_library is None:
            try:
                QCoreApplication.setApplicationName("Ordifile")
                self._recipe_library = RecipeLibrary.standard()
            except RecipeLibraryError as error:
                self._recipe_library_available = False
                self._recipe_library_error = error

        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(2)
        heading = QLabel("Convert scientific instrument data to one workbook")
        heading.setObjectName("headingLabel")
        heading.setAccessibleName("Ordifile desktop converter")
        root.addWidget(heading)
        privacy = QLabel("Offline processing only. Files remain on this computer.")
        privacy.setWordWrap(True)
        root.addWidget(privacy)

        self.step_inputs = QGroupBox("STEP 1 — Inputs")
        inputs_layout = QVBoxLayout(self.step_inputs)
        recipe_layout = QHBoxLayout()
        recipe_label = QLabel("Recipe (optional):")
        self.recipe_combo = QComboBox()
        self.recipe_combo.setAccessibleName("Saved conversion recipe")
        self.recipe_combo.addItem("None / No Recipe", None)
        recipe_label.setBuddy(self.recipe_combo)
        self.save_recipe_button = QPushButton("&Save Current…")
        self.save_recipe_button.setAccessibleName("Save current settings as a named Recipe")
        self.manage_recipes_button = QPushButton("&Manage…")
        self.manage_recipes_button.setAccessibleName("Manage saved conversion recipes")
        self.recipe_status_label = QLabel("No saved Recipe")
        self.recipe_status_label.setAccessibleName("Conversion recipe status")
        recipe_layout.addWidget(recipe_label)
        recipe_layout.addWidget(self.recipe_combo, stretch=1)
        recipe_layout.addWidget(self.save_recipe_button)
        recipe_layout.addWidget(self.manage_recipes_button)
        recipe_layout.addWidget(self.recipe_status_label)
        inputs_layout.addLayout(recipe_layout)

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
        inputs_layout.addLayout(input_buttons)

        selected_label = QLabel("Selected &files and folders:")
        self.selection_list = QListWidget()
        self.selection_list.setObjectName("selectionList")
        self.selection_list.setAccessibleName("Selected files and folders")
        self.selection_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.selection_list.setMaximumHeight(44)
        selected_label.setBuddy(self.selection_list)
        inputs_layout.addWidget(selected_label)
        inputs_layout.addWidget(self.selection_list)
        root.addWidget(self.step_inputs)

        self.mapping_toggle_button = QToolButton()
        self.mapping_toggle_button.setText("Mappings && reusable workflow")
        self.mapping_toggle_button.setAccessibleName("Show mappings and reusable workflow")
        self.mapping_toggle_button.setCheckable(True)
        self.mapping_toggle_button.setChecked(False)
        self.mapping_toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.mapping_toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        root.addWidget(self.mapping_toggle_button)
        self.mapping_advanced_group = QGroupBox("Mappings & reusable workflow")
        mapping_advanced_layout = QVBoxLayout(self.mapping_advanced_group)
        mapping_buttons = QHBoxLayout()
        self.map_peaks_button = QPushButton("&Map Peak Columns…")
        self.map_peaks_button.setAccessibleName("Map selected file peak columns")
        self.map_peaks_button.setEnabled(False)
        self.load_mapping_button = QPushButton("&Load Mapping…")
        self.load_mapping_button.setAccessibleName("Load peak mapping JSON")
        self.clear_mapping_button = QPushButton("Clear Mappin&g")
        self.clear_mapping_button.setAccessibleName("Clear explicit peak mapping")
        self.clear_mapping_button.setEnabled(False)
        self.save_mapping_button = QPushButton("&Save Mapping…")
        self.save_mapping_button.setAccessibleName("Save peak mapping JSON")
        self.save_mapping_button.setEnabled(False)
        for button in (
            self.map_peaks_button,
            self.load_mapping_button,
            self.save_mapping_button,
            self.clear_mapping_button,
        ):
            mapping_buttons.addWidget(button)
        mapping_buttons.addStretch()
        mapping_advanced_layout.addLayout(mapping_buttons)
        self.mapping_label = QLabel("Explicit peak mapping: none")
        self.mapping_label.setAccessibleName("Explicit peak mapping status")
        self.mapping_label.setWordWrap(True)
        mapping_advanced_layout.addWidget(self.mapping_label)

        mapping_set_group = QGroupBox("Reusable mapping set")
        mapping_set_layout = QGridLayout(mapping_set_group)
        self.use_mapping_set_checkbox = QCheckBox("Use mapping set for batch routing")
        self.use_mapping_set_checkbox.setAccessibleName("Use reusable peak mapping set")
        self.use_mapping_set_checkbox.setEnabled(False)
        mapping_set_layout.addWidget(self.use_mapping_set_checkbox, 0, 0, 1, 6)
        mapping_set_entry_label = QLabel("&Profiles:")
        self.mapping_set_combo = QComboBox()
        self.mapping_set_combo.setAccessibleName("Reusable peak mapping profiles")
        mapping_set_combo_size = self.mapping_set_combo.sizePolicy()
        mapping_set_combo_size.setHorizontalStretch(1)
        self.mapping_set_combo.setSizePolicy(mapping_set_combo_size)
        mapping_set_entry_label.setBuddy(self.mapping_set_combo)
        mapping_set_layout.addWidget(mapping_set_entry_label, 1, 0)
        mapping_set_layout.addWidget(self.mapping_set_combo, 1, 1, 1, 5)
        self.load_mapping_set_button = QPushButton("Load &Set…")
        self.load_mapping_set_button.setAccessibleName("Load reusable peak mapping set JSON")
        self.save_mapping_set_button = QPushButton("Save Se&t…")
        self.save_mapping_set_button.setAccessibleName("Save reusable peak mapping set JSON")
        self.add_mapping_profile_button = QPushButton("Add &Current")
        self.add_mapping_profile_button.setAccessibleName(
            "Add current mapping to reusable mapping set"
        )
        self.rename_mapping_profile_button = QPushButton("Re&name…")
        self.rename_mapping_profile_button.setAccessibleName("Rename selected mapping profile")
        self.remove_mapping_profile_button = QPushButton("Remo&ve")
        self.remove_mapping_profile_button.setAccessibleName("Remove selected mapping profile")
        for column, button in enumerate(
            (
                self.load_mapping_set_button,
                self.save_mapping_set_button,
                self.add_mapping_profile_button,
                self.rename_mapping_profile_button,
                self.remove_mapping_profile_button,
            ),
            start=1,
        ):
            mapping_set_layout.addWidget(button, 2, column)
        self.mapping_set_label = QLabel("Mapping set: none")
        self.mapping_set_label.setAccessibleName("Reusable mapping set status")
        self.mapping_set_label.setWordWrap(True)
        mapping_set_layout.addWidget(self.mapping_set_label, 3, 0, 1, 6)
        mapping_advanced_layout.addWidget(mapping_set_group)
        self.mapping_advanced_group.setVisible(False)
        root.addWidget(self.mapping_advanced_group)

        self.step_output = QGroupBox("STEP 2 — Output")
        output_layout = QGridLayout(self.step_output)
        output_label = QLabel("&Output workbook:")
        self.output_edit = QLineEdit(str(Path.cwd() / "Ordifile_Result.xlsx"))
        self.output_edit.setAccessibleName("Output workbook path")
        output_label.setBuddy(self.output_edit)
        self.output_button = QPushButton("&Browse…")
        self.output_button.setAccessibleName("Choose output workbook")
        output_layout.addWidget(output_label, 0, 0)
        output_layout.addWidget(self.output_edit, 0, 1)
        output_layout.addWidget(self.output_button, 0, 2)
        self.advanced_options_button = QToolButton()
        self.advanced_options_button.setText("Advanced conversion options")
        self.advanced_options_button.setAccessibleName("Show advanced conversion options")
        self.advanced_options_button.setCheckable(True)
        self.advanced_options_button.setChecked(False)
        self.advanced_options_button.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_options_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        output_layout.addWidget(self.advanced_options_button, 1, 0, 1, 3)
        self.advanced_options_container = QWidget()
        option_grid = QGridLayout(self.advanced_options_container)
        option_grid.setContentsMargins(0, 0, 0, 0)
        sort_label = QLabel("&Sort:")
        self.sort_combo = QComboBox()
        self.sort_combo.setAccessibleName("Sort method")
        for label, value in SORT_OPTIONS:
            self.sort_combo.addItem(label, value)
        sort_label.setBuddy(self.sort_combo)
        option_grid.addWidget(sort_label, 0, 0)
        option_grid.addWidget(self.sort_combo, 0, 1)
        self.advanced_options_container.setVisible(False)
        output_layout.addWidget(self.advanced_options_container, 2, 0, 1, 3)
        root.addWidget(self.step_output)

        self.step_preflight = QGroupBox("STEP 3 — Preflight")
        preflight_layout = QVBoxLayout(self.step_preflight)
        detected_header = QHBoxLayout()
        detected_label = QLabel("Review conversion routes before creating a workbook.")
        self.refresh_preflight_button = QPushButton("&Refresh Preflight")
        self.refresh_preflight_button.setAccessibleName("Refresh conversion preflight")
        self.refresh_preflight_button.setEnabled(False)
        detected_header.addWidget(detected_label)
        detected_header.addStretch()
        detected_header.addWidget(self.refresh_preflight_button)
        preflight_layout.addLayout(detected_header)
        self.preflight_summary_label = QLabel("Preflight has not run.")
        self.preflight_summary_label.setAccessibleName("Conversion preflight summary")
        self.preflight_summary_label.setWordWrap(True)
        preflight_layout.addWidget(self.preflight_summary_label)
        self.input_table = QTableWidget(0, 6)
        self.input_table.setObjectName("inputTable")
        self.input_table.setAccessibleName("Conversion preflight inputs")
        self.input_table.setHorizontalHeaderLabels(
            ("File", "Detected format", "Adapter", "Conversion route", "Action", "Status")
        )
        self.input_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.input_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.input_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.input_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.input_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.input_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.input_table.setToolTip("Drop files or folders here, or use the Add buttons.")
        self.input_table.setMinimumHeight(100)
        preflight_layout.addWidget(self.input_table, stretch=1)
        root.addWidget(self.step_preflight, stretch=1)

        self.drift_group = QGroupBox("Mapping schema drift review")
        drift_layout = QGridLayout(self.drift_group)
        drift_candidate_label = QLabel("Drift &candidate:")
        self.drift_candidate_combo = QComboBox()
        self.drift_candidate_combo.setAccessibleName("Mapping schema drift candidates")
        self.drift_candidate_combo.addItem("Choose a candidate…", None)
        self.drift_candidate_combo.setEnabled(False)
        drift_candidate_label.setBuddy(self.drift_candidate_combo)
        self.review_mapping_button = QPushButton("Re&view Mapping…")
        self.review_mapping_button.setAccessibleName("Review selected schema drift mapping")
        self.review_mapping_button.setEnabled(False)
        drift_layout.addWidget(drift_candidate_label, 0, 0)
        drift_layout.addWidget(self.drift_candidate_combo, 0, 1)
        drift_layout.addWidget(self.review_mapping_button, 0, 2)
        self.mapping_drift_label = QLabel(
            "Select one schema-drift row to review public-safe structural diagnostics."
        )
        self.mapping_drift_label.setAccessibleName("Mapping schema drift diagnostic details")
        self.mapping_drift_label.setWordWrap(True)
        drift_layout.addWidget(self.mapping_drift_label, 1, 0, 1, 3)
        self.drift_group.setVisible(False)
        root.addWidget(self.drift_group)

        self.step_convert = QGroupBox("STEP 4 — Convert")
        convert_layout = QVBoxLayout(self.step_convert)
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
        convert_layout.addLayout(actions)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAccessibleName("Conversion progress")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        convert_layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Add files or folders to begin.")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAccessibleName("Conversion status")
        self.status_label.setWordWrap(True)
        convert_layout.addWidget(self.status_label)
        self.details_toggle_button = QToolButton()
        self.details_toggle_button.setText("Show Details")
        self.details_toggle_button.setAccessibleName("Show conversion details")
        self.details_toggle_button.setCheckable(True)
        self.details_toggle_button.setChecked(False)
        self.details_toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.details_toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        convert_layout.addWidget(self.details_toggle_button)
        self.details = QPlainTextEdit()
        self.details.setObjectName("detailsText")
        self.details.setAccessibleName("Conversion details")
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(110)
        self.details.setPlainText("No conversion has run.")
        self.details.setVisible(False)
        convert_layout.addWidget(self.details)
        root.addWidget(self.step_convert)
        self.setCentralWidget(central)

        self.add_files_button.clicked.connect(self._choose_files)
        self.add_folder_button.clicked.connect(self._choose_folder)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self._clear_inputs)
        self.map_peaks_button.clicked.connect(self._map_peak_columns)
        self.load_mapping_button.clicked.connect(self._load_peak_mapping)
        self.save_mapping_button.clicked.connect(self._save_peak_mapping)
        self.clear_mapping_button.clicked.connect(self._clear_peak_mapping)
        self.use_mapping_set_checkbox.toggled.connect(self._mapping_set_toggled)
        self.mapping_set_combo.currentIndexChanged.connect(self._update_mapping_controls)
        self.load_mapping_set_button.clicked.connect(self._load_peak_mapping_set)
        self.save_mapping_set_button.clicked.connect(self._save_peak_mapping_set)
        self.add_mapping_profile_button.clicked.connect(self._add_current_mapping_profile)
        self.rename_mapping_profile_button.clicked.connect(self._rename_mapping_profile)
        self.remove_mapping_profile_button.clicked.connect(self._remove_mapping_profile)
        self.save_recipe_button.clicked.connect(self._save_current_recipe)
        self.manage_recipes_button.clicked.connect(self._manage_recipes)
        self.recipe_combo.activated.connect(self._select_saved_recipe)
        self.mapping_toggle_button.toggled.connect(
            lambda checked: self._toggle_section(
                self.mapping_toggle_button, self.mapping_advanced_group, checked
            )
        )
        self.advanced_options_button.toggled.connect(
            lambda checked: self._toggle_section(
                self.advanced_options_button, self.advanced_options_container, checked
            )
        )
        self.details_toggle_button.toggled.connect(
            lambda checked: self._toggle_section(
                self.details_toggle_button,
                self.details,
                checked,
                expanded_text="Hide Details",
                collapsed_text="Show Details",
            )
        )
        self.selection_list.itemSelectionChanged.connect(self._update_mapping_controls)
        self.input_table.itemSelectionChanged.connect(self._mapping_drift_row_changed)
        self.drift_candidate_combo.currentIndexChanged.connect(self._update_drift_candidate_detail)
        self.review_mapping_button.clicked.connect(self._review_mapping)
        self.output_button.clicked.connect(self._choose_output)
        self.refresh_preflight_button.clicked.connect(self._request_preview)
        self.convert_button.clicked.connect(self._start_conversion)
        self.open_output_button.clicked.connect(self._open_output)
        self.sort_combo.currentIndexChanged.connect(self._sort_changed)
        self.output_edit.textChanged.connect(self._output_changed)

        self.setTabOrder(self.add_files_button, self.add_folder_button)
        self.setTabOrder(self.add_folder_button, self.selection_list)
        self.setTabOrder(self.selection_list, self.recipe_combo)
        self.setTabOrder(self.recipe_combo, self.save_recipe_button)
        self.setTabOrder(self.save_recipe_button, self.manage_recipes_button)
        self.setTabOrder(self.manage_recipes_button, self.remove_button)
        self.setTabOrder(self.remove_button, self.clear_button)
        self.setTabOrder(self.clear_button, self.mapping_toggle_button)
        self.setTabOrder(self.mapping_toggle_button, self.output_edit)
        self.setTabOrder(self.output_edit, self.output_button)
        self.setTabOrder(self.output_button, self.advanced_options_button)
        self.setTabOrder(self.advanced_options_button, self.input_table)
        self.setTabOrder(self.input_table, self.refresh_preflight_button)
        self.setTabOrder(self.refresh_preflight_button, self.convert_button)
        self.setTabOrder(self.convert_button, self.open_output_button)
        self.setTabOrder(self.open_output_button, self.details_toggle_button)
        self._reload_recipe_selector()
        self._update_mapping_controls()

    @property
    def selected_paths(self) -> tuple[Path, ...]:
        """Expose immutable top-level selection for interface tests."""
        return self._selection.paths

    @property
    def peak_table_mapping(self) -> PeakTableMapping | None:
        """Expose the immutable user-confirmed mapping for interface tests."""
        return self._peak_table_mapping

    @property
    def peak_table_mapping_set(self) -> PeakTableMappingSet | None:
        """Expose the immutable reusable mapping set for interface tests."""
        return self._peak_table_mapping_set

    @property
    def conversion_recipe(self) -> ConversionRecipe | None:
        """Expose the immutable active recipe snapshot for interface tests."""
        return self._conversion_recipe

    @property
    def recipe_modified(self) -> bool:
        """Return whether local recipe settings differ from the last load or save."""
        return (
            self._active_recipe_id is not None
            and self._conversion_recipe is not None
            and self._recipe_baseline_sha256 is not None
            and self._conversion_recipe.semantic_sha256 != self._recipe_baseline_sha256
        )

    @property
    def mapping_set_active(self) -> bool:
        """Return whether batch routing currently uses the reusable mapping set."""
        return self.use_mapping_set_checkbox.isChecked()

    def add_paths(self, paths: Iterable[str | Path]) -> bool:
        """Add local files/folders and require an explicit Preflight refresh."""
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
        return True

    def _mapping_source(self) -> Path | None:
        rows = sorted({index.row() for index in self.selection_list.selectedIndexes()})
        if not rows and len(self._selection.paths) == 1:
            rows = [0]
        if len(rows) != 1 or rows[0] >= len(self._selection.paths):
            return None
        source = self._selection.paths[rows[0]]
        return (
            source
            if not source.is_symlink() and source.is_file() and formats_for_path(source)
            else None
        )

    def _update_mapping_controls(self) -> None:
        idle = self._conversion_thread is None
        self.refresh_preflight_button.setEnabled(
            idle and self._preview_thread is None and bool(self._selection.paths)
        )
        self.map_peaks_button.setEnabled(idle and self._mapping_source() is not None)
        self.load_mapping_button.setEnabled(idle)
        has_mapping = self._peak_table_mapping is not None
        self.save_mapping_button.setEnabled(idle and has_mapping)
        self.clear_mapping_button.setEnabled(idle and has_mapping)
        has_set = self._peak_table_mapping_set is not None
        has_profile = has_set and self.mapping_set_combo.currentIndex() >= 0
        self.use_mapping_set_checkbox.setEnabled(idle and has_set)
        self.mapping_set_combo.setEnabled(idle and has_set)
        self.load_mapping_set_button.setEnabled(idle)
        self.save_mapping_set_button.setEnabled(idle and has_set)
        self.add_mapping_profile_button.setEnabled(idle and has_mapping)
        self.rename_mapping_profile_button.setEnabled(idle and has_profile)
        self.remove_mapping_profile_button.setEnabled(idle and has_profile)
        recipe_controls = idle and self._recipe_library_available
        self.recipe_combo.setEnabled(recipe_controls)
        self.save_recipe_button.setEnabled(recipe_controls)
        self.manage_recipes_button.setEnabled(recipe_controls)
        self._update_convert_enabled()

    def _refresh_recipe_status(self) -> None:
        recipe = self._conversion_recipe
        if recipe is None:
            self.recipe_status_label.setText("No saved Recipe")
            return
        if self._active_recipe_id is None:
            self.recipe_status_label.setText("Unsaved settings")
            return
        self.recipe_status_label.setText(
            "Modified — not saved" if self.recipe_modified else "Saved"
        )

    @staticmethod
    def _toggle_section(
        button: QToolButton,
        content: QWidget,
        checked: bool,
        *,
        expanded_text: str | None = None,
        collapsed_text: str | None = None,
    ) -> None:
        content.setVisible(checked)
        button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        if checked and expanded_text is not None:
            button.setText(expanded_text)
        elif not checked and collapsed_text is not None:
            button.setText(collapsed_text)

    def _recipe_library_or_error(self) -> RecipeLibrary:
        library = self._recipe_library
        if library is None or not self._recipe_library_available:
            error = self._recipe_library_error
            if error is not None:
                raise error
            raise RecipeLibraryError(
                "RECIPE_LIBRARY_UNAVAILABLE",
                "The standard local Recipe library is unavailable.",
            )
        return library

    def _reload_recipe_selector(self, *, selected_id: str | None = None) -> None:
        self.recipe_combo.blockSignals(True)
        self.recipe_combo.clear()
        self.recipe_combo.addItem("None / No Recipe", None)
        try:
            snapshot = self._recipe_library_or_error().snapshot()
        except RecipeLibraryError as error:
            self._recipe_library_available = False
            self._recipe_library_error = error
            self.recipe_combo.blockSignals(False)
            self.recipe_status_label.setText(
                f"Saved setups unavailable [{error.code}]. Direct conversion remains available."
            )
            return
        selected_index = 0
        for index, entry in enumerate(snapshot.entries, start=1):
            self.recipe_combo.addItem(entry.display_name, entry.recipe_id)
            if entry.recipe_id == selected_id:
                selected_index = index
        self.recipe_combo.setCurrentIndex(selected_index)
        self.recipe_combo.blockSignals(False)
        if snapshot.invalid_count:
            self.status_label.setText(
                f"{snapshot.invalid_count} saved Recipe file(s) could not be loaded; "
                "other Recipes remain available."
            )

    def _select_saved_recipe(self, index: int) -> None:
        recipe_id = self.recipe_combo.itemData(index)
        if recipe_id != self._active_recipe_id and self.recipe_modified:
            answer = QMessageBox.warning(
                self,
                "Unsaved Recipe changes",
                "The selected Recipe has changes that were not saved.",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Save:
                if not self._save_current_recipe():
                    self._reload_recipe_selector(selected_id=self._active_recipe_id)
                    return
            elif answer != QMessageBox.StandardButton.Discard:
                self._reload_recipe_selector(selected_id=self._active_recipe_id)
                return
        if recipe_id is None:
            self._conversion_recipe = None
            self._recipe_baseline_sha256 = None
            self._active_recipe_id = None
            self._refresh_recipe_status()
            self._invalidate_preflight("Saved setup changed. Refresh preflight.")
            return
        if type(recipe_id) is not str:
            return
        try:
            entry = self._recipe_library_or_error().get(recipe_id)
        except RecipeLibraryError as error:
            self.status_label.setText(f"Saved Recipe load failed [{error.code}]: {error.message}")
            self._reload_recipe_selector(selected_id=self._active_recipe_id)
            return
        self.recipe_combo.blockSignals(True)
        self.recipe_combo.setCurrentIndex(self.recipe_combo.findData(recipe_id))
        self.recipe_combo.blockSignals(False)
        self._apply_conversion_recipe(entry.recipe, recipe_id=entry.recipe_id)
        self.status_label.setText(
            "Saved Recipe applied. Add inputs and output, then refresh preflight."
        )

    def _manage_recipes(self) -> None:
        try:
            library = self._recipe_library_or_error()
        except RecipeLibraryError as error:
            self.status_label.setText(f"Recipe library unavailable [{error.code}]: {error.message}")
            return
        dialog = RecipeManagerDialog(library, self)
        self._recipe_manager_dialog = dialog
        dialog.finished.connect(self._recipe_manager_finished)
        dialog.open()

    def _recipe_manager_finished(self, _result: int) -> None:
        self._recipe_manager_dialog = None
        try:
            library = self._recipe_library_or_error()
        except RecipeLibraryError:
            self._reload_recipe_selector()
            return
        active_id = self._active_recipe_id
        if active_id is not None:
            try:
                entry = library.get(active_id)
            except RecipeLibraryError:
                self._active_recipe_id = None
                self._recipe_baseline_sha256 = None
                self._reload_recipe_selector()
                self._refresh_recipe_status()
                self.status_label.setText(
                    "The selected saved Recipe was removed; current settings were kept."
                )
                return
            if self._conversion_recipe is not None:
                self._conversion_recipe = replace(
                    self._conversion_recipe, display_label=entry.display_name
                )
            self._reload_recipe_selector(selected_id=active_id)
            self._refresh_recipe_status()
        else:
            self._reload_recipe_selector()

    def _sync_active_recipe_from_controls(self) -> None:
        recipe = self._conversion_recipe
        if recipe is None:
            return
        mapping, mapping_set = self._active_peak_mappings()
        mapping_changed = (
            mapping != recipe.peak_table_mapping or mapping_set != recipe.peak_table_mapping_set
        )
        adapter = recipe.adapter
        sheet = recipe.sheet
        include_hidden_sheets = recipe.include_hidden_sheets
        if mapping_changed and (mapping is not None or mapping_set is not None):
            adapter = None
        if mapping_set is not None:
            sheet = None
            include_hidden_sheets = False
        elif mapping is not None:
            sheet = self._peak_table_mapping_sheet
            include_hidden_sheets = False
        elif mapping_changed:
            sheet = None
            include_hidden_sheets = False
        self._conversion_recipe = replace(
            recipe,
            sort=SortMode(self._sort_value()),
            adapter=adapter,
            sheet=sheet,
            include_hidden_sheets=include_hidden_sheets,
            peak_table_mapping=mapping,
            peak_table_mapping_set=mapping_set,
        )
        self._refresh_recipe_status()

    def _refresh_mapping_status(self) -> None:
        set_active = self.mapping_set_active
        mapping = self._peak_table_mapping
        if mapping is None:
            self.mapping_label.setText("Explicit peak mapping: none")
        else:
            inactive = " Current mapping is not active." if set_active else ""
            self.mapping_label.setText(
                "Explicit peak mapping: user-supplied "
                f"{mapping.source_format.value.upper()} mapping, "
                f"schema {mapping.schema_version}.{inactive}"
            )
        mapping_set = self._peak_table_mapping_set
        if mapping_set is None:
            self.mapping_set_label.setText("Mapping set: none")
        else:
            state = "active" if set_active else "inactive"
            self.mapping_set_label.setText(
                f"Mapping set: {len(mapping_set.profiles)} profile(s), {state}. "
                "Exact vendor adapters remain authoritative."
            )

    def _set_peak_mapping(
        self,
        mapping: PeakTableMapping | None,
        *,
        sheet: str | None = None,
        request_preview: bool = True,
        sync_recipe: bool = True,
    ) -> None:
        self._peak_table_mapping = mapping
        self._peak_table_mapping_sheet = (
            sheet if mapping is not None and mapping.source_format is PeakTableFormat.XLSX else None
        )
        if sync_recipe:
            self._sync_active_recipe_from_controls()
        self._refresh_mapping_status()
        self._update_mapping_controls()
        if request_preview:
            self._invalidate_preflight("Mapping changed. Refresh preflight.")

    def _set_peak_mapping_set(
        self,
        mapping_set: PeakTableMappingSet | None,
        *,
        activate: bool | None = None,
        selected_profile_id: str | None = None,
        request_preview: bool = True,
        sync_recipe: bool = True,
    ) -> None:
        self._peak_table_mapping_set = mapping_set
        self.mapping_set_combo.blockSignals(True)
        self.mapping_set_combo.clear()
        selected_index = 0
        if mapping_set is not None:
            for index, profile in enumerate(mapping_set.profiles):
                label = safe_preview_text(profile.display_label)
                profile_suffix = profile.profile_id.rsplit("-", maxsplit=1)[-1][-6:]
                self.mapping_set_combo.addItem(
                    f"{profile.mapping.source_format.value.upper()} — {label} [{profile_suffix}]",
                    profile.profile_id,
                )
                if profile.profile_id == selected_profile_id:
                    selected_index = index
            self.mapping_set_combo.setCurrentIndex(selected_index)
        self.mapping_set_combo.blockSignals(False)
        checked = mapping_set is not None and (
            self.mapping_set_active if activate is None else activate
        )
        self.use_mapping_set_checkbox.blockSignals(True)
        self.use_mapping_set_checkbox.setChecked(checked)
        self.use_mapping_set_checkbox.blockSignals(False)
        if sync_recipe:
            self._sync_active_recipe_from_controls()
        self._refresh_mapping_status()
        self._update_mapping_controls()
        if request_preview:
            self._invalidate_preflight("Mapping Set changed. Refresh preflight.")

    def _active_peak_mappings(
        self,
    ) -> tuple[PeakTableMapping | None, PeakTableMappingSet | None]:
        if self.mapping_set_active and self._peak_table_mapping_set is not None:
            return None, self._peak_table_mapping_set
        return self._peak_table_mapping, None

    def _current_preflight_request(self) -> DesktopRequest:
        if self._conversion_recipe is not None:
            return DesktopRequest(
                inputs=self._selection.paths,
                output=Path(self.output_edit.text()),
                recipe=self._conversion_recipe,
            )
        active_mapping, active_mapping_set = self._active_peak_mappings()
        return DesktopRequest(
            inputs=self._selection.paths,
            output=Path(self.output_edit.text()),
            sort=self._sort_value(),
            peak_table_mapping=active_mapping,
            peak_table_mapping_set=active_mapping_set,
            sheet=self._peak_table_mapping_sheet if active_mapping is not None else None,
        )

    def _apply_conversion_recipe(
        self, recipe: ConversionRecipe, *, recipe_id: str | None = None
    ) -> None:
        """Apply one immutable Recipe snapshot and require explicit preflight refresh."""
        self._conversion_recipe = recipe
        self._recipe_baseline_sha256 = recipe.semantic_sha256
        self._active_recipe_id = recipe_id
        self.sort_combo.blockSignals(True)
        self.sort_combo.setCurrentIndex(self.sort_combo.findData(recipe.sort.value))
        self.sort_combo.blockSignals(False)
        self._peak_table_mapping = recipe.peak_table_mapping
        self._peak_table_mapping_sheet = (
            recipe.sheet if recipe.peak_table_mapping is not None else None
        )
        self._set_peak_mapping_set(
            recipe.peak_table_mapping_set,
            activate=recipe.peak_table_mapping_set is not None,
            request_preview=False,
            sync_recipe=False,
        )
        self._refresh_mapping_status()
        self._refresh_recipe_status()
        self._update_mapping_controls()
        self._invalidate_preflight("Saved setup changed. Refresh preflight.")

    def _current_settings_recipe(self) -> ConversionRecipe:
        if self._conversion_recipe is not None:
            self._sync_active_recipe_from_controls()
            assert self._conversion_recipe is not None
            return self._conversion_recipe
        mapping, mapping_set = self._active_peak_mappings()
        return ConversionRecipe(
            sort=SortMode(self._sort_value()),
            include_signals=True,
            sheet=self._peak_table_mapping_sheet if mapping is not None else None,
            peak_table_mapping=mapping,
            peak_table_mapping_set=mapping_set,
        )

    def _save_current_recipe(self) -> bool:
        current_label = (
            self._conversion_recipe.display_label
            if self._conversion_recipe is not None
            and self._conversion_recipe.display_label is not None
            else ""
        )
        name, accepted = QInputDialog.getText(
            self,
            "Save Current Settings as Recipe",
            "Recipe name:",
            text=current_label,
        )
        if not accepted:
            self.status_label.setText("Current settings were not saved.")
            return False
        try:
            recipe = self._current_settings_recipe()
            library = self._recipe_library_or_error()
            normalized_name = normalize_recipe_name(name)
        except Exception as error:
            if isinstance(error, RecipeLibraryError):
                self.status_label.setText(f"Recipe save failed [{error.code}]: {error.message}")
            else:
                code, message = presentation_error(error)
                self.status_label.setText(f"Recipe creation failed [{code}]: {message}")
            return False
        try:
            conflict = next(
                (
                    entry
                    for entry in library.snapshot().entries
                    if entry.display_name.casefold() == normalized_name.casefold()
                ),
                None,
            )
            if conflict is not None:
                prompt = (
                    "Update this saved Recipe with the current settings?"
                    if conflict.recipe_id == self._active_recipe_id
                    else "Another saved Recipe uses this name. Replace its settings explicitly?"
                )
                answer = QMessageBox.question(
                    self,
                    "Replace saved Recipe?",
                    prompt,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self.status_label.setText(
                        "Current settings were not saved; choose a new name to keep both Recipes."
                    )
                    return False
                stored = library.update(
                    conflict.recipe_id,
                    recipe,
                    expected_revision_sha256=conflict.revision_sha256,
                )
            else:
                stored = library.create(recipe, normalized_name)
        except RecipeLibraryError as error:
            self.status_label.setText(f"Recipe save failed [{error.code}]: {error.message}")
            return False
        self._conversion_recipe = stored.recipe
        self._recipe_baseline_sha256 = stored.recipe.semantic_sha256
        self._active_recipe_id = stored.recipe_id
        self._reload_recipe_selector(selected_id=stored.recipe_id)
        self._refresh_recipe_status()
        self.status_label.setText("Current conversion settings saved as a named local Recipe.")
        return True

    def _sort_changed(self, *_unused: object) -> None:
        self._sync_active_recipe_from_controls()
        self._invalidate_preflight("Conversion settings changed. Refresh preflight.")

    def _output_changed(self, *_unused: object) -> None:
        self._invalidate_preflight("Output changed. Refresh preflight.")

    def _invalidate_preflight(self, message: str) -> None:
        self._preflight_generation += 1
        self._displayed_plan = None
        self._displayed_request = None
        self._displayed_generation = None
        self._invalidate_mapping_drift_review()
        self.preflight_summary_label.setText(message)
        self._update_convert_enabled()

    def _current_plan(self) -> ConversionPlan | None:
        if (
            self._displayed_plan is None
            or self._displayed_request != self._current_preflight_request()
            or self._displayed_generation != self._preflight_generation
        ):
            return None
        return self._displayed_plan

    def _update_convert_enabled(self) -> None:
        plan = self._current_plan()
        enabled = (
            self._preview_thread is None
            and self._conversion_thread is None
            and plan is not None
            and plan.is_executable
            and plan.summary.routable > 0
        )
        self.convert_button.setEnabled(enabled)
        if plan is not None and plan.readiness is ConversionPlanReadiness.READY_WITH_KNOWN_FAILURES:
            self.convert_button.setAccessibleName(
                f"Convert {plan.summary.routable} routable inputs with "
                f"{plan.summary.failed} known failures"
            )
        else:
            self.convert_button.setAccessibleName("Convert selected inputs")

    def _selected_mapping_profile(self) -> PeakTableMappingProfile | None:
        mapping_set = self._peak_table_mapping_set
        profile_id = self.mapping_set_combo.currentData()
        if mapping_set is None or not isinstance(profile_id, str):
            return None
        return next(
            (profile for profile in mapping_set.profiles if profile.profile_id == profile_id),
            None,
        )

    def _clear_mapping_drift_ui(self, message: str) -> None:
        self.drift_candidate_combo.blockSignals(True)
        self.drift_candidate_combo.clear()
        self.drift_candidate_combo.addItem("Choose a candidate…", None)
        self.drift_candidate_combo.setCurrentIndex(0)
        self.drift_candidate_combo.blockSignals(False)
        self.drift_candidate_combo.setEnabled(False)
        self.review_mapping_button.setEnabled(False)
        self.mapping_drift_label.setText(message)

    def _invalidate_mapping_drift_review(self) -> None:
        self._displayed_files = ()
        self._displayed_inputs = ()
        self._displayed_mapping_set = None
        self.drift_group.setVisible(False)
        self._clear_mapping_drift_ui(
            "Inspection is required before a schema-drift mapping can be reviewed."
        )

    def _selected_displayed_file(self) -> DesktopFileReport | None:
        rows = sorted({index.row() for index in self.input_table.selectedIndexes()})
        if len(rows) != 1 or rows[0] >= len(self._displayed_files):
            return None
        return self._displayed_files[rows[0]]

    def _mapping_drift_snapshot_is_current(self) -> bool:
        return (
            self._preview_thread is None
            and self._conversion_thread is None
            and self._current_plan() is not None
            and self.mapping_set_active
            and self._displayed_inputs == self._selection.paths
            and self._displayed_mapping_set is not None
            and self._displayed_mapping_set == self._peak_table_mapping_set
        )

    def _profile_for_diagnostic(
        self,
        diagnostic: PeakMappingDriftDiagnostic,
    ) -> PeakTableMappingProfile | None:
        mapping_set = self._peak_table_mapping_set
        if mapping_set is None:
            return None
        return next(
            (
                profile
                for profile in mapping_set.profiles
                if profile.profile_id == diagnostic.profile_id
                and profile.structural_fingerprint_sha256
                == diagnostic.profile_structural_fingerprint
            ),
            None,
        )

    def _mapping_drift_row_changed(self) -> None:
        self._clear_mapping_drift_ui(
            "Select one schema-drift row to review public-safe structural diagnostics."
        )
        if not self._mapping_drift_snapshot_is_current():
            return
        item = self._selected_displayed_file()
        if (
            item is None
            or (
                item.plan_problem is not ConversionPlanProblem.MAPPING_SCHEMA_DRIFT
                and item.mapping_route != "SCHEMA_DRIFT_CANDIDATE"
            )
            or not item.mapping_diagnostics
        ):
            return
        available = tuple(
            diagnostic
            for diagnostic in item.mapping_diagnostics
            if self._profile_for_diagnostic(diagnostic) is not None
        )
        if not available:
            self.mapping_drift_label.setText(
                "The reported candidates are no longer present in the active mapping set."
            )
            return
        self.drift_candidate_combo.blockSignals(True)
        for diagnostic in available:
            profile = self._profile_for_diagnostic(diagnostic)
            assert profile is not None
            label = safe_preview_text(profile.display_label)
            suffix = profile.profile_id.rsplit("-", maxsplit=1)[-1][-6:]
            self.drift_candidate_combo.addItem(
                f"{label} [{suffix}] — {diagnostic.total_difference_count} difference(s)",
                diagnostic.profile_id,
            )
        self.drift_candidate_combo.setCurrentIndex(0)
        self.drift_candidate_combo.blockSignals(False)
        self.drift_candidate_combo.setEnabled(True)
        self.mapping_drift_label.setText(
            f"{len(available)} bounded candidate(s) reported. Choose one explicitly; "
            "no mapping has been applied."
        )

    def _selected_drift_diagnostic(self) -> PeakMappingDriftDiagnostic | None:
        item = self._selected_displayed_file()
        profile_id = self.drift_candidate_combo.currentData()
        if item is None or not isinstance(profile_id, str):
            return None
        return next(
            (
                diagnostic
                for diagnostic in item.mapping_diagnostics
                if diagnostic.profile_id == profile_id
            ),
            None,
        )

    @staticmethod
    def _role_summary(roles: tuple[str, ...]) -> str:
        return ", ".join(role.replace("_", " ") for role in roles) or "none"

    def _update_drift_candidate_detail(self, *_unused: object) -> None:
        diagnostic = self._selected_drift_diagnostic()
        item = self._selected_displayed_file()
        review_source = (
            self._review_source(item, diagnostic)
            if item is not None and diagnostic is not None
            else None
        )
        enabled = (
            self._mapping_drift_snapshot_is_current()
            and diagnostic is not None
            and review_source is not None
        )
        self.review_mapping_button.setEnabled(enabled)
        if diagnostic is None:
            if self.drift_candidate_combo.count() > 1:
                self.mapping_drift_label.setText(
                    "Choose one candidate explicitly; no mapping has been applied."
                )
            return
        categories = ", ".join(
            category.value.replace("_", " ").title() for category in diagnostic.categories
        )
        direct_file_note = (
            " Add this file directly to the input list to open the mapping reviewer."
            if review_source is None
            else ""
        )
        self.mapping_drift_label.setText(
            f"{categories}. Expected {diagnostic.expected_column_count} column(s), observed "
            f"{diagnostic.observed_column_count}; exact positions "
            f"{diagnostic.exact_position_matches}, changed {diagnostic.changed_column_count}, "
            f"added {diagnostic.added_column_count}, removed {diagnostic.removed_column_count}, "
            f"moved {diagnostic.moved_column_count}. Unresolved required roles: "
            f"{self._role_summary(diagnostic.unresolved_required_roles)}. Unresolved optional "
            f"roles: {self._role_summary(diagnostic.unresolved_optional_roles)}."
            f"{direct_file_note}"
        )

    def _review_source(
        self,
        item: DesktopFileReport,
        diagnostic: PeakMappingDriftDiagnostic,
    ) -> Path | None:
        index = item.review_input_index
        if index is None or index >= len(self._selection.paths):
            return None
        source = self._selection.paths[index]
        if source.is_symlink() or not source.is_file():
            return None
        if diagnostic.source_format not in formats_for_path(source):
            return None
        return source

    def _review_mapping(self) -> None:
        if not self._mapping_drift_snapshot_is_current():
            self.status_label.setText("Run inspection again before reviewing this mapping.")
            return
        item = self._selected_displayed_file()
        diagnostic = self._selected_drift_diagnostic()
        if item is None or diagnostic is None:
            return
        profile = self._profile_for_diagnostic(diagnostic)
        source = self._review_source(item, diagnostic)
        original_set = self._peak_table_mapping_set
        if profile is None or source is None or original_set is None:
            self.status_label.setText(
                "This drift candidate cannot be joined to a current direct-file selection."
            )
            return
        label, accepted = QInputDialog.getText(
            self,
            "Save repaired mapping as new profile",
            "Local profile name:",
            QLineEdit.EchoMode.Normal,
            f"{profile.display_label} (repaired)",
        )
        if not accepted:
            return
        review_sheet = (
            profile.worksheet_title
            if PeakMappingDriftCategory.WORKSHEET_IDENTITY_CHANGED_UNRESOLVED
            not in diagnostic.categories
            else None
        )
        dialog = PeakMappingDialog(
            source,
            mapping=profile.mapping,
            parent=self,
            review_mode=True,
            sheet=review_sheet,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.mapping is None:
            return
        if (
            not self.mapping_set_active
            or self._peak_table_mapping_set != original_set
            or self._selection.paths != self._displayed_inputs
        ):
            self.status_label.setText(
                "The input or mapping set changed; the reviewed mapping was not saved."
            )
            return
        if item.source_sha256 is None or dialog.preview_source_sha256 != item.source_sha256:
            self.status_label.setText(
                "The source changed after inspection; run inspection again before repair."
            )
            return
        try:
            observed_preview = PeakTablePreview(
                dialog.mapping.source_format,
                dialog.mapping.declared_headers,
                (),
                dialog.preview_worksheet_title,
                import_settings=dialog.mapping.import_settings,
            )
            updated = clone_peak_table_mapping_profile(
                original_set,
                parent_profile_id=profile.profile_id,
                observed_preview=observed_preview,
                repaired_mapping=dialog.mapping,
                display_label=label.strip(),
            )
            repaired = updated.profiles[-1]
        except Exception as error:
            code, message = presentation_error(error)
            self.status_label.setText(f"Repaired mapping save failed [{code}]: {message}")
            return
        self._set_peak_mapping_set(
            updated,
            activate=True,
            selected_profile_id=repaired.profile_id,
        )
        self.status_label.setText(
            "Repaired mapping added locally as a new profile; use Save Set to persist it."
        )

    def _map_peak_columns(self) -> None:
        source = self._mapping_source()
        if source is None:
            self.status_label.setText(
                "Select one regular CSV, TSV, TXT, or XLSX file to map its peak columns."
            )
            return
        dialog = PeakMappingDialog(source, mapping=self._peak_table_mapping, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.mapping is not None:
            self._set_peak_mapping(
                dialog.mapping,
                sheet=dialog.preview_worksheet_title,
            )
            if self.mapping_set_active:
                self.status_label.setText(
                    "Current mapping updated but the mapping set remains active. "
                    "Use Add Current to include it in batch routing."
                )
            else:
                self.status_label.setText(
                    "Explicit peak mapping applied. Column meanings remain user-declared."
                )

    def _load_peak_mapping(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Load peak mapping",
            str(Path.home()),
            "Peak mapping JSON (*.json)",
        )
        if not path:
            return
        try:
            mapping = load_mapping(Path(path))
        except Exception as error:
            code, message = presentation_error(error)
            self.status_label.setText(f"Mapping load failed [{code}]: {message}")
            return
        self._set_peak_mapping(mapping)
        self.status_label.setText(
            "Explicit peak mapping loaded."
            if not self.mapping_set_active
            else "Current mapping loaded; the mapping set remains active."
        )

    def _save_peak_mapping(self) -> None:
        if self._peak_table_mapping is None:
            return
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Save peak mapping",
            str(Path.cwd() / "peak-mapping.json"),
            "Peak mapping JSON (*.json)",
        )
        if not path:
            return
        destination = Path(path)
        if destination.suffix.casefold() != ".json":
            destination = destination.with_suffix(".json")
        try:
            save_mapping(
                self._peak_table_mapping,
                destination,
                overwrite=destination.exists(),
            )
        except Exception as error:
            code, message = presentation_error(error)
            self.status_label.setText(f"Mapping save failed [{code}]: {message}")
            return
        self.status_label.setText("Explicit peak mapping saved.")

    def _clear_peak_mapping(self) -> None:
        self._set_peak_mapping(None)
        self.status_label.setText("Explicit peak mapping cleared.")

    def _mapping_set_toggled(self, checked: bool) -> None:
        if checked and self._peak_table_mapping_set is None:
            self.use_mapping_set_checkbox.blockSignals(True)
            self.use_mapping_set_checkbox.setChecked(False)
            self.use_mapping_set_checkbox.blockSignals(False)
            return
        self._sync_active_recipe_from_controls()
        self._refresh_mapping_status()
        self._refresh_recipe_status()
        self._update_mapping_controls()
        self.status_label.setText(
            "Reusable mapping set enabled for batch routing."
            if checked
            else "Reusable mapping set disabled; single-mapping mode is active."
        )
        self._invalidate_preflight("Mapping repair changed the configuration. Refresh preflight.")

    def _load_peak_mapping_set(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Load peak mapping set",
            str(Path.home()),
            "Peak mapping set JSON (*.json)",
        )
        if not path:
            return
        try:
            mapping_set = load_mapping_set(Path(path))
        except Exception as error:
            code, message = presentation_error(error)
            self.status_label.setText(f"Mapping set load failed [{code}]: {message}")
            return
        self._set_peak_mapping_set(mapping_set, activate=True)
        self.status_label.setText(
            f"Reusable mapping set loaded with {len(mapping_set.profiles)} profile(s)."
        )

    def _save_peak_mapping_set(self) -> None:
        mapping_set = self._peak_table_mapping_set
        if mapping_set is None:
            return
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Save peak mapping set",
            str(Path.cwd() / "peak-mapping-set.json"),
            "Peak mapping set JSON (*.json)",
        )
        if not path:
            return
        destination = Path(path)
        if destination.suffix.casefold() != ".json":
            destination = destination.with_suffix(".json")
        try:
            save_mapping_set(mapping_set, destination, overwrite=destination.exists())
        except Exception as error:
            code, message = presentation_error(error)
            self.status_label.setText(f"Mapping set save failed [{code}]: {message}")
            return
        self.status_label.setText("Reusable mapping set saved.")

    def _add_current_mapping_profile(self) -> None:
        mapping = self._peak_table_mapping
        if mapping is None:
            return
        label, accepted = QInputDialog.getText(
            self,
            "Add mapping profile",
            "Local profile name:",
            QLineEdit.EchoMode.Normal,
            f"{mapping.source_format.value.upper()} mapping",
        )
        if not accepted:
            return
        try:
            profile = PeakTableMappingProfile(
                mapping,
                display_label=label.strip(),
                worksheet_title=self._peak_table_mapping_sheet,
            )
            mapping_set = self._peak_table_mapping_set
            if mapping_set is None:
                updated = PeakTableMappingSet((profile,))
            else:
                updated = replace(mapping_set, profiles=(*mapping_set.profiles, profile))
        except Exception as error:
            code, message = presentation_error(error)
            self.status_label.setText(f"Mapping profile add failed [{code}]: {message}")
            return
        self._set_peak_mapping_set(
            updated,
            activate=True,
            selected_profile_id=profile.profile_id,
        )
        self.status_label.setText("Current mapping added to the active reusable mapping set.")

    def _rename_mapping_profile(self) -> None:
        profile = self._selected_mapping_profile()
        mapping_set = self._peak_table_mapping_set
        if profile is None or mapping_set is None:
            return
        label, accepted = QInputDialog.getText(
            self,
            "Rename mapping profile",
            "Local profile name:",
            QLineEdit.EchoMode.Normal,
            profile.display_label,
        )
        if not accepted:
            return
        try:
            renamed = replace(profile, display_label=label.strip())
            updated_profiles = tuple(
                renamed if item.profile_id == profile.profile_id else item
                for item in mapping_set.profiles
            )
            updated = replace(mapping_set, profiles=updated_profiles)
        except Exception as error:
            code, message = presentation_error(error)
            self.status_label.setText(f"Mapping profile rename failed [{code}]: {message}")
            return
        self._set_peak_mapping_set(
            updated,
            selected_profile_id=profile.profile_id,
        )
        self.status_label.setText("Mapping profile renamed locally.")

    def _remove_mapping_profile(self) -> None:
        profile = self._selected_mapping_profile()
        mapping_set = self._peak_table_mapping_set
        if profile is None or mapping_set is None:
            return
        remaining = tuple(
            item for item in mapping_set.profiles if item.profile_id != profile.profile_id
        )
        if not remaining:
            self._set_peak_mapping_set(None, activate=False)
            self.status_label.setText(
                "Last mapping profile removed; single-mapping mode is active."
            )
            return
        try:
            updated = replace(mapping_set, profiles=remaining)
        except Exception as error:
            code, message = presentation_error(error)
            self.status_label.setText(f"Mapping profile removal failed [{code}]: {message}")
            return
        self._set_peak_mapping_set(updated)
        self.status_label.setText("Mapping profile removed from the local set.")

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

    def _clear_inputs(self) -> None:
        self._selection.clear()
        self._invalidate_preflight("Preflight has not run.")
        self.selection_list.clear()
        self.input_table.setRowCount(0)
        self.status_label.setText("Input list cleared.")
        self.details.setPlainText("No inputs selected.")
        self._update_mapping_controls()

    def _sort_value(self) -> str:
        value = self.sort_combo.currentData()
        return value if isinstance(value, str) else "auto"

    def _render_queued_inputs(self) -> None:
        self._invalidate_preflight("Preflight is required for the current selection.")
        self.selection_list.clear()
        for path in self._selection.paths:
            self.selection_list.addItem(safe_display_name(path))
        self.input_table.setRowCount(len(self._selection.paths))
        for row, path in enumerate(self._selection.paths):
            values = (
                safe_display_name(path),
                "Pending core discovery",
                "—",
                "Pending inspection",
                "Wait for preflight",
                "Queued",
            )
            for column, value in enumerate(values):
                self.input_table.setItem(row, column, QTableWidgetItem(value))
        self._update_mapping_controls()

    def _render_report(self, report: DesktopBatchReport) -> None:
        self.drift_group.setVisible(
            any(
                item.plan_problem is ConversionPlanProblem.MAPPING_SCHEMA_DRIFT
                or item.mapping_route == "SCHEMA_DRIFT_CANDIDATE"
                for item in report.files
            )
        )
        self.input_table.setRowCount(len(report.files))
        for row, item in enumerate(report.files):
            action = (
                "Choose another output"
                if report.plan is not None
                and report.plan.output_disposition is ConversionPlanOutputDisposition.BLOCKED
                else self._plan_action_text(item)
            )
            values = (
                item.source,
                item.format_name,
                item.adapter_id,
                self._mapping_route_text(item),
                action,
                self._plan_status_text(item),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if item.message:
                    cell.setToolTip(item.message)
                self.input_table.setItem(row, column, cell)

    def _mapping_route_text(self, item: DesktopFileReport) -> str:
        plan_route_labels = {
            ConversionPlanRoute.EXACT_ADAPTER: "Exact adapter",
            ConversionPlanRoute.USER_MAPPING: "Single user mapping",
            ConversionPlanRoute.USER_MAPPING_PROFILE: "User mapping profile",
            ConversionPlanRoute.GENERIC_INPUT: "Generic input",
            ConversionPlanRoute.UNROUTED: "Unrouted",
        }
        if item.plan_route is not None:
            if (
                item.plan_route is ConversionPlanRoute.USER_MAPPING_PROFILE
                and item.mapping_profile_id is not None
            ):
                mapping_set = self._peak_table_mapping_set
                if mapping_set is not None:
                    profile = next(
                        (
                            candidate
                            for candidate in mapping_set.profiles
                            if candidate.profile_id == item.mapping_profile_id
                        ),
                        None,
                    )
                    if profile is not None:
                        return f"User mapping: {safe_preview_text(profile.display_label)}"
            return plan_route_labels[item.plan_route]
        route_labels = {
            "EXACT_ADAPTER": "Exact adapter",
            "USER_MAPPING": "Single user mapping",
            "SCHEMA_DRIFT_CANDIDATE": "Schema changed — review required",
            "NO_MAPPING_MATCH": "No mapping profile matched",
            "AMBIGUOUS_MAPPING_PROFILE": "Ambiguous mapping profiles",
            "AMBIGUOUS_WORKSHEET": "Ambiguous workbook sheets",
            "MAPPING_VALIDATION_FAILED": "Mapping validation failed",
        }
        if item.mapping_route == "USER_MAPPING_PROFILE":
            mapping_set = self._peak_table_mapping_set
            if mapping_set is not None and item.mapping_profile_id is not None:
                profile = next(
                    (
                        candidate
                        for candidate in mapping_set.profiles
                        if candidate.profile_id == item.mapping_profile_id
                    ),
                    None,
                )
                if profile is not None:
                    return f"User mapping: {safe_preview_text(profile.display_label)}"
            return "User mapping profile"
        if item.mapping_route is None:
            return "Automatic detection"
        return route_labels.get(item.mapping_route, safe_preview_text(item.mapping_route))

    @staticmethod
    def _plan_action_text(item: DesktopFileReport) -> str:
        if item.plan_status is None:
            return "Completed"
        if item.plan_status is ConversionPlanEntryStatus.ROUTABLE:
            return "Convert"
        if item.plan_status is ConversionPlanEntryStatus.DUPLICATE:
            return "Skip duplicate"
        if item.plan_status is ConversionPlanEntryStatus.EXCLUDED_ARTIFACT:
            return "Exclude prior artifact"
        actions = {
            ConversionPlanProblem.UNMAPPED_GENERIC_TABLE: "Map peak columns",
            ConversionPlanProblem.MAPPING_SCHEMA_DRIFT: "Review mapping",
            ConversionPlanProblem.MAPPING_PROFILE_AMBIGUOUS: "Resolve profile ambiguity",
            ConversionPlanProblem.WORKSHEET_AMBIGUOUS: "Choose worksheet",
            ConversionPlanProblem.ADAPTER_AMBIGUOUS: "Resolve adapter ambiguity",
            ConversionPlanProblem.UNSUPPORTED_FORMAT: "Unsupported",
            ConversionPlanProblem.MALFORMED_INPUT: "Repair input structure",
            ConversionPlanProblem.INPUT_DISCOVERY_FAILED: "Resolve input failure",
            ConversionPlanProblem.OUTPUT_CONFLICT: "Choose another output",
            ConversionPlanProblem.DUPLICATE_INPUT: "Skip duplicate",
            ConversionPlanProblem.NONE: "Resolve failure",
        }
        return actions[item.plan_problem or ConversionPlanProblem.NONE]

    @staticmethod
    def _plan_status_text(item: DesktopFileReport) -> str:
        if item.plan_status is None:
            return item.status.value
        return {
            ConversionPlanEntryStatus.ROUTABLE: "Routable",
            ConversionPlanEntryStatus.FAILED: "Failed",
            ConversionPlanEntryStatus.DUPLICATE: "Duplicate",
            ConversionPlanEntryStatus.EXCLUDED_ARTIFACT: "Excluded",
        }[item.plan_status]

    def _render_preflight_summary(self, plan: ConversionPlan) -> None:
        summary = plan.summary
        readiness = {
            ConversionPlanReadiness.READY: "Ready",
            ConversionPlanReadiness.READY_WITH_KNOWN_FAILURES: ("Ready with known failures"),
            ConversionPlanReadiness.BLOCKED: "Blocked",
        }[plan.readiness]
        output_note = (
            f" Output: {safe_preview_text(plan.output_issue_code)}."
            if plan.output_issue_code
            else ""
        )
        self.preflight_summary_label.setText(
            f"{readiness}: {summary.routable} routable, {summary.failed} failed, "
            f"{summary.duplicates} duplicate, {summary.exact_adapters} exact-adapter, "
            f"{summary.user_mappings + summary.mapping_profiles} user-mapped, "
            f"{summary.drifted} schema-drift, {summary.unmapped} unmapped, "
            f"{summary.unsupported} unsupported.{output_note}"
        )

    def _request_preview(self, *_unused: object) -> None:
        if not self._selection.paths or self._conversion_thread is not None:
            return
        self._invalidate_preflight("Preflight is pending for the current configuration.")
        if self._preview_thread is not None:
            self._preview_pending = True
            return
        self._start_preview()

    def _start_preview(self) -> None:
        if not self._selection.paths or self._conversion_thread is not None:
            return
        self._preview_pending = False
        request = self._current_preflight_request()
        self._preview_request = request
        self._preview_generation = self._preflight_generation
        self.refresh_preflight_button.setEnabled(False)
        self._update_convert_enabled()
        self.status_label.setText("Planning selected inputs…")
        thread = QThread(self)
        worker = PreviewWorker(request)
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
        if isinstance(event, PlanProgressEvent):
            total = max(event.total, 1)
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(min(event.completed, total))
            label = {
                "planning_discovery": "Discovering inputs",
                "planning_routing": "Planning conversion routes",
                "planning_complete": "Preflight complete",
            }.get(event.stage, "Planning conversion")
            self.status_label.setText(f"{label}: {event.completed}/{event.total}")

    def _on_preview_complete(self, report: object) -> None:
        if not isinstance(report, DesktopBatchReport):
            return
        if (
            self._preview_generation != self._preflight_generation
            or self._preview_request != self._current_preflight_request()
        ):
            return
        if report.is_fatal_error:
            self.preflight_summary_label.setText("Preflight failed; conversion is disabled.")
            self.status_label.setText(
                f"Inspection failed [{report.error_code}]: {report.error_message}"
            )
        else:
            self._displayed_files = report.files
            self._displayed_inputs = self._selection.paths
            self._displayed_mapping_set = self._active_peak_mappings()[1]
            self._displayed_plan = report.plan
            self._displayed_request = self._preview_request
            self._displayed_generation = self._preview_generation
            self._render_report(report)
            if report.plan is not None:
                self._render_preflight_summary(report.plan)
            self.status_label.setText(
                f"Preflight complete: {len(report.files)} input(s), "
                f"{report.failure_count} known failure(s)."
            )
        self.details.setPlainText(details_text(report))
        self.details_toggle_button.setChecked(report.is_fatal_error or report.failure_count > 0)
        self._update_convert_enabled()

    def _preview_finished(self) -> None:
        self._preview_thread = None
        self._preview_worker = None
        self._preview_request = None
        self._preview_generation = None
        if self._preview_pending:
            self._start_preview()
        else:
            self._update_mapping_controls()
            self._mapping_drift_row_changed()

    def _start_conversion(self) -> None:
        if self._conversion_thread is not None:
            return
        plan = self._current_plan()
        if plan is None or not plan.is_executable or plan.summary.routable == 0:
            self.status_label.setText(
                "Refresh preflight and resolve blocking actions before conversion."
            )
            self._update_convert_enabled()
            return
        self._invalidate_mapping_drift_review()
        self._set_conversion_controls(False)
        self.open_output_button.setEnabled(False)
        self._last_output = None
        self.status_label.setText("Starting conversion…")
        self.details.setPlainText("Conversion is running.")
        thread = QThread(self)
        worker = ConversionWorker(plan)
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
        self.details_toggle_button.setChecked(
            report.is_fatal_error or report.outcome is not BatchOutcome.SUCCESS
        )
        output_exists = report.output_path is not None and report.output_path.is_file()
        if output_exists:
            self._last_output = report.output_path
            self.open_output_button.setEnabled(True)
        summary = report.summary
        result_counts = None
        if summary is not None:
            plan = self._current_plan()
            series_included = plan is None or plan.options.include_signals
            count_parts = [
                f"{summary.converted_sources} source(s)",
                f"{summary.sample_records} sample(s)",
                f"{summary.peak_records} peak(s)",
            ]
            if series_included and summary.scientific_signal_series:
                count_parts.append(
                    f"{summary.scientific_signal_series} scientific signal stream(s)"
                )
            if series_included and summary.structural_record_series:
                count_parts.append(
                    f"{summary.structural_record_series} structural record stream(s)"
                )
            result_counts = ", ".join(count_parts)
        if report.is_fatal_error:
            self.status_label.setText(
                f"Conversion failed [{report.error_code}]: {report.error_message}"
            )
        elif report.outcome is BatchOutcome.PARTIAL_SUCCESS:
            if summary is None:
                self.status_label.setText(
                    f"Workbook created with partial success: {report.success_count} succeeded, "
                    f"{report.failure_count} failed."
                )
            else:
                self.status_label.setText(
                    f"Workbook created with partial success: {result_counts}; "
                    f"{summary.failed_sources} failed, {summary.skipped_sources} skipped."
                )
        elif report.outcome is BatchOutcome.FAILED:
            suffix = " A diagnostic workbook was created." if output_exists else ""
            self.status_label.setText(
                f"No files converted successfully; {report.failure_count} failed.{suffix}"
            )
        else:
            if summary is None:
                self.status_label.setText(
                    f"Conversion complete: {report.success_count} succeeded, "
                    f"{report.warning_count} with warnings."
                )
            else:
                self.status_label.setText(
                    f"Conversion complete: {result_counts}; "
                    f"{summary.warning_sources} with warnings, "
                    f"{summary.skipped_sources} skipped."
                )

    def _conversion_finished(self) -> None:
        self._conversion_thread = None
        self._conversion_worker = None
        self._set_conversion_controls(True)
        self._update_mapping_controls()
        self._invalidate_preflight("Refresh preflight before another conversion.")
        self._update_convert_enabled()

    def _set_conversion_controls(self, enabled: bool) -> None:
        for widget in (
            self.add_files_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
            self.map_peaks_button,
            self.load_mapping_button,
            self.save_mapping_button,
            self.clear_mapping_button,
            self.use_mapping_set_checkbox,
            self.mapping_set_combo,
            self.load_mapping_set_button,
            self.save_mapping_set_button,
            self.add_mapping_profile_button,
            self.rename_mapping_profile_button,
            self.remove_mapping_profile_button,
            self.recipe_combo,
            self.save_recipe_button,
            self.manage_recipes_button,
            self.mapping_toggle_button,
            self.advanced_options_button,
            self.details_toggle_button,
            self.drift_candidate_combo,
            self.review_mapping_button,
            self.refresh_preflight_button,
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
