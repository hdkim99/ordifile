# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Dependency-neutral exact XLSX text representability rules."""

from __future__ import annotations

import re

XLSX_ESCAPE_TOKEN = re.compile(r"_x[0-9A-Fa-f]{4}_", re.IGNORECASE)
MAX_WORKBOOK_CELL_CHARACTERS = 32_767


def text_codepoint_unrepresentable(character: str) -> bool:
    """Return whether XLSX/XML serialization cannot round-trip one code point exactly."""
    codepoint = ord(character)
    return (
        codepoint == 0x0D
        or codepoint < 0x20
        and codepoint not in {0x09, 0x0A}
        or 0xD800 <= codepoint <= 0xDFFF
        or 0xFDD0 <= codepoint <= 0xFDEF
        or codepoint & 0xFFFF in {0xFFFE, 0xFFFF}
    )


def workbook_text_is_exact(text: str) -> bool:
    """Return whether current XLSX writers can preserve text without silent escaping."""
    return not any(text_codepoint_unrepresentable(character) for character in text) and (
        XLSX_ESCAPE_TOKEN.search(text) is None
    )


def workbook_cell_text_is_exact(text: str) -> bool:
    """Return whether one mandatory workbook cell can preserve the complete text."""
    return len(text) <= MAX_WORKBOOK_CELL_CHARACTERS and workbook_text_is_exact(text)


def workbook_audit_display(text: str) -> str:
    """Encode unsafe source identity text reversibly without exposing absolute paths."""
    encoded: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "~":
            encoded.append("~~")
        elif text_codepoint_unrepresentable(character):
            encoded.append(f"~u{ord(character):06X};")
        elif character == "_" and XLSX_ESCAPE_TOKEN.match(text, index) is not None:
            encoded.append("~u00005F;")
        else:
            encoded.append(character)
        index += 1
    return "".join(encoded)
