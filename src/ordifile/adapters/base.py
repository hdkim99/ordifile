# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Typed parser plugin boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

from ordifile.core.models import DatasetBundle

ADAPTER_API_VERSION = "1"


class SupportStatus(StrEnum):
    """Public evidence level for one adapter descriptor."""

    VERIFIED = "verified"
    EXPERIMENTAL = "experimental"
    FIXTURE_DECLARED = "fixture_declared"


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Bounded probe result with confidence and inspectable evidence."""

    matched: bool
    confidence: float
    reason: str


@dataclass(frozen=True, slots=True)
class ParseOptions:
    """Format-neutral parsing choices."""

    sheet: str | None = None
    include_hidden_sheets: bool = False


@dataclass(frozen=True, slots=True)
class AdapterDescriptor:
    """Safe metadata shown by `formats` without claiming vendor compatibility."""

    adapter_id: str
    adapter_version: str
    display_name: str
    extensions: tuple[str, ...]
    metadata: bool
    peaks: bool
    signals: bool
    tested_fixture: bool
    support_status: SupportStatus = SupportStatus.FIXTURE_DECLARED


@runtime_checkable
class FormatAdapter(Protocol):
    """Protocol implemented by built-in and trusted third-party parsers."""

    api_version: ClassVar[str]
    adapter_id: ClassVar[str]
    adapter_version: ClassVar[str]
    descriptor: ClassVar[AdapterDescriptor]

    def probe(self, path: Path) -> DetectionResult:
        """Inspect bounded content and return evidence, without mutating the file."""
        ...

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Parse one input to the canonical model."""
        ...
