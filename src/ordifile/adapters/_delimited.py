# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Safe parser implementation shared by delimited-text adapters."""

from __future__ import annotations

import codecs
import csv
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from ordifile.adapters._tabular import (
    is_compatible_header,
    parse_mapped_peak_rows,
    parse_rows,
    semantic_headers,
)
from ordifile.adapters.base import AdapterDescriptor, DetectionResult, ParseOptions
from ordifile.core.errors import OrdifileError, ParseError
from ordifile.core.models import DatasetBundle
from ordifile.core.peak_mapping import (
    MAX_PEAK_PREVIEW_CELL_CHARACTERS,
    MAX_PEAK_PREVIEW_CELLS,
    MAX_PEAK_PREVIEW_COLUMNS,
    MAX_PEAK_PREVIEW_LINE_BYTES,
    MAX_PEAK_PREVIEW_READ_BYTES,
    MAX_PEAK_PREVIEW_ROWS,
    MAX_PEAK_PREVIEW_TOTAL_CHARACTERS,
    ColumnSelector,
    PeakTableFormat,
    PeakTablePreview,
    peak_preview_display,
)

PROBE_BYTES = 64 * 1024
MAX_DELIMITED_BYTES = 512 * 1024 * 1024


def preview_delimited_peak_table(
    path: Path,
    source_format: PeakTableFormat,
    *,
    row_limit: int = 5,
) -> PeakTablePreview:
    """Return a bounded display preview through the existing audited text boundary."""
    delimiters = {
        PeakTableFormat.CSV: ",",
        PeakTableFormat.TSV: "\t",
        PeakTableFormat.SEMICOLON: ";",
    }
    delimiter = delimiters.get(source_format)
    if delimiter is None:
        raise ParseError("PEAK_MAPPING_FORMAT_MISMATCH", "A text source format is required.")
    if type(row_limit) is not int or row_limit < 1 or row_limit > MAX_PEAK_PREVIEW_ROWS:
        raise ParseError(
            "PEAK_MAPPING_PREVIEW_LIMIT_INVALID",
            f"row_limit must be from 1 through {MAX_PEAK_PREVIEW_ROWS}.",
        )
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ParseError("INPUT_READ_FAILED", "Could not stat the preview input.") from error
    if size > MAX_DELIMITED_BYTES:
        raise ParseError(
            "TEXT_FILE_TOO_LARGE",
            f"Delimited input exceeds the {MAX_DELIMITED_BYTES}-byte safety limit.",
        )
    try:
        with path.open("rb") as stream:
            decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
            bytes_read = 0

            def bounded_lines() -> Iterator[str]:
                nonlocal bytes_read
                while True:
                    raw_line = stream.readline(MAX_PEAK_PREVIEW_LINE_BYTES + 1)
                    if not raw_line:
                        decoder.decode(b"", final=True)
                        return
                    bytes_read += len(raw_line)
                    if (
                        len(raw_line) > MAX_PEAK_PREVIEW_LINE_BYTES
                        or bytes_read > MAX_PEAK_PREVIEW_READ_BYTES
                    ):
                        raise ParseError(
                            "PEAK_MAPPING_PREVIEW_SIZE_LIMIT",
                            "The bounded preview prefix exceeds its byte or line limit.",
                        )
                    yield decoder.decode(raw_line, final=False)

            reader = csv.reader(bounded_lines(), delimiter=delimiter, strict=True)
            header = next(reader)
            while header and header[-1] == "":
                header.pop()
            if not header:
                raise ParseError("MISSING_HEADER", "The mapped table has no header row.")
            if len(header) > MAX_PEAK_PREVIEW_COLUMNS:
                raise ParseError(
                    "PEAK_MAPPING_PREVIEW_COLUMN_LIMIT",
                    f"Peak-table preview supports at most {MAX_PEAK_PREVIEW_COLUMNS} columns.",
                )
            try:
                tuple(ColumnSelector(value, index) for index, value in enumerate(header, start=1))
            except OrdifileError as error:
                raise ParseError(
                    "PEAK_MAPPING_PREVIEW_HEADER_INVALID",
                    "Preview headers must be nonempty exact text without controls or "
                    "directional formatting.",
                ) from error
            total_cells = len(header)
            total_characters = sum(len(value) for value in header)
            if any(len(value) > MAX_PEAK_PREVIEW_CELL_CHARACTERS for value in header):
                raise ParseError(
                    "PEAK_MAPPING_PREVIEW_CELL_LIMIT",
                    "A preview header exceeds the bounded cell-text limit.",
                )
            rows: list[tuple[str, ...]] = []
            for raw in reader:
                if all(value == "" for value in raw):
                    continue
                if len(raw) > len(header) and any(value != "" for value in raw[len(header) :]):
                    raise ParseError(
                        "PEAK_MAPPING_PREVIEW_EXTRA_CELLS",
                        "A preview row contains data beyond the header.",
                    )
                values = [*raw[: len(header)], *([""] * max(0, len(header) - len(raw)))]
                rendered = tuple(peak_preview_display(value) for value in values)
                total_cells += len(rendered)
                total_characters += sum(len(value) for value in rendered)
                if (
                    total_cells > MAX_PEAK_PREVIEW_CELLS
                    or total_characters > MAX_PEAK_PREVIEW_TOTAL_CHARACTERS
                    or any(len(value) > MAX_PEAK_PREVIEW_CELL_CHARACTERS for value in rendered)
                ):
                    raise ParseError(
                        "PEAK_MAPPING_PREVIEW_SIZE_LIMIT",
                        "The bounded preview exceeds its cell or rendered-text limit.",
                    )
                rows.append(rendered)
                if len(rows) == row_limit:
                    break
    except StopIteration as error:
        raise ParseError("MISSING_HEADER", "The mapped table is empty.") from error
    except UnicodeDecodeError as error:
        raise ParseError(
            "TEXT_ENCODING_UNSUPPORTED",
            "Delimited input must be valid UTF-8 or UTF-8 with BOM.",
        ) from error
    except (OSError, csv.Error) as error:
        raise ParseError("DELIMITED_PARSE_FAILED", "Could not preview delimited input.") from error
    return PeakTablePreview(
        source_format,
        tuple(header),
        tuple(rows),
    )


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
                if options.peak_table_mapping is not None:
                    expected = {
                        ",": PeakTableFormat.CSV,
                        "\t": PeakTableFormat.TSV,
                        ";": PeakTableFormat.SEMICOLON,
                    }[self.delimiter]
                    if options.peak_table_mapping.source_format is not expected:
                        raise ParseError(
                            "PEAK_MAPPING_FORMAT_MISMATCH",
                            "The mapping source format does not match the selected text reader.",
                        )
                    return parse_mapped_peak_rows(
                        path,
                        csv.reader(stream, delimiter=self.delimiter, strict=True),
                        options.peak_table_mapping,
                        namespace=f"adapter:{self.adapter_id}:user_mapping",
                        mapping_profile_id=options.peak_table_mapping_profile_id,
                        mapping_profile_fingerprint=(
                            options.peak_table_mapping_profile_fingerprint
                        ),
                        mapping_set_id=options.peak_table_mapping_set_id,
                    )
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
