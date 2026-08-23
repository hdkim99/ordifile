# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest
from PySide6.QtGui import QIcon

from ordifile.desktop import resources
from ordifile.desktop.app import create_application
from ordifile.desktop.window import MainWindow


def test_runtime_icon_loads_at_required_qt_sizes() -> None:
    create_application([])
    icon = resources.load_application_icon()
    assert icon is not None
    assert not icon.isNull()
    for size in (16, 32, 64):
        pixmap = icon.pixmap(size, size)
        assert not pixmap.isNull()
        assert pixmap.width() == size
        assert pixmap.height() == size


def test_application_icon_is_inherited_by_the_main_window() -> None:
    application = create_application([])
    window = MainWindow()
    assert not application.windowIcon().isNull()
    assert not window.windowIcon().isNull()
    window.close()


def test_missing_or_corrupt_runtime_icon_is_nonfatal(monkeypatch: pytest.MonkeyPatch) -> None:
    application = create_application([])
    application.setWindowIcon(QIcon())
    monkeypatch.setattr(resources, "_read_application_icon", lambda: None)
    assert create_application([]).windowIcon().isNull()
    monkeypatch.setattr(resources, "_read_application_icon", lambda: b"not a png")
    assert resources.load_application_icon() is None


def test_standalone_runtime_icon_is_used_when_package_data_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_application([])
    standalone = tmp_path / "ordifile-icon.png"
    standalone.write_bytes(
        (files("ordifile.desktop") / "assets" / "ordifile-icon-512.png").read_bytes()
    )
    monkeypatch.setattr(resources, "_read_packaged_application_icon", lambda: None)
    monkeypatch.setattr(resources, "_standalone_application_icon_path", lambda: standalone)
    icon = resources.load_application_icon()
    assert icon is not None
    assert not icon.isNull()
