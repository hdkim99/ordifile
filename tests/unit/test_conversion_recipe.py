# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

import ordifile.core.recipe as recipe_module
from ordifile.core.errors import OrdifileError
from ordifile.core.models import SortMode
from ordifile.core.peak_mapping import (
    ColumnSelector,
    PeakTableFormat,
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
)
from ordifile.core.recipe import (
    MAX_CONVERSION_RECIPE_BYTES,
    ConversionRecipe,
    load_conversion_recipe,
    save_conversion_recipe,
)


def _mapping() -> PeakTableMapping:
    return PeakTableMapping(
        ColumnSelector("Retention Time", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
        area_unit="mV.s",
        ignored_columns=(ColumnSelector("Note", 3),),
    )


def _mapping_set(*, label: str = "로컬 템플릿") -> PeakTableMappingSet:
    return PeakTableMappingSet(
        (
            PeakTableMappingProfile(
                _mapping(),
                label,
                profile_id="profile-11111111111111111111111111111111",
            ),
        ),
        set_id="profile-set-22222222222222222222222222222222",
    )


def test_recipe_round_trip_is_strict_unicode_and_path_free(tmp_path: Path) -> None:
    recipe = ConversionRecipe(
        recursive=True,
        extensions=(".csv", ".xlsx"),
        sort=SortMode.INPUT_ORDER,
        include_signals=True,
        peak_table_mapping_set=_mapping_set(),
        on_error="stop",
        sidecar_mode="csv",
        display_label="주간 GC 변환",
    )
    destination = tmp_path / "laboratory-recipe.json"

    save_conversion_recipe(recipe, destination)
    restored = load_conversion_recipe(destination)

    assert restored == recipe
    assert restored.display_label == "주간 GC 변환"
    assert restored.to_json() == recipe.to_json()
    assert "/Users/" not in restored.to_json()
    assert "C:\\" not in restored.to_json()
    assert "source_path" not in restored.to_json()
    assert "output_path" not in restored.to_json()
    assert "overwrite" not in restored.to_json()
    assert restored.to_json().endswith("\n")
    assert restored.semantic_sha256 == (
        "2b0fe027fb0976b887a2bced4f5eb7d96de7f8a6b3a5c01f3b75179da3350f51"
    )
    assert restored.public_fingerprint_sha256 == (
        "5238a3e975a0e781bc1ddae8ce81868353e2c655ef1dd373c82263c851b82eea"
    )


def test_recipe_supports_one_embedded_single_mapping() -> None:
    recipe = ConversionRecipe(peak_table_mapping=_mapping(), display_label="Single mapping")

    restored = ConversionRecipe.from_json(recipe.to_json())

    assert restored == recipe
    assert restored.peak_table_mapping == _mapping()
    assert restored.peak_table_mapping_set is None


def test_recipe_semantic_hash_excludes_only_recipe_display_label() -> None:
    first = ConversionRecipe(peak_table_mapping_set=_mapping_set(), display_label="First")
    renamed = replace(first, display_label="두 번째")
    changed = replace(first, include_signals=True)

    assert first.semantic_sha256 == renamed.semantic_sha256
    assert first.public_fingerprint_sha256 == renamed.public_fingerprint_sha256
    assert first.semantic_sha256 != changed.semantic_sha256
    assert first.public_fingerprint_sha256 != changed.public_fingerprint_sha256


@pytest.mark.parametrize(
    "changed",
    [
        ConversionRecipe(recursive=True),
        ConversionRecipe(extensions=(".csv",)),
        ConversionRecipe(sort=SortMode.INPUT_ORDER),
        ConversionRecipe(include_signals=True),
        ConversionRecipe(adapter="generic_csv"),
        ConversionRecipe(sheet="Results"),
        ConversionRecipe(include_hidden_sheets=True),
        ConversionRecipe(on_error="stop"),
        ConversionRecipe(sidecar_mode="csv"),
    ],
)
def test_every_persisted_behavior_option_changes_recipe_identity(
    changed: ConversionRecipe,
) -> None:
    baseline = ConversionRecipe()

    assert changed.semantic_sha256 != baseline.semantic_sha256
    assert changed.public_fingerprint_sha256 != baseline.public_fingerprint_sha256


def test_private_sheet_title_changes_only_exact_semantic_identity() -> None:
    first = ConversionRecipe(sheet="PRIVATE-FIRST")
    second = ConversionRecipe(sheet="PRIVATE-SECOND")

    assert first.semantic_sha256 != second.semantic_sha256
    assert first.public_fingerprint_sha256 == second.public_fingerprint_sha256


def test_mapping_profile_display_label_does_not_change_behavior_identity() -> None:
    first = ConversionRecipe(peak_table_mapping_set=_mapping_set(label="First"))
    second = ConversionRecipe(peak_table_mapping_set=_mapping_set(label="두 번째"))

    assert first.semantic_sha256 == second.semantic_sha256
    assert first.public_fingerprint_sha256 == second.public_fingerprint_sha256


def test_recipe_hash_is_independent_of_json_key_order_whitespace_and_line_endings() -> None:
    recipe = ConversionRecipe(peak_table_mapping_set=_mapping_set())
    payload = recipe.to_dict()
    reordered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    windows_lines = recipe.to_json().replace("\n", "\r\n")

    assert ConversionRecipe.from_json(reordered).semantic_sha256 == recipe.semantic_sha256
    assert ConversionRecipe.from_json(windows_lines).semantic_sha256 == recipe.semantic_sha256


def test_recipe_public_fingerprint_excludes_private_mapping_text() -> None:
    private = ConversionRecipe(peak_table_mapping_set=_mapping_set(label="PRIVATE-LABEL"))
    public_text = json.dumps(
        {"fingerprint": private.public_fingerprint_sha256, "repr": repr(private)},
        sort_keys=True,
    )

    assert "PRIVATE-LABEL" not in public_text
    assert "Retention Time" not in public_text
    assert "mV.s" not in public_text
    assert private.semantic_sha256 not in public_text


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update({"unknown": True}),
        lambda payload: payload.pop("options"),
        lambda payload: payload["options"].update({"recursive": 1}),
        lambda payload: payload["options"].update({"sort": "unknown"}),
        lambda payload: payload["mapping"].update({"extra": None}),
    ],
)
def test_recipe_rejects_unknown_missing_and_wrong_typed_fields(
    mutator: Callable[[dict[str, object]], None],
) -> None:
    payload = ConversionRecipe().to_dict()
    mutator(payload)

    with pytest.raises(OrdifileError) as captured:
        ConversionRecipe.from_json(json.dumps(payload))

    assert captured.value.code == "CONVERSION_RECIPE_INVALID"


def test_recipe_rejects_duplicate_keys_nonstandard_numbers_and_lone_surrogate() -> None:
    with pytest.raises(OrdifileError, match="duplicate"):
        ConversionRecipe.from_json('{"schema_version":1,"schema_version":1}')
    with pytest.raises(OrdifileError, match="non-standard"):
        ConversionRecipe.from_json('{"schema_version":NaN}')
    with pytest.raises(OrdifileError, match="Unicode"):
        ConversionRecipe.from_json("\ud800")


def test_recipe_rejects_oversized_json_before_decode() -> None:
    with pytest.raises(OrdifileError, match="byte limit"):
        ConversionRecipe.from_json(" " * (MAX_CONVERSION_RECIPE_BYTES + 1))


def test_recipe_rejects_conflicting_routing_configuration() -> None:
    with pytest.raises(OrdifileError, match="adapter fallback"):
        ConversionRecipe(adapter="generic.csv", peak_table_mapping_set=_mapping_set())
    with pytest.raises(OrdifileError, match="both"):
        ConversionRecipe(
            peak_table_mapping=_mapping(),
            peak_table_mapping_set=_mapping_set(),
        )
    with pytest.raises(OrdifileError, match="worksheet selection"):
        ConversionRecipe(peak_table_mapping_set=_mapping_set(), sheet="Results")


def test_recipe_save_is_no_overwrite_by_default(tmp_path: Path) -> None:
    destination = tmp_path / "recipe.json"
    destination.write_bytes(b"foreign-preserved")

    with pytest.raises(OrdifileError) as captured:
        save_conversion_recipe(ConversionRecipe(), destination)

    assert captured.value.code == "CONVERSION_RECIPE_EXISTS"
    assert destination.read_bytes() == b"foreign-preserved"


def test_recipe_save_replaces_only_after_explicit_local_confirmation(tmp_path: Path) -> None:
    destination = tmp_path / "recipe.json"
    first = ConversionRecipe(display_label="First")
    second = ConversionRecipe(display_label="두 번째", include_signals=True)
    save_conversion_recipe(first, destination)

    save_conversion_recipe(second, destination, overwrite=True)

    assert load_conversion_recipe(destination) == second
    assert load_conversion_recipe(destination).display_label == "두 번째"


def test_recipe_save_no_replace_consumes_private_temp_without_path_unlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "recipe.json"
    original_unlink = os.unlink

    def reject_recipe_temp_unlink(path: str | os.PathLike[str]) -> None:
        if ".ordifile-conversion-recipe-" in os.fspath(path):
            raise AssertionError("successful publication must consume the private temp")
        original_unlink(path)

    monkeypatch.setattr(os, "unlink", reject_recipe_temp_unlink)

    save_conversion_recipe(ConversionRecipe(display_label="private local label"), destination)

    assert load_conversion_recipe(destination).display_label == "private local label"
    assert not tuple(tmp_path.glob(".ordifile-conversion-recipe-*.tmp"))


def test_recipe_save_failed_publication_retries_owned_temp_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "recipe.json"
    original_unlink = os.unlink
    failures = 0

    def transient_unlink(path: str | os.PathLike[str]) -> None:
        nonlocal failures
        if ".ordifile-conversion-recipe-" in os.fspath(path) and failures == 0:
            failures += 1
            raise OSError("synthetic transient cleanup failure")
        original_unlink(path)

    def fail_publication(_source: Path, _destination: Path) -> None:
        raise OSError("synthetic publication failure")

    monkeypatch.setattr(os, "unlink", transient_unlink)
    monkeypatch.setattr(recipe_module, "rename_no_replace", fail_publication)

    with pytest.raises(OrdifileError, match="could not be written"):
        save_conversion_recipe(ConversionRecipe(display_label="private local label"), destination)

    assert not destination.exists()
    assert not tuple(tmp_path.glob(".ordifile-conversion-recipe-*.tmp"))


def test_recipe_save_persistent_cleanup_failure_keeps_error_path_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "recipe.json"
    original_unlink = os.unlink

    def persistent_unlink(path: str | os.PathLike[str]) -> None:
        if ".ordifile-conversion-recipe-" in os.fspath(path):
            raise OSError(5, "synthetic cleanup failure", os.fspath(path))
        original_unlink(path)

    def fail_publication(_source: Path, _destination: Path) -> None:
        raise OSError("synthetic publication failure")

    monkeypatch.setattr(os, "unlink", persistent_unlink)
    monkeypatch.setattr(recipe_module, "rename_no_replace", fail_publication)

    with pytest.raises(OrdifileError) as captured:
        save_conversion_recipe(ConversionRecipe(display_label="private local label"), destination)

    temporaries = tuple(tmp_path.glob(".ordifile-conversion-recipe-*.tmp"))
    assert captured.value.code == "CONVERSION_RECIPE_INVALID"
    assert str(tmp_path) not in str(captured.value)
    assert len(temporaries) == 1
    assert temporaries[0].stat().st_mode & 0o077 == 0
    monkeypatch.setattr(os, "unlink", original_unlink)
    temporaries[0].unlink()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs are unavailable")
def test_recipe_load_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    source = tmp_path / "recipe.json"
    os.mkfifo(source)

    with pytest.raises(OrdifileError, match="regular file"):
        load_conversion_recipe(source)


def test_recipe_load_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(ConversionRecipe().to_json(), encoding="utf-8")
    source = tmp_path / "recipe.json"
    source.symlink_to(target)

    with pytest.raises(OrdifileError, match="symbolic"):
        load_conversion_recipe(source)


@pytest.mark.parametrize("readme", ["README.md", "README.ko.md"])
def test_readme_examples_import_the_planning_function_they_call(readme: str) -> None:
    text = (Path(__file__).parents[2] / readme).read_text(encoding="utf-8")

    assert (
        "from ordifile.api import convert_plan, plan_conversion\n\n"
        'plan = plan_conversion("input", "results.xlsx")'
    ) in text
    assert "from ordifile.api import convert_plan, plan_recipe" in text
    assert 'plan = plan_recipe("new-experiment", "results.xlsx", recipe=recipe)' in text
