# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Typed, data-only contract for user-supplied generic peak-table mappings."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unicodedata
from dataclasses import dataclass, fields
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from ordifile.core.errors import OrdifileError
from ordifile.core.workbook_text import workbook_audit_display, workbook_cell_text_is_exact

PEAK_MAPPING_SCHEMA_VERSION = 1
MAX_PEAK_MAPPING_BYTES = 64 * 1024
MAX_PEAK_PREVIEW_COLUMNS = 1_024
MAX_PEAK_PREVIEW_ROWS = 10
MAX_PEAK_PREVIEW_CELLS = MAX_PEAK_PREVIEW_COLUMNS * (MAX_PEAK_PREVIEW_ROWS + 1)
MAX_PEAK_PREVIEW_CELL_CHARACTERS = 32_767
MAX_PEAK_PREVIEW_TOTAL_CHARACTERS = 1_000_000
MAX_PEAK_PREVIEW_LINE_BYTES = 256 * 1024
MAX_PEAK_PREVIEW_READ_BYTES = 2 * 1024 * 1024
MAPPED_XLSX_SHEET_MARKER = "USER_SELECTED"

_COLUMN_FIELDS = (
    "retention_time_column",
    "area_column",
    "height_column",
    "peak_name_column",
    "compound_name_column",
    "peak_index_column",
    "detector_column",
    "channel_column",
    "sample_id_column",
    "run_id_column",
    "acquisition_time_column",
    "start_time_column",
    "end_time_column",
    "secondary_retention_time_column",
)
_TEXT_FIELDS = (
    "retention_time_unit",
    "area_unit",
    "height_unit",
    "secondary_retention_time_unit",
    "manufacturer",
    "software",
)


class PeakTableFormat(StrEnum):
    """Existing audited generic containers available to explicit mappings."""

    CSV = "csv"
    TSV = "tsv"
    SEMICOLON = "semicolon"
    XLSX = "xlsx"


@dataclass(frozen=True, slots=True)
class PeakTablePreview:
    """Bounded local header and row preview for the mapping UI."""

    source_format: PeakTableFormat
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    sheet: str | None = None


_ROLE_BY_FIELD = {
    "retention_time_column": "retention_time",
    "area_column": "area",
    "height_column": "height",
    "peak_name_column": "peak_name",
    "compound_name_column": "compound",
    "peak_index_column": "peak_number",
    "detector_column": "detector",
    "channel_column": "channel",
    "sample_id_column": "sample_id",
    "run_id_column": "run_id",
    "acquisition_time_column": "acquired_at",
    "start_time_column": "start_time",
    "end_time_column": "end_time",
    "secondary_retention_time_column": "secondary_retention_time",
}


def _mapping_error(message: str) -> OrdifileError:
    return OrdifileError("PEAK_MAPPING_INVALID", message)


def peak_preview_display(value: str) -> str:
    """Render local preview text without invisible control or directional formatting."""
    visible = "".join(
        f"\\u{ord(character):04X}"
        if unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        else character
        for character in value
    )
    return workbook_audit_display(visible)


def _require_mapping_text(name: str, value: object, *, optional: bool) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str or not value.strip():
        suffix = " or null" if optional else ""
        raise _mapping_error(f"{name} must be nonempty text{suffix}.")
    if not workbook_cell_text_is_exact(value):
        raise _mapping_error(f"{name} cannot be represented exactly in the output workbook.")
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for character in value
    ):
        raise _mapping_error(f"{name} cannot contain control or directional format characters.")
    return value


@dataclass(frozen=True, slots=True)
class ColumnSelector:
    """One exact source column identified by its one-based position and label."""

    label: str
    index: int

    def __post_init__(self) -> None:
        _require_mapping_text("column label", self.label, optional=False)
        if type(self.index) is not int or self.index < 1 or self.index > 16_384:
            raise _mapping_error("column index must be an integer from 1 through 16384.")

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON object representation."""
        return {"label": self.label, "index": self.index}

    @classmethod
    def from_value(cls, name: str, value: object) -> ColumnSelector:
        """Parse one strict selector without accepting executable or ambiguous forms."""
        if type(value) is not dict:
            raise _mapping_error(f"{name} must be an object containing label and index.")
        values = cast(dict[object, object], value)
        if set(values) != {"label", "index"}:
            raise _mapping_error(f"{name} must contain exactly label and index.")
        label = values["label"]
        index = values["index"]
        if type(label) is not str or type(index) is not int:
            raise _mapping_error(f"{name} label must be text and index must be an integer.")
        return cls(label, index)


@dataclass(frozen=True, slots=True)
class PeakTableMapping:
    """User-confirmed semantic roles for one clean generic peak table."""

    retention_time_column: ColumnSelector
    area_column: ColumnSelector
    retention_time_unit: str
    source_format: PeakTableFormat
    area_unit: str | None = None
    height_column: ColumnSelector | None = None
    height_unit: str | None = None
    peak_name_column: ColumnSelector | None = None
    compound_name_column: ColumnSelector | None = None
    peak_index_column: ColumnSelector | None = None
    detector_column: ColumnSelector | None = None
    channel_column: ColumnSelector | None = None
    sample_id_column: ColumnSelector | None = None
    run_id_column: ColumnSelector | None = None
    acquisition_time_column: ColumnSelector | None = None
    start_time_column: ColumnSelector | None = None
    end_time_column: ColumnSelector | None = None
    secondary_retention_time_column: ColumnSelector | None = None
    secondary_retention_time_unit: str | None = None
    manufacturer: str | None = None
    software: str | None = None
    ignored_columns: tuple[ColumnSelector, ...] = ()
    schema_version: int = PEAK_MAPPING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != PEAK_MAPPING_SCHEMA_VERSION
        ):
            raise _mapping_error(f"schema_version must be exactly {PEAK_MAPPING_SCHEMA_VERSION}.")
        if type(self.retention_time_column) is not ColumnSelector:
            raise _mapping_error("retention_time_column must be a ColumnSelector.")
        if type(self.area_column) is not ColumnSelector:
            raise _mapping_error("area_column must be a ColumnSelector.")
        if type(self.source_format) is not PeakTableFormat:
            raise _mapping_error("source_format must be csv, tsv, semicolon, or xlsx.")
        for name in _COLUMN_FIELDS[2:]:
            value = getattr(self, name)
            if value is not None and type(value) is not ColumnSelector:
                raise _mapping_error(f"{name} must be a ColumnSelector or null.")
        _require_mapping_text("retention_time_unit", self.retention_time_unit, optional=False)
        for name in _TEXT_FIELDS[1:]:
            _require_mapping_text(name, getattr(self, name), optional=True)
        has_secondary = self.secondary_retention_time_column is not None
        has_secondary_unit = self.secondary_retention_time_unit is not None
        if has_secondary != has_secondary_unit:
            raise _mapping_error(
                "secondary_retention_time_column and secondary_retention_time_unit must be "
                "provided together."
            )
        if self.height_column is None and self.height_unit is not None:
            raise _mapping_error("height_unit requires height_column.")
        selectors = [getattr(self, name) for name in _COLUMN_FIELDS]
        if type(self.ignored_columns) is not tuple or any(
            type(selector) is not ColumnSelector for selector in self.ignored_columns
        ):
            raise _mapping_error("ignored_columns must be a tuple of ColumnSelector values.")
        if tuple(selector.index for selector in self.ignored_columns) != tuple(
            sorted(selector.index for selector in self.ignored_columns)
        ):
            raise _mapping_error("ignored_columns must be ordered by source position.")
        selectors.extend(self.ignored_columns)
        positions = [selector.index for selector in selectors if selector is not None]
        if len(positions) != len(set(positions)):
            raise _mapping_error("Each mapped semantic role must use a different source column.")
        if len(self.to_json().encode("utf-8")) > MAX_PEAK_MAPPING_BYTES:
            raise _mapping_error(
                f"The normalized peak mapping exceeds the {MAX_PEAK_MAPPING_BYTES}-byte "
                "safety limit."
            )

    def semantic_headers(self, header: tuple[object, ...] | list[object]) -> tuple[str | None, ...]:
        """Resolve every selector against one exact header or fail without fallback."""
        mapped: list[str | None] = [None] * len(header)
        for field_name in _COLUMN_FIELDS:
            selector = getattr(self, field_name)
            if selector is None:
                continue
            if selector.index > len(header):
                raise OrdifileError(
                    "PEAK_MAPPING_COLUMN_MISSING",
                    f"Mapped column {field_name} is not present at its declared position.",
                )
            actual = header[selector.index - 1]
            actual_label = "" if actual is None else str(actual)
            if actual_label != selector.label:
                raise OrdifileError(
                    "PEAK_MAPPING_COLUMN_MISMATCH",
                    f"Mapped column {field_name} does not match its declared label and position.",
                )
            mapped[selector.index - 1] = _ROLE_BY_FIELD[field_name]
        for selector in self.ignored_columns:
            if selector.index > len(header):
                raise OrdifileError(
                    "PEAK_MAPPING_COLUMN_MISSING",
                    "An ignored column is not present at its declared position.",
                )
            actual = header[selector.index - 1]
            actual_label = "" if actual is None else str(actual)
            if actual_label != selector.label:
                raise OrdifileError(
                    "PEAK_MAPPING_COLUMN_MISMATCH",
                    "An ignored column does not match its declared label and position.",
                )
        all_selectors = [
            selector for name in _COLUMN_FIELDS if (selector := getattr(self, name)) is not None
        ]
        all_selectors.extend(self.ignored_columns)
        covered = {selector.index for selector in all_selectors}
        if covered != set(range(1, len(header) + 1)):
            raise OrdifileError(
                "PEAK_MAPPING_COLUMNS_UNCLASSIFIED",
                "Every source column must be mapped or explicitly ignored.",
            )
        return tuple(mapped)

    def to_dict(self) -> dict[str, object]:
        """Return stable selectors and provenance without source data rows or paths."""
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "source_format": self.source_format.value,
        }
        for name in _COLUMN_FIELDS:
            selector = getattr(self, name)
            payload[name] = None if selector is None else selector.to_dict()
        for name in _TEXT_FIELDS:
            payload[name] = getattr(self, name)
        payload["ignored_columns"] = [selector.to_dict() for selector in self.ignored_columns]
        return payload

    def to_json(self) -> str:
        """Serialize selectors, units, and declarations without source rows or paths."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @property
    def semantic_sha256(self) -> str:
        """Return a path-independent digest of the normalized mapping semantics."""
        encoded = json.dumps(
            self.to_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("ascii")
        return sha256(encoded).hexdigest()

    @property
    def mapped_roles(self) -> tuple[str, ...]:
        """Return stable canonical role names without exposing source headers."""
        return tuple(
            _ROLE_BY_FIELD[name] for name in _COLUMN_FIELDS if getattr(self, name) is not None
        )

    @classmethod
    def from_dict(cls, value: object) -> PeakTableMapping:
        """Build a mapping from one strict data-only object."""
        if type(value) is not dict:
            raise _mapping_error("The peak mapping root must be an object.")
        payload = cast(dict[object, object], value)
        expected = {field.name for field in fields(cls)}
        required = {
            "schema_version",
            "source_format",
            "retention_time_column",
            "area_column",
            "retention_time_unit",
            "area_unit",
        }
        missing = required - set(payload)
        unknown = set(payload) - expected
        if missing:
            raise _mapping_error("The peak mapping is missing required schema fields.")
        if unknown:
            raise _mapping_error("The peak mapping contains unsupported schema fields.")
        selectors: dict[str, ColumnSelector | None] = {}
        for name in _COLUMN_FIELDS:
            raw = payload.get(name)
            selectors[name] = None if raw is None else ColumnSelector.from_value(name, raw)
        ignored_raw = payload.get("ignored_columns", [])
        if type(ignored_raw) is not list:
            raise _mapping_error("ignored_columns must be an array.")
        ignored_columns = tuple(
            ColumnSelector.from_value("ignored_columns item", item) for item in ignored_raw
        )
        text_values: dict[str, str | None] = {}
        for name in _TEXT_FIELDS:
            raw = payload.get(name)
            if raw is not None and type(raw) is not str:
                raise _mapping_error(f"{name} must be text or null.")
            text_values[name] = raw
        schema_version = payload["schema_version"]
        if type(schema_version) is not int:
            raise _mapping_error("schema_version must be an integer.")
        source_format = payload["source_format"]
        if type(source_format) is not str:
            raise _mapping_error("source_format must be text.")
        try:
            normalized_format = PeakTableFormat(source_format)
        except ValueError as error:
            raise _mapping_error("source_format must be csv, tsv, semicolon, or xlsx.") from error
        retention_selector = selectors["retention_time_column"]
        area_selector = selectors["area_column"]
        retention_unit = text_values["retention_time_unit"]
        if retention_selector is None or area_selector is None or retention_unit is None:
            raise _mapping_error(
                "retention_time_column, area_column, and retention_time_unit cannot be null."
            )
        return cls(
            retention_time_column=retention_selector,
            area_column=area_selector,
            retention_time_unit=retention_unit,
            source_format=normalized_format,
            area_unit=text_values["area_unit"],
            height_column=selectors["height_column"],
            height_unit=text_values["height_unit"],
            peak_name_column=selectors["peak_name_column"],
            compound_name_column=selectors["compound_name_column"],
            peak_index_column=selectors["peak_index_column"],
            detector_column=selectors["detector_column"],
            channel_column=selectors["channel_column"],
            sample_id_column=selectors["sample_id_column"],
            run_id_column=selectors["run_id_column"],
            acquisition_time_column=selectors["acquisition_time_column"],
            start_time_column=selectors["start_time_column"],
            end_time_column=selectors["end_time_column"],
            secondary_retention_time_column=selectors["secondary_retention_time_column"],
            secondary_retention_time_unit=text_values["secondary_retention_time_unit"],
            manufacturer=text_values["manufacturer"],
            software=text_values["software"],
            ignored_columns=ignored_columns,
            schema_version=schema_version,
        )

    @classmethod
    def from_json(cls, text: str) -> PeakTableMapping:
        """Parse bounded JSON while rejecting duplicate keys and non-standard numbers."""
        if type(text) is not str:
            raise _mapping_error("Peak mapping JSON must be text.")
        if len(text.encode("utf-8")) > MAX_PEAK_MAPPING_BYTES:
            raise _mapping_error(
                f"Peak mapping JSON exceeds the {MAX_PEAK_MAPPING_BYTES}-byte safety limit."
            )

        def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in pairs:
                if key in result:
                    raise _mapping_error("Peak mapping JSON contains a duplicate object key.")
                result[key] = item
            return result

        def invalid_constant(_value: str) -> None:
            raise _mapping_error("Peak mapping JSON contains a non-standard numeric constant.")

        try:
            decoded = json.loads(
                text,
                object_pairs_hook=object_pairs,
                parse_constant=invalid_constant,
            )
        except OrdifileError:
            raise
        except (UnicodeError, ValueError, RecursionError) as error:
            raise _mapping_error(
                "Peak mapping JSON is malformed or exceeds nesting limits."
            ) from error
        return cls.from_dict(decoded)


def load_peak_table_mapping(path: str | os.PathLike[str]) -> PeakTableMapping:
    """Load one bounded mapping file without recording its local path in provenance."""
    candidate = Path(path)
    if candidate.is_symlink():
        raise _mapping_error("Peak mapping files must not be symbolic links.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as error:
        raise _mapping_error("Peak mapping file could not be read.") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise _mapping_error("Peak mapping input must be a regular file.")
        if before.st_size > MAX_PEAK_MAPPING_BYTES:
            raise _mapping_error(
                f"Peak mapping file exceeds the {MAX_PEAK_MAPPING_BYTES}-byte safety limit."
            )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(MAX_PEAK_MAPPING_BYTES + 1)
        after = os.fstat(descriptor)
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if len(data) > MAX_PEAK_MAPPING_BYTES or identity_before != identity_after:
            raise _mapping_error("Peak mapping file changed while it was being read.")
    except OSError as error:
        raise _mapping_error("Peak mapping file could not be read safely.") from error
    finally:
        os.close(descriptor)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise _mapping_error("Peak mapping file must be valid UTF-8 JSON.") from error
    return PeakTableMapping.from_json(text)


def save_peak_table_mapping(
    mapping: PeakTableMapping,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> None:
    """Save a mapping atomically without source data, source paths, or executable content."""
    if type(mapping) is not PeakTableMapping:
        raise _mapping_error("mapping must be a PeakTableMapping.")
    if type(overwrite) is not bool:
        raise _mapping_error("overwrite must be an exact boolean value.")
    destination = Path(path)
    if destination.suffix.casefold() != ".json":
        raise _mapping_error("Peak mapping files must use the .json extension.")
    if not destination.parent.is_dir():
        raise _mapping_error("The peak mapping destination directory does not exist.")

    def destination_status() -> os.stat_result | None:
        try:
            return os.lstat(destination)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise _mapping_error("The peak mapping destination could not be inspected.") from error

    current = destination_status()
    if current is not None:
        if not stat.S_ISREG(current.st_mode):
            raise _mapping_error("The peak mapping destination must be a regular file.")
        if not overwrite:
            raise OrdifileError("PEAK_MAPPING_EXISTS", "The peak mapping file already exists.")

    encoded = mapping.to_json().encode("utf-8")
    if len(encoded) > MAX_PEAK_MAPPING_BYTES:
        raise _mapping_error(
            f"The normalized peak mapping exceeds the {MAX_PEAK_MAPPING_BYTES}-byte safety limit."
        )
    descriptor = -1
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".ordifile-peak-mapping-",
            suffix=".tmp",
            dir=destination.parent,
        )
        created = os.fstat(descriptor)
        if not stat.S_ISREG(created.st_mode):
            raise _mapping_error("The owned peak mapping temporary file is not regular.")
        temporary_identity = (created.st_dev, created.st_ino)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        temporary = Path(temporary_name)
        if overwrite:
            current = destination_status()
            if current is not None and not stat.S_ISREG(current.st_mode):
                raise _mapping_error("The peak mapping destination must be a regular file.")
            os.replace(temporary, destination)
            temporary_name = None
        else:
            try:
                os.link(temporary, destination, follow_symlinks=False)
            except FileExistsError as error:
                raise OrdifileError(
                    "PEAK_MAPPING_EXISTS", "The peak mapping file already exists."
                ) from error
            temporary.unlink()
            temporary_name = None
    except (OrdifileError, KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except OSError as error:
        raise _mapping_error("Peak mapping file could not be written safely.") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None and temporary_identity is not None:
            try:
                remaining = os.lstat(temporary_name)
                if (
                    stat.S_ISREG(remaining.st_mode)
                    and (remaining.st_dev, remaining.st_ino) == temporary_identity
                ):
                    os.unlink(temporary_name)
            except FileNotFoundError:
                pass
