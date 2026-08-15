# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Safe parser implementation shared by delimited-text adapters."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import ClassVar

from ordifile.adapters._tabular import is_compatible_header, parse_rows, semantic_headers
from ordifile.adapters.base import AdapterDescriptor, DetectionResult, ParseOptions
from ordifile.core.errors import ParseError
from ordifile.core.models import DatasetBundle

PROBE_BYTES = 64 * 1024
MAX_DELIMITED_BYTES = 512 * 1024 * 1024


class DelimitedAdapter:
    """Base adapter whose delimiter and public identity are fixed by subclasses."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str]
    adapter_version: ClassVar[str] = "0.1.0"
    descriptor: ClassVar[AdapterDescriptor]
    delimiter: ClassVar[str]
    preferred_extensions: ClassVar[tuple[str, ...]]

    def probe(self, path: Path) -> DetectionResult:
        """Inspect UTF-8 text, delimiter structure, and the explicit header schema."""
        try:
            with path.open("rb") as stream:
                raw = stream.read(PROBE_BYTES + 1)
        except OSError as error:
            return DetectionResult(False, 0.0, f"read failed ({type(error).__name__})")
        if not raw:
            return DetectionResult(False, 0.0, "empty file")
        if b"\x00" in raw:
            return DetectionResult(False, 0.0, "NUL byte indicates non-text content")
        try:
            text = raw[:PROBE_BYTES].decode("utf-8-sig", errors="strict")
            first_row = next(
                csv.reader([text.splitlines()[0]], delimiter=self.delimiter, strict=True)
            )
        except (UnicodeDecodeError, csv.Error, StopIteration) as error:
            return DetectionResult(
                False,
                0.0,
                f"not valid delimited UTF-8 text ({type(error).__name__})",
            )
        if len(first_row) < 2:
            return DetectionResult(False, 0.0, "no delimiter structure")
        try:
            compatible = is_compatible_header(first_row)
            semantic_headers(first_row)
        except ParseError as error:
            # Claim a delimiter/schema match so parse() can expose the exact duplicate error.
            return DetectionResult(True, 0.99, f"documented schema is invalid: {error.message}")
        if not compatible:
            return DetectionResult(False, 0.0, "header has no unambiguous documented schema")
        extension_evidence = path.suffix.casefold() in self.preferred_extensions
        confidence = 0.98
        reason = "delimiter and documented header matched"
        if extension_evidence:
            confidence = min(1.0, confidence + 0.01)
            reason += "; extension is consistent"
        return DetectionResult(True, confidence, reason)

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Parse a UTF-8/UTF-8-BOM table without type guessing."""
        del options
        try:
            size = path.stat().st_size
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                f"Could not stat the input ({type(error).__name__}).",
            ) from error
        if size > MAX_DELIMITED_BYTES:
            raise ParseError(
                "TEXT_FILE_TOO_LARGE",
                f"Delimited input exceeds the {MAX_DELIMITED_BYTES}-byte safety limit.",
            )
        try:
            with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as stream:
                return parse_rows(
                    path,
                    csv.reader(stream, delimiter=self.delimiter, strict=True),
                    namespace=f"adapter:{self.adapter_id}",
                    source_label="table",
                )
        except UnicodeDecodeError as error:
            raise ParseError(
                "TEXT_ENCODING_UNSUPPORTED",
                "Delimited input must be valid UTF-8 or UTF-8 with BOM.",
            ) from error
        except (OSError, csv.Error) as error:
            raise ParseError(
                "DELIMITED_PARSE_FAILED",
                f"Could not parse delimited input ({type(error).__name__}).",
            ) from error
