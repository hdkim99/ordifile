# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Repository-wide pytest setup with a stable macOS Qt offscreen plugin."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

_QT_TEST_PLUGIN_ROOT: Path | None = None


def _is_macos() -> bool:
    """Return whether the current test process runs on macOS."""
    return sys.platform == "darwin"


def _prepare_macos_qt_offscreen_plugin() -> None:
    """Copy the Qt test plugin without macOS file metadata before GUI collection."""
    global _QT_TEST_PLUGIN_ROOT
    if not _is_macos() or os.environ.get("QT_PLUGIN_PATH"):
        return
    specification = importlib.util.find_spec("PySide6")
    locations = specification.submodule_search_locations if specification is not None else None
    if not locations:
        return
    package_root = Path(next(iter(locations)))
    source = package_root / "Qt" / "plugins" / "platforms" / "libqoffscreen.dylib"
    if not source.is_file():
        return
    temporary_root = Path(tempfile.mkdtemp(prefix="ordifile-qt-test-plugins-"))
    platforms = temporary_root / "platforms"
    platforms.mkdir(mode=0o700)
    shutil.copyfile(source, platforms / source.name)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["QT_PLUGIN_PATH"] = os.fspath(temporary_root)
    _QT_TEST_PLUGIN_ROOT = temporary_root


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Remove only the exact temporary Qt files created by this pytest process."""
    del session, exitstatus
    root = _QT_TEST_PLUGIN_ROOT
    if root is None:
        return
    try:
        (root / "platforms" / "libqoffscreen.dylib").unlink(missing_ok=True)
        (root / "platforms").rmdir()
        root.rmdir()
    except OSError:
        pass


_prepare_macos_qt_offscreen_plugin()
