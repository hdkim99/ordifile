# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from itertools import pairwise
from pathlib import Path
from typing import cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import openpyxl  # type: ignore[import-untyped]
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QWidget

from ordifile import ColumnSelector, PeakTableFormat, PeakTableMapping
from ordifile.core.errors import OrdifileError
from ordifile.desktop.models import DesktopPeakTablePreview, DesktopPeakTablePreviewReport
from ordifile.desktop.peak_mapping_dialog import PeakMappingDialog, formats_for_path
from ordifile.desktop.workers import PeakTablePreviewWorker


@pytest.fixture(scope="module")
def app() -> QApplication:
    existing = QApplication.instance()
    return cast(QApplication, existing) if existing is not None else QApplication([])


def _preview(*headers: str) -> DesktopPeakTablePreview:
    return DesktopPeakTablePreview(
        PeakTableFormat.CSV,
        headers,
        (tuple(str(index) for index in range(len(headers))),),
    )


def _select(combo: QComboBox, selector: ColumnSelector) -> None:
    index = next(
        (index for index in range(combo.count()) if combo.itemData(index) == selector),
        -1,
    )
    assert index >= 0
    combo.setCurrentIndex(index)


def _next_expected_widget(current: QWidget, expected: set[QWidget]) -> QWidget:
    candidate = current.nextInFocusChain()
    assert candidate is not None
    while candidate not in expected:
        candidate = candidate.nextInFocusChain()
        assert candidate is not None
        assert candidate is not current
    return candidate


def test_formats_for_path_exposes_only_audited_generic_containers() -> None:
    assert formats_for_path(Path("result.csv")) == (PeakTableFormat.CSV,)
    assert formats_for_path(Path("result.tsv")) == (PeakTableFormat.TSV,)
    assert formats_for_path(Path("result.txt")) == (
        PeakTableFormat.TSV,
        PeakTableFormat.SEMICOLON,
    )
    assert formats_for_path(Path("result.xlsx")) == (PeakTableFormat.XLSX,)
    assert formats_for_path(Path("result.xls")) == ()
    assert formats_for_path(Path("result.pdf")) == ()


def test_dialog_requires_explicit_rt_area_and_rt_unit(app: QApplication, tmp_path: Path) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("RT,Area\n1,2\n", encoding="utf-8")
    dialog = PeakMappingDialog(source, auto_preview=False)
    dialog.set_preview(_preview("RT", "Area"))

    assert not dialog.apply_button.isEnabled()
    _select(dialog.retention_time_combo, ColumnSelector("RT", 1))
    _select(dialog.area_combo, ColumnSelector("Area", 2))
    assert not dialog.apply_button.isEnabled()

    dialog.retention_time_unit_edit.setText("min")

    assert dialog.apply_button.isEnabled()
    assert "user-declared" in dialog.validation_label.text()
    dialog.close()


def test_dialog_has_explicit_keyboard_focus_order(app: QApplication, tmp_path: Path) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("RT,Area\n1,2\n", encoding="utf-8")
    dialog = PeakMappingDialog(source, auto_preview=False)

    expected_order = (
        dialog.format_combo,
        dialog.reload_button,
        dialog.preview_table,
        dialog.retention_time_combo,
        dialog.retention_time_unit_edit,
        dialog.area_combo,
        dialog.area_unit_edit,
        *dialog.optional_combos.values(),
        dialog.height_unit_edit,
        dialog.secondary_retention_time_unit_edit,
        dialog.manufacturer_edit,
        dialog.software_edit,
        dialog.apply_button,
        dialog.cancel_button,
    )
    expected = set(expected_order)
    assert all(
        _next_expected_widget(current, expected) is following
        for current, following in pairwise(expected_order)
    )
    dialog.close()


def test_dialog_cancel_discards_unapplied_mapping(app: QApplication, tmp_path: Path) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("RT,Area\n1,2\n", encoding="utf-8")
    dialog = PeakMappingDialog(source, auto_preview=False)
    dialog.set_preview(_preview("RT", "Area"))
    _select(dialog.retention_time_combo, ColumnSelector("RT", 1))
    _select(dialog.area_combo, ColumnSelector("Area", 2))
    dialog.retention_time_unit_edit.setText("min")

    dialog.cancel_button.click()

    assert dialog.result() == dialog.DialogCode.Rejected
    assert dialog.mapping is None


def test_dialog_defers_cancel_while_preview_worker_is_active(
    app: QApplication, tmp_path: Path
) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("RT,Area\n1,2\n", encoding="utf-8")
    dialog = PeakMappingDialog(source, auto_preview=False)
    thread = QThread(dialog)
    dialog._preview_thread = thread

    dialog.cancel_button.click()

    assert dialog.result() == 0
    assert "wait" in dialog.preview_status.text().casefold()
    dialog._preview_thread = None
    dialog.close()


def test_dialog_rejects_unrepresentable_preview_headers_without_crashing(
    app: QApplication, tmp_path: Path
) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text(",Area\n1,2\n", encoding="utf-8")
    dialog = PeakMappingDialog(source, auto_preview=False)

    dialog.set_preview(_preview("", "Area"))

    assert not dialog.apply_button.isEnabled()
    assert "cannot be mapped safely" in dialog.preview_status.text()
    dialog.close()


def test_dialog_escapes_directional_worksheet_title_in_status(
    app: QApplication, tmp_path: Path
) -> None:
    del app
    source = tmp_path / "result.xlsx"
    dialog = PeakMappingDialog(source, auto_preview=False)

    dialog.set_preview(
        DesktopPeakTablePreview(
            PeakTableFormat.XLSX,
            ("RT", "Area"),
            (("1", "2"),),
            "left\u202eright",
        )
    )

    assert "left\\u202Eright" in dialog.preview_status.text()
    assert "\u202e" not in dialog.preview_status.text()
    dialog.close()


def test_dialog_builds_immutable_mapping_and_classifies_every_unselected_column(
    app: QApplication, tmp_path: Path
) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("RT,Area,Height,Compound,Notes,Other\n1,2,3,A,x,y\n", encoding="utf-8")
    dialog = PeakMappingDialog(source, auto_preview=False)
    dialog.set_preview(_preview("RT", "Area", "Height", "Compound", "Notes", "Other"))
    _select(dialog.retention_time_combo, ColumnSelector("RT", 1))
    _select(dialog.area_combo, ColumnSelector("Area", 2))
    _select(dialog.optional_combos["height_column"], ColumnSelector("Height", 3))
    _select(
        dialog.optional_combos["compound_name_column"],
        ColumnSelector("Compound", 4),
    )
    dialog.retention_time_unit_edit.setText("s")
    dialog.area_unit_edit.setText("AU")
    dialog.height_unit_edit.setText("AU")
    dialog.manufacturer_edit.setText("User entry")

    dialog._accept_mapping()

    mapping = dialog.mapping
    assert mapping is not None
    assert mapping.retention_time_column == ColumnSelector("RT", 1)
    assert mapping.area_column == ColumnSelector("Area", 2)
    assert mapping.height_column == ColumnSelector("Height", 3)
    assert mapping.compound_name_column == ColumnSelector("Compound", 4)
    assert mapping.ignored_columns == (
        ColumnSelector("Notes", 5),
        ColumnSelector("Other", 6),
    )
    assert mapping.manufacturer == "User entry"
    assert mapping.source_format is PeakTableFormat.CSV
    dialog.close()


def test_dialog_rejects_duplicate_semantic_column_and_unpaired_secondary_rt(
    app: QApplication, tmp_path: Path
) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("RT1,RT2,Area\n1,2,3\n", encoding="utf-8")
    dialog = PeakMappingDialog(source, auto_preview=False)
    dialog.set_preview(_preview("RT1", "RT2", "Area"))
    _select(dialog.retention_time_combo, ColumnSelector("RT1", 1))
    _select(dialog.area_combo, ColumnSelector("Area", 3))
    dialog.retention_time_unit_edit.setText("s")
    _select(dialog.optional_combos["height_column"], ColumnSelector("Area", 3))

    assert not dialog.apply_button.isEnabled()
    assert "different" in dialog.validation_label.text()

    dialog.optional_combos["height_column"].setCurrentIndex(0)
    _select(
        dialog.optional_combos["secondary_retention_time_column"],
        ColumnSelector("RT2", 2),
    )
    assert not dialog.apply_button.isEnabled()
    assert "together" in dialog.validation_label.text()

    dialog.secondary_retention_time_unit_edit.setText("s")
    assert dialog.apply_button.isEnabled()
    dialog.close()


def test_dialog_restores_loaded_mapping_after_preview(app: QApplication, tmp_path: Path) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("RT,Area,Ignored\n1,2,x\n", encoding="utf-8")
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
        area_unit="mV.s",
        ignored_columns=(ColumnSelector("Ignored", 3),),
    )
    dialog = PeakMappingDialog(source, mapping=mapping, auto_preview=False)

    dialog.set_preview(_preview("RT", "Area", "Ignored"))

    assert dialog.retention_time_combo.currentData() == ColumnSelector("RT", 1)
    assert dialog.area_combo.currentData() == ColumnSelector("Area", 2)
    assert dialog.retention_time_unit_edit.text() == "min"
    assert dialog.area_unit_edit.text() == "mV.s"
    assert dialog.apply_button.isEnabled()
    dialog.close()


def test_review_dialog_restores_only_exact_surviving_selectors(
    app: QApplication, tmp_path: Path
) -> None:
    del app
    source = tmp_path / "changed.csv"
    source.write_text("RT,Height,Peak Area\n1,2,3\n", encoding="utf-8")
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
        height_column=ColumnSelector("Height", 3),
    )
    dialog = PeakMappingDialog(
        source,
        mapping=mapping,
        auto_preview=False,
        review_mode=True,
    )

    dialog.set_preview(_preview("RT", "Height", "Peak Area"))

    assert dialog.windowTitle() == "Review Mapping"
    assert dialog.retention_time_combo.currentData() == ColumnSelector("RT", 1)
    assert dialog.area_combo.currentData() is None
    assert dialog.optional_combos["height_column"].currentData() is None
    assert not dialog.apply_button.isEnabled()
    dialog.close()


def test_review_dialog_does_not_rebind_a_changed_duplicate_occurrence(
    app: QApplication, tmp_path: Path
) -> None:
    del app
    source = tmp_path / "duplicates.csv"
    source.write_text("RT,Signal,Area\n1,2,3\n", encoding="utf-8")
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
        height_column=ColumnSelector("Area", 3),
    )
    dialog = PeakMappingDialog(
        source,
        mapping=mapping,
        auto_preview=False,
        review_mode=True,
    )

    dialog.set_preview(_preview("RT", "Signal", "Area"))

    assert dialog.retention_time_combo.currentData() == ColumnSelector("RT", 1)
    assert dialog.area_combo.currentData() is None
    assert dialog.optional_combos["height_column"].currentData() is None
    assert not dialog.apply_button.isEnabled()
    dialog.close()


def test_review_dialog_exposes_only_previewed_xlsx_worksheet_title(
    app: QApplication, tmp_path: Path
) -> None:
    del app
    dialog = PeakMappingDialog(
        tmp_path / "changed.xlsx",
        auto_preview=False,
        review_mode=True,
    )

    dialog.set_preview(
        DesktopPeakTablePreview(
            PeakTableFormat.XLSX,
            ("RT", "Area"),
            (("1", "2"),),
            "Reviewed Sheet",
        )
    )

    assert dialog.preview_worksheet_title == "Reviewed Sheet"
    dialog.close()


def test_review_dialog_rechecks_source_before_accepting(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "changed.csv"
    source.write_text("RT,Peak Area\n1,2\n", encoding="utf-8")
    dialog = PeakMappingDialog(source, auto_preview=False, review_mode=True)
    preview = DesktopPeakTablePreview(
        PeakTableFormat.CSV,
        ("RT", "Peak Area"),
        (("1", "2"),),
        source_sha256="1" * 64,
    )
    dialog.set_preview(preview)
    _select(dialog.retention_time_combo, ColumnSelector("RT", 1))
    _select(dialog.area_combo, ColumnSelector("Peak Area", 2))
    dialog.retention_time_unit_edit.setText("min")
    monkeypatch.setattr(dialog, "_start_preview_worker", lambda *_args: None)

    dialog._accept_mapping()
    dialog._on_confirmation_complete(DesktopPeakTablePreviewReport(preview=preview))
    dialog._preview_finished()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.mapping is not None
    dialog.close()


def test_review_dialog_rejects_source_changed_after_mapping_review(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "changed.csv"
    source.write_text("RT,Peak Area\n1,2\n", encoding="utf-8")
    dialog = PeakMappingDialog(source, auto_preview=False, review_mode=True)
    first = DesktopPeakTablePreview(
        PeakTableFormat.CSV,
        ("RT", "Peak Area"),
        (("1", "2"),),
        source_sha256="1" * 64,
    )
    changed = DesktopPeakTablePreview(
        PeakTableFormat.CSV,
        ("RT", "Peak Area"),
        (("3", "4"),),
        source_sha256="2" * 64,
    )
    dialog.set_preview(first)
    _select(dialog.retention_time_combo, ColumnSelector("RT", 1))
    _select(dialog.area_combo, ColumnSelector("Peak Area", 2))
    dialog.retention_time_unit_edit.setText("min")
    monkeypatch.setattr(dialog, "_start_preview_worker", lambda *_args: None)

    dialog._accept_mapping()
    dialog._on_confirmation_complete(DesktopPeakTablePreviewReport(preview=changed))
    dialog._preview_finished()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.mapping is None
    assert "changed after preview" in dialog.preview_status.text().casefold()
    assert dialog.apply_button.isEnabled()
    dialog.close()


def test_review_preview_worker_reads_the_selected_xlsx_sheet(
    app: QApplication, tmp_path: Path
) -> None:
    del app
    source = tmp_path / "changed.xlsx"
    workbook = openpyxl.Workbook()
    results = workbook.active
    results.title = "Results"
    results.append(("RT", "Peak Area"))
    results.append((1, 2))
    other = workbook.create_sheet("Other")
    other.append(("Unrelated",))
    workbook.save(source)
    worker = PeakTablePreviewWorker(source, PeakTableFormat.XLSX, "Results")
    completed: list[object] = []
    worker.completed.connect(completed.append)

    worker.run()

    assert len(completed) == 1
    report = completed[0]
    assert isinstance(report, DesktopPeakTablePreviewReport)
    assert not report.is_error
    assert report.preview is not None
    assert report.preview.sheet == "Results"
    assert report.preview.headers == ("RT", "Peak Area")


def test_dialog_handles_mapping_construction_failure_without_accepting(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("RT,Area\n1,2\n", encoding="utf-8")
    dialog = PeakMappingDialog(source, auto_preview=False)
    dialog.set_preview(_preview("RT", "Area"))
    _select(dialog.retention_time_combo, ColumnSelector("RT", 1))
    _select(dialog.area_combo, ColumnSelector("Area", 2))
    dialog.retention_time_unit_edit.setText("min")

    def fail_mapping(*_args: object, **_kwargs: object) -> None:
        raise OrdifileError("PEAK_MAPPING_INVALID", "The mapping exceeds its safety limit.")

    monkeypatch.setattr("ordifile.desktop.peak_mapping_dialog.PeakTableMapping", fail_mapping)
    dialog._accept_mapping()

    assert dialog.mapping is None
    assert "PEAK_MAPPING_INVALID" in dialog.validation_label.text()
    assert dialog.isVisible() or dialog.result() == 0
    dialog.close()


def test_bounded_preview_worker_emits_completed_and_finished(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    report = DesktopPeakTablePreviewReport(preview=_preview("RT", "Area"))
    monkeypatch.setattr(
        "ordifile.desktop.workers.preview_peak_table",
        lambda *_args, **_kwargs: report,
    )
    worker = PeakTablePreviewWorker(tmp_path / "input.csv", PeakTableFormat.CSV)
    completed: list[object] = []
    finished: list[bool] = []
    worker.completed.connect(completed.append)
    worker.finished.connect(lambda: finished.append(True))

    worker.run()

    assert completed == [report]
    assert finished == [True]
