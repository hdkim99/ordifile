# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Collect user-confirmed peak mappings without exposing Mapping Set mechanics."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from ordifile import (
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
)


class MappingCollectionAction(StrEnum):
    """Describe one deterministic mapping-collection result."""

    SINGLE = "SINGLE"
    UNCHANGED = "UNCHANGED"
    REPLACED = "REPLACED"
    PROMOTED = "PROMOTED"
    APPENDED = "APPENDED"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class MappingCollectionResult:
    """Return one atomic GUI state update or a conflict that changes nothing."""

    mapping: PeakTableMapping | None
    mapping_sheet: str | None
    mapping_set: PeakTableMappingSet | None
    selected_profile_id: str | None
    action: MappingCollectionAction


def _profile(
    mapping: PeakTableMapping,
    sheet: str | None,
    *,
    position: int,
) -> PeakTableMappingProfile:
    return PeakTableMappingProfile(
        mapping,
        f"{mapping.source_format.value.upper()} layout {position}",
        worksheet_title=sheet,
    )


def collect_confirmed_mapping(
    *,
    current_mapping: PeakTableMapping | None,
    current_sheet: str | None,
    current_set: PeakTableMappingSet | None,
    confirmed_mapping: PeakTableMapping,
    confirmed_sheet: str | None,
    replace_conflict: bool = False,
) -> MappingCollectionResult:
    """Collect one explicit mapping while preserving stable profile identities and order."""
    candidate = _profile(
        confirmed_mapping,
        confirmed_sheet,
        position=len(current_set.profiles) + 1 if current_set is not None else 2,
    )
    if current_set is not None:
        structural_matches = tuple(
            (index, profile)
            for index, profile in enumerate(current_set.profiles)
            if profile.exact_structure_sha256 == candidate.exact_structure_sha256
        )
        if len(structural_matches) > 1:
            return MappingCollectionResult(
                current_mapping,
                current_sheet,
                current_set,
                None,
                MappingCollectionAction.CONFLICT,
            )
        if structural_matches:
            index, existing = structural_matches[0]
            if existing.semantic_sha256 == candidate.semantic_sha256:
                return MappingCollectionResult(
                    confirmed_mapping,
                    confirmed_sheet,
                    current_set,
                    existing.profile_id,
                    MappingCollectionAction.UNCHANGED,
                )
            if not replace_conflict:
                return MappingCollectionResult(
                    current_mapping,
                    current_sheet,
                    current_set,
                    existing.profile_id,
                    MappingCollectionAction.CONFLICT,
                )
            replacement = replace(
                existing,
                mapping=confirmed_mapping,
                worksheet_title=confirmed_sheet,
            )
            profiles = list(current_set.profiles)
            profiles[index] = replacement
            updated = replace(current_set, profiles=tuple(profiles))
            return MappingCollectionResult(
                confirmed_mapping,
                confirmed_sheet,
                updated,
                replacement.profile_id,
                MappingCollectionAction.REPLACED,
            )
        updated = replace(current_set, profiles=(*current_set.profiles, candidate))
        return MappingCollectionResult(
            confirmed_mapping,
            confirmed_sheet,
            updated,
            candidate.profile_id,
            MappingCollectionAction.APPENDED,
        )

    if current_mapping is None:
        return MappingCollectionResult(
            confirmed_mapping,
            confirmed_sheet,
            None,
            None,
            MappingCollectionAction.SINGLE,
        )

    existing = _profile(current_mapping, current_sheet, position=1)
    if existing.exact_structure_sha256 == candidate.exact_structure_sha256:
        if existing.semantic_sha256 == candidate.semantic_sha256:
            return MappingCollectionResult(
                confirmed_mapping,
                confirmed_sheet,
                None,
                None,
                MappingCollectionAction.UNCHANGED,
            )
        if not replace_conflict:
            return MappingCollectionResult(
                current_mapping,
                current_sheet,
                None,
                None,
                MappingCollectionAction.CONFLICT,
            )
        return MappingCollectionResult(
            confirmed_mapping,
            confirmed_sheet,
            None,
            None,
            MappingCollectionAction.REPLACED,
        )

    promoted = PeakTableMappingSet((existing, candidate))
    return MappingCollectionResult(
        confirmed_mapping,
        confirmed_sheet,
        promoted,
        candidate.profile_id,
        MappingCollectionAction.PROMOTED,
    )
