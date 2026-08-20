# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from ordifile import (
    ColumnSelector,
    PeakMappingDriftCategory,
    PeakMappingDriftDiagnostic,
    PeakTableFormat,
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
)
from ordifile.core.models import BatchOutcome, ProgressEvent
from ordifile.desktop.models import (
    DesktopBatchReport,
    DesktopFileReport,
    DesktopInputStatus,
)
from ordifile.desktop.window import MainWindow, local_paths_from_urls
from ordifile.desktop.workers import ConversionWorker, PreviewWorker


@pytest.fixture(scope="module")
def app() -> QApplication:
    existing = QApplication.instance()
    return cast(QApplication, existing) if existing is not None else QApplication([])


def _mapping(*, unit: str = "min") -> PeakTableMapping:
    return PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        unit,
        PeakTableFormat.CSV,
    )


def _mapping_set(
    mapping: PeakTableMapping | None = None,
    *,
    label: str = "Daily CSV",
) -> PeakTableMappingSet:
    return PeakTableMappingSet((PeakTableMappingProfile(mapping or _mapping(), label),))


def _drift_diagnostic(
    profile: PeakTableMappingProfile,
    *,
    unresolved_required_roles: tuple[str, ...] = ("area",),
) -> PeakMappingDriftDiagnostic:
    return PeakMappingDriftDiagnostic(
        profile_id=profile.profile_id,
        profile_structural_fingerprint=profile.structural_fingerprint_sha256,
        source_format=profile.mapping.source_format,
        categories=(PeakMappingDriftCategory.HEADER_CHANGED_UNRESOLVED,),
        expected_column_count=2,
        observed_column_count=2,
        exact_position_matches=1,
        changed_column_count=1,
        added_column_count=0,
        removed_column_count=0,
        moved_column_count=0,
        total_difference_count=1,
        unresolved_required_roles=unresolved_required_roles,
        unresolved_optional_roles=(),
    )


def _next_expected_widget(current: QWidget, expected: set[QWidget]) -> QWidget:
    candidate = current.nextInFocusChain()
    assert candidate is not None
    while candidate not in expected:
        candidate = candidate.nextInFocusChain()
        assert candidate is not None
        assert candidate is not current
    return candidate


def test_drop_normalization_accepts_files_folders_and_ignores_remote_urls(
    tmp_path: Path,
) -> None:
    file = tmp_path / "input.csv"
    folder = tmp_path / "folder"

    paths = local_paths_from_urls(
        (
            QUrl.fromLocalFile(str(file)),
            QUrl("https://example.invalid/private.csv"),
            QUrl.fromLocalFile(str(folder)),
        )
    )

    assert paths == (file, folder)


def test_drop_normalization_ignores_empty_and_nonlocal_urls() -> None:
    assert local_paths_from_urls((QUrl(), QUrl("mailto:private@example.invalid"))) == ()


def test_drop_normalization_preserves_multiple_local_files(tmp_path: Path) -> None:
    paths = (tmp_path / "first.csv", tmp_path / "second.tsv")

    assert local_paths_from_urls(tuple(QUrl.fromLocalFile(str(path)) for path in paths)) == paths


def test_window_adds_files_and_folder_without_duplicating_inputs(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    file = tmp_path / "input.csv"
    file.write_text("a,b\n1,2\n", encoding="utf-8")
    folder = tmp_path / "folder"
    folder.mkdir()
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)

    window.add_paths((file, folder, file))

    assert window.selected_paths == (file, folder)
    assert window.input_table.rowCount() == 2
    status_item = window.input_table.item(0, 4)
    folder_item = window.input_table.item(1, 1)
    assert status_item is not None and status_item.text() == "Queued"
    assert folder_item is not None and folder_item.text() == "Pending core discovery"
    assert "duplicate" in window.status_label.text()
    window.close()


def test_window_rejects_new_inputs_while_conversion_snapshot_is_active(
    app: QApplication, tmp_path: Path
) -> None:
    del app
    window = MainWindow()
    window._conversion_thread = cast(Any, object())

    assert not window.add_paths((tmp_path / "late.csv",))
    assert window.selected_paths == ()
    assert "Wait" in window.status_label.text()
    window._conversion_thread = None
    window.close()


def test_queued_input_display_removes_controls_and_bidi(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)

    window.add_paths((tmp_path / "line\nbad\u202ename.csv",))

    selected = window.selection_list.item(0)
    queued = window.input_table.item(0, 0)
    assert selected is not None and selected.text() == "line bad name.csv"
    assert queued is not None and queued.text() == "line bad name.csv"
    window.close()


def test_remove_selected_uses_top_level_selection_after_folder_preview_expands(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    first = tmp_path / "first-folder"
    second = tmp_path / "second-folder"
    first.mkdir()
    second.mkdir()
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.add_paths((first, second))
    expanded = DesktopBatchReport(
        BatchOutcome.SUCCESS,
        files=tuple(
            DesktopFileReport(
                f"public-{index}.csv",
                "Generic CSV (Verified)",
                "generic_csv",
                DesktopInputStatus.SUCCESS,
            )
            for index in range(5)
        ),
        success_count=5,
    )
    window._render_report(expanded)
    window.selection_list.setCurrentRow(1)

    window._remove_selected()

    assert window.selected_paths == (first,)
    assert window.selection_list.count() == 1
    window.close()


def test_window_has_keyboard_labels_accessible_names_and_offline_copy(
    app: QApplication,
) -> None:
    del app
    window = MainWindow()

    assert "&" in window.add_files_button.text()
    assert window.input_table.accessibleName() == "Detected input files"
    assert window.sort_combo.accessibleName() == "Sort method"
    assert window.convert_button.accessibleName() == "Convert selected inputs"
    assert window.map_peaks_button.accessibleName() == "Map selected file peak columns"
    assert window.mapping_set_combo.accessibleName() == "Reusable peak mapping profiles"
    assert window.use_mapping_set_checkbox.accessibleName() == ("Use reusable peak mapping set")
    assert window.drift_candidate_combo.accessibleName() == "Mapping schema drift candidates"
    assert window.review_mapping_button.accessibleName() == ("Review selected schema drift mapping")
    central = window.centralWidget()
    assert central is not None
    assert any(
        "Offline" in label.text() for label in central.findChildren(type(window.status_label))
    )
    assert not window.open_output_button.isEnabled()
    assert not window.convert_button.isEnabled()
    window.close()


def test_window_mapping_controls_have_explicit_keyboard_focus_order(app: QApplication) -> None:
    del app
    window = MainWindow()
    expected_order = (
        window.map_peaks_button,
        window.load_mapping_button,
        window.save_mapping_button,
        window.clear_mapping_button,
        window.use_mapping_set_checkbox,
        window.mapping_set_combo,
        window.load_mapping_set_button,
        window.save_mapping_set_button,
        window.add_mapping_profile_button,
        window.rename_mapping_profile_button,
        window.remove_mapping_profile_button,
        window.remove_button,
        window.clear_button,
        window.input_table,
        window.drift_candidate_combo,
        window.review_mapping_button,
        window.sort_combo,
    )
    expected = set(expected_order)

    assert all(
        _next_expected_widget(current, expected) is following
        for current, following in pairwise(expected_order)
    )
    window.close()


def test_mapping_action_is_explicit_and_requires_one_supported_regular_file(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    csv = tmp_path / "result.csv"
    csv.write_text("RT,Area\n1,2\n", encoding="utf-8")
    folder = tmp_path / "folder"
    folder.mkdir()
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)

    window.add_paths((csv,))
    assert window.map_peaks_button.isEnabled()

    window.add_paths((folder,))
    window.selection_list.clearSelection()
    window.selection_list.setCurrentRow(1)
    assert not window.map_peaks_button.isEnabled()

    window.selection_list.setCurrentRow(0)
    assert window.map_peaks_button.isEnabled()
    window.close()


def test_window_loads_saves_and_clears_one_frozen_mapping(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
    )
    mapping_file = tmp_path / "mapping.json"
    saved: list[tuple[PeakTableMapping, Path, bool]] = []
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    monkeypatch.setattr(
        "ordifile.desktop.window.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(mapping_file), ""),
    )
    monkeypatch.setattr("ordifile.desktop.window.load_mapping", lambda _path: mapping)

    window._load_peak_mapping()

    current_mapping = window.peak_table_mapping
    assert current_mapping is mapping
    assert window.save_mapping_button.isEnabled()
    assert "user-supplied" in window.mapping_label.text()

    monkeypatch.setattr(
        "ordifile.desktop.window.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(mapping_file), ""),
    )
    monkeypatch.setattr(
        "ordifile.desktop.window.save_mapping",
        lambda value, path, *, overwrite: saved.append((value, path, overwrite)),
    )
    window._save_peak_mapping()
    assert saved == [(mapping, mapping_file, False)]

    window._clear_peak_mapping()
    assert window.peak_table_mapping is None
    assert window.mapping_label.text().endswith("none")
    window.close()


def test_window_loads_and_saves_one_frozen_mapping_set(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    mapping_set = _mapping_set()
    mapping_file = tmp_path / "mapping-set.json"
    saved: list[tuple[PeakTableMappingSet, Path, bool]] = []
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    monkeypatch.setattr(
        "ordifile.desktop.window.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(mapping_file), ""),
    )
    monkeypatch.setattr(
        "ordifile.desktop.window.load_mapping_set",
        lambda _path: mapping_set,
    )

    window._load_peak_mapping_set()

    assert window.peak_table_mapping_set is mapping_set
    assert window.use_mapping_set_checkbox.isChecked()
    assert window.mapping_set_combo.count() == 1
    assert "Daily CSV" in window.mapping_set_combo.currentText()
    assert window.save_mapping_set_button.isEnabled()

    monkeypatch.setattr(
        "ordifile.desktop.window.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(mapping_file), ""),
    )
    monkeypatch.setattr(
        "ordifile.desktop.window.save_mapping_set",
        lambda value, path, *, overwrite: saved.append((value, path, overwrite)),
    )
    window._save_peak_mapping_set()

    assert saved == [(mapping_set, mapping_file, False)]
    window.close()


def test_window_adds_renames_and_removes_current_mapping_profile(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    answers = iter(("First local profile", "Renamed local profile"))
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    monkeypatch.setattr(
        "ordifile.desktop.window.QInputDialog.getText",
        lambda *_args, **_kwargs: (next(answers), True),
    )
    mapping = _mapping()
    window._set_peak_mapping(mapping)

    window._add_current_mapping_profile()

    added_set = window.peak_table_mapping_set
    assert added_set is not None
    assert window.mapping_set_active
    assert added_set.profiles[0].mapping is mapping
    original_id = added_set.profiles[0].profile_id
    original_set_id = added_set.set_id

    window._rename_mapping_profile()

    renamed_set = window.peak_table_mapping_set
    assert renamed_set is not None
    assert renamed_set.set_id == original_set_id
    assert renamed_set.profiles[0].profile_id == original_id
    assert renamed_set.profiles[0].display_label == "Renamed local profile"

    window._remove_mapping_profile()

    assert window.peak_table_mapping_set is None
    assert not window.use_mapping_set_checkbox.isChecked()
    assert window.peak_table_mapping is mapping
    window.close()


def test_window_mapping_profile_dialog_cancel_keeps_existing_set(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    mapping_set = _mapping_set()
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window._set_peak_mapping(_mapping(unit="s"))
    window._set_peak_mapping_set(mapping_set, activate=True)
    monkeypatch.setattr(
        "ordifile.desktop.window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Discarded", False),
    )

    window._add_current_mapping_profile()
    window._rename_mapping_profile()

    assert window.peak_table_mapping_set is mapping_set
    assert window.mapping_set_active
    window.close()


def test_window_active_mapping_modes_are_mutually_exclusive(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    mapping = _mapping()
    mapping_set = _mapping_set(mapping)
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window._set_peak_mapping(mapping)
    assert window._active_peak_mappings() == (mapping, None)

    window._set_peak_mapping_set(mapping_set, activate=True)

    assert window._active_peak_mappings() == (None, mapping_set)
    window.use_mapping_set_checkbox.setChecked(False)
    assert window._active_peak_mappings() == (mapping, None)
    window.close()


def test_window_route_display_uses_public_route_and_local_profile_label(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    mapping_set = _mapping_set(label="Daily CSV")
    profile = mapping_set.profiles[0]
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window._set_peak_mapping_set(mapping_set, activate=True)
    report = DesktopBatchReport(
        BatchOutcome.SUCCESS,
        files=(
            DesktopFileReport(
                "mapped.csv",
                "Generic CSV (Verified)",
                "generic_csv",
                DesktopInputStatus.SUCCESS,
                mapping_route="USER_MAPPING_PROFILE",
                mapping_profile_id=profile.profile_id,
            ),
            DesktopFileReport(
                "exact.txt",
                "LECO exact profile (Experimental)",
                "leco_chromatof_gcxgc_result_txt",
                DesktopInputStatus.WARNING,
                mapping_route="EXACT_ADAPTER",
            ),
        ),
        success_count=2,
    )

    window._render_report(report)

    mapped_route = window.input_table.item(0, 3)
    exact_route = window.input_table.item(1, 3)
    assert mapped_route is not None and mapped_route.text() == "User mapping: Daily CSV"
    assert exact_route is not None and exact_route.text() == "Exact adapter"
    window.close()


def test_window_requires_explicit_drift_candidate_selection(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "changed.csv"
    source.write_text("RT,Peak Area\n1,2\n", encoding="utf-8")
    first = PeakTableMappingProfile(
        _mapping(),
        "First",
        profile_id="profile-11111111111111111111111111111111",
    )
    second = PeakTableMappingProfile(
        _mapping(unit="s"),
        "Second",
        profile_id="profile-22222222222222222222222222222222",
    )
    mapping_set = PeakTableMappingSet((first, second))
    diagnostics = (_drift_diagnostic(first), _drift_diagnostic(second))
    report_file = DesktopFileReport(
        "source-public",
        "Not detected",
        "—",
        DesktopInputStatus.FAILED,
        mapping_route="SCHEMA_DRIFT_CANDIDATE",
        mapping_diagnostics=diagnostics,
        review_input_index=0,
    )
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.add_paths((source,))
    window._set_peak_mapping_set(mapping_set, activate=True)
    window._displayed_files = (report_file,)
    window._displayed_inputs = window.selected_paths
    window._displayed_mapping_set = mapping_set
    window._render_report(DesktopBatchReport(BatchOutcome.FAILED, files=(report_file,)))

    window.input_table.selectRow(0)

    route = window.input_table.item(0, 3)
    assert route is not None and route.text() == "Schema changed — review required"
    assert window.drift_candidate_combo.count() == 3
    assert window.drift_candidate_combo.currentData() is None
    assert not window.review_mapping_button.isEnabled()
    assert "Choose one" in window.mapping_drift_label.text()

    window.drift_candidate_combo.setCurrentIndex(2)

    assert window.review_mapping_button.isEnabled()
    assert "Unresolved required roles: area" in window.mapping_drift_label.text()
    window.close()


def test_window_review_saves_a_new_profile_without_replacing_candidate(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "changed.csv"
    source.write_text("RT,Peak Area\n1,2\n", encoding="utf-8")
    mapping_set = _mapping_set(label="Original")
    original = mapping_set.profiles[0]
    diagnostic = _drift_diagnostic(original)
    report_file = DesktopFileReport(
        "source-public",
        "Not detected",
        "—",
        DesktopInputStatus.FAILED,
        mapping_route="SCHEMA_DRIFT_CANDIDATE",
        mapping_diagnostics=(diagnostic,),
        review_input_index=0,
        source_sha256="1" * 64,
    )
    repaired_mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Peak Area", 2),
        "min",
        PeakTableFormat.CSV,
    )
    dialog_calls: list[dict[str, object]] = []

    class AcceptedReviewDialog:
        mapping = repaired_mapping
        preview_worksheet_title = None
        preview_source_sha256 = "1" * 64

        def __init__(self, _source: Path, **kwargs: object) -> None:
            dialog_calls.append(kwargs)

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    monkeypatch.setattr("ordifile.desktop.window.PeakMappingDialog", AcceptedReviewDialog)
    monkeypatch.setattr(
        "ordifile.desktop.window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Repaired", True),
    )
    window.add_paths((source,))
    window._set_peak_mapping_set(mapping_set, activate=True)
    window._displayed_files = (report_file,)
    window._displayed_inputs = window.selected_paths
    window._displayed_mapping_set = mapping_set
    window._render_report(DesktopBatchReport(BatchOutcome.FAILED, files=(report_file,)))
    window.input_table.selectRow(0)
    window.drift_candidate_combo.setCurrentIndex(1)

    window._review_mapping()

    updated = window.peak_table_mapping_set
    assert updated is not None
    assert updated.set_id == mapping_set.set_id
    assert len(updated.profiles) == 2
    assert updated.profiles[0] is original
    assert updated.profiles[1].profile_id != original.profile_id
    assert updated.profiles[1].mapping == repaired_mapping
    assert updated.profiles[1].display_label == "Repaired"
    assert dialog_calls[0]["mapping"] is original.mapping
    assert dialog_calls[0]["review_mode"] is True
    assert "new profile" in window.status_label.text()
    window.close()


def test_window_repaired_xlsx_profile_uses_reviewed_worksheet_title(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "changed.xlsx"
    source.write_bytes(b"local test placeholder")
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.XLSX,
    )
    original = PeakTableMappingProfile(mapping, "Workbook", worksheet_title="Old Sheet")
    mapping_set = PeakTableMappingSet((original,))
    diagnostic = _drift_diagnostic(original)
    report_file = DesktopFileReport(
        "source-public",
        "Not detected",
        "—",
        DesktopInputStatus.FAILED,
        mapping_route="SCHEMA_DRIFT_CANDIDATE",
        mapping_diagnostics=(diagnostic,),
        review_input_index=0,
        source_sha256="2" * 64,
    )
    reviewed_mapping = mapping
    dialog_calls: list[dict[str, object]] = []

    class AcceptedXlsxReviewDialog:
        mapping = reviewed_mapping
        preview_worksheet_title = "Reviewed Sheet"
        preview_source_sha256 = "2" * 64

        def __init__(self, _source: Path, **kwargs: object) -> None:
            dialog_calls.append(kwargs)

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    monkeypatch.setattr(
        "ordifile.desktop.window.PeakMappingDialog",
        AcceptedXlsxReviewDialog,
    )
    monkeypatch.setattr(
        "ordifile.desktop.window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Repaired workbook", True),
    )
    window.add_paths((source,))
    window._set_peak_mapping_set(mapping_set, activate=True)
    window._displayed_files = (report_file,)
    window._displayed_inputs = window.selected_paths
    window._displayed_mapping_set = mapping_set
    window._render_report(DesktopBatchReport(BatchOutcome.FAILED, files=(report_file,)))
    window.input_table.selectRow(0)
    window.drift_candidate_combo.setCurrentIndex(1)

    window._review_mapping()

    updated = window.peak_table_mapping_set
    assert updated is not None
    assert updated.profiles[-1].worksheet_title == "Reviewed Sheet"
    assert dialog_calls[0]["sheet"] == "Old Sheet"
    window.close()


def test_window_repair_rejects_a_source_changed_after_inspection(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "changed.csv"
    source.write_text("RT,Peak Area\n1,2\n", encoding="utf-8")
    mapping_set = _mapping_set()
    original = mapping_set.profiles[0]
    diagnostic = _drift_diagnostic(original)
    report_file = DesktopFileReport(
        "source-public",
        "Not detected",
        "—",
        DesktopInputStatus.FAILED,
        mapping_route="SCHEMA_DRIFT_CANDIDATE",
        mapping_diagnostics=(diagnostic,),
        review_input_index=0,
        source_sha256="1" * 64,
    )

    class ChangedSourceReviewDialog:
        mapping = PeakTableMapping(
            ColumnSelector("RT", 1),
            ColumnSelector("Peak Area", 2),
            "min",
            PeakTableFormat.CSV,
        )
        preview_worksheet_title = None
        preview_source_sha256 = "2" * 64

        def __init__(self, _source: Path, **_kwargs: object) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    monkeypatch.setattr(
        "ordifile.desktop.window.PeakMappingDialog",
        ChangedSourceReviewDialog,
    )
    monkeypatch.setattr(
        "ordifile.desktop.window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Repaired", True),
    )
    window.add_paths((source,))
    window._set_peak_mapping_set(mapping_set, activate=True)
    window._displayed_files = (report_file,)
    window._displayed_inputs = window.selected_paths
    window._displayed_mapping_set = mapping_set
    window._render_report(DesktopBatchReport(BatchOutcome.FAILED, files=(report_file,)))
    window.input_table.selectRow(0)
    window.drift_candidate_combo.setCurrentIndex(1)

    window._review_mapping()

    assert window.peak_table_mapping_set is mapping_set
    assert "source changed" in window.status_label.text().casefold()
    window.close()


def test_window_review_cancel_does_not_mutate_mapping_set(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "changed.csv"
    source.write_text("RT,Peak Area\n1,2\n", encoding="utf-8")
    mapping_set = _mapping_set()
    diagnostic = _drift_diagnostic(mapping_set.profiles[0])
    report_file = DesktopFileReport(
        "source-public",
        "Not detected",
        "—",
        DesktopInputStatus.FAILED,
        mapping_route="SCHEMA_DRIFT_CANDIDATE",
        mapping_diagnostics=(diagnostic,),
        review_input_index=0,
    )

    class CancelledReviewDialog:
        mapping = None

        def __init__(self, _source: Path, **_kwargs: object) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Rejected

    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    monkeypatch.setattr("ordifile.desktop.window.PeakMappingDialog", CancelledReviewDialog)
    monkeypatch.setattr(
        "ordifile.desktop.window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Unused repaired label", True),
    )
    window.add_paths((source,))
    window._set_peak_mapping_set(mapping_set, activate=True)
    window._displayed_files = (report_file,)
    window._displayed_inputs = window.selected_paths
    window._displayed_mapping_set = mapping_set
    window._render_report(DesktopBatchReport(BatchOutcome.FAILED, files=(report_file,)))
    window.input_table.selectRow(0)
    window.drift_candidate_combo.setCurrentIndex(1)

    window._review_mapping()

    assert window.peak_table_mapping_set is mapping_set
    window.close()


def test_window_stale_mapping_set_disables_drift_review(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "changed.csv"
    source.write_text("RT,Peak Area\n1,2\n", encoding="utf-8")
    first = _mapping_set(label="First")
    second = _mapping_set(_mapping(unit="s"), label="Second")
    diagnostic = _drift_diagnostic(first.profiles[0])
    report_file = DesktopFileReport(
        "source-public",
        "Not detected",
        "—",
        DesktopInputStatus.FAILED,
        mapping_route="SCHEMA_DRIFT_CANDIDATE",
        mapping_diagnostics=(diagnostic,),
        review_input_index=0,
    )
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.add_paths((source,))
    window._set_peak_mapping_set(first, activate=True)
    window._displayed_files = (report_file,)
    window._displayed_inputs = window.selected_paths
    window._displayed_mapping_set = first
    window._render_report(DesktopBatchReport(BatchOutcome.FAILED, files=(report_file,)))
    window.input_table.selectRow(0)
    window._peak_table_mapping_set = second

    window._mapping_drift_row_changed()

    assert not window.drift_candidate_combo.isEnabled()
    assert not window.review_mapping_button.isEnabled()
    window.close()


def test_window_mapping_combo_distinguishes_duplicate_local_labels(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    first = PeakTableMappingProfile(
        _mapping(),
        "Daily result",
        profile_id="profile-11111111111111111111111111aaaaaa",
    )
    second_mapping = PeakTableMapping(
        ColumnSelector("Time", 1),
        ColumnSelector("Integrated", 2),
        "min",
        PeakTableFormat.CSV,
    )
    second = PeakTableMappingProfile(
        second_mapping,
        "Daily result",
        profile_id="profile-22222222222222222222222222bbbbbb",
    )
    mapping_set = PeakTableMappingSet((first, second))
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)

    window._set_peak_mapping_set(mapping_set, activate=True)

    assert window.mapping_set_combo.itemText(0).endswith("[aaaaaa]")
    assert window.mapping_set_combo.itemText(1).endswith("[bbbbbb]")
    assert window.mapping_set_combo.itemText(0) != window.mapping_set_combo.itemText(1)
    window.close()


def test_stale_preview_does_not_replace_rows_after_mapping_changes(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("RT,Area\n1,2\n", encoding="utf-8")
    first = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
    )
    second = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "s",
        PeakTableFormat.CSV,
    )
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.add_paths((source,))
    window._peak_table_mapping = first
    window._preview_inputs = window.selected_paths
    window._preview_mapping = first
    window._peak_table_mapping = second
    stale = DesktopBatchReport(
        BatchOutcome.SUCCESS,
        files=(
            DesktopFileReport(
                "stale.csv",
                "Generic CSV (Verified)",
                "generic_csv",
                DesktopInputStatus.SUCCESS,
            ),
        ),
        success_count=1,
    )

    window._on_preview_complete(stale)

    queued = window.input_table.item(0, 0)
    assert queued is not None and queued.text() != "stale.csv"
    window.close()


def test_stale_preview_does_not_replace_rows_after_mapping_set_changes(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "result.csv"
    first = _mapping_set(_mapping(unit="min"), label="First")
    second = _mapping_set(_mapping(unit="s"), label="Second")
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.add_paths((source,))
    window._set_peak_mapping_set(first, activate=True)
    window._preview_inputs = window.selected_paths
    window._preview_mapping = None
    window._preview_mapping_set = first
    window._set_peak_mapping_set(second, activate=True)
    stale = DesktopBatchReport(
        BatchOutcome.SUCCESS,
        files=(
            DesktopFileReport(
                "stale.csv",
                "Generic CSV (Verified)",
                "generic_csv",
                DesktopInputStatus.SUCCESS,
                mapping_route="USER_MAPPING_PROFILE",
                mapping_profile_id=first.profiles[0].profile_id,
            ),
        ),
        success_count=1,
    )

    window._on_preview_complete(stale)

    queued = window.input_table.item(0, 0)
    assert queued is not None and queued.text() != "stale.csv"
    window.close()


def test_stale_preview_does_not_replace_rows_after_selection_changes(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.add_paths((first,))
    window._preview_inputs = window.selected_paths
    window.add_paths((second,))
    stale = DesktopBatchReport(
        BatchOutcome.SUCCESS,
        files=(
            DesktopFileReport(
                "stale.csv",
                "Generic CSV (Verified)",
                "generic_csv",
                DesktopInputStatus.SUCCESS,
            ),
        ),
        success_count=1,
    )

    window._on_preview_complete(stale)

    assert window.input_table.rowCount() == 2
    first_item = window.input_table.item(0, 0)
    assert first_item is not None and first_item.text() != "stale.csv"
    window.close()


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (BatchOutcome.SUCCESS, "Conversion complete"),
        (BatchOutcome.PARTIAL_SUCCESS, "partial success"),
        (BatchOutcome.FAILED, "No files converted successfully"),
    ],
)
def test_window_distinguishes_conversion_outcomes(
    app: QApplication, tmp_path: Path, outcome: BatchOutcome, expected: str
) -> None:
    del app
    output = tmp_path / "result.xlsx"
    output.write_bytes(b"xlsx")
    successes = 0 if outcome is BatchOutcome.FAILED else 1
    failures = 1 if outcome is not BatchOutcome.SUCCESS else 0
    report = DesktopBatchReport(
        outcome,
        files=(
            DesktopFileReport(
                "public.csv", "Generic CSV (Verified)", "generic_csv", DesktopInputStatus.SUCCESS
            ),
        ),
        success_count=successes,
        failure_count=failures,
        output_path=output,
    )
    window = MainWindow()

    window._on_conversion_complete(report)

    assert expected in window.status_label.text()
    assert window.open_output_button.isEnabled()
    window.close()


def test_window_shows_structured_fatal_error_without_traceback(app: QApplication) -> None:
    del app
    window = MainWindow()
    report = DesktopBatchReport(
        BatchOutcome.FAILED,
        error_code="OUTPUT_EXISTS",
        error_message="Output already exists.",
    )

    window._on_conversion_complete(report)

    assert "[OUTPUT_EXISTS]" in window.status_label.text()
    assert "Traceback" not in window.details.toPlainText()
    window.close()


def test_window_progress_uses_existing_public_stages(app: QApplication) -> None:
    del app
    window = MainWindow()

    window._show_progress(ProgressEvent("processing", 2, 3), inspecting=False)
    assert window.progress_bar.maximum() == 3
    assert window.progress_bar.value() == 2
    assert "Converting files" in window.status_label.text()

    window._show_progress(ProgressEvent("export_start", 0, 1), inspecting=False)
    assert "Writing workbook" in window.status_label.text()
    window.close()


def test_conversion_disables_mapping_set_controls(app: QApplication) -> None:
    del app
    window = MainWindow()
    window._peak_table_mapping = _mapping()
    window._peak_table_mapping_set = _mapping_set()
    window.use_mapping_set_checkbox.setChecked(True)
    window._update_mapping_controls()

    window._set_conversion_controls(False)

    assert not window.use_mapping_set_checkbox.isEnabled()
    assert not window.mapping_set_combo.isEnabled()
    assert not window.load_mapping_set_button.isEnabled()
    assert not window.save_mapping_set_button.isEnabled()
    assert not window.add_mapping_profile_button.isEnabled()
    assert not window.rename_mapping_profile_button.isEnabled()
    assert not window.remove_mapping_profile_button.isEnabled()
    assert not window.drift_candidate_combo.isEnabled()
    assert not window.review_mapping_button.isEnabled()
    window.close()


def test_open_output_uses_local_desktop_service(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    output = tmp_path / "result.xlsx"
    output.write_bytes(b"xlsx")
    opened: list[QUrl] = []

    def open_url(url: QUrl) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr(QDesktopServices, "openUrl", open_url)
    window = MainWindow()
    window._last_output = output

    window._open_output()

    assert len(opened) == 1
    assert opened[0].isLocalFile()
    assert Path(opened[0].toLocalFile()) == output
    window.close()


@pytest.mark.parametrize("worker_type", [PreviewWorker, ConversionWorker])
def test_workers_always_emit_completed_and_finished(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worker_type: type[PreviewWorker] | type[ConversionWorker],
) -> None:
    del app
    report = DesktopBatchReport(BatchOutcome.SUCCESS)
    if worker_type is PreviewWorker:
        monkeypatch.setattr("ordifile.desktop.workers.inspect_selection", lambda *_a, **_k: report)
        worker: Any = PreviewWorker((tmp_path,), "auto")
    else:
        monkeypatch.setattr("ordifile.desktop.workers.convert_selection", lambda *_a, **_k: report)
        from ordifile.desktop.models import DesktopRequest

        worker = ConversionWorker(DesktopRequest((tmp_path,), tmp_path / "output.xlsx"))
    completed: list[object] = []
    finished: list[bool] = []
    worker.completed.connect(completed.append)
    worker.finished.connect(lambda: finished.append(True))

    worker.run()

    assert completed == [report]
    assert finished == [True]


def test_preview_worker_forwards_one_frozen_mapping_set_snapshot(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del app
    mapping_set = _mapping_set()
    captured: list[tuple[object, object]] = []

    def inspect(*_args: object, **kwargs: object) -> DesktopBatchReport:
        captured.append((kwargs.get("peak_table_mapping"), kwargs.get("peak_table_mapping_set")))
        return DesktopBatchReport(BatchOutcome.SUCCESS)

    monkeypatch.setattr("ordifile.desktop.workers.inspect_selection", inspect)
    worker = PreviewWorker((tmp_path / "input.csv",), "auto", None, mapping_set)

    worker.run()

    assert captured == [(None, mapping_set)]


@pytest.mark.parametrize("worker_type", [PreviewWorker, ConversionWorker])
def test_workers_convert_base_exceptions_to_fixed_reports(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worker_type: type[PreviewWorker] | type[ConversionWorker],
) -> None:
    del app

    def stop(*_args: object, **_kwargs: object) -> DesktopBatchReport:
        raise SystemExit("private scientific filename")

    if worker_type is PreviewWorker:
        monkeypatch.setattr("ordifile.desktop.workers.inspect_selection", stop)
        worker: Any = PreviewWorker((tmp_path,), "auto")
    else:
        monkeypatch.setattr("ordifile.desktop.workers.convert_selection", stop)
        from ordifile.desktop.models import DesktopRequest

        worker = ConversionWorker(DesktopRequest((tmp_path,), tmp_path / "output.xlsx"))
    completed: list[object] = []
    finished: list[bool] = []
    worker.completed.connect(completed.append)
    worker.finished.connect(lambda: finished.append(True))

    worker.run()

    assert len(completed) == 1
    failure = completed[0]
    assert isinstance(failure, DesktopBatchReport)
    assert failure.error_code == "DESKTOP_WORKER_FAILED"
    assert "private" not in (failure.error_message or "")
    assert finished == [True]
