# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from dataclasses import replace
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
    ConversionPlanProblem,
    PeakMappingDriftCategory,
    PeakMappingDriftDiagnostic,
    PeakTableFormat,
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
    PlanProgressEvent,
)
from ordifile.api import plan_conversion
from ordifile.core.models import BatchOutcome, ProgressEvent
from ordifile.desktop.models import (
    DesktopBatchReport,
    DesktopFileReport,
    DesktopInputStatus,
    DesktopRequest,
)
from ordifile.desktop.services import preflight_selection
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


def _install_current_preflight(
    window: MainWindow,
    report_file: DesktopFileReport,
    mapping_set: PeakTableMappingSet,
) -> DesktopFileReport:
    request = window._current_preflight_request()
    plan = plan_conversion(
        request.inputs,
        request.output,
        sort=request.sort,
        peak_table_mapping_set=mapping_set,
        on_error="continue",
    )
    current_file = replace(
        report_file,
        source_sha256=plan.entries[0].sha256,
        plan_problem=ConversionPlanProblem.MAPPING_SCHEMA_DRIFT,
    )
    window._displayed_files = (current_file,)
    window._displayed_inputs = window.selected_paths
    window._displayed_mapping_set = mapping_set
    window._displayed_plan = plan
    window._displayed_request = request
    window._displayed_generation = window._preflight_generation
    window._render_report(DesktopBatchReport(BatchOutcome.FAILED, files=(current_file,)))
    return current_file


def _complete_current_preflight(window: MainWindow) -> DesktopBatchReport:
    request = window._current_preflight_request()
    report = preflight_selection(request)
    window._preview_request = request
    window._preview_generation = window._preflight_generation
    window._on_preview_complete(report)
    return report


def _table_text(window: MainWindow, row: int, column: int) -> str:
    item = window.input_table.item(row, column)
    assert item is not None
    return item.text()


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
    status_item = window.input_table.item(0, 5)
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
    assert window.input_table.accessibleName() == "Conversion preflight inputs"
    assert window.sort_combo.accessibleName() == "Sort method"
    assert window.convert_button.accessibleName() == "Convert selected inputs"
    assert window.map_peaks_button.accessibleName() == "Map selected file peak columns"
    assert window.mapping_set_combo.accessibleName() == "Reusable peak mapping profiles"
    assert window.use_mapping_set_checkbox.accessibleName() == ("Use reusable peak mapping set")
    assert window.drift_candidate_combo.accessibleName() == "Mapping schema drift candidates"
    assert window.review_mapping_button.accessibleName() == ("Review selected schema drift mapping")
    assert window.refresh_preflight_button.accessibleName() == "Refresh conversion preflight"
    assert window.preflight_summary_label.accessibleName() == "Conversion preflight summary"
    central = window.centralWidget()
    assert central is not None
    assert any(
        "Offline" in label.text() for label in central.findChildren(type(window.status_label))
    )
    assert not window.open_output_button.isEnabled()
    assert not window.convert_button.isEnabled()
    window.close()


def test_preflight_summary_routes_actions_and_enables_current_executable_plan(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "local-private.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.output_edit.setText(str(tmp_path / "result.xlsx"))
    window.add_paths((source,))

    report = _complete_current_preflight(window)

    assert report.plan is window._current_plan()
    assert window.convert_button.isEnabled()
    assert window.refresh_preflight_button.isEnabled()
    assert "1 routable" in window.preflight_summary_label.text()
    assert _table_text(window, 0, 3) == "Generic input"
    assert _table_text(window, 0, 4) == "Convert"
    assert _table_text(window, 0, 5) == "Routable"
    assert source.name not in _table_text(window, 0, 0)
    window.close()


def test_preflight_known_failures_remain_visible_and_executable(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    valid = tmp_path / "valid.csv"
    valid.write_text("sample_id,area\na,1\n", encoding="utf-8")
    unsupported = tmp_path / "unsupported.bin"
    unsupported.write_bytes(b"unsupported")
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.output_edit.setText(str(tmp_path / "result.xlsx"))
    window.add_paths((valid, unsupported))

    report = _complete_current_preflight(window)

    assert report.plan is not None and report.plan.is_executable
    assert window.convert_button.isEnabled()
    assert "1 failed" in window.preflight_summary_label.text()
    assert "known failures" in window.convert_button.accessibleName()
    assert _table_text(window, 1, 4) == "Unsupported"
    window.close()


def test_blocked_output_plan_disables_conversion(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "valid.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    output = tmp_path / "result.xlsx"
    output.write_bytes(b"existing")
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.output_edit.setText(str(output))
    window.add_paths((source,))

    report = _complete_current_preflight(window)

    assert report.plan is not None and not report.plan.is_executable
    assert not window.convert_button.isEnabled()
    assert "Blocked" in window.preflight_summary_label.text()
    assert "OUTPUT_EXISTS" in window.preflight_summary_label.text()
    assert _table_text(window, 0, 4) == "Choose another output"
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
        window.refresh_preflight_button,
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
    _install_current_preflight(window, report_file, mapping_set)

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
    current_file = _install_current_preflight(window, report_file, mapping_set)
    assert current_file.source_sha256 is not None
    AcceptedReviewDialog.preview_source_sha256 = current_file.source_sha256
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
    current_file = _install_current_preflight(window, report_file, mapping_set)
    assert current_file.source_sha256 is not None
    AcceptedXlsxReviewDialog.preview_source_sha256 = current_file.source_sha256
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
    _install_current_preflight(window, report_file, mapping_set)
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
    _install_current_preflight(window, report_file, mapping_set)
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
    _install_current_preflight(window, report_file, first)
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


@pytest.mark.parametrize("change", ["input", "sort", "output", "mapping_set"])
def test_preflight_config_changes_invalidate_plan_and_disable_conversion(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.output_edit.setText(str(tmp_path / "result.xlsx"))
    window.add_paths((source,))
    _complete_current_preflight(window)
    assert window.convert_button.isEnabled()
    monkeypatch.setattr(window, "_start_preview", lambda: None)

    if change == "input":
        added = tmp_path / "added.csv"
        added.write_text("sample_id,area\nb,2\n", encoding="utf-8")
        window.add_paths((added,))
    elif change == "sort":
        window.sort_combo.blockSignals(True)
        window.sort_combo.setCurrentIndex(1)
        window.sort_combo.blockSignals(False)
    elif change == "output":
        window.output_edit.blockSignals(True)
        window.output_edit.setText(str(tmp_path / "changed.xlsx"))
        window.output_edit.blockSignals(False)
    else:
        window._set_peak_mapping_set(_mapping_set(), activate=True)
    MainWindow._request_preview(window)

    assert window._current_plan() is None
    assert not window.convert_button.isEnabled()
    assert "pending" in window.preflight_summary_label.text().casefold()
    window.close()


def test_stale_preflight_generation_cannot_replace_current_rows(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "result.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.output_edit.setText(str(tmp_path / "result.xlsx"))
    window.add_paths((source,))
    request = window._current_preflight_request()
    stale = preflight_selection(request)
    window._preview_request = request
    window._preview_generation = window._preflight_generation
    window._invalidate_preflight("New configuration pending.")

    window._on_preview_complete(stale)

    queued = window.input_table.item(0, 0)
    assert queued is not None and queued.text() == source.name
    assert window._current_plan() is None
    assert not window.convert_button.isEnabled()
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
    window._preview_request = window._current_preflight_request()
    window._preview_generation = window._preflight_generation
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
    window._preview_request = window._current_preflight_request()
    window._preview_generation = window._preflight_generation
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
    window._preview_request = window._current_preflight_request()
    window._preview_generation = window._preflight_generation
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


def test_window_progress_reports_public_preflight_stages(app: QApplication) -> None:
    del app
    window = MainWindow()

    window._on_preview_progress(PlanProgressEvent("planning_routing", 2, 3))

    assert window.progress_bar.maximum() == 3
    assert window.progress_bar.value() == 2
    assert "Planning conversion routes" in window.status_label.text()
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
    assert not window.refresh_preflight_button.isEnabled()
    window.close()


def test_active_preflight_disables_refresh_and_conversion(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    source = tmp_path / "input.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    window = MainWindow()
    monkeypatch.setattr(window, "_request_preview", lambda *_args: None)
    window.output_edit.setText(str(tmp_path / "result.xlsx"))
    window.add_paths((source,))
    _complete_current_preflight(window)
    assert window.convert_button.isEnabled()

    window._preview_thread = cast(Any, object())
    window._update_mapping_controls()

    assert not window.refresh_preflight_button.isEnabled()
    assert not window.convert_button.isEnabled()
    window._preview_thread = None
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
    source = tmp_path / "input.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    request = DesktopRequest((source,), tmp_path / "output.xlsx")
    if worker_type is PreviewWorker:
        monkeypatch.setattr(
            "ordifile.desktop.workers.preflight_selection", lambda *_a, **_k: report
        )
        worker: Any = PreviewWorker(request)
    else:
        plan = plan_conversion(source, request.output)
        monkeypatch.setattr(
            "ordifile.desktop.workers.convert_preflight_plan", lambda *_a, **_k: report
        )
        worker = ConversionWorker(plan)
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
    captured: list[DesktopRequest] = []
    source = tmp_path / "input.csv"
    source.write_text("RT,Area\n1,2\n", encoding="utf-8")
    request = DesktopRequest(
        (source,),
        tmp_path / "output.xlsx",
        peak_table_mapping_set=mapping_set,
    )

    def preflight(captured_request: DesktopRequest, **_kwargs: object) -> DesktopBatchReport:
        captured.append(captured_request)
        return DesktopBatchReport(BatchOutcome.SUCCESS)

    monkeypatch.setattr("ordifile.desktop.workers.preflight_selection", preflight)
    worker = PreviewWorker(request)

    worker.run()

    assert captured == [request]
    assert captured[0].peak_table_mapping is None
    assert captured[0].peak_table_mapping_set is mapping_set


def test_conversion_worker_forwards_the_exact_preflight_plan(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del app
    source = tmp_path / "input.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    plan = plan_conversion(source, tmp_path / "output.xlsx")
    report = DesktopBatchReport(BatchOutcome.SUCCESS)
    captured: list[object] = []

    def convert(candidate: object, **_kwargs: object) -> DesktopBatchReport:
        captured.append(candidate)
        return report

    monkeypatch.setattr("ordifile.desktop.workers.convert_preflight_plan", convert)
    worker = ConversionWorker(plan)

    worker.run()

    assert captured == [plan]
    assert captured[0] is plan


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

    source = tmp_path / "input.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    request = DesktopRequest((source,), tmp_path / "output.xlsx")
    if worker_type is PreviewWorker:
        monkeypatch.setattr("ordifile.desktop.workers.preflight_selection", stop)
        worker: Any = PreviewWorker(request)
    else:
        plan = plan_conversion(source, request.output)
        monkeypatch.setattr("ordifile.desktop.workers.convert_preflight_plan", stop)
        worker = ConversionWorker(plan)
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
