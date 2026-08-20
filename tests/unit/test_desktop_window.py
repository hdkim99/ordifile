# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from ordifile import ColumnSelector, PeakTableFormat, PeakTableMapping
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
    status_item = window.input_table.item(0, 3)
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
    central = window.centralWidget()
    assert central is not None
    assert any(
        "Offline" in label.text() for label in central.findChildren(type(window.status_label))
    )
    assert not window.open_output_button.isEnabled()
    assert not window.convert_button.isEnabled()
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
