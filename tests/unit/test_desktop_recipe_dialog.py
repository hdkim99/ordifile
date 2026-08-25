# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from ordifile import ConversionRecipe, load_conversion_recipe, save_conversion_recipe
from ordifile.core.models import SortMode
from ordifile.desktop.recipe_dialog import RecipeManagerDialog
from ordifile.desktop.recipe_library import RecipeLibrary


@pytest.fixture(scope="module")
def app() -> QApplication:
    existing = QApplication.instance()
    return cast(QApplication, existing) if existing is not None else QApplication([])


def test_empty_manager_is_keyboard_accessible_and_escape_closes(
    app: QApplication, tmp_path: Path
) -> None:
    dialog = RecipeManagerDialog(RecipeLibrary(tmp_path / "recipes"))

    assert dialog.recipe_list.accessibleName() == "Saved conversion setups"
    assert dialog.rename_button.accessibleName() == "Rename saved conversion setup"
    assert dialog.import_button.accessibleName() == "Import portable conversion setup"
    assert not dialog.rename_button.isEnabled()
    assert dialog.import_button.isEnabled()
    dialog.open()
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    app.processEvents()

    assert not dialog.isVisible()


def test_manager_rename_duplicate_and_delete_are_explicit(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    library = RecipeLibrary(tmp_path / "recipes")
    original = library.create(ConversionRecipe(sort=SortMode.FILENAME), "Daily")
    dialog = RecipeManagerDialog(library)
    names = iter((("GC 주간 분석", True), ("GC 주간 분석 copy", True)))
    monkeypatch.setattr(
        "ordifile.desktop.recipe_dialog.QInputDialog.getText",
        lambda *_args, **_kwargs: next(names),
    )

    dialog.rename_selected()
    renamed = library.get(original.recipe_id)
    assert renamed.display_name == "GC 주간 분석"
    assert renamed.recipe.semantic_sha256 == original.recipe.semantic_sha256

    dialog.duplicate_selected()
    entries = library.snapshot().entries
    assert len(entries) == 2
    duplicate = next(entry for entry in entries if entry.recipe_id != original.recipe_id)
    assert duplicate.recipe.semantic_sha256 == original.recipe.semantic_sha256
    assert duplicate.display_name == "GC 주간 분석 copy"

    dialog.recipe_list.setCurrentRow(
        next(
            row
            for row in range(dialog.recipe_list.count())
            if dialog.recipe_list.item(row).text() == "GC 주간 분석 copy"
        )
    )
    monkeypatch.setattr(
        "ordifile.desktop.recipe_dialog.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    dialog.delete_selected()
    assert len(library.snapshot().entries) == 2

    monkeypatch.setattr(
        "ordifile.desktop.recipe_dialog.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    dialog.delete_selected()
    assert len(library.snapshot().entries) == 1


def test_manager_import_and_export_reuse_strict_portable_json(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    portable = tmp_path / "portable.json"
    exported = tmp_path / "exported.json"
    recipe = ConversionRecipe(sort=SortMode.INPUT_ORDER, display_label="외부 설정")
    save_conversion_recipe(recipe, portable)
    library = RecipeLibrary(tmp_path / "library")
    dialog = RecipeManagerDialog(library)
    monkeypatch.setattr(
        "ordifile.desktop.recipe_dialog.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(portable), ""),
    )
    monkeypatch.setattr(
        "ordifile.desktop.recipe_dialog.QInputDialog.getText",
        lambda *_args, **_kwargs: ("가져온 설정", True),
    )

    dialog.import_recipe()

    imported = library.snapshot().entries[0]
    assert imported.display_name == "가져온 설정"
    assert imported.recipe.semantic_sha256 == recipe.semantic_sha256
    monkeypatch.setattr(
        "ordifile.desktop.recipe_dialog.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(exported), ""),
    )
    dialog.export_selected()
    round_trip = load_conversion_recipe(exported)
    assert round_trip.semantic_sha256 == recipe.semantic_sha256
    assert round_trip.display_label == "가져온 설정"


def test_invalid_import_keeps_existing_library_and_hides_local_path(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    malformed = tmp_path / "private-invalid-name.json"
    malformed.write_text("not-json", encoding="utf-8")
    library = RecipeLibrary(tmp_path / "library")
    existing = library.create(ConversionRecipe(), "Existing")
    dialog = RecipeManagerDialog(library)
    monkeypatch.setattr(
        "ordifile.desktop.recipe_dialog.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(malformed), ""),
    )

    dialog.import_recipe()

    assert library.snapshot().entries == (existing,)
    assert "Import failed" in dialog.status_label.text()
    assert malformed.name not in dialog.status_label.text()
