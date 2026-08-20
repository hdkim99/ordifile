# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded structural routing and diagnostics for explicit peak-table mappings."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ordifile.adapters._delimited import preview_delimited_peak_table
from ordifile.adapters.generic_xlsx import preview_xlsx_peak_table
from ordifile.core.errors import AdapterAmbiguityError, OrdifileError, ParseError
from ordifile.core.peak_mapping import (
    MAX_PEAK_MAPPING_DRIFT_CANDIDATES,
    ColumnSelector,
    PeakMappingDriftCategory,
    PeakMappingDriftDiagnostic,
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
_REQUIRED_ROLE_FIELDS = (
    ("retention_time", "retention_time_column"),
    ("area", "area_column"),
)
_OPTIONAL_ROLE_FIELDS = (
    ("height", "height_column"),
    ("peak_name", "peak_name_column"),
    ("compound", "compound_name_column"),
    ("peak_number", "peak_index_column"),
    ("detector", "detector_column"),
    ("channel", "channel_column"),
    ("sample_id", "sample_id_column"),
    ("run_id", "run_id_column"),
    ("acquired_at", "acquisition_time_column"),
    ("start_time", "start_time_column"),
    ("end_time", "end_time_column"),
    ("secondary_retention_time", "secondary_retention_time_column"),
)


@dataclass(frozen=True, slots=True)
class ResolvedPeakTableMapping:
    """One exact local profile match ready for the existing generic parser."""

    adapter_id: str
    profile: PeakTableMappingProfile
    sheet: str | None = None


@dataclass(frozen=True, slots=True)
class _ObservedPeakTableStructure:
    source_format: PeakTableFormat
    headers: tuple[str, ...]
    worksheet_title: str | None = None
    single_visible_worksheet: bool = False


class PeakMappingResolutionError(OrdifileError):
    """A fixed routing failure with optional privacy-safe diagnostics."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostics: tuple[PeakMappingDriftDiagnostic, ...] = (),
    ) -> None:
        super().__init__(code, message)
        self.diagnostics = diagnostics


def _candidate_formats(path: Path, mapping_set: PeakTableMappingSet) -> tuple[PeakTableFormat, ...]:
    suffix = path.suffix.casefold()
    requested = {profile.mapping.source_format for profile in mapping_set.profiles}
    return tuple(
        source_format
        for source_format in PeakTableFormat
        if source_format in requested and suffix in _SUFFIXES_BY_FORMAT[source_format]
    )


def _occurrence_tokens(headers: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    occurrences: Counter[str] = Counter()
    tokens: list[tuple[str, int]] = []
    for header in headers:
        occurrences[header] += 1
        tokens.append((header, occurrences[header]))
    return tuple(tokens)


def _selector_survives(
    selector: ColumnSelector,
    expected_tokens: tuple[tuple[str, int], ...],
    observed_tokens: tuple[tuple[str, int], ...],
) -> bool:
    return (
        selector.index <= len(observed_tokens)
        and expected_tokens[selector.index - 1] == observed_tokens[selector.index - 1]
    )


def _selector_token_present(
    selector: ColumnSelector,
    expected_tokens: tuple[tuple[str, int], ...],
    observed_tokens: tuple[tuple[str, int], ...],
) -> bool:
    return expected_tokens[selector.index - 1] in set(observed_tokens)


def _role_differences(
    profile: PeakTableMappingProfile,
    expected_tokens: tuple[tuple[str, int], ...],
    observed_tokens: tuple[tuple[str, int], ...],
) -> tuple[tuple[str, ...], tuple[str, ...], bool, bool]:
    required: list[str] = []
    optional: list[str] = []
    required_missing = False
    optional_missing = False
    for role, field_name in _REQUIRED_ROLE_FIELDS:
        selector = getattr(profile.mapping, field_name)
        assert isinstance(selector, ColumnSelector)
        if not _selector_survives(selector, expected_tokens, observed_tokens):
            required.append(role)
            required_missing = required_missing or not _selector_token_present(
                selector, expected_tokens, observed_tokens
            )
    for role, field_name in _OPTIONAL_ROLE_FIELDS:
        selector = getattr(profile.mapping, field_name)
        if not isinstance(selector, ColumnSelector):
            continue
        if not _selector_survives(selector, expected_tokens, observed_tokens):
            optional.append(role)
            optional_missing = optional_missing or not _selector_token_present(
                selector, expected_tokens, observed_tokens
            )
    return tuple(required), tuple(optional), required_missing, optional_missing


def _diagnostic(
    profile: PeakTableMappingProfile,
    observed: _ObservedPeakTableStructure,
) -> PeakMappingDriftDiagnostic:
    expected = profile.mapping.declared_headers
    current = observed.headers
    expected_tokens = _occurrence_tokens(expected)
    observed_tokens = _occurrence_tokens(current)
    expected_positions = {token: index for index, token in enumerate(expected_tokens, start=1)}
    observed_positions = {token: index for index, token in enumerate(observed_tokens, start=1)}
    expected_set = set(expected_tokens)
    observed_set = set(observed_tokens)
    added = observed_set - expected_set
    removed = expected_set - observed_set
    common = expected_set & observed_set
    exact_positions = sum(
        expected_positions[token] == observed_positions[token] for token in common
    )
    expected_common_order = tuple(token for token in expected_tokens if token in common)
    observed_common_order = tuple(token for token in observed_tokens if token in common)
    moved_tokens = {
        token
        for expected_token, observed_token in zip(
            expected_common_order,
            observed_common_order,
            strict=True,
        )
        if expected_token != observed_token
        for token in (expected_token, observed_token)
    }
    moved = len(moved_tokens)
    changed_positions = {
        position
        for position in range(1, min(len(expected), len(current)) + 1)
        if expected_tokens[position - 1] in removed and observed_tokens[position - 1] in added
    }
    changed = len(changed_positions)
    added_only = {token for token in added if observed_positions[token] not in changed_positions}
    removed_only = {
        token for token in removed if expected_positions[token] not in changed_positions
    }
    required, optional, required_missing, optional_missing = _role_differences(
        profile,
        expected_tokens,
        observed_tokens,
    )
    categories: set[PeakMappingDriftCategory] = set()
    if added_only:
        categories.add(PeakMappingDriftCategory.COLUMN_ADDED)
    if removed_only:
        categories.add(PeakMappingDriftCategory.COLUMN_REMOVED)
    if moved:
        categories.add(PeakMappingDriftCategory.COLUMN_REORDERED)
    if changed:
        categories.add(PeakMappingDriftCategory.HEADER_CHANGED_UNRESOLVED)
    expected_counts = Counter(expected)
    observed_counts = Counter(current)
    if any(
        expected_counts[label] != observed_counts[label]
        and max(expected_counts[label], observed_counts[label]) > 1
        for label in expected_counts.keys() | observed_counts.keys()
    ):
        categories.add(PeakMappingDriftCategory.DUPLICATE_HEADER_CHANGED)
    if required_missing:
        categories.add(PeakMappingDriftCategory.REQUIRED_MAPPING_COLUMN_MISSING)
    if optional_missing:
        categories.add(PeakMappingDriftCategory.OPTIONAL_MAPPING_COLUMN_MISSING)
    worksheet_mismatch = (
        profile.mapping.source_format is PeakTableFormat.XLSX
        and profile.worksheet_title is not None
        and profile.worksheet_title != observed.worksheet_title
    )
    if worksheet_mismatch:
        categories.add(PeakMappingDriftCategory.WORKSHEET_IDENTITY_CHANGED_UNRESOLVED)
    if not common and len(expected) != len(current):
        categories.add(PeakMappingDriftCategory.INCOMPATIBLE_STRUCTURE)
    if not categories:
        categories.add(PeakMappingDriftCategory.INCOMPATIBLE_STRUCTURE)
    total_differences = changed + len(added_only) + len(removed_only) + moved
    if worksheet_mismatch:
        total_differences += 1
    ordered_categories = tuple(
        category for category in PeakMappingDriftCategory if category in categories
    )
    return PeakMappingDriftDiagnostic(
        profile_id=profile.profile_id,
        profile_structural_fingerprint=profile.structural_fingerprint_sha256,
        source_format=observed.source_format,
        categories=ordered_categories,
        expected_column_count=len(expected),
        observed_column_count=len(current),
        exact_position_matches=exact_positions,
        changed_column_count=changed,
        added_column_count=len(added_only),
        removed_column_count=len(removed_only),
        moved_column_count=moved,
        total_difference_count=total_differences,
        unresolved_required_roles=required,
        unresolved_optional_roles=optional,
    )


def _diagnostics(
    observations: tuple[_ObservedPeakTableStructure, ...],
    mapping_set: PeakTableMappingSet,
) -> tuple[PeakMappingDriftDiagnostic, ...]:
    def rank(item: PeakMappingDriftDiagnostic) -> tuple[int, int, int, int, int, str]:
        return (
            len(item.unresolved_required_roles),
            len(item.unresolved_required_roles) + len(item.unresolved_optional_roles),
            item.changed_column_count + item.added_column_count + item.removed_column_count,
            item.moved_column_count,
            int(PeakMappingDriftCategory.WORKSHEET_IDENTITY_CHANGED_UNRESOLVED in item.categories),
            item.profile_id,
        )

    candidates: dict[tuple[str, PeakTableFormat], PeakMappingDriftDiagnostic] = {}
    for observed in observations:
        for profile in mapping_set.profiles:
            if profile.mapping.source_format is not observed.source_format:
                continue
            diagnostic = _diagnostic(profile, observed)
            key = (diagnostic.profile_id, diagnostic.source_format)
            previous = candidates.get(key)
            if previous is None or rank(diagnostic) < rank(previous):
                candidates[key] = diagnostic
    compatible = tuple(
        item
        for item in candidates.values()
        if PeakMappingDriftCategory.INCOMPATIBLE_STRUCTURE not in item.categories
    )
    ordered = sorted(compatible or tuple(candidates.values()), key=rank)
    return tuple(ordered[:MAX_PEAK_MAPPING_DRIFT_CANDIDATES])


def _text_observation(
    path: Path,
    source_format: PeakTableFormat,
) -> _ObservedPeakTableStructure:
    preview = preview_delimited_peak_table(path, source_format, row_limit=0)
    return _ObservedPeakTableStructure(source_format, preview.headers)


def _xlsx_observations(
    path: Path,
    mapping_set: PeakTableMappingSet,
) -> tuple[tuple[_ObservedPeakTableStructure, ...], bool]:
    profiles = tuple(
        profile
        for profile in mapping_set.profiles
        if profile.mapping.source_format is PeakTableFormat.XLSX
    )
    observations: list[_ObservedPeakTableStructure] = []
    exact_titles = tuple(
        dict.fromkeys(
            profile.worksheet_title for profile in profiles if profile.worksheet_title is not None
        )
    )
    for title in exact_titles:
        assert title is not None
        try:
            preview = preview_xlsx_peak_table(path, sheet=title, row_limit=0)
        except ParseError as error:
            if error.code == "XLSX_SHEET_NOT_FOUND":
                continue
            raise
        observations.append(
            _ObservedPeakTableStructure(PeakTableFormat.XLSX, preview.headers, title)
        )
    ambiguous_default = False
    try:
        preview = preview_xlsx_peak_table(path, row_limit=0)
    except AdapterAmbiguityError:
        ambiguous_default = True
    else:
        observations.append(
            _ObservedPeakTableStructure(
                PeakTableFormat.XLSX,
                preview.headers,
                preview.sheet,
                single_visible_worksheet=True,
            )
        )
    unique = {
        (
            item.source_format,
            item.headers,
            item.worksheet_title,
            item.single_visible_worksheet,
        ): item
        for item in observations
    }
    return tuple(unique.values()), ambiguous_default


def resolve_peak_table_mapping(
    path: Path,
    mapping_set: PeakTableMappingSet,
) -> ResolvedPeakTableMapping:
    """Resolve one exact profile or fail with diagnostics that never authorize parsing."""
    observations: list[_ObservedPeakTableStructure] = []
    errors: list[OrdifileError] = []
    ambiguous_xlsx = False
    for source_format in _candidate_formats(path, mapping_set):
        try:
            if source_format is PeakTableFormat.XLSX:
                xlsx_observations, ambiguous_xlsx = _xlsx_observations(path, mapping_set)
                observations.extend(xlsx_observations)
            else:
                observations.append(_text_observation(path, source_format))
        except OrdifileError as error:
            errors.append(error)

    matches: dict[tuple[str, str | None], ResolvedPeakTableMapping] = {}
    for observed in observations:
        for profile in mapping_set.match(
            observed.source_format,
            observed.headers,
            worksheet_title=observed.worksheet_title,
            single_visible_worksheet=observed.single_visible_worksheet,
        ):
            resolved = ResolvedPeakTableMapping(
                _ADAPTER_BY_FORMAT[observed.source_format],
                profile,
                observed.worksheet_title
                if observed.source_format is PeakTableFormat.XLSX
                else None,
            )
            matches[(profile.profile_id, resolved.sheet)] = resolved
    exact_matches = tuple(matches.values())
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise PeakMappingResolutionError(
            "PEAK_MAPPING_PROFILE_AMBIGUOUS",
            "More than one reusable mapping profile exactly matched this table structure.",
        )
    if ambiguous_xlsx and not observations:
        raise PeakMappingResolutionError(
            "PEAK_MAPPING_WORKSHEET_AMBIGUOUS",
            "A reusable mapping profile cannot select an ambiguous workbook.",
        )
    if not observations and errors:
        raise errors[0]
    diagnostics = _diagnostics(tuple(observations), mapping_set)
    raise PeakMappingResolutionError(
        "PEAK_MAPPING_PROFILE_NOT_MATCHED",
        "No reusable mapping profile exactly matched this generic table structure.",
        diagnostics=diagnostics,
    )
