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
    PeakTableImportSettings,
    PeakTableMapping,
    PeakTableTextEncoding,
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


def test_default_import_settings_preserve_schema_one_json_and_semantic_hash() -> None:
    original = mapping()

    assert "import_settings" not in original.to_dict()
    assert original.semantic_sha256 == (
        "0cfcc34585095dd60d3fbc65aeb73a1e8d38b6d09f61cb0d1db3fbaa533f5e19"
    )


def test_explicit_import_settings_round_trip_and_change_semantic_identity() -> None:
    original = mapping()
    configured = PeakTableMapping(
        original.retention_time_column,
        original.area_column,
        original.retention_time_unit,
        original.source_format,
        area_unit=original.area_unit,
        peak_index_column=original.peak_index_column,
        ignored_columns=original.ignored_columns,
        import_settings=PeakTableImportSettings(PeakTableTextEncoding.CP949, 6),
    )

    restored = PeakTableMapping.from_json(configured.to_json())

    assert restored == configured
    assert restored.to_dict()["import_settings"] == {
        "text_encoding": "cp949",
        "header_row": 6,
    }
    assert restored.semantic_sha256 != original.semantic_sha256


def test_import_settings_accept_documented_header_row_maximum() -> None:
    settings = PeakTableImportSettings(header_row=100)

    assert settings.header_row == 100


@pytest.mark.parametrize("header_row", (0, 101, True))
def test_import_settings_reject_invalid_header_row(header_row: object) -> None:
    with pytest.raises(OrdifileError, match="header_row"):
        PeakTableImportSettings.from_value({"text_encoding": "utf-8-sig", "header_row": header_row})


def test_import_settings_reject_unknown_encoding_and_fields() -> None:
    with pytest.raises(OrdifileError, match="text_encoding"):
        PeakTableImportSettings.from_value({"text_encoding": "auto", "header_row": 1})
    with pytest.raises(OrdifileError, match="exactly"):
        PeakTableImportSettings.from_value(
            {"text_encoding": "utf-8-sig", "header_row": 1, "guess": True}
        )


def test_xlsx_mapping_rejects_text_encoding_setting() -> None:
    with pytest.raises(OrdifileError, match="only for text"):
        PeakTableMapping(
            ColumnSelector("RT", 1),
            ColumnSelector("Area", 2),
            "min",
            PeakTableFormat.XLSX,
            import_settings=PeakTableImportSettings(PeakTableTextEncoding.CP949, 1),
        )


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


def test_mapping_rejects_lone_surrogate_as_structured_error() -> None:
    with pytest.raises(OrdifileError) as captured:
        PeakTableMapping.from_json("\ud800")

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


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs are unavailable")
def test_mapping_load_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    source = tmp_path / "mapping.json"
    os.mkfifo(source)

    with pytest.raises(OrdifileError, match="regular file"):
        load_peak_table_mapping(source)


def test_mapping_non_overwrite_publish_retries_temp_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "mapping.json"
    real_unlink = os.unlink
    failed_once = False

    def reject_owned_temporary(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> None:
        nonlocal failed_once
        if ".ordifile-peak-mapping-" in os.fsdecode(path) and not failed_once:
            failed_once = True
            raise PermissionError("PRIVATE-CANARY-PATH")
        real_unlink(path)

    monkeypatch.setattr(os, "unlink", reject_owned_temporary)

    save_peak_table_mapping(mapping(), destination)

    assert load_peak_table_mapping(destination) == mapping()
    assert not tuple(tmp_path.glob(".ordifile-peak-mapping-*.tmp"))


def test_mapping_publish_reports_repeated_temp_cleanup_failure_without_raw_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "mapping.json"
    real_unlink = os.unlink
    failures = 0

    def reject_twice(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> None:
        nonlocal failures
        if ".ordifile-peak-mapping-" in os.fsdecode(path) and failures < 2:
            failures += 1
            raise PermissionError("PRIVATE-CANARY-PATH")
        real_unlink(path)

    monkeypatch.setattr(os, "unlink", reject_twice)

    with pytest.raises(OrdifileError) as captured:
        save_peak_table_mapping(mapping(), destination)

    assert captured.value.code == "PEAK_MAPPING_INVALID"
    assert "PRIVATE-CANARY-PATH" not in str(captured.value)
    assert load_peak_table_mapping(destination) == mapping()
    assert not tuple(tmp_path.glob(".ordifile-peak-mapping-*.tmp"))


def test_mapping_publish_preserves_foreign_destination_swapped_during_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "mapping.json"
    foreign = b"foreign-preserved"
    real_unlink = os.unlink
    swapped = False

    def swap_destination(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> None:
        nonlocal swapped
        if ".ordifile-peak-mapping-" in os.fsdecode(path) and not swapped:
            swapped = True
            real_unlink(destination)
            destination.write_bytes(foreign)
            raise PermissionError("PRIVATE-CANARY-PATH")
        real_unlink(path)

    monkeypatch.setattr(os, "unlink", swap_destination)

    with pytest.raises(OrdifileError) as captured:
        save_peak_table_mapping(mapping(), destination)

    assert captured.value.code == "PEAK_MAPPING_INVALID"
    assert "PRIVATE-CANARY-PATH" not in str(captured.value)
    assert destination.read_bytes() == foreign
    assert not tuple(tmp_path.glob(".ordifile-peak-mapping-*.tmp"))


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
