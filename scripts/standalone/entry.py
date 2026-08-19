# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Native packaging entry point; normal use launches the existing desktop layer."""

from __future__ import annotations

import sys
from collections.abc import Sequence

try:
    from .smoke import main as smoke_main
except ImportError:  # copied beside smoke.py in the temporary packaging project
    from smoke import main as smoke_main  # type: ignore[import-not-found,no-redef]


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the GUI, or the explicit checkout-free artifact smoke contract."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "--standalone-smoke":
        return smoke_main(["run", *arguments[1:]])
    if arguments == ["--standalone-window-smoke"]:
        try:
            return _window_smoke()
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception:
            print("Standalone window smoke failed; details were withheld.", file=sys.stderr)
            return 1
    from ordifile.desktop.app import main as desktop_main

    return desktop_main(arguments)


def _window_smoke() -> int:
    from ordifile.desktop.app import create_application
    from ordifile.desktop.window import MainWindow

    application = create_application(["ordifile-standalone-window-smoke"])
    window = MainWindow()
    window.show()
    application.processEvents()
    visible = window.isVisible()
    window.close()
    application.processEvents()
    if not visible:
        raise RuntimeError("The packaged desktop window did not become visible.")
    print("Standalone window smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
