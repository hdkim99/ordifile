# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Application bootstrap for the optional Qt desktop interface."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

MISSING_GUI_EXIT = 2
MISSING_GUI_MESSAGE = (
    "Ordifile desktop requires the optional GUI package. "
    "Install it with: pip install 'ordifile[gui]'"
)


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Return the existing Qt application or create one without network services."""
    from PySide6.QtWidgets import QApplication

    existing = QApplication.instance()
    if existing is not None:
        return cast(QApplication, existing)
    return QApplication(list(sys.argv if argv is None else argv))


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the offline desktop window."""
    try:
        app = create_application(argv)
        from ordifile.desktop.window import MainWindow
    except ModuleNotFoundError as error:
        if error.name is None or not error.name.startswith("PySide6"):
            raise
        print(MISSING_GUI_MESSAGE, file=sys.stderr)
        return MISSING_GUI_EXIT
    window = MainWindow()
    window.show()
    return app.exec()
