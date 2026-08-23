# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Typed, data-only contract for user-supplied generic peak-table mappings."""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
import tempfile
import unicodedata
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from ordifile.core.errors import OrdifileError
from ordifile.core.workbook_text import workbook_audit_display, workbook_cell_text_is_exact

PEAK_MAPPING_SCHEMA_VERSION = 1
PEAK_MAPPING_PROFILE_SCHEMA_VERSION = 1
PEAK_MAPPING_SET_SCHEMA_VERSION = 1
PEAK_MAPPING_FINGERPRINT_SCHEMA_VERSION = 1
PEAK_MAPPING_DRIFT_SCHEMA_VERSION = 1
MAX_PEAK_MAPPING_BYTES = 64 * 1024
MAX_PEAK_MAPPING_PROFILE_BYTES = 128 * 1024
MAX_PEAK_MAPPING_SET_BYTES = 4 * 1024 * 1024
MAX_PEAK_MAPPING_PROFILES = 32
MAX_PEAK_MAPPING_DRIFT_CANDIDATES = 3
MAX_PEAK_MAPPING_PROFILE_LABEL_CHARACTERS = 128
MAX_PEAK_MAPPING_PROFILE_LABEL_BYTES = 512
MAX_PEAK_PREVIEW_COLUMNS = 1_024
MAX_PEAK_PREVIEW_ROWS = 10
MAX_PEAK_PREVIEW_CELLS = MAX_PEAK_PREVIEW_COLUMNS * (MAX_PEAK_PREVIEW_ROWS + 1)
MAX_PEAK_PREVIEW_CELL_CHARACTERS = 32_767
MAX_PEAK_PREVIEW_TOTAL_CHARACTERS = 1_000_000
MAX_PEAK_PREVIEW_LINE_BYTES = 256 * 1024
MAX_PEAK_PREVIEW_READ_BYTES = 2 * 1024 * 1024
MAX_PEAK_TABLE_HEADER_ROW = 100
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
_PROFILE_ID = re.compile(r"profile-[0-9a-f]{32}\Z")
_MAPPING_SET_ID = re.compile(r"profile-set-[0-9a-f]{32}\Z")


class PeakTableFormat(StrEnum):
    """Existing audited generic containers available to explicit mappings."""

    CSV = "csv"
    TSV = "tsv"
    SEMICOLON = "semicolon"
    XLSX = "xlsx"


class PeakTableTextEncoding(StrEnum):
    """Bounded text encodings available to explicit generic mappings."""

    UTF8 = "utf-8-sig"
    CP949 = "cp949"
    WINDOWS_1252 = "windows-1252"

    @property
    def codec_name(self) -> str:
        """Return the fixed Python codec without performing charset detection."""
        return self.value


@dataclass(frozen=True, slots=True)
class PeakTableImportSettings:
    """Explicit structural reading choices; never scientific column meanings."""

    text_encoding: PeakTableTextEncoding = PeakTableTextEncoding.UTF8
    header_row: int = 1

    def __post_init__(self) -> None:
        if type(self.text_encoding) is not PeakTableTextEncoding:
            raise _mapping_error("text_encoding must be utf-8-sig, cp949, or windows-1252.")
        if (
            type(self.header_row) is not int
            or self.header_row < 1
            or self.header_row > MAX_PEAK_TABLE_HEADER_ROW
        ):
            raise _mapping_error(
                f"header_row must be an integer from 1 through {MAX_PEAK_TABLE_HEADER_ROW}."
            )

    @property
    def is_default(self) -> bool:
        """Return whether the settings preserve the original clean-table contract."""
        return self.text_encoding is PeakTableTextEncoding.UTF8 and self.header_row == 1

    def to_dict(self) -> dict[str, object]:
        """Return one deterministic data-only representation."""
        return {
            "text_encoding": self.text_encoding.value,
            "header_row": self.header_row,
        }

    @classmethod
    def from_value(cls, value: object) -> PeakTableImportSettings:
        """Parse a strict optional schema extension."""
        if type(value) is not dict:
            raise _mapping_error("import_settings must be an object.")
        payload = cast(dict[object, object], value)
        if set(payload) != {"text_encoding", "header_row"}:
            raise _mapping_error(
                "import_settings must contain exactly text_encoding and header_row."
            )
        raw_encoding = payload["text_encoding"]
        raw_header_row = payload["header_row"]
        if type(raw_encoding) is not str:
            raise _mapping_error("text_encoding must be text.")
        try:
            encoding = PeakTableTextEncoding(raw_encoding)
        except ValueError as error:
            raise _mapping_error(
                "text_encoding must be utf-8-sig, cp949, or windows-1252."
            ) from error
        if type(raw_header_row) is not int:
            raise _mapping_error("header_row must be an integer.")
        return cls(encoding, raw_header_row)


DEFAULT_PEAK_TABLE_IMPORT_SETTINGS = PeakTableImportSettings()


class PeakMappingDriftCategory(StrEnum):
    """Fixed, non-semantic structural differences for a failed exact match."""

    HEADER_CHANGED_UNRESOLVED = "HEADER_CHANGED_UNRESOLVED"
    COLUMN_ADDED = "COLUMN_ADDED"
    COLUMN_REMOVED = "COLUMN_REMOVED"
    COLUMN_REORDERED = "COLUMN_REORDERED"
    DUPLICATE_HEADER_CHANGED = "DUPLICATE_HEADER_CHANGED"
    REQUIRED_MAPPING_COLUMN_MISSING = "REQUIRED_MAPPING_COLUMN_MISSING"
    OPTIONAL_MAPPING_COLUMN_MISSING = "OPTIONAL_MAPPING_COLUMN_MISSING"
    WORKSHEET_IDENTITY_CHANGED_UNRESOLVED = "WORKSHEET_IDENTITY_CHANGED_UNRESOLVED"
    INCOMPATIBLE_STRUCTURE = "INCOMPATIBLE_STRUCTURE"


@dataclass(frozen=True, slots=True)
class PeakMappingDriftDiagnostic:
    """Privacy-safe structural summary that can never authorize a mapping."""

    profile_id: str
    profile_structural_fingerprint: str
    source_format: PeakTableFormat
    categories: tuple[PeakMappingDriftCategory, ...]
    expected_column_count: int
    observed_column_count: int
    exact_position_matches: int
    changed_column_count: int
    added_column_count: int
    removed_column_count: int
    moved_column_count: int
    total_difference_count: int
    unresolved_required_roles: tuple[str, ...]
    unresolved_optional_roles: tuple[str, ...]
    schema_version: int = PEAK_MAPPING_DRIFT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.profile_id) is not str or _PROFILE_ID.fullmatch(self.profile_id) is None:
            raise _mapping_error("drift profile_id must be an opaque profile identifier.")
        if (
            type(self.profile_structural_fingerprint) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.profile_structural_fingerprint) is None
        ):
            raise _mapping_error("drift profile fingerprint must be a SHA-256 value.")
        if type(self.source_format) is not PeakTableFormat:
            raise _mapping_error("drift source_format must be a PeakTableFormat.")
        if not self.categories or any(
            type(category) is not PeakMappingDriftCategory for category in self.categories
        ):
            raise _mapping_error("drift categories must contain fixed category values.")
        if len(self.categories) != len(set(self.categories)):
            raise _mapping_error("drift categories cannot contain duplicates.")
        integer_fields = (
            self.expected_column_count,
            self.observed_column_count,
            self.exact_position_matches,
            self.changed_column_count,
            self.added_column_count,
            self.removed_column_count,
            self.moved_column_count,
            self.total_difference_count,
        )
        if any(type(value) is not int or value < 0 for value in integer_fields):
            raise _mapping_error("drift counts must be nonnegative integers.")
        allowed_roles = frozenset(_ROLE_BY_FIELD.values())
        for roles in (self.unresolved_required_roles, self.unresolved_optional_roles):
            if type(roles) is not tuple or any(
                type(role) is not str or role not in allowed_roles for role in roles
            ):
                raise _mapping_error("drift unresolved roles must use fixed mapping role names.")
            if len(roles) != len(set(roles)):
                raise _mapping_error("drift unresolved roles cannot contain duplicates.")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise _mapping_error("drift schema_version must be exactly 1.")


@dataclass(frozen=True, slots=True)
class PeakTablePreview:
    """Bounded local header and row preview for the mapping UI."""

    source_format: PeakTableFormat
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    sheet: str | None = None
    source_sha256: str | None = None
    import_settings: PeakTableImportSettings = DEFAULT_PEAK_TABLE_IMPORT_SETTINGS


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


def _json_text_size(text: str, *, document: str) -> int:
    """Return strict UTF-8 size without leaking an invalid Python string."""
    try:
        return len(text.encode("utf-8", errors="strict"))
    except UnicodeError as error:
        raise _mapping_error(f"{document} JSON must be valid Unicode text.") from error


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
    import_settings: PeakTableImportSettings = DEFAULT_PEAK_TABLE_IMPORT_SETTINGS

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
        if type(self.import_settings) is not PeakTableImportSettings:
            raise _mapping_error("import_settings must be a PeakTableImportSettings value.")
        if (
            self.source_format is PeakTableFormat.XLSX
            and self.import_settings.text_encoding is not PeakTableTextEncoding.UTF8
        ):
            raise _mapping_error("text_encoding is available only for text peak tables.")
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
        if not self.import_settings.is_default:
            payload["import_settings"] = self.import_settings.to_dict()
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

    @property
    def declared_headers(self) -> tuple[str, ...]:
        """Return the complete ordered local header contract for exact matching."""
        selectors = [
            selector for name in _COLUMN_FIELDS if (selector := getattr(self, name)) is not None
        ]
        selectors.extend(self.ignored_columns)
        if not selectors:
            raise _mapping_error("A peak mapping must classify at least one source column.")
        maximum = max(selector.index for selector in selectors)
        by_position = {selector.index: selector.label for selector in selectors}
        if set(by_position) != set(range(1, maximum + 1)):
            raise _mapping_error(
                "A reusable mapping profile must classify contiguous source columns."
            )
        return tuple(by_position[index] for index in range(1, maximum + 1))

    @property
    def structural_roles(self) -> tuple[str, ...]:
        """Return privacy-safe ordered role names for a public structure summary."""
        selectors: dict[int, str] = {}
        for name in _COLUMN_FIELDS:
            selector = getattr(self, name)
            if selector is not None:
                selectors[selector.index] = _ROLE_BY_FIELD[name]
        for selector in self.ignored_columns:
            selectors[selector.index] = "IGNORED"
        headers = self.declared_headers
        return tuple(selectors[index] for index in range(1, len(headers) + 1))

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
        import_settings = PeakTableImportSettings.from_value(
            payload.get("import_settings", DEFAULT_PEAK_TABLE_IMPORT_SETTINGS.to_dict())
        )
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
            import_settings=import_settings,
        )

    @classmethod
    def from_json(cls, text: str) -> PeakTableMapping:
        """Parse bounded JSON while rejecting duplicate keys and non-standard numbers."""
        if type(text) is not str:
            raise _mapping_error("Peak mapping JSON must be text.")
        if _json_text_size(text, document="Peak mapping") > MAX_PEAK_MAPPING_BYTES:
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


def _new_profile_id() -> str:
    return f"profile-{secrets.token_hex(16)}"


def _new_mapping_set_id() -> str:
    return f"profile-set-{secrets.token_hex(16)}"


def _require_profile_label(value: object) -> str:
    label = _require_mapping_text("display_label", value, optional=False)
    assert label is not None
    if (
        len(label) > MAX_PEAK_MAPPING_PROFILE_LABEL_CHARACTERS
        or len(label.encode("utf-8")) > MAX_PEAK_MAPPING_PROFILE_LABEL_BYTES
    ):
        raise _mapping_error("display_label exceeds the reusable-profile safety limit.")
    return label


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class PeakTableMappingProfile:
    """One user-approved mapping plus its exact local table structure."""

    mapping: PeakTableMapping
    display_label: str = "Mapping profile"
    profile_id: str = ""
    worksheet_title: str | None = None
    schema_version: int = PEAK_MAPPING_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.mapping) is not PeakTableMapping:
            raise _mapping_error("mapping must be a PeakTableMapping.")
        _require_profile_label(self.display_label)
        if self.profile_id == "":
            object.__setattr__(self, "profile_id", _new_profile_id())
        if type(self.profile_id) is not str or _PROFILE_ID.fullmatch(self.profile_id) is None:
            raise _mapping_error("profile_id must be an opaque Ordifile profile identifier.")
        if (
            type(self.schema_version) is not int
            or self.schema_version != PEAK_MAPPING_PROFILE_SCHEMA_VERSION
        ):
            raise _mapping_error(
                f"profile schema_version must be exactly {PEAK_MAPPING_PROFILE_SCHEMA_VERSION}."
            )
        if self.mapping.source_format is PeakTableFormat.XLSX:
            if self.worksheet_title is not None:
                _require_mapping_text("worksheet_title", self.worksheet_title, optional=False)
        elif self.worksheet_title is not None:
            raise _mapping_error("worksheet_title is available only for XLSX profiles.")
        # Profiles require a complete, contiguous structural contract.
        declared_headers = self.mapping.declared_headers
        if not declared_headers:
            raise _mapping_error("A reusable mapping profile requires source columns.")
        if len(self.to_json().encode("utf-8")) > MAX_PEAK_MAPPING_PROFILE_BYTES:
            raise _mapping_error(
                f"The normalized mapping profile exceeds the "
                f"{MAX_PEAK_MAPPING_PROFILE_BYTES}-byte safety limit."
            )

    @property
    def exact_structure_sha256(self) -> str:
        """Return a local-only exact structure digest; never public provenance."""
        payload: dict[str, object] = {
            "source_format": self.mapping.source_format.value,
            "headers": self.mapping.declared_headers,
            "worksheet_title": self.worksheet_title,
        }
        if not self.mapping.import_settings.is_default:
            payload["import_settings"] = self.mapping.import_settings.to_dict()
        return _canonical_sha256(payload)

    @property
    def structural_fingerprint_sha256(self) -> str:
        """Return a public-safe summary without header labels, values, or local names."""
        payload: dict[str, object] = {
            "fingerprint_schema_version": PEAK_MAPPING_FINGERPRINT_SCHEMA_VERSION,
            "mapping_schema_version": self.mapping.schema_version,
            "source_format": self.mapping.source_format.value,
            "column_count": len(self.mapping.declared_headers),
            "ordered_roles": self.mapping.structural_roles,
            "unit_presence": {
                "retention_time": True,
                "area": self.mapping.area_unit is not None,
                "height": self.mapping.height_unit is not None,
                "secondary_retention_time": (
                    self.mapping.secondary_retention_time_unit is not None
                ),
            },
            "worksheet_policy": (
                "EXACT_TITLE" if self.worksheet_title is not None else "SINGLE_VISIBLE"
            )
            if self.mapping.source_format is PeakTableFormat.XLSX
            else "NOT_APPLICABLE",
        }
        if not self.mapping.import_settings.is_default:
            payload["import_settings"] = self.mapping.import_settings.to_dict()
        return _canonical_sha256(payload)

    @property
    def semantic_sha256(self) -> str:
        """Return the private semantic identity used only for duplicate validation."""
        return _canonical_sha256(
            {
                "mapping": self.mapping.to_dict(),
                "worksheet_title": self.worksheet_title,
            }
        )

    def matches(
        self,
        source_format: PeakTableFormat,
        headers: tuple[str, ...],
        *,
        import_settings: PeakTableImportSettings = DEFAULT_PEAK_TABLE_IMPORT_SETTINGS,
        worksheet_title: str | None = None,
        single_visible_worksheet: bool = False,
    ) -> bool:
        """Match exact local structure without reading any scientific row values."""
        if source_format is not self.mapping.source_format:
            return False
        if import_settings != self.mapping.import_settings:
            return False
        if headers != self.mapping.declared_headers:
            return False
        if source_format is not PeakTableFormat.XLSX:
            return worksheet_title is None
        if self.worksheet_title is not None:
            return worksheet_title == self.worksheet_title
        return single_visible_worksheet

    def to_dict(self) -> dict[str, object]:
        """Return local profile configuration; labels and headers remain private."""
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "display_label": self.display_label,
            "worksheet_title": self.worksheet_title,
            "mapping": self.mapping.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, value: object) -> PeakTableMappingProfile:
        if type(value) is not dict:
            raise _mapping_error("A mapping profile must be an object.")
        payload = cast(dict[object, object], value)
        expected = {
            "schema_version",
            "profile_id",
            "display_label",
            "worksheet_title",
            "mapping",
        }
        if set(payload) != expected:
            raise _mapping_error("A mapping profile has missing or unsupported schema fields.")
        if type(payload["schema_version"]) is not int:
            raise _mapping_error("Profile schema_version must be an integer.")
        if type(payload["profile_id"]) is not str or type(payload["display_label"]) is not str:
            raise _mapping_error("Profile identifiers and display labels must be text.")
        worksheet_title = payload["worksheet_title"]
        if worksheet_title is not None and type(worksheet_title) is not str:
            raise _mapping_error("worksheet_title must be text or null.")
        return cls(
            mapping=PeakTableMapping.from_dict(payload["mapping"]),
            display_label=payload["display_label"],
            profile_id=payload["profile_id"],
            worksheet_title=worksheet_title,
            schema_version=payload["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class PeakTableMappingSet:
    """Bounded ordered collection of reusable user-approved mapping profiles."""

    profiles: tuple[PeakTableMappingProfile, ...]
    set_id: str = ""
    schema_version: int = PEAK_MAPPING_SET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.profiles) is not tuple or any(
            type(profile) is not PeakTableMappingProfile for profile in self.profiles
        ):
            raise _mapping_error("profiles must be a tuple of PeakTableMappingProfile values.")
        if not self.profiles or len(self.profiles) > MAX_PEAK_MAPPING_PROFILES:
            raise _mapping_error(
                f"A mapping set must contain from 1 through {MAX_PEAK_MAPPING_PROFILES} profiles."
            )
        if self.set_id == "":
            object.__setattr__(self, "set_id", _new_mapping_set_id())
        if type(self.set_id) is not str or _MAPPING_SET_ID.fullmatch(self.set_id) is None:
            raise _mapping_error("set_id must be an opaque Ordifile mapping-set identifier.")
        if (
            type(self.schema_version) is not int
            or self.schema_version != PEAK_MAPPING_SET_SCHEMA_VERSION
        ):
            raise _mapping_error(
                f"mapping-set schema_version must be exactly {PEAK_MAPPING_SET_SCHEMA_VERSION}."
            )
        ids = [profile.profile_id for profile in self.profiles]
        if len(ids) != len(set(ids)):
            raise _mapping_error("A mapping set cannot contain duplicate profile identifiers.")
        exact_profiles = [
            (profile.exact_structure_sha256, profile.semantic_sha256) for profile in self.profiles
        ]
        if len(exact_profiles) != len(set(exact_profiles)):
            raise _mapping_error("A mapping set cannot contain duplicate complete profiles.")
        if len(self.to_json().encode("utf-8")) > MAX_PEAK_MAPPING_SET_BYTES:
            raise _mapping_error(
                f"The normalized mapping set exceeds the {MAX_PEAK_MAPPING_SET_BYTES}-byte "
                "safety limit."
            )

    @property
    def structural_fingerprint_sha256(self) -> str:
        """Return an ordered public-safe summary independent of local labels and paths."""
        return _canonical_sha256(
            {
                "mapping_set_schema_version": self.schema_version,
                "fingerprint_schema_version": PEAK_MAPPING_FINGERPRINT_SCHEMA_VERSION,
                "profiles": [profile.structural_fingerprint_sha256 for profile in self.profiles],
            }
        )

    def match(
        self,
        source_format: PeakTableFormat,
        headers: tuple[str, ...],
        *,
        import_settings: PeakTableImportSettings = DEFAULT_PEAK_TABLE_IMPORT_SETTINGS,
        worksheet_title: str | None = None,
        single_visible_worksheet: bool = False,
    ) -> tuple[PeakTableMappingProfile, ...]:
        """Return every exact match so callers can fail closed on ambiguity."""
        return tuple(
            profile
            for profile in self.profiles
            if profile.matches(
                source_format,
                headers,
                import_settings=import_settings,
                worksheet_title=worksheet_title,
                single_visible_worksheet=single_visible_worksheet,
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "set_id": self.set_id,
            "profiles": [profile.to_dict() for profile in self.profiles],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, value: object) -> PeakTableMappingSet:
        if type(value) is not dict:
            raise _mapping_error("The mapping-set root must be an object.")
        payload = cast(dict[object, object], value)
        if set(payload) != {"schema_version", "set_id", "profiles"}:
            raise _mapping_error("The mapping set has missing or unsupported schema fields.")
        if type(payload["schema_version"]) is not int or type(payload["set_id"]) is not str:
            raise _mapping_error("Mapping-set version and identifier types are invalid.")
        raw_profiles = payload["profiles"]
        if type(raw_profiles) is not list:
            raise _mapping_error("profiles must be an array.")
        if len(raw_profiles) > MAX_PEAK_MAPPING_PROFILES:
            raise _mapping_error("The mapping set exceeds its profile-count safety limit.")
        return cls(
            profiles=tuple(PeakTableMappingProfile.from_dict(item) for item in raw_profiles),
            set_id=payload["set_id"],
            schema_version=payload["schema_version"],
        )

    @classmethod
    def from_json(cls, text: str) -> PeakTableMappingSet:
        if type(text) is not str:
            raise _mapping_error("Mapping-set JSON must be text.")
        if _json_text_size(text, document="Mapping-set") > MAX_PEAK_MAPPING_SET_BYTES:
            raise _mapping_error("Mapping-set JSON exceeds its byte safety limit.")

        def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in pairs:
                if key in result:
                    raise _mapping_error("Mapping-set JSON contains a duplicate object key.")
                result[key] = item
            return result

        def invalid_constant(_value: str) -> None:
            raise _mapping_error("Mapping-set JSON contains a non-standard numeric constant.")

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
                "Mapping-set JSON is malformed or exceeds nesting limits."
            ) from error
        return cls.from_dict(decoded)


def clone_peak_table_mapping_profile(
    mapping_set: PeakTableMappingSet,
    *,
    parent_profile_id: str,
    observed_preview: PeakTablePreview,
    repaired_mapping: PeakTableMapping,
    display_label: str,
) -> PeakTableMappingSet:
    """Add one user-confirmed repaired profile without mutating its parent or source set."""
    if type(mapping_set) is not PeakTableMappingSet:
        raise _mapping_error("mapping_set must be a PeakTableMappingSet.")
    if type(parent_profile_id) is not str:
        raise _mapping_error("parent_profile_id must be text.")
    parent = next(
        (profile for profile in mapping_set.profiles if profile.profile_id == parent_profile_id),
        None,
    )
    if parent is None:
        raise OrdifileError(
            "PEAK_MAPPING_REPAIR_PARENT_MISSING",
            "The selected repair parent is not present in the immutable mapping set.",
        )
    if type(observed_preview) is not PeakTablePreview:
        raise _mapping_error("observed_preview must be a PeakTablePreview.")
    if type(repaired_mapping) is not PeakTableMapping:
        raise _mapping_error("repaired_mapping must be a PeakTableMapping.")
    if parent.mapping.source_format is not observed_preview.source_format:
        raise OrdifileError(
            "PEAK_MAPPING_REPAIR_FORMAT_MISMATCH",
            "The repair preview format does not match the selected parent profile.",
        )
    if repaired_mapping.source_format is not observed_preview.source_format:
        raise OrdifileError(
            "PEAK_MAPPING_REPAIR_FORMAT_MISMATCH",
            "The repaired mapping format does not match the observed table.",
        )
    if repaired_mapping.source_format is PeakTableFormat.XLSX:
        if type(observed_preview.sheet) is not str or not observed_preview.sheet:
            raise OrdifileError(
                "PEAK_MAPPING_REPAIR_WORKSHEET_REQUIRED",
                "An XLSX repair requires one explicitly previewed worksheet title.",
            )
    elif observed_preview.sheet is not None:
        raise OrdifileError(
            "PEAK_MAPPING_REPAIR_WORKSHEET_INVALID",
            "A non-XLSX repair cannot contain a worksheet title.",
        )
    if repaired_mapping.declared_headers != observed_preview.headers:
        raise OrdifileError(
            "PEAK_MAPPING_REPAIR_STRUCTURE_MISMATCH",
            "The repaired mapping does not classify the exact observed table structure.",
        )
    if repaired_mapping.import_settings != observed_preview.import_settings:
        raise OrdifileError(
            "PEAK_MAPPING_REPAIR_IMPORT_SETTINGS_MISMATCH",
            "The repaired mapping does not use the explicitly previewed table settings.",
        )
    repaired_mapping.semantic_headers(observed_preview.headers)
    worksheet_title = (
        observed_preview.sheet if repaired_mapping.source_format is PeakTableFormat.XLSX else None
    )
    existing_matches = mapping_set.match(
        observed_preview.source_format,
        observed_preview.headers,
        import_settings=observed_preview.import_settings,
        worksheet_title=observed_preview.sheet,
        single_visible_worksheet=observed_preview.source_format is PeakTableFormat.XLSX,
    )
    if existing_matches:
        raise OrdifileError(
            "PEAK_MAPPING_REPAIR_AMBIGUOUS",
            "The repaired structure is already claimed by a mapping profile.",
        )
    profile = PeakTableMappingProfile(
        repaired_mapping,
        display_label=display_label,
        worksheet_title=worksheet_title,
    )
    updated = replace(mapping_set, profiles=(*mapping_set.profiles, profile))
    matches = updated.match(
        observed_preview.source_format,
        observed_preview.headers,
        import_settings=observed_preview.import_settings,
        worksheet_title=observed_preview.sheet,
        single_visible_worksheet=observed_preview.source_format is PeakTableFormat.XLSX,
    )
    if tuple(item.profile_id for item in matches) != (profile.profile_id,):
        raise OrdifileError(
            "PEAK_MAPPING_REPAIR_AMBIGUOUS",
            "The repaired profile would make exact mapping selection ambiguous.",
        )
    return updated


def load_peak_table_mapping(path: str | os.PathLike[str]) -> PeakTableMapping:
    """Load one bounded mapping file without recording its local path in provenance."""
    candidate = Path(path)
    if candidate.is_symlink():
        raise _mapping_error("Peak mapping files must not be symbolic links.")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
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
            try:
                os.unlink(temporary)
            except OSError:
                try:
                    os.unlink(temporary)
                except OSError as retry_error:
                    raise _mapping_error(
                        "Peak mapping publication completed but temporary cleanup failed safely."
                    ) from retry_error
            try:
                published = os.lstat(destination)
            except OSError as error:
                raise _mapping_error(
                    "Peak mapping destination changed during publication."
                ) from error
            if (
                not stat.S_ISREG(published.st_mode)
                or (published.st_dev, published.st_ino) != temporary_identity
            ):
                raise _mapping_error("Peak mapping destination changed during publication.")
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
            except OSError:
                pass


def load_peak_table_mapping_set(path: str | os.PathLike[str]) -> PeakTableMappingSet:
    """Load one bounded mapping set without exposing its local path."""
    candidate = Path(path)
    if candidate.is_symlink():
        raise _mapping_error("Mapping-set files must not be symbolic links.")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(candidate, flags)
    except OSError as error:
        raise _mapping_error("Mapping-set file could not be read.") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise _mapping_error("Mapping-set input must be a regular file.")
        if before.st_size > MAX_PEAK_MAPPING_SET_BYTES:
            raise _mapping_error("Mapping-set file exceeds its byte safety limit.")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(MAX_PEAK_MAPPING_SET_BYTES + 1)
        after = os.fstat(descriptor)
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if len(data) > MAX_PEAK_MAPPING_SET_BYTES or identity_before != identity_after:
            raise _mapping_error("Mapping-set file changed while it was being read.")
    except OSError as error:
        raise _mapping_error("Mapping-set file could not be read safely.") from error
    finally:
        os.close(descriptor)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise _mapping_error("Mapping-set file must be valid UTF-8 JSON.") from error
    return PeakTableMappingSet.from_json(text)


def save_peak_table_mapping_set(
    mapping_set: PeakTableMappingSet,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> None:
    """Save a bounded local mapping set with the existing atomic file policy."""
    if type(mapping_set) is not PeakTableMappingSet:
        raise _mapping_error("mapping_set must be a PeakTableMappingSet.")
    if type(overwrite) is not bool:
        raise _mapping_error("overwrite must be an exact boolean value.")
    destination = Path(path)
    if destination.suffix.casefold() != ".json":
        raise _mapping_error("Mapping-set files must use the .json extension.")
    if not destination.parent.is_dir():
        raise _mapping_error("The mapping-set destination directory does not exist.")

    def destination_status() -> os.stat_result | None:
        try:
            return os.lstat(destination)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise _mapping_error("The mapping-set destination could not be inspected.") from error

    current = destination_status()
    if current is not None:
        if not stat.S_ISREG(current.st_mode):
            raise _mapping_error("The mapping-set destination must be a regular file.")
        if not overwrite:
            raise OrdifileError("PEAK_MAPPING_SET_EXISTS", "The mapping-set file already exists.")
    encoded = mapping_set.to_json().encode("utf-8")
    if len(encoded) > MAX_PEAK_MAPPING_SET_BYTES:
        raise _mapping_error("The normalized mapping set exceeds its byte safety limit.")
    descriptor = -1
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".ordifile-peak-mapping-set-",
            suffix=".tmp",
            dir=destination.parent,
        )
        created = os.fstat(descriptor)
        if not stat.S_ISREG(created.st_mode):
            raise _mapping_error("The owned mapping-set temporary file is not regular.")
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
                raise _mapping_error("The mapping-set destination must be a regular file.")
            os.replace(temporary, destination)
            temporary_name = None
        else:
            try:
                os.link(temporary, destination, follow_symlinks=False)
            except FileExistsError as error:
                raise OrdifileError(
                    "PEAK_MAPPING_SET_EXISTS", "The mapping-set file already exists."
                ) from error
            try:
                os.unlink(temporary)
            except OSError:
                try:
                    os.unlink(temporary)
                except OSError as retry_error:
                    raise _mapping_error(
                        "Mapping-set publication completed but temporary cleanup failed safely."
                    ) from retry_error
            try:
                published = os.lstat(destination)
            except OSError as error:
                raise _mapping_error(
                    "Mapping-set destination changed during publication."
                ) from error
            if (
                not stat.S_ISREG(published.st_mode)
                or (published.st_dev, published.st_ino) != temporary_identity
            ):
                raise _mapping_error("Mapping-set destination changed during publication.")
            temporary_name = None
    except (OrdifileError, KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except OSError as error:
        raise _mapping_error("Mapping-set file could not be written safely.") from error
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
            except OSError:
                pass
