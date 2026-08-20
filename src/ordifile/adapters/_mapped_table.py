# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded structural routing for reusable explicit peak-table mappings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ordifile.adapters._delimited import preview_delimited_peak_table
from ordifile.adapters.generic_xlsx import preview_xlsx_peak_table
from ordifile.core.errors import AdapterAmbiguityError, OrdifileError, ParseError
from ordifile.core.peak_mapping import (
    PeakTableFormat,
    PeakTableMappingProfile,
    PeakTableMappingSet,
)

GENERIC_PEAK_TABLE_ADAPTER_IDS = frozenset(
    {"generic_csv", "generic_tsv", "generic_semicolon", "generic_xlsx"}
)

_ADAPTER_BY_FORMAT = {
    PeakTableFormat.CSV: "generic_csv",
    PeakTableFormat.TSV: "generic_tsv",
    PeakTableFormat.SEMICOLON: "generic_semicolon",
    PeakTableFormat.XLSX: "generic_xlsx",
}
_SUFFIXES_BY_FORMAT = {
    PeakTableFormat.CSV: frozenset({".csv"}),
    PeakTableFormat.TSV: frozenset({".tsv", ".txt"}),
    PeakTableFormat.SEMICOLON: frozenset({".txt"}),
    PeakTableFormat.XLSX: frozenset({".xlsx"}),
}


@dataclass(frozen=True, slots=True)
class ResolvedPeakTableMapping:
    """One exact local profile match ready for the existing generic parser."""

    adapter_id: str
    profile: PeakTableMappingProfile
    sheet: str | None = None


def _candidate_formats(path: Path, mapping_set: PeakTableMappingSet) -> tuple[PeakTableFormat, ...]:
    suffix = path.suffix.casefold()
    requested = {profile.mapping.source_format for profile in mapping_set.profiles}
    return tuple(
        source_format
        for source_format in PeakTableFormat
        if source_format in requested and suffix in _SUFFIXES_BY_FORMAT[source_format]
    )


def _text_candidates(
    path: Path,
    source_format: PeakTableFormat,
    mapping_set: PeakTableMappingSet,
) -> tuple[ResolvedPeakTableMapping, ...]:
    preview = preview_delimited_peak_table(path, source_format, row_limit=1)
    return tuple(
        ResolvedPeakTableMapping(_ADAPTER_BY_FORMAT[source_format], profile)
        for profile in mapping_set.match(source_format, preview.headers)
    )


def _xlsx_candidates(
    path: Path,
    mapping_set: PeakTableMappingSet,
) -> tuple[ResolvedPeakTableMapping, ...]:
    profiles = tuple(
        profile
        for profile in mapping_set.profiles
        if profile.mapping.source_format is PeakTableFormat.XLSX
    )
    candidates: list[ResolvedPeakTableMapping] = []
    exact_titles = tuple(
        dict.fromkeys(
            profile.worksheet_title for profile in profiles if profile.worksheet_title is not None
        )
    )
    for title in exact_titles:
        assert title is not None
        try:
            preview = preview_xlsx_peak_table(path, sheet=title, row_limit=1)
        except ParseError as error:
            if error.code == "XLSX_SHEET_NOT_FOUND":
                continue
            raise
        candidates.extend(
            ResolvedPeakTableMapping("generic_xlsx", profile, title)
            for profile in mapping_set.match(
                PeakTableFormat.XLSX,
                preview.headers,
                worksheet_title=title,
            )
        )
    if any(profile.worksheet_title is None for profile in profiles):
        try:
            preview = preview_xlsx_peak_table(path, row_limit=1)
        except AdapterAmbiguityError as error:
            raise OrdifileError(
                "PEAK_MAPPING_WORKSHEET_AMBIGUOUS",
                "A single-visible-sheet profile cannot select an ambiguous workbook.",
            ) from error
        candidates.extend(
            ResolvedPeakTableMapping("generic_xlsx", profile, preview.sheet)
            for profile in mapping_set.match(
                PeakTableFormat.XLSX,
                preview.headers,
                worksheet_title=preview.sheet,
                single_visible_worksheet=True,
            )
        )
    return tuple(candidates)


def resolve_peak_table_mapping(
    path: Path,
    mapping_set: PeakTableMappingSet,
) -> ResolvedPeakTableMapping:
    """Resolve exactly one profile from structure or fail without generic fallback."""
    candidates: list[ResolvedPeakTableMapping] = []
    for source_format in _candidate_formats(path, mapping_set):
        if source_format is PeakTableFormat.XLSX:
            candidates.extend(_xlsx_candidates(path, mapping_set))
        else:
            candidates.extend(_text_candidates(path, source_format, mapping_set))
    unique = {
        (candidate.adapter_id, candidate.profile.profile_id, candidate.sheet): candidate
        for candidate in candidates
    }
    matches = tuple(unique.values())
    if not matches:
        raise OrdifileError(
            "PEAK_MAPPING_PROFILE_NOT_MATCHED",
            "No reusable mapping profile exactly matched this generic table structure.",
        )
    if len(matches) > 1:
        raise OrdifileError(
            "PEAK_MAPPING_PROFILE_AMBIGUOUS",
            "More than one reusable mapping profile exactly matched this table structure.",
        )
    return matches[0]
