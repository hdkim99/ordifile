# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Manage researcher-facing saved setups backed by strict Conversion Recipes."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ordifile.desktop.recipe_library import RecipeLibrary, RecipeLibraryError, StoredRecipe
from ordifile.desktop.services import load_recipe, presentation_error, save_recipe


class RecipeManagerDialog(QDialog):
    """Provide explicit rename, copy, delete, import, and export actions."""

    def __init__(self, library: RecipeLibrary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Saved Setups")
        self.resize(650, 420)
        self.setModal(True)
        self._library = library
        self._changed = False

        root = QVBoxLayout(self)
        explanation = QLabel(
            "Saved setups keep reusable conversion settings on this computer. Import and "
            "export are only needed when moving a setup between computers or command-line "
            "workflows."
        )
        explanation.setWordWrap(True)
        root.addWidget(explanation)

        self.recipe_list = QListWidget()
        self.recipe_list.setAccessibleName("Saved conversion setups")
        self.recipe_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        root.addWidget(self.recipe_list, stretch=1)

        edit_actions = QHBoxLayout()
        self.rename_button = QPushButton("&Rename…")
        self.rename_button.setAccessibleName("Rename saved conversion setup")
        self.duplicate_button = QPushButton("D&uplicate…")
        self.duplicate_button.setAccessibleName("Duplicate saved conversion setup")
        self.delete_button = QPushButton("&Delete…")
        self.delete_button.setAccessibleName("Delete saved conversion setup")
        for button in (self.rename_button, self.duplicate_button, self.delete_button):
            edit_actions.addWidget(button)
        edit_actions.addStretch()
        root.addLayout(edit_actions)

        portability_actions = QHBoxLayout()
        self.import_button = QPushButton("&Import Setup…")
        self.import_button.setAccessibleName("Import portable conversion setup")
        self.export_button = QPushButton("&Export Setup…")
        self.export_button.setAccessibleName("Export portable conversion setup")
        portability_actions.addWidget(self.import_button)
        portability_actions.addWidget(self.export_button)
        portability_actions.addStretch()
        root.addLayout(portability_actions)

        self.status_label = QLabel("Select a saved setup to manage it.")
        self.status_label.setAccessibleName("Saved setup management status")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_button = self.buttons.button(QDialogButtonBox.StandardButton.Close)
        assert close_button is not None
        close_button.setAccessibleName("Close saved setup manager")
        root.addWidget(self.buttons)

        self.recipe_list.itemSelectionChanged.connect(self._update_actions)
        self.rename_button.clicked.connect(self.rename_selected)
        self.duplicate_button.clicked.connect(self.duplicate_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.import_button.clicked.connect(self.import_recipe)
        self.export_button.clicked.connect(self.export_selected)
        self.buttons.rejected.connect(self.reject)

        self.setTabOrder(self.recipe_list, self.rename_button)
        self.setTabOrder(self.rename_button, self.duplicate_button)
        self.setTabOrder(self.duplicate_button, self.delete_button)
        self.setTabOrder(self.delete_button, self.import_button)
        self.setTabOrder(self.import_button, self.export_button)
        self.setTabOrder(self.export_button, close_button)
        self.reload()

    @property
    def changed(self) -> bool:
        """Return whether this dialog completed a library write."""
        return self._changed

    def _selected_id(self) -> str | None:
        items = self.recipe_list.selectedItems()
        if not items:
            return None
        value = items[0].data(Qt.ItemDataRole.UserRole)
        return value if type(value) is str else None

    def _selected_entry(self) -> StoredRecipe | None:
        recipe_id = self._selected_id()
        if recipe_id is None:
            return None
        try:
            return self._library.get(recipe_id)
        except RecipeLibraryError as error:
            self.status_label.setText(f"Saved setup unavailable [{error.code}]: {error.message}")
            self.reload()
            return None

    def reload(self, *, selected_id: str | None = None) -> None:
        """Refresh valid entries while keeping one damaged member isolated."""
        try:
            snapshot = self._library.snapshot()
        except RecipeLibraryError as error:
            self.recipe_list.clear()
            self.status_label.setText(
                f"Saved setup library unavailable [{error.code}]: {error.message}"
            )
            self._update_actions()
            return
        self.recipe_list.clear()
        selected_row = -1
        for row, entry in enumerate(snapshot.entries):
            item = QListWidgetItem(entry.display_name)
            item.setData(Qt.ItemDataRole.UserRole, entry.recipe_id)
            self.recipe_list.addItem(item)
            if entry.recipe_id == selected_id:
                selected_row = row
        if selected_row >= 0:
            self.recipe_list.setCurrentRow(selected_row)
        elif self.recipe_list.count() > 0:
            self.recipe_list.setCurrentRow(0)
        if snapshot.invalid_count:
            self.status_label.setText(
                f"{snapshot.invalid_count} saved setup file(s) could not be loaded; "
                "other setups remain available."
            )
        elif not snapshot.entries:
            self.status_label.setText("No saved setups yet.")
        else:
            self.status_label.setText(f"{len(snapshot.entries)} saved setup(s) available.")
        self._update_actions()

    def _update_actions(self) -> None:
        selected = self._selected_id() is not None
        self.rename_button.setEnabled(selected)
        self.duplicate_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)
        self.export_button.setEnabled(selected)

    def rename_selected(self) -> None:
        """Rename only local display metadata."""
        entry = self._selected_entry()
        if entry is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename Saved Setup", "Saved setup name:", text=entry.display_name
        )
        if not accepted:
            return
        try:
            renamed = self._library.rename(entry.recipe_id, name)
        except RecipeLibraryError as error:
            self.status_label.setText(f"Rename failed [{error.code}]: {error.message}")
            return
        self._changed = True
        self.reload(selected_id=renamed.recipe_id)
        self.status_label.setText("Saved setup renamed. Conversion settings are unchanged.")

    def duplicate_selected(self) -> None:
        """Create an explicit copy with a new local name and identifier."""
        entry = self._selected_entry()
        if entry is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Duplicate Saved Setup",
            "New saved setup name:",
            text=f"{entry.display_name} copy",
        )
        if not accepted:
            return
        try:
            duplicate = self._library.duplicate(entry.recipe_id, name)
        except RecipeLibraryError as error:
            self.status_label.setText(f"Duplicate failed [{error.code}]: {error.message}")
            return
        self._changed = True
        self.reload(selected_id=duplicate.recipe_id)
        self.status_label.setText("Saved setup duplicated.")

    def delete_selected(self) -> None:
        """Delete one saved setup only after explicit confirmation."""
        entry = self._selected_entry()
        if entry is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete Saved Setup?",
            f'Delete the saved setup "{entry.display_name}"? Current GUI settings are kept.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._library.delete(entry.recipe_id, expected_revision_sha256=entry.revision_sha256)
        except RecipeLibraryError as error:
            self.status_label.setText(f"Delete failed [{error.code}]: {error.message}")
            return
        self._changed = True
        self.reload()
        self.status_label.setText("Saved setup deleted. Current GUI settings are unchanged.")

    def import_recipe(self) -> None:
        """Validate one portable JSON Recipe and copy it into the local library."""
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import Saved Setup",
            str(Path.home()),
            "Ordifile Recipe (*.json)",
        )
        if not path:
            return
        try:
            recipe = load_recipe(Path(path))
        except Exception as error:
            code, message = presentation_error(error)
            self.status_label.setText(f"Import failed [{code}]: {message}")
            return
        try:
            match = self._library.semantic_match(recipe)
        except RecipeLibraryError as error:
            self.status_label.setText(f"Import failed [{error.code}]: {error.message}")
            return
        if match is not None:
            answer = QMessageBox.question(
                self,
                "Setup already exists",
                "A saved setup has the same conversion settings. Import it as a separate copy?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.status_label.setText("Setup import cancelled; the settings already exist.")
                return
        proposed = recipe.display_label or "Imported setup"
        if match is not None:
            proposed = f"{proposed} copy"
        name, accepted = QInputDialog.getText(
            self, "Name Imported Setup", "Saved setup name:", text=proposed
        )
        if not accepted:
            return
        try:
            imported = self._library.create(recipe, name)
        except RecipeLibraryError as error:
            self.status_label.setText(f"Import failed [{error.code}]: {error.message}")
            return
        self._changed = True
        self.reload(selected_id=imported.recipe_id)
        self.status_label.setText("Setup imported into the local saved setup library.")

    def export_selected(self) -> None:
        """Write one portable strict Recipe JSON to an explicit destination."""
        entry = self._selected_entry()
        if entry is None:
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Saved Setup",
            str(Path.home() / "ordifile-recipe.json"),
            "Ordifile Recipe (*.json)",
        )
        if not path:
            return
        destination = Path(path)
        if destination.suffix.casefold() != ".json":
            destination = destination.with_suffix(".json")
        overwrite = False
        if destination.exists():
            answer = QMessageBox.question(
                self,
                "Replace exported setup?",
                "A file already exists at the selected destination. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.status_label.setText("Setup export cancelled.")
                return
            overwrite = True
        try:
            save_recipe(entry.recipe, destination, overwrite=overwrite)
        except Exception as error:
            code, message = presentation_error(error)
            self.status_label.setText(f"Export failed [{code}]: {message}")
            return
        self.status_label.setText("Portable setup exported to the selected destination.")
