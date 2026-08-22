# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-specific Qt test setup")
def test_macos_qt_tests_use_the_prepared_offscreen_plugin() -> None:
    if importlib.util.find_spec("PySide6") is None:
        pytest.skip("PySide6 is not installed")

    plugin_root = Path(os.environ["QT_PLUGIN_PATH"])

    assert os.environ["QT_QPA_PLATFORM"] == "offscreen"
    assert plugin_root.name.startswith("ordifile-qt-test-plugins-")
    assert (plugin_root / "platforms" / "libqoffscreen.dylib").is_file()
