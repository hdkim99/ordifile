# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded, non-evaluating OOXML package and worksheet audit for XLSX input."""

from __future__ import annotations

import posixpath
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree.ElementTree import ParseError as XmlParseError

from defusedxml import ElementTree as DefusedElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]

from ordifile.core.errors import ParseError
from ordifile.core.workbook_text import workbook_cell_text_is_exact

XLSX_MAX_ROWS = 1_048_576
XLSX_MAX_COLUMNS = 16_384
MAX_XLSX_PHYSICAL_ROWS = 250_000
MAX_XLSX_PHYSICAL_CELLS = 1_000_000
MAX_XLSX_PROJECTED_ROW = 250_000
MAX_XLSX_PROJECTED_CELLS = 5_000_000
MAX_XLSX_XML_DEPTH = 128
MAX_XLSX_RAW_CELL_LEXEME = 32_767
MAX_XLSX_SHEET_NAME_CHARACTERS = 31
MAX_XLSX_CONTROL_XML_BYTES = 8 * 1024 * 1024

WORKBOOK_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
WORKSHEET_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
OFFICE_DOCUMENT_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)
WORKSHEET_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
)
CONTENT_TYPES_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"
PACKAGE_RELATIONSHIPS_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
SPREADSHEETML_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_DOCUMENT_RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
RELATIONSHIP_ID = f"{{{OFFICE_DOCUMENT_RELATIONSHIPS_NAMESPACE}}}id"

_CONTENT_TYPE_ELEMENTS = frozenset({"Types", "Default", "Override"})
_RELATIONSHIP_ELEMENTS = frozenset({"Relationships", "Relationship"})
_WORKBOOK_ELEMENTS = frozenset({"workbook", "workbookPr", "sheet"})
_WORKSHEET_ELEMENTS = frozenset(
    {"worksheet", "dimension", "sheetData", "row", "c", "v", "f", "is", "t", "r", "rPr"}
)

_CELL_REFERENCE = re.compile(r"([A-Z]+)([1-9][0-9]*)\Z")
_ROW_REFERENCE = re.compile(r"[1-9][0-9]*\Z")
_RANGE_REFERENCE = re.compile(r"([A-Z]+[1-9][0-9]*)(?::([A-Z]+[1-9][0-9]*))?\Z")
_DRIVE_PATH = re.compile(r"^[A-Za-z]:")
_ASCII_UNSIGNED_INTEGER = re.compile(r"[0-9]+\Z")
_OOXML_NUMERIC_LEXEME = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?\Z")
_OOXML_ISO_DATE_LEXEME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})?)?\Z"
)
_ALLOWED_CELL_TYPES = frozenset({"n", "s", "str", "inlineStr", "b", "e", "d"})
_FORMULA_ATTRIBUTES = frozenset(
    {"t", "aca", "ref", "dt2D", "dtr", "del1", "del2", "r1", "r2", "ca", "si", "bx"}
)
_FORMULA_TYPES = frozenset({"normal", "array", "dataTable", "shared"})
_FORMULA_BOOLEAN_ATTRIBUTES = frozenset({"aca", "dt2D", "dtr", "del1", "del2", "ca", "bx"})
_FORMULA_BOOLEANS = frozenset({"0", "1", "false", "true"})
_SHEET_STATES = frozenset({"visible", "hidden", "veryHidden"})
_SHEET_NAME_FORBIDDEN = frozenset("[]:*?/\\")


def _bounded_ascii_integer(value: str, *, positive: bool = False) -> bool:
    return (
        0 < len(value) <= 12
        and _ASCII_UNSIGNED_INTEGER.fullmatch(value) is not None
        and (not positive or any(character != "0" for character in value))
    )


def _require_audited_workbook_string(value: str, *, code: str, label: str) -> None:
    """Require one source-controlled string to round-trip through an XLSX cell."""
    if not workbook_cell_text_is_exact(value):
        raise ParseError(
            code,
            f"{label} exceeds the exact {MAX_XLSX_RAW_CELL_LEXEME}-character workbook "
            "boundary or contains text XLSX cannot preserve exactly.",
        )


def _validate_sheet_name(value: str) -> None:
    if (
        not value
        or len(value) > MAX_XLSX_SHEET_NAME_CHARACTERS
        or any(character in _SHEET_NAME_FORBIDDEN for character in value)
        or value.startswith("'")
        or value.endswith("'")
        or value.casefold() == "history"
    ):
        raise ParseError(
            "XLSX_SHEET_NAME_INVALID",
            "Worksheet names must be nonempty, at most 31 characters, and satisfy the "
            "portable Excel title rules.",
        )
    _require_audited_workbook_string(
        value,
        code="XLSX_SHEET_NAME_INVALID",
        label="A worksheet name",
    )


@dataclass(frozen=True, slots=True)
class XlsxAuditLimits:
    """Practical parsing bounds applied before openpyxl sees the package."""

    max_members: int
    max_uncompressed_bytes: int
    max_compression_ratio: float
    ratio_minimum_size: int


@dataclass(frozen=True, slots=True)
class RawCell:
    """Non-evaluated XML attributes and lexemes for one physical worksheet cell."""

    coordinate: str
    row: int
    column: int
    cell_type: str
    style_index: int | None
    value: str | None
    value_present: bool
    formula: str | None
    formula_present: bool
    formula_attributes: tuple[tuple[str, str], ...]
    inline_text: str | None
    shared_text: str | None


@dataclass(frozen=True, slots=True)
class WorksheetAudit:
    """Verified worksheet structure and the exact safe iteration boundary."""

    part_name: str
    declared_dimension: str
    actual_min_row: int | None
    actual_min_column: int | None
    actual_max_row: int
    actual_max_column: int
    physical_rows: int
    physical_cells: int
    dimension_mismatch: bool
    raw_cells: tuple[RawCell, ...] = ()


@dataclass(frozen=True, slots=True)
class SheetPart:
    """A workbook sheet resolved to one verified internal worksheet part."""

    index: int
    title: str
    state: str
    relationship_id: str
    part_name: str
    worksheet: WorksheetAudit


@dataclass(frozen=True, slots=True)
class XlsxPackageAudit:
    """Verified package map needed by the generic XLSX adapter."""

    members: tuple[zipfile.ZipInfo, ...]
    sheets: tuple[SheetPart, ...]
    date_1904: bool
    shared_string_count: int
    style_count: int
    shared_strings: tuple[str, ...]


@dataclass(slots=True)
class _CellState:
    coordinate: str
    row: int
    column: int
    cell_type: str
    style_index: int | None
    value: str | None = None
    value_present: bool = False
    formula: str | None = None
    formula_present: bool = False
    formula_attributes: tuple[tuple[str, str], ...] = ()
    inline_parts: list[str] | None = None
    inline_string_present: bool = False


def _local_name(tag: str) -> str:
    return tag.rpartition("}")[2]


def _qualified(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _require_root(root: Any, namespace: str, local: str, part_name: str) -> None:
    if root.tag != _qualified(namespace, local):
        raise ParseError(
            "XLSX_NAMESPACE_INVALID",
            f"OOXML part {part_name!r} does not use the required transitional {local} root.",
        )


def _semantic_local(
    element: Any, namespace: str, semantic_names: frozenset[str], part_name: str
) -> str | None:
    local = _local_name(element.tag)
    if local not in semantic_names:
        return None
    if element.tag != _qualified(namespace, local):
        raise ParseError(
            "XLSX_NAMESPACE_INVALID",
            f"OOXML semantic element {local!r} in {part_name!r} has an invalid namespace.",
        )
    return local


def _reject_attribute_namespace(element: Any, names: frozenset[str], part_name: str) -> None:
    for attribute in element.attrib:
        local = _local_name(attribute)
        if local in names and attribute != local:
            raise ParseError(
                "XLSX_NAMESPACE_INVALID",
                f"OOXML attribute {local!r} in {part_name!r} has an invalid namespace.",
            )


def _normalized_member_name(name: str) -> str:
    normalized = unicodedata.normalize("NFC", name.replace("\\", "/"))
    parts = tuple(part for part in PurePosixPath(normalized).parts if part not in ("", "."))
    return "/".join(parts).casefold()


def _unsafe_member(name: str) -> bool:
    if "\\" in name or "\x00" in name:
        return True
    normalized = unicodedata.normalize("NFC", name)
    path = PurePosixPath(normalized)
    return (
        path.is_absolute()
        or _DRIVE_PATH.match(normalized) is not None
        or any(part == ".." for part in path.parts)
    )


def _bounded_control_xml(archive: zipfile.ZipFile, name: str) -> Any:
    try:
        info = archive.getinfo(name)
    except KeyError as error:
        raise ParseError(
            "XLSX_STRUCTURE_MISSING", f"Required XLSX part {name!r} is missing."
        ) from error
    if info.file_size > MAX_XLSX_CONTROL_XML_BYTES:
        raise ParseError(
            "XLSX_CONTROL_XML_LIMIT",
            f"XLSX control part {name!r} exceeds {MAX_XLSX_CONTROL_XML_BYTES} bytes.",
        )
    try:
        root = DefusedElementTree.fromstring(archive.read(info))
    except (DefusedXmlException, OSError, ValueError, XmlParseError) as error:
        raise ParseError(
            "XLSX_XML_INVALID", f"XLSX control part {name!r} is not safe, well-formed XML."
        ) from error
    stack: list[tuple[Any, int]] = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        if depth > MAX_XLSX_XML_DEPTH:
            raise ParseError(
                "XLSX_XML_DEPTH_LIMIT",
                f"XLSX control part {name!r} exceeds XML depth {MAX_XLSX_XML_DEPTH}.",
            )
        stack.extend((child, depth + 1) for child in element)
    return root


def _column_number(letters: str) -> int:
    column = 0
    for character in letters:
        column = column * 26 + ord(character) - ord("A") + 1
        if column > XLSX_MAX_COLUMNS:
            break
    return column


def _coordinate(reference: str, *, code: str) -> tuple[int, int]:
    if len(reference) > 16:
        raise ParseError(code, "Worksheet coordinate exceeds the bounded A1 lexeme length.")
    match = _CELL_REFERENCE.fullmatch(reference)
    if match is None:
        raise ParseError(code, f"Worksheet coordinate {reference!r} is not explicit uppercase A1.")
    column = _column_number(match.group(1))
    row_text = match.group(2)
    if len(row_text) > 7:
        raise ParseError(
            "XLSX_COORDINATE_OUT_OF_RANGE",
            f"Worksheet coordinate {reference!r} is outside A1:XFD1048576.",
        )
    row = int(row_text)
    if row > XLSX_MAX_ROWS or column > XLSX_MAX_COLUMNS:
        raise ParseError(
            "XLSX_COORDINATE_OUT_OF_RANGE",
            f"Worksheet coordinate {reference!r} is outside A1:XFD1048576.",
        )
    return row, column


def _dimension_bounds(reference: str) -> tuple[int, int, int, int]:
    if len(reference) > 40:
        raise ParseError("XLSX_DIMENSION_INVALID", "Worksheet dimension lexeme is too long.")
    match = _RANGE_REFERENCE.fullmatch(reference)
    if match is None:
        raise ParseError(
            "XLSX_DIMENSION_INVALID",
            f"Worksheet dimension {reference!r} is not a valid uppercase A1 range.",
        )
    start_row, start_column = _coordinate(match.group(1), code="XLSX_DIMENSION_INVALID")
    end_row, end_column = _coordinate(
        match.group(2) or match.group(1), code="XLSX_DIMENSION_INVALID"
    )
    if end_row < start_row or end_column < start_column:
        raise ParseError(
            "XLSX_DIMENSION_INVALID", f"Worksheet dimension {reference!r} is reversed."
        )
    return start_row, start_column, end_row, end_column


def _validate_formula_attributes(element: Any, coordinate: str) -> tuple[tuple[str, str], ...]:
    """Validate the bounded transitional CT_CellFormula attribute subset."""
    attributes: list[tuple[str, str]] = []
    total_characters = 0
    for name, value in element.attrib.items():
        if name.startswith("{"):
            raise ParseError(
                "XLSX_NAMESPACE_INVALID",
                f"Cell {coordinate} formula has a namespaced attribute.",
            )
        if name not in _FORMULA_ATTRIBUTES:
            raise ParseError(
                "XLSX_FORMULA_ATTRIBUTE_INVALID",
                f"Cell {coordinate} formula has unsupported attribute {name!r}.",
            )
        _require_audited_workbook_string(
            value,
            code="XLSX_FORMULA_ATTRIBUTE_LIMIT",
            label=f"Cell {coordinate} formula attribute {name!r}",
        )
        total_characters += len(name) + len(value)
        if total_characters > MAX_XLSX_RAW_CELL_LEXEME:
            raise ParseError(
                "XLSX_FORMULA_ATTRIBUTE_LIMIT",
                f"Cell {coordinate} formula attributes exceed the bounded capture limit.",
            )
        attributes.append((name, value))
    values = dict(attributes)
    formula_type = values.get("t")
    if formula_type is not None and formula_type not in _FORMULA_TYPES:
        raise ParseError(
            "XLSX_FORMULA_ATTRIBUTE_INVALID",
            f"Cell {coordinate} formula has an invalid formula type.",
        )
    for name in _FORMULA_BOOLEAN_ATTRIBUTES:
        value = values.get(name)
        if value is not None and value not in _FORMULA_BOOLEANS:
            raise ParseError(
                "XLSX_FORMULA_ATTRIBUTE_INVALID",
                f"Cell {coordinate} formula attribute {name!r} is not an exact Boolean.",
            )
    formula_index = values.get("si")
    if formula_index is not None and not _bounded_ascii_integer(formula_index):
        raise ParseError(
            "XLSX_FORMULA_INDEX_INVALID",
            f"Cell {coordinate} has an invalid shared formula index.",
        )
    reference = values.get("ref")
    if reference is not None:
        try:
            _dimension_bounds(reference)
        except ParseError as error:
            raise ParseError(
                "XLSX_FORMULA_REFERENCE_INVALID",
                f"Cell {coordinate} formula ref is not a bounded uppercase A1 range.",
            ) from error
    for name in ("r1", "r2"):
        reference = values.get(name)
        if reference is None:
            continue
        try:
            _coordinate(reference, code="XLSX_FORMULA_REFERENCE_INVALID")
        except ParseError as error:
            raise ParseError(
                "XLSX_FORMULA_REFERENCE_INVALID",
                f"Cell {coordinate} formula attribute {name!r} is not a bounded A1 cell.",
            ) from error
    return tuple(sorted(attributes))


def _relationship_target(base_part: str, target: str) -> str:
    if (
        not target
        or "\\" in target
        or "\x00" in target
        or "?" in target
        or "#" in target
        or "%" in target
        or _DRIVE_PATH.match(target) is not None
    ):
        raise ParseError(
            "XLSX_RELATIONSHIP_UNSAFE", f"Unsafe OOXML relationship target {target!r}."
        )
    if target.startswith("/"):
        resolved = posixpath.normpath(target.lstrip("/"))
    else:
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(base_part), target))
    if resolved in ("", ".", "..") or resolved.startswith("../"):
        raise ParseError(
            "XLSX_RELATIONSHIP_UNSAFE", f"Unsafe OOXML relationship target {target!r}."
        )
    return resolved


def _content_types(archive: zipfile.ZipFile) -> dict[str, str]:
    root = _bounded_control_xml(archive, "[Content_Types].xml")
    _require_root(root, CONTENT_TYPES_NAMESPACE, "Types", "[Content_Types].xml")
    overrides: dict[str, str] = {}
    for element in root:
        local = _semantic_local(
            element,
            CONTENT_TYPES_NAMESPACE,
            _CONTENT_TYPE_ELEMENTS,
            "[Content_Types].xml",
        )
        if local not in {"Default", "Override"}:
            continue
        _reject_attribute_namespace(
            element, frozenset({"Extension", "ContentType", "PartName"}), "[Content_Types].xml"
        )
        content_type = element.attrib.get("ContentType", "")
        if "macroenabled" in content_type.casefold() or "vbaproject" in content_type.casefold():
            raise ParseError(
                "XLSX_MACRO_CONTENT_UNSUPPORTED",
                "Macro-enabled XLSX package content is not supported.",
            )
        if local != "Override":
            continue
        raw_part = element.attrib.get("PartName", "")
        if not raw_part.startswith("/"):
            raise ParseError(
                "XLSX_CONTENT_TYPE_INVALID", "OOXML override part names must be package-absolute."
            )
        part = raw_part.lstrip("/")
        key = _normalized_member_name(part)
        if key in overrides:
            raise ParseError(
                "XLSX_CONTENT_TYPE_DUPLICATE",
                f"Duplicate normalized content type override for {part!r}.",
            )
        overrides[key] = content_type
    workbook_type = overrides.get(_normalized_member_name("xl/workbook.xml"))
    if workbook_type != WORKBOOK_CONTENT_TYPE:
        raise ParseError(
            "XLSX_WORKBOOK_CONTENT_TYPE",
            "The workbook main part is not an exact non-macro .xlsx workbook content type.",
        )
    return overrides


def _relationships(
    root: Any, *, base_part: str, part_name: str
) -> dict[str, tuple[str, str, str | None]]:
    _require_root(root, PACKAGE_RELATIONSHIPS_NAMESPACE, "Relationships", part_name)
    relationships: dict[str, tuple[str, str, str | None]] = {}
    for element in root:
        local = _semantic_local(
            element,
            PACKAGE_RELATIONSHIPS_NAMESPACE,
            _RELATIONSHIP_ELEMENTS,
            part_name,
        )
        if local != "Relationship":
            continue
        _reject_attribute_namespace(
            element, frozenset({"Id", "Type", "Target", "TargetMode"}), part_name
        )
        identifier = element.attrib.get("Id", "")
        if not identifier or identifier in relationships:
            raise ParseError(
                "XLSX_RELATIONSHIP_DUPLICATE", "OOXML relationship IDs must be present and unique."
            )
        target = element.attrib.get("Target", "")
        target_mode = element.attrib.get("TargetMode")
        resolved = _relationship_target(base_part, target)
        relationships[identifier] = (element.attrib.get("Type", ""), resolved, target_mode)
    return relationships


def _string_text_payload(element: Any, label: str, limit_code: str) -> str:
    text_tag = _qualified(SPREADSHEETML_NAMESPACE, "t")
    if element.tag != text_tag:
        if _local_name(element.tag) == "t":
            raise ParseError("XLSX_NAMESPACE_INVALID", f"{label} text uses an invalid namespace.")
        raise ParseError("XLSX_STRING_STRUCTURE_INVALID", f"{label} has a non-text payload.")
    allowed_space = _qualified(XML_NAMESPACE, "space")
    if any(attribute != allowed_space for attribute in element.attrib):
        raise ParseError(
            "XLSX_STRING_STRUCTURE_INVALID",
            f"{label} text has an unsupported or incorrectly namespaced attribute.",
        )
    if element.attrib.get(allowed_space) not in {None, "default", "preserve"}:
        raise ParseError(
            "XLSX_STRING_STRUCTURE_INVALID",
            f"{label} xml:space must be exactly default or preserve.",
        )
    if len(element):
        raise ParseError(
            "XLSX_STRING_STRUCTURE_INVALID", f"{label} text cannot contain nested elements."
        )
    value = element.text or ""
    _require_audited_workbook_string(
        value,
        code=limit_code,
        label=f"{label} text payload",
    )
    return value


def _reconstruct_string_container(container: Any, label: str, limit_code: str) -> str:
    """Validate and reconstruct the supported direct or rich SpreadsheetML string tree."""
    if container.attrib:
        raise ParseError(
            "XLSX_STRING_STRUCTURE_INVALID",
            f"{label} container cannot have attributes in the supported subset.",
        )
    children = list(container)
    text_tag = _qualified(SPREADSHEETML_NAMESPACE, "t")
    run_tag = _qualified(SPREADSHEETML_NAMESPACE, "r")
    properties_tag = _qualified(SPREADSHEETML_NAMESPACE, "rPr")
    if len(children) == 1 and children[0].tag == text_tag:
        logical_text = _string_text_payload(children[0], label, limit_code)
    elif children and all(child.tag == run_tag for child in children):
        parts: list[str] = []
        for run in children:
            if run.attrib:
                raise ParseError(
                    "XLSX_STRING_STRUCTURE_INVALID",
                    f"{label} rich-text run cannot have attributes.",
                )
            run_children = list(run)
            if (
                len(run_children) == 1
                and run_children[0].tag == text_tag
                or len(run_children) == 2
                and run_children[0].tag == properties_tag
                and run_children[1].tag == text_tag
            ):
                text_element = run_children[-1]
            else:
                raise ParseError(
                    "XLSX_STRING_STRUCTURE_INVALID",
                    f"{label} rich-text run must contain optional rPr then exactly one t.",
                )
            if len(run_children) == 2:
                properties = run_children[0]
                if any(
                    not descendant.tag.startswith(f"{{{SPREADSHEETML_NAMESPACE}}}")
                    for descendant in properties.iter()
                ):
                    raise ParseError(
                        "XLSX_NAMESPACE_INVALID",
                        f"{label} rich-text properties use an invalid namespace.",
                    )
            parts.append(_string_text_payload(text_element, label, limit_code))
        logical_text = "".join(parts)
    else:
        semantic_names = {"t", "r", "rPr"}
        if any(
            _local_name(child.tag) in semantic_names
            and child.tag != _qualified(SPREADSHEETML_NAMESPACE, _local_name(child.tag))
            for child in children
        ):
            raise ParseError(
                "XLSX_NAMESPACE_INVALID", f"{label} content uses an invalid namespace."
            )
        raise ParseError(
            "XLSX_STRING_STRUCTURE_INVALID",
            f"{label} must contain one direct t or one or more rich-text runs.",
        )
    _require_audited_workbook_string(
        logical_text,
        code=limit_code,
        label=f"{label} reconstructed text",
    )
    return logical_text


def _shared_strings(archive: zipfile.ZipFile, names: dict[str, str]) -> tuple[str, ...]:
    key = _normalized_member_name("xl/sharedStrings.xml")
    actual_name = names.get(key)
    if actual_name is None:
        return ()
    root = _bounded_control_xml(archive, actual_name)
    _require_root(root, SPREADSHEETML_NAMESPACE, "sst", actual_name)
    _reject_attribute_namespace(root, frozenset({"count", "uniqueCount"}), actual_name)
    if any(attribute not in {"count", "uniqueCount"} for attribute in root.attrib):
        raise ParseError(
            "XLSX_SHARED_STRING_STRUCTURE_INVALID",
            "The shared-string table has unsupported attributes.",
        )
    for attribute in ("count", "uniqueCount"):
        declared = root.attrib.get(attribute)
        if declared is not None and not _bounded_ascii_integer(declared):
            raise ParseError(
                "XLSX_SHARED_STRING_COUNT_INVALID",
                f"Shared-string {attribute} must be a bounded ASCII integer.",
            )
    strings: list[str] = []
    si_tag = _qualified(SPREADSHEETML_NAMESPACE, "si")
    for item in root:
        if item.tag != si_tag:
            local = _local_name(item.tag)
            if local in {"si", "t", "r", "rPr"}:
                raise ParseError(
                    "XLSX_NAMESPACE_INVALID",
                    f"Shared-string semantic element {local!r} has an invalid namespace.",
                )
            raise ParseError(
                "XLSX_SHARED_STRING_STRUCTURE_INVALID",
                "The v0.1 shared-string table accepts only direct si children.",
            )
        strings.append(
            _reconstruct_string_container(item, "A shared string", "XLSX_SHARED_STRING_LIMIT")
        )
    declared_unique = root.attrib.get("uniqueCount")
    if declared_unique is not None and int(declared_unique) != len(strings):
        raise ParseError(
            "XLSX_SHARED_STRING_COUNT_MISMATCH",
            "Shared-string uniqueCount does not match the audited direct si children.",
        )
    return tuple(strings)


def _style_count(archive: zipfile.ZipFile, names: dict[str, str]) -> int:
    key = _normalized_member_name("xl/styles.xml")
    actual_name = names.get(key)
    if actual_name is None:
        return 0
    root = _bounded_control_xml(archive, actual_name)
    _require_root(root, SPREADSHEETML_NAMESPACE, "styleSheet", actual_name)
    tables: list[Any] = []
    for child in root:
        local = _local_name(child.tag)
        if local == "cellXfs" and child.tag != _qualified(SPREADSHEETML_NAMESPACE, local):
            raise ParseError(
                "XLSX_NAMESPACE_INVALID", "cellXfs has an invalid SpreadsheetML namespace."
            )
        if child.tag == _qualified(SPREADSHEETML_NAMESPACE, "cellXfs"):
            tables.append(child)
    if len(tables) != 1:
        raise ParseError(
            "XLSX_STYLE_TABLE_INVALID",
            "A styles part must contain exactly one direct cellXfs table.",
        )
    table = tables[0]
    _reject_attribute_namespace(table, frozenset({"count"}), actual_name)
    declared = table.attrib.get("count")
    if declared is None or not _bounded_ascii_integer(declared):
        raise ParseError(
            "XLSX_STYLE_COUNT_INVALID",
            "cellXfs count must be one bounded ASCII integer.",
        )
    count = 0
    for element in table:
        if _local_name(element.tag) == "xf" and element.tag != _qualified(
            SPREADSHEETML_NAMESPACE, "xf"
        ):
            raise ParseError("XLSX_NAMESPACE_INVALID", "cellXfs/xf has an invalid namespace.")
        if element.tag == _qualified(SPREADSHEETML_NAMESPACE, "xf"):
            count += 1
    if int(declared) != count:
        raise ParseError(
            "XLSX_STYLE_COUNT_MISMATCH",
            "cellXfs count does not match the audited direct xf children.",
        )
    return count


def _validate_raw_cell(
    cell: _CellState, *, shared_strings: tuple[str, ...], style_count: int
) -> RawCell:
    for label, lexeme in (
        ("value", cell.value if cell.value_present else None),
        ("inline string", "".join(cell.inline_parts or [])),
    ):
        if lexeme is not None and len(lexeme) > MAX_XLSX_RAW_CELL_LEXEME:
            raise ParseError(
                "XLSX_CELL_LEXEME_LIMIT",
                f"Cell {cell.coordinate} {label} exceeds {MAX_XLSX_RAW_CELL_LEXEME} characters.",
            )
    if cell.formula_present:
        formula_literal = "=" + (cell.formula or "")
        _require_audited_workbook_string(
            formula_literal,
            code="XLSX_FORMULA_LITERAL_LIMIT",
            label=f"Cell {cell.coordinate} exported formula literal",
        )
    if cell.cell_type not in _ALLOWED_CELL_TYPES:
        raise ParseError(
            "XLSX_CELL_TYPE_UNSUPPORTED",
            f"Cell {cell.coordinate} has unsupported OOXML type {cell.cell_type!r}.",
        )
    if cell.inline_string_present and (
        cell.cell_type != "inlineStr" or cell.value_present or cell.formula_present
    ):
        raise ParseError(
            "XLSX_CELL_VALUE_MIXED",
            f"Cell {cell.coordinate} mixes inline-string content with another value form.",
        )
    if cell.cell_type == "inlineStr" and not cell.inline_string_present:
        raise ParseError(
            "XLSX_INLINE_STRING_INVALID",
            f"Cell {cell.coordinate} declares inlineStr without one inline string payload.",
        )
    if cell.style_index is not None and (
        style_count == 0 or cell.style_index < 0 or cell.style_index >= style_count
    ):
        raise ParseError(
            "XLSX_STYLE_INDEX_INVALID",
            f"Cell {cell.coordinate} references invalid style index {cell.style_index}.",
        )
    if cell.cell_type == "s":
        if not cell.value_present or cell.value is None or not _bounded_ascii_integer(cell.value):
            raise ParseError(
                "XLSX_SHARED_STRING_INDEX_INVALID",
                f"Cell {cell.coordinate} has an invalid shared-string index.",
            )
        index = int(cell.value)
        if index >= len(shared_strings):
            raise ParseError(
                "XLSX_SHARED_STRING_INDEX_INVALID",
                f"Cell {cell.coordinate} shared-string index {index} is out of range.",
            )
    if cell.cell_type == "b" and cell.value not in {"0", "1"}:
        raise ParseError(
            "XLSX_BOOLEAN_INVALID", f"Cell {cell.coordinate} has an invalid boolean value."
        )
    if cell.cell_type == "n" and cell.value_present and not cell.formula_present:
        numeric_lexeme = cell.value or ""
        unsigned_lexeme = numeric_lexeme.lstrip("+-").casefold()
        if unsigned_lexeme in {"nan", "snan", "inf", "infinity"}:
            raise ParseError(
                "XLSX_NUMERIC_LEXEME_NONFINITE",
                f"Cell {cell.coordinate} stores a non-finite value as OOXML numeric data; "
                "use an explicit text cell to preserve that literal.",
            )
        if _OOXML_NUMERIC_LEXEME.fullmatch(numeric_lexeme) is None:
            raise ParseError(
                "XLSX_NUMERIC_LEXEME_INVALID",
                f"Cell {cell.coordinate} has an invalid OOXML numeric lexeme; numeric values "
                "must use ASCII sign, decimal, and exponent characters without whitespace.",
            )
    if cell.cell_type == "d" and not cell.formula_present and not cell.value_present:
        raise ParseError(
            "XLSX_ISO_DATE_LEXEME_INVALID",
            f"Cell {cell.coordinate} declares an ISO date without a value lexeme.",
        )
    if cell.cell_type == "d" and cell.value_present and not cell.formula_present:
        iso_lexeme = cell.value or ""
        if _OOXML_ISO_DATE_LEXEME.fullmatch(iso_lexeme) is None:
            raise ParseError(
                "XLSX_ISO_DATE_LEXEME_INVALID",
                f"Cell {cell.coordinate} has an unsupported ISO date lexeme.",
            )
        try:
            if "T" in iso_lexeme:
                datetime.fromisoformat(iso_lexeme.replace("Z", "+00:00"))
            else:
                date.fromisoformat(iso_lexeme)
        except ValueError as error:
            raise ParseError(
                "XLSX_ISO_DATE_LEXEME_INVALID",
                f"Cell {cell.coordinate} has an invalid ISO calendar date or offset.",
            ) from error
    return RawCell(
        cell.coordinate,
        cell.row,
        cell.column,
        cell.cell_type,
        cell.style_index,
        cell.value,
        cell.value_present,
        cell.formula,
        cell.formula_present,
        cell.formula_attributes,
        "".join(cell.inline_parts or []) if cell.inline_parts is not None else None,
        shared_strings[int(cell.value)]
        if cell.cell_type == "s" and cell.value is not None
        else None,
    )


def _audit_worksheet_stream(
    archive: zipfile.ZipFile,
    part_name: str,
    *,
    shared_strings: tuple[str, ...],
    style_count: int,
    capture_cells: bool,
    capture_max_row: int | None = None,
) -> WorksheetAudit:
    dimension: str | None = None
    dimension_count = 0
    sheet_data_count = 0
    inside_sheet_data = False
    current_row: int | None = None
    previous_row = 0
    previous_column = 0
    current_cell: _CellState | None = None
    physical_rows = 0
    physical_cells = 0
    min_row: int | None = None
    min_column: int | None = None
    max_row = 0
    max_column = 0
    raw_cells: list[RawCell] = []
    depth = 0
    tag_stack: list[str] = []
    inside_inline_string = False
    try:
        with archive.open(part_name) as stream:
            for event, element in DefusedElementTree.iterparse(stream, events=("start", "end")):
                semantic = _semantic_local(
                    element, SPREADSHEETML_NAMESPACE, _WORKSHEET_ELEMENTS, part_name
                )
                if event == "start":
                    parent = tag_stack[-1] if tag_stack else None
                    tag_stack.append(element.tag)
                    depth += 1
                    if depth > MAX_XLSX_XML_DEPTH:
                        raise ParseError(
                            "XLSX_XML_DEPTH_LIMIT",
                            f"Worksheet {part_name!r} exceeds XML depth {MAX_XLSX_XML_DEPTH}.",
                        )
                    if depth == 1:
                        if element.tag != _qualified(SPREADSHEETML_NAMESPACE, "worksheet"):
                            raise ParseError(
                                "XLSX_NAMESPACE_INVALID",
                                f"Worksheet part {part_name!r} is not transitional SpreadsheetML.",
                            )
                    elif semantic == "dimension":
                        if parent != _qualified(SPREADSHEETML_NAMESPACE, "worksheet"):
                            raise ParseError(
                                "XLSX_CELL_STRUCTURE_INVALID",
                                "Worksheet dimension must be a direct worksheet child.",
                            )
                        _reject_attribute_namespace(element, frozenset({"ref"}), part_name)
                        dimension_count += 1
                        if dimension_count > 1:
                            raise ParseError(
                                "XLSX_DIMENSION_INVALID",
                                f"Worksheet {part_name!r} contains multiple dimension elements.",
                            )
                        dimension = element.attrib.get("ref")
                        if dimension is None:
                            raise ParseError(
                                "XLSX_DIMENSION_INVALID",
                                f"Worksheet {part_name!r} has a dimension without a ref.",
                            )
                        _dimension_bounds(dimension)
                    elif semantic == "sheetData":
                        if parent != _qualified(SPREADSHEETML_NAMESPACE, "worksheet"):
                            raise ParseError(
                                "XLSX_CELL_STRUCTURE_INVALID",
                                "sheetData must be a direct worksheet child.",
                            )
                        sheet_data_count += 1
                        if sheet_data_count > 1 or inside_sheet_data:
                            raise ParseError(
                                "XLSX_SHEETDATA_INVALID",
                                f"Worksheet {part_name!r} must contain exactly one sheetData.",
                            )
                        inside_sheet_data = True
                    elif semantic == "row":
                        if parent != _qualified(SPREADSHEETML_NAMESPACE, "sheetData"):
                            raise ParseError(
                                "XLSX_CELL_STRUCTURE_INVALID",
                                "Every worksheet row must be a direct sheetData child.",
                            )
                        _reject_attribute_namespace(element, frozenset({"r"}), part_name)
                        if current_row is not None:
                            raise ParseError(
                                "XLSX_ROW_NESTED", f"Worksheet {part_name!r} contains nested rows."
                            )
                        row_reference = element.attrib.get("r")
                        if (
                            row_reference is None
                            or len(row_reference) > 7
                            or _ROW_REFERENCE.fullmatch(row_reference) is None
                        ):
                            raise ParseError(
                                "XLSX_ROW_COORDINATE_REQUIRED",
                                "XLSX v0.1 requires every physical row to have an explicit "
                                "row number.",
                            )
                        current_row = int(row_reference)
                        if current_row > XLSX_MAX_ROWS:
                            raise ParseError(
                                "XLSX_COORDINATE_OUT_OF_RANGE",
                                f"Worksheet row {current_row} exceeds {XLSX_MAX_ROWS}.",
                            )
                        if current_row > MAX_XLSX_PROJECTED_ROW:
                            raise ParseError(
                                "XLSX_PROJECTED_ROW_LIMIT",
                                f"Worksheet row {current_row} exceeds the practical row bound "
                                f"{MAX_XLSX_PROJECTED_ROW}.",
                            )
                        if current_row <= previous_row:
                            raise ParseError(
                                "XLSX_ROW_ORDER_INVALID",
                                "Worksheet rows must be strictly increasing without duplicates.",
                            )
                        previous_row = current_row
                        previous_column = 0
                        physical_rows += 1
                        if physical_rows > MAX_XLSX_PHYSICAL_ROWS:
                            raise ParseError(
                                "XLSX_PHYSICAL_ROW_LIMIT",
                                f"Worksheet exceeds {MAX_XLSX_PHYSICAL_ROWS} physical rows.",
                            )
                    elif semantic == "c":
                        if parent != _qualified(SPREADSHEETML_NAMESPACE, "row"):
                            raise ParseError(
                                "XLSX_CELL_STRUCTURE_INVALID",
                                "Every XLSX cell must be a direct row child.",
                            )
                        _reject_attribute_namespace(element, frozenset({"r", "t", "s"}), part_name)
                        if current_row is None or current_cell is not None:
                            raise ParseError(
                                "XLSX_CELL_STRUCTURE_INVALID",
                                "Every XLSX cell must occur directly within an explicit row.",
                            )
                        reference = element.attrib.get("r")
                        if reference is None:
                            raise ParseError(
                                "XLSX_CELL_COORDINATE_REQUIRED",
                                "XLSX v0.1 requires every physical cell to have an explicit "
                                "coordinate.",
                            )
                        row, column = _coordinate(reference, code="XLSX_CELL_COORDINATE_REQUIRED")
                        if row != current_row:
                            raise ParseError(
                                "XLSX_CELL_ROW_MISMATCH",
                                f"Cell {reference} does not match parent row {current_row}.",
                            )
                        if column <= previous_column:
                            raise ParseError(
                                "XLSX_CELL_ORDER_INVALID",
                                "Cells within a row must be strictly increasing without "
                                "duplicates.",
                            )
                        previous_column = column
                        raw_style = element.attrib.get("s")
                        if raw_style is not None and not _bounded_ascii_integer(raw_style):
                            raise ParseError(
                                "XLSX_STYLE_INDEX_INVALID",
                                f"Cell {reference} has an invalid style index.",
                            )
                        current_cell = _CellState(
                            reference,
                            row,
                            column,
                            element.attrib.get("t", "n"),
                            int(raw_style) if raw_style is not None else None,
                        )
                        physical_cells += 1
                        if physical_cells > MAX_XLSX_PHYSICAL_CELLS:
                            raise ParseError(
                                "XLSX_PHYSICAL_CELL_LIMIT",
                                f"Worksheet exceeds {MAX_XLSX_PHYSICAL_CELLS} physical cells.",
                            )
                        min_row = row if min_row is None else min(min_row, row)
                        min_column = column if min_column is None else min(min_column, column)
                        max_row = max(max_row, row)
                        max_column = max(max_column, column)
                        if max_row * max_column > MAX_XLSX_PROJECTED_CELLS:
                            raise ParseError(
                                "XLSX_PROJECTED_CELL_LIMIT",
                                "Worksheet sparse bounds would materialize more than "
                                f"{MAX_XLSX_PROJECTED_CELLS} cells.",
                            )
                    elif semantic in {"v", "f", "is"}:
                        if (
                            parent != _qualified(SPREADSHEETML_NAMESPACE, "c")
                            or current_cell is None
                        ):
                            raise ParseError(
                                "XLSX_CELL_STRUCTURE_INVALID",
                                f"Worksheet {semantic} must be a direct cell child.",
                            )
                        if semantic == "is":
                            if current_cell.inline_string_present or inside_inline_string:
                                raise ParseError(
                                    "XLSX_INLINE_STRING_INVALID",
                                    f"Cell {current_cell.coordinate} has multiple inline strings.",
                                )
                            current_cell.inline_string_present = True
                            current_cell.inline_parts = []
                            inside_inline_string = True
                    elif semantic == "t":
                        if current_cell is None or not inside_inline_string:
                            raise ParseError(
                                "XLSX_CELL_STRUCTURE_INVALID",
                                "Worksheet text payload must occur inside an inline string.",
                            )
                    elif semantic in {"r", "rPr"} and (
                        current_cell is None or not inside_inline_string
                    ):
                        raise ParseError(
                            "XLSX_CELL_STRUCTURE_INVALID",
                            "Worksheet rich-text content must occur inside an inline string.",
                        )
                    if current_cell is not None and semantic == "f":
                        current_cell.formula_attributes = _validate_formula_attributes(
                            element, current_cell.coordinate
                        )
                else:
                    if current_cell is not None:
                        text = element.text or ""
                        if semantic == "v":
                            if current_cell.value_present:
                                raise ParseError(
                                    "XLSX_CELL_VALUE_DUPLICATE",
                                    f"Cell {current_cell.coordinate} contains multiple values.",
                                )
                            current_cell.value = text
                            current_cell.value_present = True
                        elif semantic == "f":
                            if current_cell.formula_present:
                                raise ParseError(
                                    "XLSX_CELL_FORMULA_DUPLICATE",
                                    f"Cell {current_cell.coordinate} contains multiple formulas.",
                                )
                            if len(element):
                                raise ParseError(
                                    "XLSX_FORMULA_STRUCTURE_INVALID",
                                    f"Cell {current_cell.coordinate} formula contains nested "
                                    "elements.",
                                )
                            current_cell.formula = text
                            current_cell.formula_present = True
                    if semantic == "is":
                        assert current_cell is not None
                        current_cell.inline_parts = [
                            _reconstruct_string_container(
                                element,
                                f"Cell {current_cell.coordinate} inline string",
                                "XLSX_INLINE_STRING_LIMIT",
                            )
                        ]
                        inside_inline_string = False
                    if semantic == "c" and current_cell is not None:
                        raw_cell = _validate_raw_cell(
                            current_cell,
                            shared_strings=shared_strings,
                            style_count=style_count,
                        )
                        if capture_cells and (
                            capture_max_row is None or raw_cell.row <= capture_max_row
                        ):
                            raw_cells.append(raw_cell)
                        current_cell = None
                    elif semantic == "row" and current_row is not None:
                        current_row = None
                    elif semantic == "sheetData":
                        inside_sheet_data = False
                    if not tag_stack or tag_stack[-1] != element.tag:
                        raise ParseError(
                            "XLSX_XML_INVALID", f"Worksheet {part_name!r} element nesting diverged."
                        )
                    tag_stack.pop()
                    depth -= 1
                    if not inside_inline_string:
                        element.clear()
    except ParseError:
        raise
    except (DefusedXmlException, OSError, ValueError, XmlParseError) as error:
        raise ParseError(
            "XLSX_XML_INVALID", f"Worksheet {part_name!r} is not safe, well-formed XML."
        ) from error
    if depth != 0 or current_row is not None or current_cell is not None:
        raise ParseError("XLSX_XML_INVALID", f"Worksheet {part_name!r} ended unexpectedly.")
    if dimension is None:
        raise ParseError(
            "XLSX_DIMENSION_MISSING", f"Worksheet {part_name!r} has no explicit dimension."
        )
    if sheet_data_count != 1:
        raise ParseError(
            "XLSX_SHEETDATA_INVALID",
            f"Worksheet {part_name!r} must contain exactly one sheetData.",
        )
    declared = _dimension_bounds(dimension)
    if physical_cells == 0:
        mismatch = declared not in {(1, 1, 1, 1)}
    else:
        assert min_row is not None and min_column is not None
        mismatch = declared != (min_row, min_column, max_row, max_column)
    return WorksheetAudit(
        part_name,
        dimension,
        min_row,
        min_column,
        max_row,
        max_column,
        physical_rows,
        physical_cells,
        mismatch,
        tuple(raw_cells),
    )


def audit_xlsx_package(path: Path, limits: XlsxAuditLimits) -> XlsxPackageAudit:
    """Audit package mapping and all worksheet XML before openpyxl interpretation."""
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ParseError("XLSX_INVALID_ZIP", "The XLSX file is not a valid ZIP archive.") from error
    with archive:
        members = tuple(archive.infolist())
        if len(members) > limits.max_members:
            raise ParseError(
                "XLSX_MEMBER_LIMIT",
                f"The XLSX archive contains more than {limits.max_members} members.",
            )
        names: dict[str, str] = {}
        total = 0
        for member in members:
            if _unsafe_member(member.filename):
                raise ParseError(
                    "XLSX_PATH_TRAVERSAL", f"Unsafe archive member path: {member.filename!r}."
                )
            normalized = _normalized_member_name(member.filename)
            if normalized in names:
                raise ParseError(
                    "XLSX_DUPLICATE_MEMBER",
                    f"Duplicate normalized ZIP member {member.filename!r} is not supported.",
                )
            names[normalized] = member.filename
            if member.flag_bits & 0x1:
                raise ParseError("XLSX_ENCRYPTED", "Encrypted XLSX archives are not supported.")
            if normalized.endswith("vbaproject.bin"):
                raise ParseError(
                    "XLSX_MACRO_CONTENT_UNSUPPORTED", "VBA project content is not supported."
                )
            total += member.file_size
            if total > limits.max_uncompressed_bytes:
                raise ParseError(
                    "XLSX_SIZE_LIMIT",
                    f"Uncompressed XLSX content exceeds {limits.max_uncompressed_bytes} bytes.",
                )
            if member.file_size >= limits.ratio_minimum_size:
                ratio = member.file_size / max(member.compress_size, 1)
                if ratio > limits.max_compression_ratio:
                    raise ParseError(
                        "XLSX_COMPRESSION_RATIO",
                        f"Archive member {member.filename!r} has an unsafe compression ratio.",
                    )
        required = {
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
        }
        if not required.issubset({member.filename for member in members}):
            raise ParseError(
                "XLSX_STRUCTURE_MISSING", "Required XLSX workbook members are missing."
            )
        content_types = _content_types(archive)
        root_relationships = _relationships(
            _bounded_control_xml(archive, "_rels/.rels"),
            base_part="",
            part_name="_rels/.rels",
        )
        office_targets = [
            target
            for relationship_type, target, mode in root_relationships.values()
            if relationship_type == OFFICE_DOCUMENT_RELATIONSHIP and mode is None
        ]
        if office_targets != ["xl/workbook.xml"]:
            raise ParseError(
                "XLSX_WORKBOOK_RELATIONSHIP",
                "The package must map exactly one internal officeDocument to xl/workbook.xml.",
            )
        workbook_relationships = _relationships(
            _bounded_control_xml(archive, "xl/_rels/workbook.xml.rels"),
            base_part="xl/workbook.xml",
            part_name="xl/_rels/workbook.xml.rels",
        )
        workbook_root = _bounded_control_xml(archive, "xl/workbook.xml")
        _require_root(workbook_root, SPREADSHEETML_NAMESPACE, "workbook", "xl/workbook.xml")
        date_1904 = False
        workbook_properties_count = 0
        direct_workbook_children = {id(element) for element in workbook_root}
        sheet_elements: list[Any] = []
        sheet_ids: set[str] = set()
        sheet_names: set[str] = set()
        for element in workbook_root.iter():
            local = _semantic_local(
                element,
                SPREADSHEETML_NAMESPACE,
                _WORKBOOK_ELEMENTS,
                "xl/workbook.xml",
            )
            if local == "workbookPr":
                workbook_properties_count += 1
                if workbook_properties_count > 1 or id(element) not in direct_workbook_children:
                    raise ParseError(
                        "XLSX_WORKBOOK_PROPERTIES_INVALID",
                        "The transitional workbook may contain at most one direct workbookPr.",
                    )
                _reject_attribute_namespace(element, frozenset({"date1904"}), "xl/workbook.xml")
                raw_date_1904 = element.attrib.get("date1904", "0")
                if raw_date_1904 not in {"0", "1", "false", "true"}:
                    raise ParseError(
                        "XLSX_DATE1904_INVALID",
                        "workbookPr@date1904 must be exactly 0, 1, false, or true.",
                    )
                date_1904 = raw_date_1904 in {"1", "true"}
            elif local == "sheet":
                allowed_attributes = {"name", "sheetId", "state", RELATIONSHIP_ID}
                for attribute in element.attrib:
                    if attribute not in allowed_attributes:
                        if attribute.startswith("{"):
                            code = "XLSX_NAMESPACE_INVALID"
                        else:
                            code = "XLSX_SHEET_ATTRIBUTE_INVALID"
                        raise ParseError(
                            code,
                            "Workbook sheet has an unsupported or incorrectly namespaced "
                            "attribute.",
                        )
                title = element.attrib.get("name")
                if title is None:
                    raise ParseError(
                        "XLSX_SHEET_NAME_INVALID", "Every workbook sheet must have one name."
                    )
                _validate_sheet_name(title)
                folded_title = title.casefold()
                if folded_title in sheet_names:
                    raise ParseError(
                        "XLSX_SHEET_NAME_DUPLICATE",
                        "Workbook sheet names must be case-insensitively unique.",
                    )
                sheet_names.add(folded_title)
                sheet_id = element.attrib.get("sheetId", "")
                if not _bounded_ascii_integer(sheet_id, positive=True) or sheet_id in sheet_ids:
                    raise ParseError(
                        "XLSX_SHEET_ID_INVALID",
                        "Workbook sheetId values must be unique positive bounded ASCII integers.",
                    )
                sheet_ids.add(sheet_id)
                if not element.attrib.get(RELATIONSHIP_ID):
                    raise ParseError(
                        "XLSX_WORKSHEET_RELATIONSHIP",
                        "Every workbook sheet must have one relationship id.",
                    )
                if element.attrib.get("state", "visible") not in _SHEET_STATES:
                    raise ParseError(
                        "XLSX_SHEET_STATE_INVALID",
                        "Workbook sheet state must be visible, hidden, or veryHidden.",
                    )
                sheet_elements.append(element)
        shared_strings = _shared_strings(archive, names)
        shared_string_count = len(shared_strings)
        style_count = _style_count(archive, names)
        sheets: list[SheetPart] = []
        used_targets: set[str] = set()
        for index, element in enumerate(sheet_elements, start=1):
            relationship_id = element.attrib.get(RELATIONSHIP_ID, "")
            relationship = workbook_relationships.get(relationship_id)
            if relationship is None:
                raise ParseError(
                    "XLSX_WORKSHEET_RELATIONSHIP",
                    f"Workbook sheet {index} has no matching worksheet relationship.",
                )
            relationship_type, target, target_mode = relationship
            if (
                relationship_type != WORKSHEET_RELATIONSHIP
                or target_mode is not None
                or not target.startswith("xl/worksheets/")
            ):
                raise ParseError(
                    "XLSX_WORKSHEET_RELATIONSHIP",
                    f"Workbook sheet {index} does not map to a safe internal worksheet part.",
                )
            normalized_target = _normalized_member_name(target)
            actual_target = names.get(normalized_target)
            if actual_target is None:
                raise ParseError("XLSX_WORKSHEET_MISSING", f"Worksheet part {target!r} is missing.")
            if normalized_target in used_targets:
                raise ParseError(
                    "XLSX_WORKSHEET_RELATIONSHIP",
                    "Multiple workbook sheets cannot reference the same worksheet part.",
                )
            used_targets.add(normalized_target)
            if content_types.get(normalized_target) != WORKSHEET_CONTENT_TYPE:
                raise ParseError(
                    "XLSX_WORKSHEET_CONTENT_TYPE",
                    f"Worksheet part {target!r} does not have the exact worksheet content type.",
                )
            worksheet = _audit_worksheet_stream(
                archive,
                actual_target,
                shared_strings=shared_strings,
                style_count=style_count,
                capture_cells=False,
            )
            sheets.append(
                SheetPart(
                    index,
                    element.attrib["name"],
                    element.attrib.get("state", "visible"),
                    relationship_id,
                    actual_target,
                    worksheet,
                )
            )
        return XlsxPackageAudit(
            members,
            tuple(sheets),
            date_1904,
            shared_string_count,
            style_count,
            shared_strings,
        )


def capture_worksheet_cells(
    path: Path,
    package: XlsxPackageAudit,
    sheet: SheetPart,
    *,
    capture_max_row: int | None = None,
) -> WorksheetAudit:
    """Re-audit and capture raw cells for only the selected bounded worksheet."""
    if capture_max_row is not None and (type(capture_max_row) is not int or capture_max_row < 1):
        raise ParseError(
            "XLSX_CAPTURE_LIMIT_INVALID", "capture_max_row must be a positive integer."
        )
    try:
        with zipfile.ZipFile(path) as archive:
            captured = _audit_worksheet_stream(
                archive,
                sheet.part_name,
                shared_strings=package.shared_strings,
                style_count=package.style_count,
                capture_cells=True,
                capture_max_row=capture_max_row,
            )
    except (OSError, zipfile.BadZipFile) as error:
        raise ParseError(
            "XLSX_INVALID_ZIP", "The XLSX file changed or is not a valid ZIP."
        ) from error
    if (
        captured.actual_min_row != sheet.worksheet.actual_min_row
        or captured.actual_min_column != sheet.worksheet.actual_min_column
        or captured.actual_max_row != sheet.worksheet.actual_max_row
        or captured.actual_max_column != sheet.worksheet.actual_max_column
        or captured.physical_cells != sheet.worksheet.physical_cells
    ):
        raise ParseError(
            "XLSX_CHANGED_DURING_AUDIT", "The selected worksheet changed during XLSX audit."
        )
    return captured
