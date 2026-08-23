# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Private package-resource helpers for the optional desktop interface."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QIcon

_APPLICATION_ICON = ("assets", "ordifile-icon-512.png")
_STANDALONE_APPLICATION_ICON = "ordifile-icon.png"


def _read_packaged_application_icon() -> bytes | None:
    try:
        resource = files("ordifile.desktop")
        for component in _APPLICATION_ICON:
            resource = resource.joinpath(component)
        return resource.read_bytes()
    except (OSError, TypeError):
        return None


def _standalone_application_icon_path() -> Path | None:
    from PySide6.QtCore import QCoreApplication

    directory = QCoreApplication.applicationDirPath()
    return Path(directory) / _STANDALONE_APPLICATION_ICON if directory else None


def _read_application_icon() -> bytes | None:
    packaged = _read_packaged_application_icon()
    if packaged is not None:
        return packaged
    standalone = _standalone_application_icon_path()
    if standalone is None:
        return None
    try:
        return standalone.read_bytes()
    except OSError:
        return None


def load_application_icon() -> QIcon | None:
    """Load the project-owned icon without depending on an extracted resource path."""
    from PySide6.QtGui import QIcon, QPixmap

    content = _read_application_icon()
    if content is None:
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(content):
        return None
    icon = QIcon(pixmap)
    return None if icon.isNull() else icon
