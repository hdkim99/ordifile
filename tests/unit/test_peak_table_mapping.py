# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ordifile.core.errors import OrdifileError
from ordifile.core.peak_mapping import (
    MAX_PEAK_MAPPING_BYTES,
    ColumnSelector,
    PeakTableFormat,
    PeakTableMapping,
    load_peak_table_mapping,
    save_peak_table_mapping,
)


def mapping() -> PeakTableMapping:
    return PeakTableMapping(
        retention_time_column=ColumnSelector("RT result", 2),
        area_column=ColumnSelector("Peak area", 3),
        retention_time_unit="min",
        source_format=PeakTableFormat.CSV,
        peak_index_column=ColumnSelector("Peak", 1),
        ignored_columns=(ColumnSelector("Comment", 4),),
        area_unit="mV.s",
    )


def test_mapping_json_round_trip_is_deterministic() -> None:
    original = mapping()

    restored = PeakTableMapping.from_json(original.to_json())

    assert restored == original
    assert restored.semantic_sha256 == original.semantic_sha256
    assert restored.mapped_roles == ("retention_time", "area", "peak_number")


def test_mapping_rejects_duplicate_json_keys() -> None:
    payload = mapping().to_dict()
    text = json.dumps(payload)
    text = text.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')

    with pytest.raises(OrdifileError, match="duplicate object key"):
        PeakTableMapping.from_json(text)


def test_mapping_requires_every_header_to_be_mapped_or_ignored() -> None:
    incomplete = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "s",
        PeakTableFormat.CSV,
    )

    with pytest.raises(OrdifileError) as captured:
        incomplete.semantic_headers(["RT", "Area", "private note"])

    assert captured.value.code == "PEAK_MAPPING_COLUMNS_UNCLASSIFIED"


def test_mapping_rejects_shared_source_position() -> None:
    with pytest.raises(OrdifileError, match="different source column"):
        PeakTableMapping(
            ColumnSelector("Value", 1),
            ColumnSelector("Value", 1),
            "s",
            PeakTableFormat.CSV,
        )


def test_secondary_retention_requires_unit() -> None:
    with pytest.raises(OrdifileError, match="provided together"):
        PeakTableMapping(
            ColumnSelector("RT1", 1),
            ColumnSelector("Area", 3),
            "s",
            PeakTableFormat.TSV,
            secondary_retention_time_column=ColumnSelector("RT2", 2),
        )


def test_height_unit_requires_height_column() -> None:
    with pytest.raises(OrdifileError, match="height_unit requires"):
        PeakTableMapping(
            ColumnSelector("RT", 1),
            ColumnSelector("Area", 2),
            "s",
            PeakTableFormat.CSV,
            height_unit="mV",
        )


def test_minimal_json_omits_optional_fields() -> None:
    restored = PeakTableMapping.from_json(
        """{
          "schema_version": 1,
          "source_format": "csv",
          "retention_time_column": {"label": "RT", "index": 1},
          "area_column": {"label": "Area", "index": 2},
          "retention_time_unit": "min",
          "area_unit": null
        }"""
    )

    assert restored == PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
    )


def test_mapping_rejects_directional_format_character() -> None:
    with pytest.raises(OrdifileError, match="directional format"):
        ColumnSelector("RT\u202e", 1)


def test_mapping_rejects_normalized_payload_larger_than_loader_limit() -> None:
    ignored = tuple(
        ColumnSelector(f"ignored-{index:04d}-" + "x" * 90, index) for index in range(3, 703)
    )

    with pytest.raises(OrdifileError, match=str(MAX_PEAK_MAPPING_BYTES)):
        PeakTableMapping(
            ColumnSelector("RT", 1),
            ColumnSelector("Area", 2),
            "s",
            PeakTableFormat.CSV,
            ignored_columns=ignored,
        )


def test_mapping_rejects_huge_json_integer_as_structured_error() -> None:
    text = (
        mapping()
        .to_json()
        .replace(
            '"schema_version": 1',
            '"schema_version": ' + "9" * 10_000,
        )
    )

    with pytest.raises(OrdifileError) as captured:
        PeakTableMapping.from_json(text)

    assert captured.value.code == "PEAK_MAPPING_INVALID"


def test_mapping_save_load_round_trip_and_no_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "mapping.json"
    save_peak_table_mapping(mapping(), destination)

    assert load_peak_table_mapping(destination) == mapping()
    before = destination.read_bytes()
    with pytest.raises(OrdifileError) as captured:
        save_peak_table_mapping(mapping(), destination)

    assert captured.value.code == "PEAK_MAPPING_EXISTS"
    assert destination.read_bytes() == before


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are unavailable")
def test_mapping_save_rejects_dangling_destination_symlink(tmp_path: Path) -> None:
    target = tmp_path / "uncreated-target.json"
    destination = tmp_path / "mapping.json"
    try:
        destination.symlink_to(target)
    except OSError:
        pytest.skip("this environment does not permit symlink creation")

    with pytest.raises(OrdifileError, match="regular file"):
        save_peak_table_mapping(mapping(), destination, overwrite=True)

    assert destination.is_symlink()
    assert not target.exists()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are unavailable")
def test_mapping_save_rejects_existing_destination_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("preserve", encoding="utf-8")
    destination = tmp_path / "mapping.json"
    try:
        destination.symlink_to(target)
    except OSError:
        pytest.skip("this environment does not permit symlink creation")

    with pytest.raises(OrdifileError, match="regular file"):
        save_peak_table_mapping(mapping(), destination, overwrite=True)

    assert target.read_text(encoding="utf-8") == "preserve"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are unavailable")
def test_mapping_save_ignores_preplanted_legacy_fixed_temp_symlink(tmp_path: Path) -> None:
    destination = tmp_path / "mapping.json"
    legacy_temporary = tmp_path / ".mapping.json.tmp"
    target = tmp_path / "uncreated-target.json"
    try:
        legacy_temporary.symlink_to(target)
    except OSError:
        pytest.skip("this environment does not permit symlink creation")

    save_peak_table_mapping(mapping(), destination)

    assert load_peak_table_mapping(destination) == mapping()
    assert legacy_temporary.is_symlink()
    assert not target.exists()
