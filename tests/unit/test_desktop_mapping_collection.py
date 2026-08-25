# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ordifile import (
    ColumnSelector,
    PeakTableFormat,
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
)
from ordifile.desktop.mapping_collection import (
    MappingCollectionAction,
    collect_confirmed_mapping,
)


def _mapping(
    retention_header: str = "RT",
    area_header: str = "Area",
    *,
    unit: str = "min",
    source_format: PeakTableFormat = PeakTableFormat.CSV,
) -> PeakTableMapping:
    return PeakTableMapping(
        ColumnSelector(retention_header, 1),
        ColumnSelector(area_header, 2),
        unit,
        source_format,
    )


def test_first_confirmed_mapping_remains_simple() -> None:
    mapping = _mapping()

    result = collect_confirmed_mapping(
        current_mapping=None,
        current_sheet=None,
        current_set=None,
        confirmed_mapping=mapping,
        confirmed_sheet=None,
    )

    assert result.action is MappingCollectionAction.SINGLE
    assert result.mapping is mapping
    assert result.mapping_set is None


def test_second_distinct_layout_automatically_promotes_to_mapping_set() -> None:
    first = _mapping()
    second = _mapping("Retention Time", "Peak Area")

    result = collect_confirmed_mapping(
        current_mapping=first,
        current_sheet=None,
        current_set=None,
        confirmed_mapping=second,
        confirmed_sheet=None,
    )

    assert result.action is MappingCollectionAction.PROMOTED
    assert result.mapping_set is not None
    assert tuple(profile.mapping for profile in result.mapping_set.profiles) == (first, second)
    assert tuple(profile.display_label for profile in result.mapping_set.profiles) == (
        "CSV layout 1",
        "CSV layout 2",
    )
    assert result.selected_profile_id == result.mapping_set.profiles[1].profile_id


def test_third_distinct_layout_appends_without_changing_existing_identity() -> None:
    first = PeakTableMappingProfile(_mapping(), "CSV layout 1")
    second = PeakTableMappingProfile(_mapping("Retention Time", "Peak Area"), "CSV layout 2")
    mapping_set = PeakTableMappingSet((first, second))
    third = _mapping("Time", "Integrated Area")

    result = collect_confirmed_mapping(
        current_mapping=second.mapping,
        current_sheet=None,
        current_set=mapping_set,
        confirmed_mapping=third,
        confirmed_sheet=None,
    )

    assert result.action is MappingCollectionAction.APPENDED
    assert result.mapping_set is not None
    assert result.mapping_set.set_id == mapping_set.set_id
    assert result.mapping_set.profiles[:2] == mapping_set.profiles
    assert result.mapping_set.profiles[2].display_label == "CSV layout 3"


def test_same_layout_and_semantics_is_an_idempotent_no_op() -> None:
    profile = PeakTableMappingProfile(_mapping(), "CSV layout 1")
    mapping_set = PeakTableMappingSet((profile,))

    result = collect_confirmed_mapping(
        current_mapping=profile.mapping,
        current_sheet=None,
        current_set=mapping_set,
        confirmed_mapping=profile.mapping,
        confirmed_sheet=None,
    )

    assert result.action is MappingCollectionAction.UNCHANGED
    assert result.mapping_set is mapping_set
    assert result.selected_profile_id == profile.profile_id


def test_same_single_layout_and_semantics_remains_simple() -> None:
    mapping = _mapping()

    result = collect_confirmed_mapping(
        current_mapping=mapping,
        current_sheet=None,
        current_set=None,
        confirmed_mapping=mapping,
        confirmed_sheet=None,
    )

    assert result.action is MappingCollectionAction.UNCHANGED
    assert result.mapping is mapping
    assert result.mapping_set is None


def test_same_layout_with_different_semantics_requires_explicit_replacement() -> None:
    original = _mapping(unit="min")
    changed = _mapping(unit="s")

    conflict = collect_confirmed_mapping(
        current_mapping=original,
        current_sheet=None,
        current_set=None,
        confirmed_mapping=changed,
        confirmed_sheet=None,
    )
    replaced = collect_confirmed_mapping(
        current_mapping=original,
        current_sheet=None,
        current_set=None,
        confirmed_mapping=changed,
        confirmed_sheet=None,
        replace_conflict=True,
    )

    assert conflict.action is MappingCollectionAction.CONFLICT
    assert conflict.mapping is original
    assert replaced.action is MappingCollectionAction.REPLACED
    assert replaced.mapping is changed


def test_set_replacement_preserves_profile_and_set_identity() -> None:
    profile = PeakTableMappingProfile(_mapping(), "CSV layout 1")
    mapping_set = PeakTableMappingSet((profile,))
    changed = _mapping(unit="s")

    result = collect_confirmed_mapping(
        current_mapping=profile.mapping,
        current_sheet=None,
        current_set=mapping_set,
        confirmed_mapping=changed,
        confirmed_sheet=None,
        replace_conflict=True,
    )

    assert result.action is MappingCollectionAction.REPLACED
    assert result.mapping_set is not None
    assert result.mapping_set.set_id == mapping_set.set_id
    assert result.mapping_set.profiles[0].profile_id == profile.profile_id
    assert result.mapping_set.profiles[0].display_label == profile.display_label
    assert result.mapping_set.profiles[0].mapping is changed


def test_set_semantic_conflict_changes_nothing_without_confirmation() -> None:
    profile = PeakTableMappingProfile(_mapping(), "CSV layout 1")
    mapping_set = PeakTableMappingSet((profile,))

    result = collect_confirmed_mapping(
        current_mapping=profile.mapping,
        current_sheet=None,
        current_set=mapping_set,
        confirmed_mapping=_mapping(unit="s"),
        confirmed_sheet=None,
    )

    assert result.action is MappingCollectionAction.CONFLICT
    assert result.mapping is profile.mapping
    assert result.mapping_set is mapping_set
    assert result.selected_profile_id == profile.profile_id


def test_ambiguous_set_structure_fails_closed_without_selecting_a_profile() -> None:
    first = PeakTableMappingProfile(_mapping(unit="min"), "CSV layout 1")
    second = PeakTableMappingProfile(_mapping(unit="s"), "CSV layout 2")
    mapping_set = PeakTableMappingSet((first, second))

    result = collect_confirmed_mapping(
        current_mapping=first.mapping,
        current_sheet=None,
        current_set=mapping_set,
        confirmed_mapping=_mapping(unit="h"),
        confirmed_sheet=None,
        replace_conflict=True,
    )

    assert result.action is MappingCollectionAction.CONFLICT
    assert result.mapping is first.mapping
    assert result.mapping_set is mapping_set
    assert result.selected_profile_id is None
