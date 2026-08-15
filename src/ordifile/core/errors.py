# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Structured errors raised at Ordifile's public boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class OrdifileError(Exception):
    """Base class for an actionable, machine-readable failure."""

    def __init__(
        self, code: str, message: str, *, details: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


class DiscoveryError(OrdifileError):
    """An input could not be safely discovered."""


class DetectionError(OrdifileError):
    """No unambiguous adapter could be selected."""


class AdapterAmbiguityError(DetectionError):
    """More than one adapter or input sheet is equally plausible."""


class ParseError(OrdifileError):
    """An adapter could not parse its claimed input."""


class ValidationError(OrdifileError):
    """Parsed canonical data violates a required invariant."""


class ExportError(OrdifileError):
    """A workbook could not be safely exported."""


class ExportLimitError(ExportError):
    """The planned output exceeds a non-negotiable Excel limit."""
