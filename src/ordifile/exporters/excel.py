# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Atomic, limit-aware Excel workbook export."""

from __future__ import annotations

import csv
import math
import os
import re
import stat
import tempfile
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from numbers import Number
from pathlib import Path
from typing import Any

import xlsxwriter  # type: ignore[import-untyped]

from ordifile import __version__
from ordifile.core.discovery import paths_alias, sha256_file
from ordifile.core.errors import ExportError, ExportLimitError
from ordifile.core.file_publish import rename_no_replace
from ordifile.core.models import (
    MAX_CANONICAL_INTEGER_DECIMAL_DIGITS,
    BatchResult,
    FileResult,
    FileStatus,
    MetadataEntry,
    PeakRecord,
    SeriesKind,
    SidecarRecord,
    SignalSeries,
    integer_is_within_canonical_bound,
)
from ordifile.core.summary import (
    CONVERSION_RESULT_SUMMARY_SCHEMA_VERSION,
    summarize_conversion,
)
from ordifile.core.workbook_text import (
    XLSX_ESCAPE_TOKEN,
    text_codepoint_unrepresentable,
    workbook_audit_display,
    workbook_text_is_exact,
)

MAX_EXCEL_ROWS = 1_048_576
MAX_EXCEL_COLUMNS = 16_384
MAX_EXCEL_CELL_CHARACTERS = 32_767

_rename_no_replace = rename_no_replace
MAX_EXCEL_SHEET_NAME = 31
MAX_WORKBOOK_SHEETS = 512
_FORBIDDEN_SHEET = re.compile(r"[\[\]:*?/\\]")
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_WINDOWS_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_PORTABLE_OUTPUT_PATH_CHARACTERS = 218
MAX_EXCEL_EXACT_INTEGER_DIGITS: int = 15
MAX_EXCEL_EXACT_INTEGER_ABS: int = 10**MAX_EXCEL_EXACT_INTEGER_DIGITS
MAX_MANIFEST_SUMMARY_CODES = 100


@dataclass(frozen=True, slots=True)
class _SheetData:
    logical_name: str
    headers: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True, slots=True)
class _PhysicalSheet:
    logical_name: str
    name: str
    headers: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True, slots=True)
class _SheetPresentation:
    freeze_columns: int = 0
    filter_columns: int = 0
    default_width: float = 14.0
    width_overrides: tuple[tuple[int, int, float], ...] = ()
    activate: bool = False


def _validate_workbook_text(text: str, *, location: str) -> None:
    if not workbook_text_is_exact(text):
        raise ExportLimitError(
            "WORKBOOK_TEXT_UNREPRESENTABLE",
            f"Text at {location} contains a control, surrogate, Unicode noncharacter, or "
            "reserved XLSX escape token that cannot be represented exactly.",
        )


def sanitize_sheet_name(name: str, used: set[str] | None = None) -> str:
    """Return an Excel-safe, case-insensitively unique worksheet name."""
    occupied = set() if used is None else used
    normalized = unicodedata.normalize("NFC", name)
    base = "".join(
        "_"
        if ord(character) < 0x20
        or _FORBIDDEN_SHEET.fullmatch(character)
        or text_codepoint_unrepresentable(character)
        else character
        for character in normalized
    )
    base = XLSX_ESCAPE_TOKEN.sub("_", base)
    base = base.strip(" '") or "Sheet"
    if base.casefold() == "history":
        base = "History_"
    base = base[:MAX_EXCEL_SHEET_NAME]
    candidate = base
    index = 2
    occupied_keys = {unicodedata.normalize("NFC", value).casefold() for value in occupied}
    while unicodedata.normalize("NFC", candidate).casefold() in occupied_keys:
        suffix = f"_{index}"
        candidate = f"{base[: MAX_EXCEL_SHEET_NAME - len(suffix)]}{suffix}"
        index += 1
    occupied.add(unicodedata.normalize("NFC", candidate).casefold())
    return candidate


def _validate_output_path(output: Path) -> None:
    """Reject workbook names that are not portable across supported platforms."""
    if output.exists() and output.is_dir():
        raise ExportError("OUTPUT_IS_DIRECTORY", "Workbook output points to an existing directory.")
    if output.name != output.name.rstrip(" ."):
        raise ExportError(
            "WINDOWS_OUTPUT_NAME_INVALID",
            "Windows-compatible output names cannot end with a dot or space.",
        )
    if _WINDOWS_INVALID_FILENAME.search(output.name):
        raise ExportError(
            "WINDOWS_OUTPUT_NAME_INVALID",
            "Output filename contains a character forbidden by Windows.",
        )
    if output.suffix.casefold() != ".xlsx":
        raise ExportError(
            "OUTPUT_EXTENSION_INVALID", "Workbook output must use the .xlsx extension."
        )
    device_name = output.name.split(".", maxsplit=1)[0].upper()
    if device_name in _WINDOWS_RESERVED_NAMES:
        raise ExportError(
            "WINDOWS_OUTPUT_NAME_RESERVED",
            f"Output basename {device_name!r} is reserved on Windows.",
        )
    # Microsoft documents the workbook path+filename boundary in characters. This
    # deliberately counts Unicode code points, not encoded bytes, on every platform.
    if len(str(output.resolve(strict=False))) > MAX_PORTABLE_OUTPUT_PATH_CHARACTERS:
        raise ExportError(
            "OUTPUT_PATH_TOO_LONG",
            f"Resolved output path exceeds {MAX_PORTABLE_OUTPUT_PATH_CHARACTERS} characters.",
        )


def _assert_artifact_is_not_input(artifact: Path, inputs: tuple[Path, ...], *, code: str) -> None:
    if any(paths_alias(artifact, input_path) for input_path in inputs):
        raise ExportError(code, f"Output artifact {artifact.name!r} aliases an input file.")


def validate_primary_output_target(
    output: Path,
    protected_inputs: tuple[Path, ...],
    *,
    overwrite: bool,
) -> None:
    """Perform the shared read-only checks available before workbook planning."""
    output = Path(output)
    if not output.parent.exists() or not output.parent.is_dir():
        raise ExportError("OUTPUT_DIRECTORY_MISSING", "The output directory does not exist.")
    if os.name != "nt":
        try:
            parent_state = os.stat(output.parent, follow_symlinks=True)
        except OSError as error:
            raise ExportError(
                "OUTPUT_DIRECTORY_UNAVAILABLE",
                "The output directory could not be inspected safely.",
            ) from error
        shared_write = parent_state.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        sticky = parent_state.st_mode & stat.S_ISVTX
        if shared_write and not sticky:
            raise ExportError(
                "OUTPUT_DIRECTORY_UNSAFE",
                "The output directory permits untrusted entry replacement; use a private "
                "or sticky directory.",
            )
    _assert_artifact_is_not_input(output, protected_inputs, code="OUTPUT_IS_INPUT")
    _validate_output_path(output)
    if output.exists() and not overwrite:
        raise ExportError(
            "OUTPUT_EXISTS", "Output already exists; pass overwrite=True to replace it."
        )


def _successful(item: FileResult) -> bool:
    return item.status in {FileStatus.SUCCESS, FileStatus.WARNING}


def _sample(item: FileResult) -> Any | None:
    if not _successful(item) or item.bundle is None or not item.bundle.samples:
        return None
    return item.bundle.samples[0]


def _samples_data(result: BatchResult) -> _SheetData:
    headers = (
        "order",
        "sample_id",
        "source_file",
        "relative_path",
        "file_format",
        "instrument_type",
        "vendor",
        "detector_channels",
        "acquired_at",
        "sequence",
        "runtime",
        "peak_count",
        "status",
        "sha256",
    )
    rows: list[tuple[Any, ...]] = []
    for order, item in enumerate(result.files, start=1):
        sample = _sample(item)
        peak_count = len(item.bundle.peaks) if _successful(item) and item.bundle is not None else 0
        detectors = () if sample is None else (*sample.detectors, *sample.channels)
        rows.append(
            (
                order,
                workbook_audit_display(Path(item.source.public_reference).stem)
                if sample is None
                else sample.sample_id,
                workbook_audit_display(item.source.public_reference),
                workbook_audit_display(item.source.public_reference),
                item.source.detected_format,
                None if sample is None else sample.instrument.instrument_type,
                None if sample is None else sample.instrument.vendor,
                "; ".join(detectors),
                None
                if sample is None or sample.acquired_at is None
                else sample.acquired_at.isoformat(),
                None if sample is None else sample.sequence,
                None if sample is None else sample.runtime,
                peak_count,
                item.status.value,
                item.source.sha256,
            )
        )
    return _SheetData("Samples", headers, tuple(rows))


def _peaks_data(result: BatchResult) -> _SheetData:
    base_headers = (
        "sample_id",
        "source_file",
        "channel",
        "detector",
        "peak_number",
        "retention_time",
        "retention_time_unit",
        "area",
        "height",
        "compound",
        "compound_source",
        "status",
        "manufacturer",
        "observation_order",
        "start_time",
        "end_time",
        "area_unit",
        "height_unit",
    )
    peak_entries = tuple(
        (item.bundle.samples[0].instrument.vendor, peak)
        for item in result.files
        if _successful(item) and item.bundle is not None and item.bundle.samples
        for peak in item.bundle.peaks
    )
    include_secondary_retention = any(
        peak.secondary_retention_time is not None or peak.secondary_retention_time_unit is not None
        for _manufacturer, peak in peak_entries
    )
    headers = (
        *base_headers,
        *(
            ("secondary_retention_time", "secondary_retention_time_unit")
            if include_secondary_retention
            else ()
        ),
    )
    rows = tuple(
        (
            peak.sample_id,
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
            manufacturer,
            peak.observation_order,
            peak.start_time,
            peak.end_time,
            peak.area_unit,
            peak.height_unit,
            *(
                (peak.secondary_retention_time, peak.secondary_retention_time_unit)
                if include_secondary_retention
                else ()
            ),
        )
        for manufacturer, peak in peak_entries
    )
    return _SheetData("Peaks", headers, rows)


def _matrix_escape(value: str) -> str:
    """Escape qualifiers so separators cannot be forged by source text."""
    encoded: list[str] = []
    for byte in value.encode("utf-8"):
        character = chr(byte)
        encoded.append(character if character.isascii() and character.isalnum() else f"%{byte:02X}")
    return "".join(encoded)


def _matrix_base(identity: tuple[str, str | None, str | None]) -> str:
    compound, detector, channel = identity
    if detector is None and channel is None:
        return f"{compound}_area"
    return (
        f"q[compound={_matrix_escape(compound)}]"
        f"[detector={_matrix_escape(detector or '')}]"
        f"[channel={_matrix_escape(channel or '')}]_area"
    )


def _peak_matrix_data(result: BatchResult) -> _SheetData:
    Identity = tuple[str, str | None, str | None]
    maximum_occurrences: dict[Identity, int] = {}
    ordered_identities: list[Identity] = []
    item_values: list[tuple[str, list[tuple[Identity, int, Any]]]] = []
    for item in result.files:
        if not _successful(item) or item.bundle is None or not item.bundle.samples:
            continue
        counts: dict[Identity, int] = defaultdict(int)
        values: list[tuple[Identity, int, Any]] = []
        for peak in item.bundle.peaks:
            if not peak.compound:
                continue
            identity = (peak.compound, peak.detector, peak.channel)
            if identity not in maximum_occurrences:
                ordered_identities.append(identity)
            counts[identity] += 1
            maximum_occurrences[identity] = max(
                maximum_occurrences.get(identity, 0), counts[identity]
            )
            values.append((identity, counts[identity], peak.area))
        item_values.append((item.bundle.samples[0].sample_id, values))

    base_by_identity: dict[Identity, str] = {}
    used_headers: set[str] = set()
    for identity in ordered_identities:
        raw_base = _matrix_base(identity)
        base = raw_base
        collision = 2
        while base.casefold() in used_headers:
            base = f"{raw_base}__identity_{collision}"
            collision += 1
        used_headers.add(base.casefold())
        base_by_identity[identity] = base

    columns = tuple(
        base_by_identity[identity]
        if occurrence == 1
        else f"{base_by_identity[identity]}_{occurrence}"
        for identity in ordered_identities
        for occurrence in range(1, maximum_occurrences[identity] + 1)
    )
    rows: list[tuple[Any, ...]] = []
    for sample_id, item_entries in item_values:
        value_map = {
            base_by_identity[identity]
            if occurrence == 1
            else f"{base_by_identity[identity]}_{occurrence}": value
            for identity, occurrence, value in item_entries
        }
        rows.append((sample_id, *(value_map.get(column) for column in columns)))
    return _SheetData("Peak_Matrix", ("sample_id", *columns), tuple(rows))


def _peak_order_matrix_data(result: BatchResult) -> _SheetData | None:
    """Preserve source observation order as atomic retention-time/area pairs."""
    fixed_headers = (
        "sample_id",
        "source_file",
        "manufacturer",
        "detector",
        "channel",
        "retention_time_unit",
        "area_unit",
    )
    rows_with_peaks: list[tuple[tuple[Any, ...], list[PeakRecord]]] = []
    maximum_peaks = 0
    for item in result.files:
        if not _successful(item) or item.bundle is None or not item.bundle.samples:
            continue
        sample = item.bundle.samples[0]
        grouped: dict[
            tuple[str, str, str | None, str | None, str | None, str | None, str | None],
            list[PeakRecord],
        ] = {}
        for peak in item.bundle.peaks:
            if peak.observation_order is None or peak.secondary_retention_time is not None:
                continue
            identity = (
                peak.sample_id,
                peak.source_file,
                sample.instrument.vendor,
                peak.detector,
                peak.channel,
                peak.retention_time_unit,
                peak.area_unit,
            )
            grouped.setdefault(identity, []).append(peak)
        for identity, peaks in grouped.items():
            maximum_peaks = max(maximum_peaks, len(peaks))
            rows_with_peaks.append((identity, peaks))
    if not rows_with_peaks:
        return None
    dynamic_headers = tuple(
        header
        for index in range(1, maximum_peaks + 1)
        for header in (f"peak_{index}_rt", f"peak_{index}_area")
    )
    rows = tuple(
        (
            *identity,
            *(value for peak in peaks for value in (peak.retention_time, peak.area)),
            *(None for _ in range(2 * (maximum_peaks - len(peaks)))),
        )
        for identity, peaks in rows_with_peaks
    )
    return _SheetData("Peak_Order_Matrix", (*fixed_headers, *dynamic_headers), rows)


def _peak_order_matrix_2d_data(result: BatchResult) -> _SheetData | None:
    """Preserve two-dimensional source order as atomic RT1/RT2/area triples."""
    fixed_headers = (
        "sample_id",
        "source_file",
        "manufacturer",
        "detector",
        "channel",
        "retention_time_unit",
        "secondary_retention_time_unit",
        "area_unit",
    )
    rows_with_peaks: list[tuple[tuple[Any, ...], list[PeakRecord]]] = []
    maximum_peaks = 0
    for item in result.files:
        if not _successful(item) or item.bundle is None or not item.bundle.samples:
            continue
        sample = item.bundle.samples[0]
        grouped: dict[
            tuple[
                str,
                str,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
            ],
            list[PeakRecord],
        ] = {}
        for peak in item.bundle.peaks:
            if peak.observation_order is None or peak.secondary_retention_time is None:
                continue
            identity = (
                peak.sample_id,
                peak.source_file,
                sample.instrument.vendor,
                peak.detector,
                peak.channel,
                peak.retention_time_unit,
                peak.secondary_retention_time_unit,
                peak.area_unit,
            )
            grouped.setdefault(identity, []).append(peak)
        for identity, peaks in grouped.items():
            maximum_peaks = max(maximum_peaks, len(peaks))
            rows_with_peaks.append((identity, peaks))
    if not rows_with_peaks:
        return None
    dynamic_headers = tuple(
        header
        for index in range(1, maximum_peaks + 1)
        for header in (f"peak_{index}_rt1", f"peak_{index}_rt2", f"peak_{index}_area")
    )
    rows = tuple(
        (
            *identity,
            *(
                value
                for peak in peaks
                for value in (
                    peak.retention_time,
                    peak.secondary_retention_time,
                    peak.area,
                )
            ),
            *(None for _ in range(3 * (maximum_peaks - len(peaks)))),
        )
        for identity, peaks in rows_with_peaks
    )
    return _SheetData("Peak_Order_Matrix_2D", (*fixed_headers, *dynamic_headers), rows)


def _metadata_data(result: BatchResult) -> _SheetData:
    headers = ("sample_id", "source_file", "namespace", "key", "value", "unit", "source")
    entries: tuple[MetadataEntry, ...] = tuple(
        entry
        for item in result.files
        if _successful(item) and item.bundle is not None
        for entry in item.bundle.metadata
    )
    rows = tuple(
        (
            entry.sample_id,
            entry.source_file,
            entry.namespace,
            entry.key,
            entry.value,
            entry.unit,
            entry.source,
        )
        for entry in entries
    )
    return _SheetData("Metadata", headers, rows)


def _import_log_data(result: BatchResult) -> _SheetData:
    base_headers = (
        "source_file",
        "detected_format",
        "adapter",
        "adapter_version",
        "status",
        "warning_code",
        "error_code",
        "message",
        "sort_key",
        "sha256",
    )
    has_profile_routes = result.options.peak_table_mapping_set_id is not None
    headers = (
        *base_headers,
        *(
            (
                "conversion_route",
                "mapping_profile_id",
                "structure_fingerprint",
                "mapping_diagnostic_candidates",
                "mapping_diagnostic_categories",
            )
            if has_profile_routes
            else ()
        ),
    )
    rows = []
    for item in result.files:
        warnings = [issue for issue in item.issues if issue.severity.value == "warning"]
        errors = [issue for issue in item.issues if issue.severity.value == "error"]
        row: tuple[Any, ...] = (
            workbook_audit_display(item.source.public_reference),
            item.source.detected_format,
            item.adapter_id,
            item.adapter_version,
            item.status.value,
            ";".join(issue.code for issue in warnings),
            ";".join(issue.code for issue in errors),
            " | ".join(issue.message for issue in item.issues),
            None if item.sort_key is None else workbook_audit_display(item.sort_key),
            item.source.sha256,
        )
        if has_profile_routes:
            row = (
                *row,
                item.mapping_route,
                item.mapping_profile_id,
                item.mapping_structure_fingerprint,
                len(item.mapping_diagnostics),
                ";".join(
                    sorted(
                        {
                            category.value
                            for diagnostic in item.mapping_diagnostics
                            for category in diagnostic.categories
                        }
                    )
                ),
            )
        rows.append(row)
    return _SheetData("Import_Log", headers, tuple(rows))


def _signal_data(result: BatchResult) -> tuple[_SheetData, ...]:
    groups: dict[tuple[SeriesKind, str | None, str | None], list[tuple[Any, ...]]] = {}
    for item in result.files:
        if not _successful(item) or item.bundle is None:
            continue
        for signal in item.bundle.signals:
            rows = groups.setdefault((signal.series_kind, signal.channel, signal.detector), [])
            rows.extend(_signal_rows(signal))
    datasets = []
    for (series_kind, channel, detector), rows in groups.items():
        label = detector or channel or "Unknown"
        is_records = series_kind is SeriesKind.DECODED_RECORDS
        headers: tuple[str, ...] = (
            "sample_id",
            "source_file",
            "channel",
            "detector",
            "x",
            "x_label",
            "x_unit",
            "y",
            "y_label",
            "y_unit",
        )
        if is_records:
            headers = (*headers, "series_kind")
        datasets.append(
            _SheetData(
                f"Signals_Records_{label}" if is_records else f"Signals_{label}",
                headers,
                tuple(rows),
            )
        )
    return tuple(datasets)


def _signal_rows(signal: SignalSeries) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for x_value, y_value in zip(signal.x_values, signal.y_values, strict=True):
        row: tuple[Any, ...] = (
            signal.sample_id,
            signal.source_file,
            signal.channel,
            signal.detector,
            x_value,
            signal.x_label,
            signal.x_unit,
            y_value,
            signal.y_label,
            signal.y_unit,
        )
        if signal.series_kind is SeriesKind.DECODED_RECORDS:
            row = (*row, signal.series_kind.value)
        rows.append(row)
    return rows


def _column_segments(sheet: _SheetData) -> tuple[_SheetData, ...]:
    if len(sheet.headers) <= MAX_EXCEL_COLUMNS:
        return (sheet,)
    column_groups = {
        "Peak_Matrix": (1, 1),
        "Peak_Order_Matrix": (7, 2),
        "Peak_Order_Matrix_2D": (8, 3),
    }
    if sheet.logical_name not in column_groups:
        raise ExportLimitError(
            "EXCEL_COLUMN_LIMIT",
            f"Sheet {sheet.logical_name!r} requires {len(sheet.headers)} columns.",
        )
    fixed_columns, atomic_columns = column_groups[sheet.logical_name]
    if MAX_EXCEL_COLUMNS < fixed_columns + atomic_columns:
        raise ExportLimitError("EXCEL_COLUMN_LIMIT", "Excel column capacity is too small.")
    capacity = MAX_EXCEL_COLUMNS - fixed_columns
    capacity -= capacity % atomic_columns
    segments = []
    fixed_headers = sheet.headers[:fixed_columns]
    data_headers = sheet.headers[fixed_columns:]
    for start in range(0, len(data_headers), capacity):
        selected = data_headers[start : start + capacity]
        rows = tuple(
            (
                *row[:fixed_columns],
                *row[fixed_columns + start : fixed_columns + start + len(selected)],
            )
            for row in sheet.rows
        )
        segments.append(_SheetData(sheet.logical_name, (*fixed_headers, *selected), rows))
    return tuple(segments)


def _physical_sheets(datasets: tuple[_SheetData, ...]) -> tuple[_PhysicalSheet, ...]:
    if MAX_EXCEL_ROWS < 2:
        raise ExportLimitError("EXCEL_ROW_LIMIT", "Excel row capacity must allow a header row.")
    used: set[str] = set()
    physical: list[_PhysicalSheet] = []
    capacity = MAX_EXCEL_ROWS - 1
    logical_counts: dict[str, int] = defaultdict(int)
    for dataset in datasets:
        for column_segment in _column_segments(dataset):
            row_chunks = max(1, math.ceil(len(column_segment.rows) / capacity))
            for chunk_index in range(row_chunks):
                start = chunk_index * capacity
                rows = column_segment.rows[start : start + capacity]
                logical_counts[dataset.logical_name] += 1
                count = logical_counts[dataset.logical_name]
                requested = (
                    dataset.logical_name if count == 1 else f"{dataset.logical_name}_{count:03d}"
                )
                name = sanitize_sheet_name(requested, used)
                physical.append(
                    _PhysicalSheet(dataset.logical_name, name, column_segment.headers, rows)
                )
    return tuple(physical)


def _cell_text(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        _validate_integer(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _validate_integer(value: int) -> None:
    if not integer_is_within_canonical_bound(value):
        raise ExportLimitError(
            "INTEGER_LIMIT_EXCEEDED",
            "Workbook data contains an integer beyond the canonical "
            f"{MAX_CANONICAL_INTEGER_DECIMAL_DIGITS}-decimal-digit limit.",
        )


def _needs_exact_integer_literal(value: int) -> bool:
    _validate_integer(value)
    return value <= -MAX_EXCEL_EXACT_INTEGER_ABS or value >= MAX_EXCEL_EXACT_INTEGER_ABS


def _check_cells(sheets: tuple[_PhysicalSheet, ...]) -> None:
    for sheet in sheets:
        for row_number, row in enumerate((sheet.headers, *sheet.rows), start=1):
            for column_number, value in enumerate(row, start=1):
                if isinstance(value, int) and not isinstance(value, bool):
                    _validate_integer(value)
                    continue
                if value is None or isinstance(value, float):
                    continue
                text = _cell_text(value)
                _validate_workbook_text(
                    text,
                    location=f"{sheet.name}!R{row_number}C{column_number}",
                )
                if len(text) > MAX_EXCEL_CELL_CHARACTERS:
                    raise ExportLimitError(
                        "EXCEL_CELL_TEXT_LIMIT",
                        f"Cell {sheet.name}!R{row_number}C{column_number} exceeds the Excel "
                        "text limit.",
                    )


def _write_cell(
    worksheet: Any,
    row: int,
    column: int,
    value: Any,
    cell_format: Any | None = None,
) -> tuple[int, int, int]:
    """Write strings literally and non-finite numbers visibly; return safety counters."""
    format_arg = () if cell_format is None else (cell_format,)
    if value is None:
        worksheet.write_blank(row, column, None, *format_arg)
        return (0, 0, 0)
    if isinstance(value, bool):
        worksheet.write_boolean(row, column, value, *format_arg)
        return (0, 0, 0)
    if isinstance(value, int):
        if _needs_exact_integer_literal(value):
            worksheet.write_string(row, column, str(value), *format_arg)
            return (0, 0, 1)
        worksheet.write_number(row, column, value, *format_arg)
        return (0, 0, 0)
    if isinstance(value, float):
        if math.isfinite(value):
            worksheet.write_number(row, column, value, *format_arg)
            return (0, 0, 0)
        worksheet.write_string(row, column, str(value), *format_arg)
        return (0, 1, 0)
    text = _cell_text(value)
    worksheet.write_string(row, column, text, *format_arg)
    return (int(text.startswith(_FORMULA_PREFIXES)), 0, 0)


def _presentation_for(sheet: _PhysicalSheet) -> _SheetPresentation:
    logical_name = sheet.logical_name
    if logical_name == "Manifest":
        return _SheetPresentation(
            default_width=18,
            width_overrides=((0, 0, 34), (1, 1, 60), (2, 2, 30)),
        )
    if logical_name == "Samples":
        return _SheetPresentation(
            freeze_columns=2,
            filter_columns=len(sheet.headers),
            default_width=15,
            width_overrides=(
                (1, 1, 22),
                (2, 3, 30),
                (7, 7, 24),
                (8, 8, 28),
                (13, 13, 18),
            ),
            activate=True,
        )
    if logical_name == "Peaks":
        return _SheetPresentation(
            freeze_columns=2,
            filter_columns=len(sheet.headers),
            default_width=14,
            width_overrides=(
                (0, 1, 24),
                (4, 4, 16),
                (5, 6, 22),
                (9, 10, 22),
                (12, 12, 18),
                (13, 17, 20),
                (18, 19, 30),
            ),
        )
    if logical_name == "Metadata":
        return _SheetPresentation(
            freeze_columns=2,
            filter_columns=len(sheet.headers),
            default_width=18,
            width_overrides=((0, 1, 24), (3, 3, 24), (4, 4, 36), (6, 6, 32)),
        )
    if logical_name == "Import_Log":
        return _SheetPresentation(
            freeze_columns=1,
            filter_columns=len(sheet.headers),
            default_width=18,
            width_overrides=((0, 0, 30), (7, 7, 48), (9, 9, 18)),
        )
    if logical_name == "Peak_Matrix":
        return _SheetPresentation(
            freeze_columns=1,
            filter_columns=min(1, len(sheet.headers)),
            default_width=12,
            width_overrides=((0, 0, 22),),
        )
    if logical_name == "Peak_Order_Matrix":
        return _SheetPresentation(
            freeze_columns=7,
            filter_columns=min(7, len(sheet.headers)),
            default_width=12,
            width_overrides=((0, 2, 22), (3, 4, 16), (5, 6, 22)),
        )
    if logical_name == "Peak_Order_Matrix_2D":
        return _SheetPresentation(
            freeze_columns=8,
            filter_columns=min(8, len(sheet.headers)),
            default_width=12,
            width_overrides=((0, 2, 22), (3, 4, 16), (5, 7, 24)),
        )
    if logical_name.startswith("Signals_"):
        return _SheetPresentation(
            freeze_columns=4,
            filter_columns=min(4, len(sheet.headers)),
            default_width=14,
            width_overrides=((0, 1, 22), (2, 3, 16)),
        )
    return _SheetPresentation(filter_columns=len(sheet.headers))


def _apply_sheet_presentation(worksheet: Any, sheet: _PhysicalSheet) -> bool:
    presentation = _presentation_for(sheet)
    if sheet.headers:
        worksheet.freeze_panes(1, min(presentation.freeze_columns, len(sheet.headers)))
        worksheet.set_column(0, len(sheet.headers) - 1, presentation.default_width)
        for first, last, width in presentation.width_overrides:
            if first < len(sheet.headers):
                worksheet.set_column(first, min(last, len(sheet.headers) - 1), width)
        if sheet.rows and presentation.filter_columns:
            worksheet.autofilter(
                0,
                0,
                len(sheet.rows),
                min(presentation.filter_columns, len(sheet.headers)) - 1,
            )
    return presentation.activate


def _write_physical(workbook: Any, sheets: tuple[_PhysicalSheet, ...]) -> tuple[int, int, int]:
    formula_like = 0
    nonfinite = 0
    exact_integer_literals = 0
    header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "bottom": 1})
    activated = False
    for sheet in sheets:
        worksheet = workbook.add_worksheet(sheet.name)
        should_activate = _apply_sheet_presentation(worksheet, sheet)
        if should_activate and not activated:
            worksheet.activate()
            activated = True
        for column, header in enumerate(sheet.headers):
            formula_count, numeric_count, integer_count = _write_cell(
                worksheet,
                0,
                column,
                header,
                header_format,
            )
            formula_like += formula_count
            nonfinite += numeric_count
            exact_integer_literals += integer_count
        for row_number, row in enumerate(sheet.rows, start=1):
            for column, value in enumerate(row):
                formula_count, numeric_count, integer_count = _write_cell(
                    worksheet, row_number, column, value
                )
                formula_like += formula_count
                nonfinite += numeric_count
                exact_integer_literals += integer_count
    return formula_like, nonfinite, exact_integer_literals


def _sidecar_safe(value: Any) -> tuple[str, int]:
    if value is None:
        return "", 0
    text = _cell_text(value)
    if not isinstance(value, Number) and text.startswith(_FORMULA_PREFIXES):
        return "'" + text, 1
    return text, 0


def _sidecar_final_path(dataset: _SheetData, output: Path, index: int) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", dataset.logical_name).strip("_") or "data"
    return output.with_name(f"{output.stem}_{safe_name}_{index:03d}.csv")


def _write_sidecar_temp(
    dataset: _SheetData,
    final: Path,
    *,
    temporary_directory: Path | None = None,
    owned_files: dict[str, tuple[int, int]] | None = None,
) -> tuple[Path, Path, SidecarRecord]:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", dataset.logical_name).strip("_") or "data"
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=f".ordifile_{safe_name}_",
        suffix=".csv.tmp",
        dir=temporary_directory or final.parent,
    )
    temporary_stat = os.fstat(descriptor)
    if owned_files is not None:
        owned_files[Path(raw_temp).name] = (
            temporary_stat.st_dev,
            temporary_stat.st_ino,
        )
    temporary = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            escape_count = 0
            safe_headers = []
            for header in dataset.headers:
                safe_header, escaped = _sidecar_safe(header)
                safe_headers.append(safe_header)
                escape_count += escaped
            writer.writerow(safe_headers)
            for row in dataset.rows:
                safe_row = []
                for value in row:
                    safe_value, escaped = _sidecar_safe(value)
                    safe_row.append(safe_value)
                    escape_count += escaped
                writer.writerow(safe_row)
        record = SidecarRecord(
            final.name,
            len(dataset.rows),
            sha256_file(temporary),
            escape_count,
        )
        return temporary, final, record
    except BaseException:
        if owned_files is None:
            temporary.unlink(missing_ok=True)
        raise


def _manifest_data(
    result: BatchResult,
    sheet_names: tuple[str, ...],
    sidecars: tuple[SidecarRecord, ...],
    *,
    include_signals: bool,
    split: bool,
    formula_like: int,
    nonfinite: int,
    exact_integer_literals: int,
) -> _SheetData:
    summary = summarize_conversion(result)

    def bounded_summary(severity: str) -> tuple[str, int]:
        codes = sorted(
            {
                issue.code
                for item in result.files
                for issue in item.issues
                if issue.severity.value == severity
            }
        )
        shown = codes[:MAX_MANIFEST_SUMMARY_CODES]
        omitted = len(codes) - len(shown)
        return "; ".join(shown), omitted

    warning_summary, warning_summary_omitted = bounded_summary("warning")
    error_summary, error_summary_omitted = bounded_summary("error")
    rows: list[tuple[Any, ...]] = [
        ("ordifile_version", __version__, None, None, None),
        ("generated_at_utc", datetime.now(UTC).isoformat(), None, None, None),
        ("input_file_count", len(result.files), None, None, None),
        ("success_count", result.success_count, None, None, None),
        ("warning_file_count", result.warning_count, None, None, None),
        ("failure_count", result.failure_count, None, None, None),
        ("duplicate_count", result.duplicate_count, None, None, None),
        ("skipped_count", summary.skipped_sources, None, None, None),
        (
            "result_summary_schema_version",
            CONVERSION_RESULT_SUMMARY_SCHEMA_VERSION,
            None,
            None,
            None,
        ),
        ("sample_record_count", summary.sample_records, None, None, None),
        ("peak_record_count", summary.peak_records, None, None, None),
        (
            "scientific_signal_series_count",
            summary.scientific_signal_series,
            None,
            None,
            None,
        ),
        (
            "structural_record_series_count",
            summary.structural_record_series,
            None,
            None,
            None,
        ),
        ("sort_requested", result.sort.requested.value, None, None, None),
        ("sort_effective", result.sort.effective.value, None, None, None),
        ("sort_reason", result.sort.reason, None, None, None),
        (
            "conversion_options_policy",
            "Immutable snapshot of behavior-affecting public conversion options.",
            None,
            None,
            None,
        ),
        ("option_recursive", str(result.options.recursive), None, None, None),
        (
            "option_extensions",
            "; ".join(result.options.extensions) if result.options.extensions else "<all>",
            None,
            None,
            None,
        ),
        ("option_sort", result.options.sort.value, None, None, None),
        ("option_include_signals", str(result.options.include_signals), None, None, None),
        ("option_adapter", result.options.adapter or "<auto>", None, None, None),
        ("option_sheet", result.options.sheet or "<auto>", None, None, None),
        (
            "option_include_hidden_sheets",
            str(result.options.include_hidden_sheets),
            None,
            None,
            None,
        ),
        ("option_on_error", result.options.on_error, None, None, None),
        ("option_overwrite", str(result.options.overwrite), None, None, None),
        ("option_sidecar_mode", result.options.sidecar_mode, None, None, None),
        ("option_output_name", result.options.output_name, None, None, None),
        ("execution_mode", result.options.execution_mode.value, None, None, None),
        ("included_sheets", "; ".join(sheet_names), None, None, None),
        ("include_signals", str(include_signals), None, None, None),
        ("original_modified", "No", None, None, None),
        (
            "source_display_policy",
            "Unsafe source identity code points and literal XLSX escape tokens use reversible "
            "~uXXXXXX; encoding; literal ~ is doubled. Input bytes and SHA-256 are unchanged.",
            None,
            None,
            None,
        ),
        (
            "source_display_escape_count",
            sum(
                1
                for item in result.files
                if workbook_audit_display(item.source.public_reference)
                != item.source.public_reference
            ),
            None,
            None,
            None,
        ),
        ("data_split", str(split or bool(sidecars)), None, None, None),
        ("warning_summary", warning_summary, None, None, None),
        ("warning_summary_omitted_count", warning_summary_omitted, None, None, None),
        ("error_summary", error_summary, None, None, None),
        ("error_summary_omitted_count", error_summary_omitted, None, None, None),
        (
            "literal_string_policy",
            "All XLSX strings use write_string; formula and URL conversion are disabled.",
            None,
            None,
            None,
        ),
        ("formula_like_literal_count", formula_like, None, None, None),
        ("nonfinite_literal_count", nonfinite, None, None, None),
        (
            "exact_integer_policy",
            "Integers over 15 decimal digits are written as literal strings.",
            None,
            None,
            None,
        ),
        ("exact_integer_literal_count", exact_integer_literals, None, None, None),
    ]
    if result.options.peak_table_mapping_sha256 is not None:
        rows.extend(
            (
                (
                    "option_peak_table_mapping_sha256",
                    result.options.peak_table_mapping_sha256,
                    None,
                    None,
                    None,
                ),
                (
                    "option_peak_table_mapping_schema_version",
                    result.options.peak_table_mapping_schema_version,
                    None,
                    None,
                    None,
                ),
                (
                    "option_peak_table_source_format",
                    result.options.peak_table_source_format,
                    None,
                    None,
                    None,
                ),
            )
        )
    if result.options.peak_table_mapping_set_id is not None:
        rows.extend(
            (
                ("option_peak_table_mapping_set_id", result.options.peak_table_mapping_set_id),
                (
                    "option_peak_table_mapping_set_schema_version",
                    result.options.peak_table_mapping_set_schema_version,
                ),
                (
                    "option_peak_table_mapping_set_fingerprint",
                    result.options.peak_table_mapping_set_fingerprint,
                ),
                (
                    "option_peak_table_mapping_set_profile_count",
                    result.options.peak_table_mapping_set_profile_count,
                ),
            )
        )
    if result.options.conversion_plan_public_summary_sha256 is not None:
        rows.extend(
            (
                (
                    "conversion_plan_schema_version",
                    result.options.conversion_plan_schema_version,
                    None,
                    None,
                    None,
                ),
                (
                    "conversion_plan_public_summary_sha256",
                    result.options.conversion_plan_public_summary_sha256,
                    None,
                    None,
                    None,
                ),
            )
        )
    if result.options.conversion_recipe_public_fingerprint_sha256 is not None:
        rows.extend(
            (
                (
                    "conversion_recipe_schema_version",
                    result.options.conversion_recipe_schema_version,
                    None,
                    None,
                    None,
                ),
                (
                    "conversion_recipe_public_fingerprint_sha256",
                    result.options.conversion_recipe_public_fingerprint_sha256,
                    None,
                    None,
                    None,
                ),
            )
        )
    rows.extend(
        (
            "sidecar",
            "CSV formula-like values are apostrophe-escaped",
            item.relative_path,
            item.row_count,
            item.sha256,
            item.formula_escape_count,
        )
        for item in sidecars
    )
    return _SheetData(
        "Manifest",
        ("key", "value", "path", "row_count", "sha256", "formula_escape_count"),
        tuple(rows),
    )


def _dataset_has_overlong_text(dataset: _SheetData) -> bool:
    for row in (dataset.headers, *dataset.rows):
        for value in row:
            if isinstance(value, int) and not isinstance(value, bool):
                _validate_integer(value)
            elif (
                value is not None
                and not isinstance(value, float)
                and len(_cell_text(value)) > MAX_EXCEL_CELL_CHARACTERS
            ):
                return True
    return False


def _sidecar_eligible(dataset: _SheetData) -> bool:
    return dataset.logical_name in {
        "Peak_Matrix",
        "Peak_Order_Matrix",
        "Peak_Order_Matrix_2D",
        "Peaks",
        "Metadata",
    } or dataset.logical_name.startswith("Signals_")


def _datasets_for_workbook(
    datasets: tuple[_SheetData, ...], sidecar_datasets: tuple[_SheetData, ...]
) -> tuple[_SheetData, ...]:
    offloaded = {id(dataset) for dataset in sidecar_datasets}
    workbook_datasets: list[_SheetData] = []
    for dataset in datasets:
        if id(dataset) not in offloaded:
            workbook_datasets.append(dataset)
        elif dataset.logical_name in {
            "Peak_Matrix",
            "Peak_Order_Matrix",
            "Peak_Order_Matrix_2D",
            "Peaks",
            "Metadata",
        }:
            headers = dataset.headers
            if dataset.logical_name == "Peak_Matrix":
                # Dynamic compound names can themselves exceed Excel's cell limit.
                headers = ("sample_id", "sidecar_status")
            elif dataset.logical_name == "Peak_Order_Matrix":
                headers = (*dataset.headers[:7], "sidecar_status")
            elif dataset.logical_name == "Peak_Order_Matrix_2D":
                headers = (*dataset.headers[:8], "sidecar_status")
            workbook_datasets.append(_SheetData(dataset.logical_name, headers, ()))
    return tuple(workbook_datasets)


def _backup_path(final: Path) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix=".ordifile_backup_", dir=final.parent)
    os.close(descriptor)
    backup = Path(raw_path)
    backup.unlink()
    return backup


def _open_private_transaction_directory(
    parent: Path,
) -> tuple[Path, int | None, tuple[int, int]]:
    directory = Path(tempfile.mkdtemp(prefix=".ordifile_transaction_", dir=parent))
    if os.name == "nt":  # pragma: no cover - exercised by Windows CI
        created = os.lstat(directory)
        return directory, None, (created.st_dev, created.st_ino)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(directory, flags)
    except BaseException:
        directory.rmdir()
        raise
    created = os.fstat(descriptor)
    return directory, descriptor, (created.st_dev, created.st_ino)


def _cleanup_private_transaction_directory(
    directory: Path,
    descriptor: int | None,
    directory_identity: tuple[int, int],
    owned_files: dict[str, tuple[int, int]],
) -> None:
    """Remove only proven owned files, never recursively delete a replaced path."""
    try:
        for name, identity in owned_files.items():
            if identity[1] == 0:
                continue
            try:
                if descriptor is None:  # pragma: no cover - exercised by Windows CI
                    current = os.lstat(directory / name)
                else:
                    current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if (
                    not stat.S_ISREG(current.st_mode)
                    or (
                        current.st_dev,
                        current.st_ino,
                    )
                    != identity
                ):
                    continue
                if descriptor is None:  # pragma: no cover - exercised by Windows CI
                    os.unlink(directory / name)
                else:
                    os.unlink(name, dir_fd=descriptor)
            except OSError:
                continue
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if directory_identity[1] == 0:
        return
    try:
        current_directory = os.lstat(directory)
        if (
            not stat.S_ISDIR(current_directory.st_mode)
            or (
                current_directory.st_dev,
                current_directory.st_ino,
            )
            != directory_identity
        ):
            return
        # This is intentionally non-recursive. A non-empty directory is preserved,
        # and the owned contents were cleaned through the open descriptor above.
        directory.rmdir()
    except OSError:
        return


def _finalize_transaction(
    artifacts: tuple[tuple[Path, Path, str], ...],
    *,
    overwrite: bool,
    protected_inputs: tuple[Path, ...],
    temporary_identities: dict[str, tuple[int, int]],
) -> None:
    """Promote artifacts without clobbering and restore replaced prior targets on failure."""

    def assert_owned_temporary(temporary: Path) -> None:
        expected = temporary_identities.get(temporary.name)
        try:
            current = os.lstat(temporary)
        except OSError as error:
            raise ExportError(
                "OUTPUT_TEMP_CHANGED",
                "A private output temporary changed before finalization.",
            ) from error
        if (
            expected is None
            or expected[1] == 0
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != expected
        ):
            raise ExportError(
                "OUTPUT_TEMP_CHANGED",
                "A private output temporary changed before finalization.",
            )

    if not overwrite:
        # A native exclusive rename consumes each private temporary without a
        # path-level cleanup window and never replaces a late foreign destination.
        # Independent final names cannot be committed as one filesystem transaction.
        # If a later artifact collides, earlier Ordifile publications are deliberately
        # left in place: deleting them by name could delete a concurrently exchanged
        # foreign file.
        published = 0
        try:
            for temporary, final, alias_code in artifacts:
                _assert_artifact_is_not_input(final, protected_inputs, code=alias_code)
                assert_owned_temporary(temporary)
                _rename_no_replace(temporary, final)
                published += 1
        except FileExistsError as error:
            code = "OUTPUT_TRANSACTION_INCOMPLETE" if published else "OUTPUT_COLLISION"
            raise ExportError(
                code,
                "An output artifact appeared during finalization; no existing artifact "
                "was replaced.",
            ) from error
        except OSError as error:
            code = "OUTPUT_TRANSACTION_INCOMPLETE" if published else "OUTPUT_FINALIZATION_FAILED"
            raise ExportError(
                code,
                "Output artifacts could not be published without replacing an existing "
                "filesystem entry.",
            ) from error
        return

    backups: list[tuple[Path, Path]] = []
    finalized: list[Path] = []
    try:
        for _temporary, final, alias_code in artifacts:
            _assert_artifact_is_not_input(final, protected_inputs, code=alias_code)
            if final.exists():
                if not overwrite:
                    raise ExportError(
                        "OUTPUT_COLLISION",
                        f"Output artifact {final.name!r} appeared during finalization.",
                    )
                backup = _backup_path(final)
                backups.append((final, backup))
                os.replace(final, backup)
        for temporary, final, alias_code in artifacts:
            _assert_artifact_is_not_input(final, protected_inputs, code=alias_code)
            assert_owned_temporary(temporary)
            os.replace(temporary, final)
            finalized.append(final)
    except BaseException:
        for final in reversed(finalized):
            final.unlink(missing_ok=True)
        for final, backup in reversed(backups):
            if backup.exists():
                os.replace(backup, final)
        for temporary, _final, _alias_code in artifacts:
            temporary.unlink(missing_ok=True)
        for _final, backup in backups:
            backup.unlink(missing_ok=True)
        raise
    else:
        for _final, backup in backups:
            backup.unlink(missing_ok=True)


class ExcelExporter:
    """Write a canonical batch to one safe, ordered workbook."""

    def export(
        self,
        result: BatchResult,
        output: Path,
        *,
        overwrite: bool = False,
        include_signals: bool = False,
        sidecar_mode: str = "error",
    ) -> BatchResult:
        """Convert every ordinary planning/write failure to a structured export error."""
        if type(result) is not BatchResult:
            raise ExportError("EXPORT_INPUT_INVALID", "result must be an exact BatchResult.")
        if type(output) is not type(Path()):
            raise ExportError("EXPORT_INPUT_INVALID", "output must be an exact platform Path.")
        if type(overwrite) is not bool or type(include_signals) is not bool:
            raise ExportError(
                "EXPORT_CONFIGURATION_INVALID",
                "overwrite and include_signals must be exact boolean values.",
            )
        if type(sidecar_mode) is not str or sidecar_mode not in {"error", "csv"}:
            raise ExportError("SIDECAR_MODE_INVALID", "sidecar_mode must be 'error' or 'csv'.")
        try:
            return self._export_impl(
                result,
                output,
                overwrite=overwrite,
                include_signals=include_signals,
                sidecar_mode=sidecar_mode,
            )
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except ExportError:
            raise
        except Exception as error:
            raise ExportError(
                "WORKBOOK_PLANNING_FAILED",
                f"Workbook planning failed safely ({type(error).__name__}); no scientific "
                "value was silently altered.",
            ) from error

    def _export_impl(
        self,
        result: BatchResult,
        output: Path,
        *,
        overwrite: bool = False,
        include_signals: bool = False,
        sidecar_mode: str = "error",
    ) -> BatchResult:
        """Plan all limits, then atomically write workbook and optional CSV sidecars."""
        output = Path(output)
        if sidecar_mode not in {"error", "csv"}:
            raise ExportError("SIDECAR_MODE_INVALID", "sidecar_mode must be 'error' or 'csv'.")
        protected_inputs = tuple(
            item.source.path
            for item in result.files
            if not any(issue.code == "ORDIFILE_ARTIFACT_EXCLUDED" for issue in item.issues)
        )
        validate_primary_output_target(output, protected_inputs, overwrite=overwrite)

        peak_order_matrix = _peak_order_matrix_data(result)
        peak_order_matrix_2d = _peak_order_matrix_2d_data(result)
        base_datasets = (
            _samples_data(result),
            _peak_matrix_data(result),
            *((peak_order_matrix,) if peak_order_matrix is not None else ()),
            *((peak_order_matrix_2d,) if peak_order_matrix_2d is not None else ()),
            _peaks_data(result),
            _metadata_data(result),
            _import_log_data(result),
        )
        signal_datasets = _signal_data(result) if include_signals else ()
        datasets = tuple((*base_datasets, *signal_datasets))
        overlong_datasets = tuple(
            dataset
            for dataset in datasets
            if _sidecar_eligible(dataset) and _dataset_has_overlong_text(dataset)
        )
        sidecar_datasets = overlong_datasets if sidecar_mode == "csv" else ()
        workbook_datasets = _datasets_for_workbook(datasets, sidecar_datasets)
        planned_without_manifest = _physical_sheets(workbook_datasets)

        if len(planned_without_manifest) + 1 > MAX_WORKBOOK_SHEETS:
            if sidecar_mode != "csv":
                raise ExportLimitError(
                    "WORKBOOK_SHEET_LIMIT",
                    "The planned workbook has too many sheets; request sidecar_mode='csv'.",
                )
            sidecar_datasets = tuple(dataset for dataset in datasets if _sidecar_eligible(dataset))
            workbook_datasets = _datasets_for_workbook(datasets, sidecar_datasets)
            planned_without_manifest = _physical_sheets(workbook_datasets)
            if len(planned_without_manifest) + 1 > MAX_WORKBOOK_SHEETS:
                raise ExportLimitError(
                    "WORKBOOK_SHEET_LIMIT",
                    "Even mandatory workbook sheets exceed the configured practical limit.",
                )

        # This catches overlong mandatory cells and error-mode scientific cells before
        # any temporary or final artifact is created.
        _check_cells(planned_without_manifest)
        sidecar_finals = tuple(
            _sidecar_final_path(dataset, output, index)
            for index, dataset in enumerate(sidecar_datasets, start=1)
        )
        for final in sidecar_finals:
            if final.exists() and not overwrite:
                raise ExportError(
                    "SIDECAR_EXISTS",
                    f"Sidecar {final.name!r} already exists; pass overwrite=True to replace it.",
                )
            _assert_artifact_is_not_input(final, protected_inputs, code="SIDECAR_IS_INPUT")

        sidecar_temps: list[tuple[Path, Path, SidecarRecord]] = []
        sidecars: tuple[SidecarRecord, ...] = ()
        split = len(planned_without_manifest) > len(workbook_datasets)
        # First pass counts literal-safety cases for an accurate Manifest. No workbook is written.
        formula_like = 0
        nonfinite = 0
        exact_integer_literals = 0
        for sheet in planned_without_manifest:
            for row in (sheet.headers, *sheet.rows):
                for value in row:
                    if isinstance(value, float) and not math.isfinite(value):
                        nonfinite += 1
                    elif (
                        isinstance(value, int)
                        and not isinstance(value, bool)
                        and _needs_exact_integer_literal(value)
                    ):
                        exact_integer_literals += 1
                    elif value is not None and not isinstance(value, (int, float, bool)):
                        formula_like += int(_cell_text(value).startswith(_FORMULA_PREFIXES))
        temporary: Path | None = None
        transaction_directory, transaction_descriptor, transaction_identity = (
            _open_private_transaction_directory(output.parent)
        )
        owned_temporaries: dict[str, tuple[int, int]] = {}
        try:
            for dataset, final in zip(sidecar_datasets, sidecar_finals, strict=True):
                sidecar_temporary = _write_sidecar_temp(
                    dataset,
                    final,
                    temporary_directory=transaction_directory,
                    owned_files=owned_temporaries,
                )
                sidecar_temps.append(sidecar_temporary)
            sidecars = tuple(item[2] for item in sidecar_temps)
            physical_names = ("Manifest", *(sheet.name for sheet in planned_without_manifest))
            manifest = _manifest_data(
                result,
                tuple(physical_names),
                sidecars,
                include_signals=include_signals,
                split=split,
                formula_like=formula_like,
                nonfinite=nonfinite,
                exact_integer_literals=exact_integer_literals,
            )
            physical = _physical_sheets((manifest,)) + planned_without_manifest
            _check_cells(physical)

            descriptor, raw_temp = tempfile.mkstemp(
                prefix=".ordifile_workbook_",
                suffix=".xlsx.tmp",
                dir=transaction_directory,
            )
            temporary_stat = os.fstat(descriptor)
            owned_temporaries[Path(raw_temp).name] = (
                temporary_stat.st_dev,
                temporary_stat.st_ino,
            )
            temporary = Path(raw_temp)
            with os.fdopen(descriptor, "w+b") as workbook_stream:
                workbook = xlsxwriter.Workbook(
                    workbook_stream,
                    {
                        "constant_memory": True,
                        "tmpdir": os.fspath(transaction_directory),
                        "strings_to_formulas": False,
                        "strings_to_urls": False,
                        "nan_inf_to_errors": False,
                    },
                )
                try:
                    _write_physical(workbook, physical)
                finally:
                    workbook.close()
            artifacts = tuple((item[0], item[1], "SIDECAR_IS_INPUT") for item in sidecar_temps) + (
                (temporary, output, "OUTPUT_IS_INPUT"),
            )
            _finalize_transaction(
                artifacts,
                overwrite=overwrite,
                protected_inputs=protected_inputs,
                temporary_identities=owned_temporaries,
            )
        except (KeyboardInterrupt, SystemExit, MemoryError):
            _cleanup_private_transaction_directory(
                transaction_directory,
                transaction_descriptor,
                transaction_identity,
                owned_temporaries,
            )
            raise
        except Exception as error:
            _cleanup_private_transaction_directory(
                transaction_directory,
                transaction_descriptor,
                transaction_identity,
                owned_temporaries,
            )
            if isinstance(error, ExportError):
                raise
            raise ExportError(
                "WORKBOOK_WRITE_FAILED",
                f"Could not write workbook ({type(error).__name__}); check output permissions "
                "and available storage.",
            ) from error
        except BaseException:
            _cleanup_private_transaction_directory(
                transaction_directory,
                transaction_descriptor,
                transaction_identity,
                owned_temporaries,
            )
            raise
        else:
            _cleanup_private_transaction_directory(
                transaction_directory,
                transaction_descriptor,
                transaction_identity,
                owned_temporaries,
            )
        return replace(
            result,
            output_path=output,
            sheets=tuple(sheet.name for sheet in physical),
            sidecars=sidecars,
        )
