# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Optional offline desktop interface for Ordifile."""

from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the optional Qt desktop application."""
    from ordifile.desktop.app import main as run

    return run(argv)


__all__ = ["main"]
