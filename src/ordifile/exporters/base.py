# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Typed exporter boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ordifile.core.models import BatchResult


class Exporter(Protocol):
    """Protocol for deterministic batch exporters."""

    def export(
        self,
        result: BatchResult,
        output: Path,
        *,
        overwrite: bool = False,
        include_signals: bool = False,
        sidecar_mode: str = "error",
    ) -> BatchResult:
        """Export a validated batch and return its finalized output metadata."""
        ...
