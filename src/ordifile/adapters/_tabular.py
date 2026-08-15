# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Shared explicit-schema parsing for generic tabular exports."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from ordifile.core.errors import ParseError
from ordifile.core.models import (
    MAX_CANONICAL_INTEGER_DECIMAL_DIGITS,
    MAX_CANONICAL_INTEGER_LEXEME_CHARACTERS,
    DatasetBundle,
    FileStatus,
    InstrumentMetadata,
    Issue,
    MetadataEntry,
    PeakRecord,
    SampleRecord,
    Severity,
    SignalSeries,
    SourceFile,
)
from ordifile.core.workbook_text import workbook_audit_display

_HEADER_SPACE = re.compile(r"[\s\-]+")
HEADER_ALIASES: dict[str, str] = {
    "sample_id": "sample_id",
    "acquired_at": "acquired_at",
    "sequence": "sequence",
    "instrument_type": "instrument_type",
    "instrument": "instrument_type",
    "vendor": "vendor",
    "channel": "channel",
    "detector": "detector",
    "runtime": "runtime",
    "peak_number": "peak_number",
    "retention_time": "retention_time",
    "rt": "retention_time",
    "retention_time_unit": "retention_time_unit",
    "area": "area",
    "height": "height",
    "compound": "compound",
    "compound_source": "compound_source",
    "time": "time",
    "x": "time",
    "signal": "signal",
    "response": "signal",
    "y": "signal",
    "x_unit": "x_unit",
    "y_unit": "y_unit",
}
MAPPED_TEXT_FIELDS = (
    "sample_id",
    "instrument_type",
    "vendor",
    "channel",
    "detector",
    "retention_time_unit",
    "compound",
    "compound_source",
    "x_unit",
    "y_unit",
)


def normalize_header(value: Any) -> str:
    """Normalize only spelling separators; aliases remain an explicit allow-list."""
    return _HEADER_SPACE.sub("_", str(value).strip().casefold())


def semantic_headers(header: Sequence[Any]) -> tuple[str | None, ...]:
    """Map documented aliases and reject duplicate semantic meanings."""
    mapped: list[str | None] = []
    seen: dict[str, str] = {}
    raw_seen: set[str] = set()
    for cell in header:
        raw = str(cell).strip()
        normalized = normalize_header(raw)
        if normalized in raw_seen:
            raise ParseError("DUPLICATE_HEADER", f"The header {raw!r} appears more than once.")
        raw_seen.add(normalized)
        semantic = HEADER_ALIASES.get(normalized)
        if semantic is not None and semantic in seen:
            raise ParseError(
                "DUPLICATE_SEMANTIC_HEADER",
                f"Headers {seen[semantic]!r} and {raw!r} both mean {semantic!r}.",
            )
        if semantic is not None:
            seen[semantic] = raw
        mapped.append(semantic)
    return tuple(mapped)


def is_compatible_header(header: Sequence[Any]) -> bool:
    """Return whether a row contains a non-ambiguous documented schema."""
    if not header or all(str(value).strip() == "" for value in header):
        return False
    try:
        mapped = semantic_headers(header)
    except ParseError:
        return False
    return any(item is not None for item in mapped)


def _source(path: Path) -> SourceFile:
    stat = path.stat()
    return SourceFile(
        path=path,
        relative_path=path.name,
        name=path.name,
        size=stat.st_size,
        sha256=None,
        modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone(),
        input_order=0,
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _raw_text(value: Any) -> str | None:
    """Return source text exactly; blank classification is deliberately separate."""
    return None if value is None else str(value)


def _float(
    value: Any,
    *,
    field: str,
    row_number: int,
    issues: list[Issue],
) -> float | None:
    text = _text(value)
    if text is None:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        issues.append(
            Issue(
                "INVALID_NUMBER",
                f"Row {row_number} field {field!r} is not numeric; its raw value was preserved.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
        return None
    try:
        exact_source = Decimal(text)
    except InvalidOperation:
        issues.append(
            Issue(
                "INVALID_NUMBER",
                f"Row {row_number} field {field!r} is not a supported decimal number; "
                "its raw value was preserved.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
        return None
    if not math.isfinite(number):
        if exact_source.is_finite():
            issues.append(
                Issue(
                    "LOSSY_FLOAT_REJECTED",
                    f"Row {row_number} field {field!r} is outside the finite float range; "
                    "its raw value was preserved instead.",
                    Severity.WARNING,
                    f"row:{row_number}",
                )
            )
            return None
        issues.append(
            Issue(
                "NONFINITE_NUMBER",
                f"Row {row_number} field {field!r} is non-finite and remains explicit.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
        return number
    float_roundtrip = Decimal(str(number))
    if exact_source != float_roundtrip:
        issues.append(
            Issue(
                "LOSSY_FLOAT_REJECTED",
                f"Row {row_number} field {field!r} cannot be represented exactly as a float; "
                "its raw value was preserved instead.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
        return None
    return number


def _integer(
    value: Any,
    *,
    field: str,
    row_number: int,
    issues: list[Issue],
) -> int | None:
    raw = _raw_text(value)
    if raw is None:
        return None
    if len(raw) > MAX_CANONICAL_INTEGER_LEXEME_CHARACTERS:
        issues.append(
            Issue(
                "INTEGER_LIMIT_EXCEEDED",
                f"Row {row_number} field {field!r} exceeds the bounded integer lexeme limit "
                f"of {MAX_CANONICAL_INTEGER_LEXEME_CHARACTERS} characters; its raw value "
                "was preserved without constructing an integer.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        issues.append(
            Issue(
                "INVALID_NUMBER",
                f"Row {row_number} field {field!r} is not numeric; its raw value was preserved.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
        return None
    if not number.is_finite():
        issues.append(
            Issue(
                "NONFINITE_NUMBER",
                f"Row {row_number} field {field!r} is non-finite and remains explicit.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
        return None
    decimal_tuple = number.as_tuple()
    exponent = cast(int, decimal_tuple.exponent)  # finite Decimal invariant
    adjusted = number.adjusted() if number else 0
    if (
        abs(exponent) > MAX_CANONICAL_INTEGER_DECIMAL_DIGITS
        or adjusted >= MAX_CANONICAL_INTEGER_DECIMAL_DIGITS
    ):
        issues.append(
            Issue(
                "INTEGER_LIMIT_EXCEEDED",
                f"Row {row_number} field {field!r} exceeds the canonical integer limit of "
                f"{MAX_CANONICAL_INTEGER_DECIMAL_DIGITS} decimal digits; its raw value was "
                "preserved without constructing an integer.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
        return None
    if number != number.to_integral_value():
        issues.append(
            Issue(
                "INVALID_INTEGER",
                f"Row {row_number} field {field!r} is not an integer; its raw value was preserved.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
        return None
    return int(number)


def _timestamp(value: Any, row_number: int, issues: list[Issue]) -> tuple[datetime | None, bool]:
    text = _text(value)
    if text is None:
        return None, False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        issues.append(
            Issue(
                "INVALID_TIMESTAMP",
                f"Row {row_number} acquired_at is not an ISO 8601 timestamp; "
                "its raw value was preserved.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
        return None, False
    # Naive values are preserved but are not reliable enough for automatic cross-file ordering.
    reliable = parsed.tzinfo is not None and parsed.utcoffset() is not None
    utc_range_unorderable = False
    if reliable:
        try:
            parsed.astimezone(UTC)
        except (OverflowError, ValueError):
            reliable = False
            utc_range_unorderable = True
            issues.append(
                Issue(
                    "ACQUIRED_AT_UTC_RANGE_UNORDERABLE",
                    f"Row {row_number} acquired_at cannot be represented on the UTC timeline; "
                    "its raw value was preserved and excluded from acquisition-time sorting.",
                    Severity.WARNING,
                    f"row:{row_number}",
                )
            )
    if not reliable and not utc_range_unorderable:
        issues.append(
            Issue(
                "TIMESTAMP_TIMEZONE_MISSING",
                f"Row {row_number} acquired_at has no timezone and is excluded from automatic "
                "acquisition-time ordering.",
                Severity.WARNING,
                f"row:{row_number}",
            )
        )
    return parsed, reliable


def parse_rows(
    path: Path,
    rows: Iterable[Sequence[Any]],
    *,
    namespace: str,
    source_label: str,
    formula_cells: set[tuple[int, int]] | frozenset[tuple[int, int]] = frozenset(),
    cell_sources: Mapping[tuple[int, int], str] | None = None,
) -> DatasetBundle:
    """Parse rows using only documented column meanings."""
    row_iterator = iter(rows)
    try:
        header_row = next(row_iterator)
    except StopIteration as error:
        raise ParseError("MISSING_HEADER", "The table is empty or has no header row.") from error
    if not header_row or all(_text(value) is None for value in header_row):
        raise ParseError("MISSING_HEADER", "The table is empty or has no header row.")
    header = ["" if value is None else str(value) for value in header_row]
    while header and header[-1] == "":
        header.pop()
    mapped = semantic_headers(header)
    if not any(item is not None for item in mapped):
        raise ParseError(
            "UNRECOGNIZED_SCHEMA",
            "No documented Ordifile column was found in the header.",
        )

    source = _source(path)
    issues: list[Issue] = []
    metadata: list[MetadataEntry] = []
    peaks: list[PeakRecord] = []
    signal_groups: dict[
        tuple[str | None, str | None, str | None, str | None], list[tuple[float, float]]
    ] = {}
    first_values: dict[str, str] = {}
    channels: list[str] = []
    detectors: list[str] = []
    sample_id = workbook_audit_display(path.stem)
    acquired_at: datetime | None = None
    acquired_reliable = False
    sequence: int | None = None
    runtime: float | None = None

    preserved_raw: set[tuple[int, str]] = set()
    field_columns = {
        semantic: index + 1 for index, semantic in enumerate(mapped) if semantic is not None
    }

    def preserve_raw(field: str, raw_value: Any, current_sample_id: str, row_number: int) -> None:
        key = (row_number, field)
        if key in preserved_raw:
            return
        preserved_raw.add(key)
        column = field_columns.get(field)
        cell_source = (
            cell_sources.get((row_number, column))
            if cell_sources is not None and column is not None
            else None
        )
        metadata.append(
            MetadataEntry(
                current_sample_id,
                source.name,
                namespace,
                field,
                raw_value,
                source=cell_source or f"{source_label}:row:{row_number}",
            )
        )

    def mapped_text(
        field: str, raw_value: Any, current_sample_id: str, row_number: int
    ) -> str | None:
        raw = _raw_text(raw_value)
        if raw is None:
            return None
        if raw == "":
            return None
        if raw.strip():
            return raw
        issues.append(
            Issue(
                "MAPPED_TEXT_WHITESPACE_ONLY",
                f"Row {row_number} field {field!r} contains only whitespace; it has no "
                "canonical meaning and its raw value was preserved in Metadata.",
                Severity.WARNING,
                f"{source_label}:row:{row_number}",
            )
        )
        preserve_raw(field, raw, current_sample_id, row_number)
        return None

    def parse_lexeme(
        field: str,
        raw_value: Any,
        current_sample_id: str,
        row_number: int,
    ) -> str | None:
        raw = _raw_text(raw_value)
        if raw is None:
            return None
        trimmed = raw.strip()
        if raw != trimmed:
            issues.append(
                Issue(
                    "PARSE_LEXEME_WHITESPACE_TRIMMED",
                    f"Row {row_number} field {field!r} was parsed from a whitespace-trimmed "
                    "copy; the exact raw lexeme was preserved in Metadata.",
                    Severity.WARNING,
                    f"{source_label}:row:{row_number}",
                )
            )
            preserve_raw(field, raw, current_sample_id, row_number)
        return trimmed or None

    def sample_field_conflicts(
        field: str, raw_value: str, current_sample_id: str, row_number: int
    ) -> bool:
        if field not in first_values:
            first_values[field] = raw_value
            return False
        if first_values[field] == raw_value:
            return True
        issues.append(
            Issue(
                "INCONSISTENT_SAMPLE_FIELD",
                f"Multiple {field} values occurred; later raw values remain in Metadata.",
                Severity.WARNING,
                f"{source_label}:row:{row_number}",
            )
        )
        preserve_raw(field, raw_value, current_sample_id, row_number)
        return True

    for data_index, row in enumerate(row_iterator, start=2):
        original_values = list(row)
        extra_values = original_values[len(header) :]
        nonempty_extras = False
        for extra_offset, raw_value in enumerate(extra_values, start=len(header) + 1):
            if (data_index, extra_offset) in formula_cells:
                issues.append(
                    Issue(
                        "FORMULA_PRESERVED",
                        f"Formula cell {source_label}!{data_index}:{extra_offset} was preserved "
                        "as literal text.",
                        Severity.WARNING,
                        f"{source_label}!R{data_index}C{extra_offset}",
                    )
                )
            if _raw_text(raw_value) not in (None, ""):
                nonempty_extras = True
                metadata.append(
                    MetadataEntry(
                        sample_id,
                        source.name,
                        namespace,
                        f"unmapped_column_{extra_offset}",
                        raw_value,
                        source=f"{source_label}:row:{data_index}:column:{extra_offset}",
                    )
                )
        if nonempty_extras:
            issues.append(
                Issue(
                    "EXTRA_CELLS_PRESERVED",
                    f"Row {data_index} contains non-empty cells beyond the header; they were "
                    "preserved as positional Metadata.",
                    Severity.WARNING,
                    f"{source_label}:row:{data_index}",
                )
            )
        values = original_values + [None] * max(0, len(header) - len(original_values))
        values = values[: len(header)]
        if all(_raw_text(value) in (None, "") for value in values):
            continue
        by_semantic = {
            semantic: values[index] for index, semantic in enumerate(mapped) if semantic is not None
        }
        for index, raw_header in enumerate(header):
            raw_value = values[index]
            semantic = mapped[index]
            if (data_index, index + 1) in formula_cells:
                issues.append(
                    Issue(
                        "FORMULA_PRESERVED",
                        f"Formula cell {source_label}!{data_index}:{index + 1} was preserved "
                        "as literal text.",
                        Severity.WARNING,
                        f"{source_label}!R{data_index}C{index + 1}",
                    )
                )
            if semantic is None and _raw_text(raw_value) not in (None, ""):
                metadata.append(
                    MetadataEntry(
                        sample_id,
                        source.name,
                        namespace,
                        raw_header,
                        raw_value,
                        source=f"{source_label}:row:{data_index}",
                    )
                )
                if isinstance(raw_value, str) and not raw_value.strip():
                    issues.append(
                        Issue(
                            "UNKNOWN_VALUE_WHITESPACE_ONLY",
                            f"Row {data_index} unknown field {raw_header!r} contains only "
                            "whitespace; its exact raw value was preserved in Metadata.",
                            Severity.WARNING,
                            f"{source_label}:row:{data_index}",
                        )
                    )
        text_values = {
            field: mapped_text(field, by_semantic.get(field), sample_id, data_index)
            for field in MAPPED_TEXT_FIELDS
            if field in by_semantic
        }
        explicit_id = text_values.get("sample_id")
        if explicit_id is not None:
            previous_id = first_values.get("sample_id")
            if previous_id is None:
                first_values["sample_id"] = explicit_id
                sample_id = explicit_id
            elif previous_id != explicit_id:
                issues.append(
                    Issue(
                        "MULTIPLE_SAMPLE_IDS",
                        "Multiple sample_id values occurred; one input still represents "
                        "one sample.",
                        Severity.WARNING,
                        f"{source_label}:row:{data_index}",
                    )
                )
                preserve_raw("sample_id", explicit_id, sample_id, data_index)
        for field in ("instrument_type", "vendor"):
            value = text_values.get(field)
            if value is not None:
                previous = first_values.setdefault(field, value)
                if previous != value:
                    issues.append(
                        Issue(
                            "INCONSISTENT_SAMPLE_FIELD",
                            f"Multiple {field} values occurred; later values remain in Metadata.",
                            Severity.WARNING,
                            f"{source_label}:row:{data_index}",
                        )
                    )
                    preserve_raw(field, value, sample_id, data_index)

        channel = text_values.get("channel")
        detector = text_values.get("detector")
        if channel is not None and channel not in channels:
            channels.append(channel)
        if detector is not None and detector not in detectors:
            detectors.append(detector)
        acquired_raw = by_semantic.get("acquired_at")
        acquired_lexeme = parse_lexeme("acquired_at", acquired_raw, sample_id, data_index)
        if acquired_lexeme is not None and not sample_field_conflicts(
            "acquired_at", acquired_lexeme, sample_id, data_index
        ):
            acquired_at, acquired_reliable = _timestamp(acquired_lexeme, data_index, issues)
            if acquired_at is None or not acquired_reliable:
                preserve_raw("acquired_at", acquired_raw, sample_id, data_index)
        sequence_raw = by_semantic.get("sequence")
        sequence_lexeme = parse_lexeme("sequence", sequence_raw, sample_id, data_index)
        if sequence_lexeme is not None and not sample_field_conflicts(
            "sequence", sequence_lexeme, sample_id, data_index
        ):
            sequence = _integer(
                sequence_raw,
                field="sequence",
                row_number=data_index,
                issues=issues,
            )
            if sequence is None:
                preserve_raw("sequence", sequence_raw, sample_id, data_index)
        runtime_raw = by_semantic.get("runtime")
        runtime_lexeme = parse_lexeme("runtime", runtime_raw, sample_id, data_index)
        if runtime_lexeme is not None and not sample_field_conflicts(
            "runtime", runtime_lexeme, sample_id, data_index
        ):
            runtime = _float(
                runtime_lexeme,
                field="runtime",
                row_number=data_index,
                issues=issues,
            )
            if runtime is None:
                preserve_raw("runtime", runtime_raw, sample_id, data_index)
            elif not math.isfinite(runtime):
                preserve_raw("runtime", runtime_raw, sample_id, data_index)

        peak_lexemes = {
            field: parse_lexeme(field, by_semantic.get(field), sample_id, data_index)
            for field in ("peak_number", "retention_time", "area", "height")
        }
        has_peak = any(
            text_values.get(field) is not None
            for field in ("retention_time_unit", "compound", "compound_source")
        ) or any(lexeme is not None for lexeme in peak_lexemes.values())
        if has_peak:
            peak = PeakRecord(
                sample_id=sample_id,
                source_file=source.name,
                channel=channel,
                detector=detector,
                peak_number=_integer(
                    by_semantic.get("peak_number"),
                    field="peak_number",
                    row_number=data_index,
                    issues=issues,
                ),
                retention_time=_float(
                    peak_lexemes["retention_time"],
                    field="retention_time",
                    row_number=data_index,
                    issues=issues,
                ),
                retention_time_unit=text_values.get("retention_time_unit"),
                area=_float(
                    peak_lexemes["area"],
                    field="area",
                    row_number=data_index,
                    issues=issues,
                ),
                height=_float(
                    peak_lexemes["height"],
                    field="height",
                    row_number=data_index,
                    issues=issues,
                ),
                compound=text_values.get("compound"),
                compound_source=text_values.get("compound_source"),
            )
            peaks.append(peak)
            for numeric_field in ("peak_number", "retention_time", "area", "height"):
                raw = _raw_text(by_semantic.get(numeric_field))
                parsed = getattr(peak, numeric_field)
                if (
                    raw is not None
                    and raw.strip()
                    and (parsed is None or isinstance(parsed, float) and not math.isfinite(parsed))
                ):
                    preserve_raw(numeric_field, raw, sample_id, data_index)

        if "time" in by_semantic and "signal" in by_semantic:
            time_lexeme = parse_lexeme("time", by_semantic.get("time"), sample_id, data_index)
            signal_lexeme = parse_lexeme("signal", by_semantic.get("signal"), sample_id, data_index)
            x_value = _float(time_lexeme, field="time", row_number=data_index, issues=issues)
            y_value = _float(signal_lexeme, field="signal", row_number=data_index, issues=issues)
            for field, raw_value, parsed_value in (
                ("time", by_semantic.get("time"), x_value),
                ("signal", by_semantic.get("signal"), y_value),
            ):
                raw = _raw_text(raw_value)
                if (
                    raw is not None
                    and raw.strip()
                    and (parsed_value is None or not math.isfinite(parsed_value))
                ):
                    preserve_raw(field, raw, sample_id, data_index)
            if x_value is not None and y_value is not None:
                group = (
                    channel,
                    detector,
                    text_values.get("x_unit"),
                    text_values.get("y_unit"),
                )
                signal_groups.setdefault(group, []).append((x_value, y_value))

    # Metadata captured before the first explicit sample id needs the final file-level id.
    metadata = [
        MetadataEntry(
            sample_id,
            entry.source_file,
            entry.namespace,
            entry.key,
            entry.value,
            entry.unit,
            entry.source,
        )
        for entry in metadata
    ]
    peaks = [
        PeakRecord(
            sample_id,
            peak.source_file,
            peak.channel,
            peak.detector,
            peak.peak_number,
            peak.retention_time,
            peak.retention_time_unit,
            peak.area,
            peak.height,
            peak.compound,
            peak.compound_source,
            peak.status,
        )
        for peak in peaks
    ]
    signals = tuple(
        SignalSeries(
            sample_id,
            source.name,
            channel,
            detector,
            tuple(point[0] for point in points),
            tuple(point[1] for point in points),
            x_unit=x_unit,
            y_unit=y_unit,
        )
        for (channel, detector, x_unit, y_unit), points in signal_groups.items()
    )
    sample = SampleRecord(
        sample_id,
        source,
        acquired_at,
        acquired_reliable,
        sequence,
        InstrumentMetadata(first_values.get("instrument_type"), first_values.get("vendor")),
        tuple(channels),
        tuple(detectors),
        runtime,
        FileStatus.WARNING if issues else FileStatus.SUCCESS,
    )
    return DatasetBundle(
        (source,),
        (sample,),
        signals,
        tuple(peaks),
        tuple(metadata),
        tuple(issues),
    )
