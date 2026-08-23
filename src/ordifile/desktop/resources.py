# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Private package-resource helpers for the optional desktop interface."""

from __future__ import annotations

from importlib.resources import files
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QIcon

_APPLICATION_ICON = ("assets", "ordifile-icon-512.png")


def _read_application_icon() -> bytes | None:
    resource = files("ordifile.desktop")
    for component in _APPLICATION_ICON:
        resource = resource.joinpath(component)
    try:
        return resource.read_bytes()
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
