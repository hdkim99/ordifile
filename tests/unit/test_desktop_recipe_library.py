# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QLockFile

from ordifile import ConversionRecipe
from ordifile.core.models import SortMode
from ordifile.desktop import recipe_library as recipe_library_module
from ordifile.desktop.recipe_library import (
    MAX_LOCAL_RECIPES,
    RecipeLibrary,
    RecipeLibraryError,
)


def test_empty_library_does_not_create_its_directory(tmp_path: Path) -> None:
    root = tmp_path / "recipes"
    library = RecipeLibrary(root)

    assert library.snapshot().entries == ()
    assert not root.exists()
    assert library.maximum == MAX_LOCAL_RECIPES


def test_named_recipe_round_trips_with_opaque_filename_and_restart(tmp_path: Path) -> None:
    root = tmp_path / "recipes"
    recipe = ConversionRecipe(sort=SortMode.FILENAME)
    library = RecipeLibrary(root)

    stored = library.create(recipe, "GC 주간 분석")

    assert stored.display_name == "GC 주간 분석"
    assert stored.recipe.display_label == "GC 주간 분석"
    assert stored.recipe.semantic_sha256 == recipe.semantic_sha256
    filenames = [member.name for member in root.iterdir()]
    assert filenames == [f"{stored.recipe_id}.json"]
    assert "GC" not in filenames[0]
    restarted = RecipeLibrary(root).snapshot()
    assert restarted.entries == (stored,)


@pytest.mark.parametrize("name", ["CON", "AUX", "촉매 실험 기본 설정"])
def test_display_names_never_become_storage_filenames(tmp_path: Path, name: str) -> None:
    stored = RecipeLibrary(tmp_path / "recipes").create(ConversionRecipe(), name)

    assert stored.display_name == name
    assert name not in f"{stored.recipe_id}.json"


def test_rename_changes_only_display_metadata_and_duplicate_gets_new_id(
    tmp_path: Path,
) -> None:
    library = RecipeLibrary(tmp_path / "recipes")
    original = library.create(ConversionRecipe(sort=SortMode.INPUT_ORDER), "Original")

    renamed = library.rename(original.recipe_id, "이름 변경")
    duplicate = library.duplicate(original.recipe_id, "Copy")

    assert renamed.recipe_id == original.recipe_id
    assert renamed.recipe.semantic_sha256 == original.recipe.semantic_sha256
    assert renamed.revision_sha256 != original.revision_sha256
    assert duplicate.recipe_id != original.recipe_id
    assert duplicate.recipe.semantic_sha256 == original.recipe.semantic_sha256


def test_duplicate_names_and_library_bound_fail_without_overwriting(tmp_path: Path) -> None:
    library = RecipeLibrary(tmp_path / "recipes", maximum=1)
    first = library.create(ConversionRecipe(), "Daily")

    with pytest.raises(RecipeLibraryError, match="already uses") as duplicate:
        library.create(ConversionRecipe(sort=SortMode.FILENAME), "daily")
    assert duplicate.value.code == "RECIPE_NAME_EXISTS"
    assert library.get(first.recipe_id) == first
    with pytest.raises(RecipeLibraryError, match="limited"):
        library.create(ConversionRecipe(sort=SortMode.FILENAME), "Second")


def test_corrupt_symlink_and_duplicate_name_members_are_isolated(tmp_path: Path) -> None:
    root = tmp_path / "recipes"
    library = RecipeLibrary(root)
    valid = library.create(ConversionRecipe(), "Daily")
    (root / ("f" * 32 + ".json")).write_text("not-json", encoding="utf-8")
    duplicate_name = replace(valid.recipe, sort=SortMode.FILENAME)
    from ordifile.desktop.services import save_recipe

    save_recipe(duplicate_name, root / ("e" * 32 + ".json"))
    (root / ("d" * 32 + ".json")).symlink_to(root / f"{valid.recipe_id}.json")

    snapshot = library.snapshot()

    assert len(snapshot.entries) == 1
    assert snapshot.entries[0].display_name == "Daily"
    assert snapshot.invalid_count == 3


def test_update_and_delete_reject_a_stale_revision(tmp_path: Path) -> None:
    library = RecipeLibrary(tmp_path / "recipes")
    first = library.create(ConversionRecipe(), "Daily")
    current = library.update(
        first.recipe_id,
        ConversionRecipe(sort=SortMode.FILENAME),
        expected_revision_sha256=first.revision_sha256,
    )

    with pytest.raises(RecipeLibraryError, match="changed in another process"):
        library.update(
            first.recipe_id,
            ConversionRecipe(sort=SortMode.INPUT_ORDER),
            expected_revision_sha256=first.revision_sha256,
        )
    with pytest.raises(RecipeLibraryError, match="changed in another process"):
        library.delete(first.recipe_id, expected_revision_sha256=first.revision_sha256)

    library.delete(current.recipe_id, expected_revision_sha256=current.revision_sha256)
    assert library.snapshot().entries == ()


def test_mutation_lock_prevents_interleaved_recipe_writes(tmp_path: Path) -> None:
    root = tmp_path / "recipes"
    library = RecipeLibrary(root)
    stored = library.create(ConversionRecipe(), "Daily")
    lock = QLockFile(str(root / ".ordifile-recipe-library.lock"))
    assert lock.tryLock(0)
    try:
        with pytest.raises(RecipeLibraryError) as update_error:
            library.update(
                stored.recipe_id,
                ConversionRecipe(sort=SortMode.FILENAME),
                expected_revision_sha256=stored.revision_sha256,
            )
        with pytest.raises(RecipeLibraryError) as delete_error:
            library.delete(
                stored.recipe_id,
                expected_revision_sha256=stored.revision_sha256,
            )
    finally:
        lock.unlock()

    assert update_error.value.code == "RECIPE_LIBRARY_BUSY"
    assert delete_error.value.code == "RECIPE_LIBRARY_BUSY"
    assert library.get(stored.recipe_id) == stored


def test_mutation_lock_permission_failure_is_not_reported_as_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PermissionDeniedLock:
        LockError = QLockFile.LockError

        def __init__(self, _path: str) -> None:
            pass

        def setStaleLockTime(self, _milliseconds: int) -> None:
            pass

        def tryLock(self, _timeout: int) -> bool:
            return False

        def error(self) -> QLockFile.LockError:
            return QLockFile.LockError.PermissionError

    monkeypatch.setattr(recipe_library_module, "QLockFile", PermissionDeniedLock)
    library = RecipeLibrary(tmp_path / "recipes")

    with pytest.raises(RecipeLibraryError) as caught:
        library.create(ConversionRecipe(), "Daily")

    assert caught.value.code == "RECIPE_LIBRARY_WRITE_FAILED"
    assert "another Ordifile window" not in caught.value.message


def test_resource_failure_is_not_reported_as_one_corrupt_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "recipes"
    library = RecipeLibrary(root)
    stored = library.create(ConversionRecipe(), "Daily")

    def fail_for_resource_pressure(_path: Path) -> ConversionRecipe:
        raise MemoryError

    monkeypatch.setattr(recipe_library_module, "load_recipe", fail_for_resource_pressure)

    with pytest.raises(MemoryError):
        library.snapshot()
    assert (root / f"{stored.recipe_id}.json").is_file()


def test_unavailable_library_does_not_change_to_another_location(tmp_path: Path) -> None:
    unavailable = tmp_path / "not-a-directory"
    unavailable.write_text("local", encoding="utf-8")
    library = RecipeLibrary(unavailable)

    with pytest.raises(RecipeLibraryError) as caught:
        library.snapshot()
    assert caught.value.code == "RECIPE_LIBRARY_UNAVAILABLE"
    assert unavailable.read_text(encoding="utf-8") == "local"
