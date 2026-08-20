# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ordifile.core.errors import OrdifileError
from ordifile.core.peak_mapping import (
    ColumnSelector,
    PeakTableFormat,
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
    load_peak_table_mapping_set,
    save_peak_table_mapping_set,
)


def _mapping(
    *,
    source_format: PeakTableFormat = PeakTableFormat.CSV,
    rt_unit: str = "min",
    area_unit: str | None = "mV.s",
) -> PeakTableMapping:
    return PeakTableMapping(
        retention_time_column=ColumnSelector("Retention Time", 1),
        area_column=ColumnSelector("Area", 2),
        retention_time_unit=rt_unit,
        source_format=source_format,
        area_unit=area_unit,
        ignored_columns=(ColumnSelector("Note", 3),),
    )


def test_profile_and_mapping_set_round_trip(tmp_path: Path) -> None:
    profile = PeakTableMappingProfile(_mapping(), "Template A")
    mapping_set = PeakTableMappingSet((profile,))
    destination = tmp_path / "mappings.json"

    save_peak_table_mapping_set(mapping_set, destination)
    restored = load_peak_table_mapping_set(destination)

    assert restored == mapping_set
    assert restored.to_json() == mapping_set.to_json()
    assert restored.structural_fingerprint_sha256 == mapping_set.structural_fingerprint_sha256


def test_mapping_set_rejects_lone_surrogate_as_structured_error() -> None:
    with pytest.raises(OrdifileError) as captured:
        PeakTableMappingSet.from_json("\ud800")

    assert captured.value.code == "PEAK_MAPPING_INVALID"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs are unavailable")
def test_mapping_set_load_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    source = tmp_path / "mapping-set.json"
    os.mkfifo(source)

    with pytest.raises(OrdifileError, match="regular file"):
        load_peak_table_mapping_set(source)


def test_mapping_set_non_overwrite_publish_retries_temp_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "mapping-set.json"
    mapping_set = PeakTableMappingSet((PeakTableMappingProfile(_mapping()),))
    real_unlink = os.unlink
    failed_once = False

    def reject_owned_temporary(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> None:
        nonlocal failed_once
        if ".ordifile-peak-mapping-set-" in os.fsdecode(path) and not failed_once:
            failed_once = True
            raise PermissionError("PRIVATE-CANARY-PATH")
        real_unlink(path)

    monkeypatch.setattr(os, "unlink", reject_owned_temporary)

    save_peak_table_mapping_set(mapping_set, destination)

    assert load_peak_table_mapping_set(destination) == mapping_set
    assert not tuple(tmp_path.glob(".ordifile-peak-mapping-set-*.tmp"))


def test_mapping_set_publish_reports_repeated_temp_cleanup_failure_without_raw_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "mapping-set.json"
    mapping_set = PeakTableMappingSet((PeakTableMappingProfile(_mapping()),))
    real_unlink = os.unlink
    failures = 0

    def reject_twice(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> None:
        nonlocal failures
        if ".ordifile-peak-mapping-set-" in os.fsdecode(path) and failures < 2:
            failures += 1
            raise PermissionError("PRIVATE-CANARY-PATH")
        real_unlink(path)

    monkeypatch.setattr(os, "unlink", reject_twice)

    with pytest.raises(OrdifileError) as captured:
        save_peak_table_mapping_set(mapping_set, destination)

    assert captured.value.code == "PEAK_MAPPING_INVALID"
    assert "PRIVATE-CANARY-PATH" not in str(captured.value)
    assert load_peak_table_mapping_set(destination) == mapping_set
    assert not tuple(tmp_path.glob(".ordifile-peak-mapping-set-*.tmp"))


def test_mapping_set_publish_preserves_foreign_destination_swapped_during_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "mapping-set.json"
    mapping_set = PeakTableMappingSet((PeakTableMappingProfile(_mapping()),))
    foreign = b"foreign-preserved"
    real_unlink = os.unlink
    swapped = False

    def swap_destination(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> None:
        nonlocal swapped
        if ".ordifile-peak-mapping-set-" in os.fsdecode(path) and not swapped:
            swapped = True
            real_unlink(destination)
            destination.write_bytes(foreign)
            raise PermissionError("PRIVATE-CANARY-PATH")
        real_unlink(path)

    monkeypatch.setattr(os, "unlink", swap_destination)

    with pytest.raises(OrdifileError) as captured:
        save_peak_table_mapping_set(mapping_set, destination)

    assert captured.value.code == "PEAK_MAPPING_INVALID"
    assert "PRIVATE-CANARY-PATH" not in str(captured.value)
    assert destination.read_bytes() == foreign
    assert not tuple(tmp_path.glob(".ordifile-peak-mapping-set-*.tmp"))


def test_profile_exact_match_uses_headers_order_and_format_not_values() -> None:
    profile = PeakTableMappingProfile(_mapping(), "Template A")

    assert profile.matches(
        PeakTableFormat.CSV,
        ("Retention Time", "Area", "Note"),
    )
    assert not profile.matches(
        PeakTableFormat.CSV,
        ("Area", "Retention Time", "Note"),
    )
    assert not profile.matches(
        PeakTableFormat.TSV,
        ("Retention Time", "Area", "Note"),
    )


def test_public_structural_fingerprint_has_golden_canonical_vector() -> None:
    profile = PeakTableMappingProfile(
        PeakTableMapping(
            ColumnSelector("RT", 1),
            ColumnSelector("Area", 2),
            "min",
            PeakTableFormat.CSV,
        ),
        "Local label",
        profile_id="profile-11111111111111111111111111111111",
    )
    mapping_set = PeakTableMappingSet(
        (profile,),
        set_id="profile-set-22222222222222222222222222222222",
    )

    assert profile.structural_fingerprint_sha256 == (
        "1529b75e98c12f1df0d80e167f205726f856bc4ce17a44d1275d7b9d82c9f615"
    )
    assert mapping_set.structural_fingerprint_sha256 == (
        "49a3dfd0728c97c5b3e311f1e125d8ec735da94d1f0c4b4dcd8fd2fd8abd3533"
    )


def test_public_fingerprint_excludes_labels_headers_units_and_user_metadata() -> None:
    first = PeakTableMappingProfile(
        _mapping(rt_unit="min", area_unit="mV.s"),
        "Private template A",
        profile_id="profile-11111111111111111111111111111111",
    )
    second = PeakTableMappingProfile(
        PeakTableMapping(
            retention_time_column=ColumnSelector("Secret RT header", 1),
            area_column=ColumnSelector("Secret Area header", 2),
            retention_time_unit="seconds",
            source_format=PeakTableFormat.CSV,
            area_unit="pA*s",
            ignored_columns=(ColumnSelector("Private note header", 3),),
            manufacturer="User declaration",
            software="Local software label",
        ),
        "Different local label",
        profile_id="profile-22222222222222222222222222222222",
    )

    assert first.structural_fingerprint_sha256 == second.structural_fingerprint_sha256
    assert first.exact_structure_sha256 != second.exact_structure_sha256
    serialized_public = json.dumps(
        {"fingerprint": first.structural_fingerprint_sha256}, sort_keys=True
    )
    assert "Private" not in serialized_public
    assert "Retention Time" not in serialized_public


def test_mapping_set_allows_same_structure_with_different_semantics_for_ambiguity() -> None:
    first = PeakTableMappingProfile(
        _mapping(rt_unit="min"),
        "Template minutes",
        profile_id="profile-11111111111111111111111111111111",
    )
    second = PeakTableMappingProfile(
        _mapping(rt_unit="s"),
        "Template seconds",
        profile_id="profile-22222222222222222222222222222222",
    )
    mapping_set = PeakTableMappingSet((first, second))

    matches = mapping_set.match(
        PeakTableFormat.CSV,
        ("Retention Time", "Area", "Note"),
    )

    assert matches == (first, second)


def test_mapping_set_rejects_duplicate_complete_profile() -> None:
    first = PeakTableMappingProfile(
        _mapping(),
        "First local label",
        profile_id="profile-11111111111111111111111111111111",
    )
    duplicate = PeakTableMappingProfile(
        _mapping(),
        "Second local label",
        profile_id="profile-22222222222222222222222222222222",
    )

    with pytest.raises(OrdifileError, match="duplicate complete"):
        PeakTableMappingSet((first, duplicate))


def test_mapping_set_rejects_duplicate_json_keys() -> None:
    mapping_set = PeakTableMappingSet((PeakTableMappingProfile(_mapping()),))
    text = mapping_set.to_json().replace(
        '"schema_version": 1',
        '"schema_version": 1, "schema_version": 1',
        1,
    )

    with pytest.raises(OrdifileError, match="duplicate object key"):
        PeakTableMappingSet.from_json(text)


def test_mapping_set_rejects_empty_and_profile_count_over_limit() -> None:
    with pytest.raises(OrdifileError, match="from 1 through"):
        PeakTableMappingSet(())

    profiles = tuple(
        PeakTableMappingProfile(
            _mapping(),
            profile_id=f"profile-{index:032x}",
            display_label=f"Profile {index}",
        )
        for index in range(33)
    )
    with pytest.raises(OrdifileError, match="from 1 through"):
        PeakTableMappingSet(profiles)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are unavailable")
def test_mapping_set_save_rejects_destination_symlink(tmp_path: Path) -> None:
    target = tmp_path / "private-target.json"
    target.write_text("preserve", encoding="utf-8")
    destination = tmp_path / "mappings.json"
    try:
        destination.symlink_to(target)
    except OSError:
        pytest.skip("this environment does not permit symlink creation")

    with pytest.raises(OrdifileError, match="regular file"):
        save_peak_table_mapping_set(
            PeakTableMappingSet((PeakTableMappingProfile(_mapping()),)),
            destination,
            overwrite=True,
        )

    assert target.read_text(encoding="utf-8") == "preserve"


def test_xlsx_profile_sheet_policy_is_exact_or_single_visible() -> None:
    mapping = _mapping(source_format=PeakTableFormat.XLSX)
    fixed = PeakTableMappingProfile(mapping, worksheet_title="Results")
    flexible = PeakTableMappingProfile(
        mapping,
        profile_id="profile-11111111111111111111111111111111",
    )

    headers = mapping.declared_headers
    assert fixed.matches(PeakTableFormat.XLSX, headers, worksheet_title="Results")
    assert not fixed.matches(PeakTableFormat.XLSX, headers, worksheet_title="Other")
    assert flexible.matches(
        PeakTableFormat.XLSX,
        headers,
        worksheet_title="Changing run title",
        single_visible_worksheet=True,
    )
    assert not flexible.matches(
        PeakTableFormat.XLSX,
        headers,
        worksheet_title="Changing run title",
        single_visible_worksheet=False,
    )
