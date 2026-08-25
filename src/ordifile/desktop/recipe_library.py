# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Private local Conversion Recipe library presented as Saved Setups in the desktop."""

from __future__ import annotations

import os
import re
import stat
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QLockFile

from ordifile import ConversionRecipe
from ordifile.core.errors import OrdifileError
from ordifile.desktop.services import load_recipe, save_recipe

MAX_LOCAL_RECIPES = 64
MAX_LOCAL_RECIPE_DIRECTORY_MEMBERS = 256
MAX_LOCAL_RECIPE_AGGREGATE_BYTES = 64 * 1024 * 1024
_RECIPE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


class RecipeLibraryError(Exception):
    """Describe one bounded local saved setup failure without exposing its path."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class StoredRecipe:
    """One validated named Recipe stored under an opaque local identifier."""

    recipe_id: str
    display_name: str
    recipe: ConversionRecipe
    revision_sha256: str


@dataclass(frozen=True, slots=True)
class RecipeLibrarySnapshot:
    """Validated entries plus a bounded count of members that could not be loaded."""

    entries: tuple[StoredRecipe, ...]
    invalid_count: int = 0


def standard_recipe_library_root() -> Path:
    """Return the OS-standard application configuration location for saved setups."""
    from PySide6.QtCore import QStandardPaths

    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    if not location:
        raise RecipeLibraryError(
            "RECIPE_LIBRARY_UNAVAILABLE",
            "The standard local configuration location is unavailable.",
        )
    return Path(location) / "recipes"


def normalize_recipe_name(value: str) -> str:
    """Return one bounded local display name without deriving a filesystem name."""
    if type(value) is not str:
        raise RecipeLibraryError("RECIPE_NAME_INVALID", "Recipe name must be text.")
    name = unicodedata.normalize("NFC", value).strip()
    if not name:
        raise RecipeLibraryError("RECIPE_NAME_INVALID", "Recipe name cannot be empty.")
    try:
        ConversionRecipe(display_label=name)
    except OrdifileError as error:
        raise RecipeLibraryError(
            "RECIPE_NAME_INVALID", "Recipe name exceeds the supported local limit."
        ) from error
    return name


class RecipeLibrary:
    """Bounded collection of strict Recipe JSON files in one user-local directory."""

    def __init__(self, root: Path, *, maximum: int = MAX_LOCAL_RECIPES) -> None:
        if not isinstance(root, Path):
            raise TypeError("root must be a Path")
        if type(maximum) is not int or maximum < 1 or maximum > MAX_LOCAL_RECIPES:
            raise ValueError(f"maximum must be between 1 and {MAX_LOCAL_RECIPES}")
        self._root = root
        self._maximum = maximum

    @classmethod
    def standard(cls) -> RecipeLibrary:
        """Create a library using the platform's user-local application config path."""
        return cls(standard_recipe_library_root())

    @property
    def maximum(self) -> int:
        """Return the maximum number of valid saved setups."""
        return self._maximum

    def _path(self, recipe_id: str) -> Path:
        if type(recipe_id) is not str or _RECIPE_ID_PATTERN.fullmatch(recipe_id) is None:
            raise RecipeLibraryError(
                "RECIPE_LIBRARY_ID_INVALID", "The saved setup identifier is invalid."
            )
        return self._root / f"{recipe_id}.json"

    def _existing_directory(self) -> bool:
        try:
            if not self._root.exists():
                return False
            if self._root.is_symlink() or not self._root.is_dir():
                raise RecipeLibraryError(
                    "RECIPE_LIBRARY_UNAVAILABLE",
                    "The local Recipe library location is not a regular directory.",
                )
        except OSError as error:
            raise RecipeLibraryError(
                "RECIPE_LIBRARY_UNAVAILABLE", "The local Recipe library could not be read."
            ) from error
        return True

    def _ensure_directory(self) -> None:
        if self._existing_directory():
            return
        try:
            self._root.mkdir(mode=0o700, parents=True, exist_ok=False)
        except FileExistsError as error:
            if not self._existing_directory():
                raise RecipeLibraryError(
                    "RECIPE_LIBRARY_UNAVAILABLE",
                    "The local Recipe library could not be created.",
                ) from error
        except OSError as error:
            raise RecipeLibraryError(
                "RECIPE_LIBRARY_UNAVAILABLE",
                "The local Recipe library could not be created.",
            ) from error

    @contextmanager
    def _mutation_lock(self) -> Iterator[None]:
        """Serialize short library writes across cooperating desktop processes."""
        self._ensure_directory()
        lock = QLockFile(os.fspath(self._root / ".ordifile-recipe-library.lock"))
        lock.setStaleLockTime(30_000)
        if not lock.tryLock(0):
            if lock.error() != QLockFile.LockError.LockFailedError:
                raise RecipeLibraryError(
                    "RECIPE_LIBRARY_WRITE_FAILED",
                    "The local Recipe library could not be locked for writing.",
                )
            raise RecipeLibraryError(
                "RECIPE_LIBRARY_BUSY",
                "The local Recipe library is being changed by another Ordifile window.",
            )
        try:
            yield
        finally:
            lock.unlock()

    def snapshot(self) -> RecipeLibrarySnapshot:
        """Load valid members independently so one damaged file cannot block the GUI."""
        if not self._existing_directory():
            return RecipeLibrarySnapshot(())
        try:
            members: list[Path] = []
            with os.scandir(self._root) as iterator:
                for directory_entry in iterator:
                    if len(members) >= MAX_LOCAL_RECIPE_DIRECTORY_MEMBERS:
                        raise RecipeLibraryError(
                            "RECIPE_LIBRARY_BOUNDS_EXCEEDED",
                            "The local Recipe library contains too many directory members.",
                        )
                    members.append(Path(directory_entry.path))
            members.sort(key=lambda item: item.name)
        except RecipeLibraryError:
            raise
        except OSError as error:
            raise RecipeLibraryError(
                "RECIPE_LIBRARY_UNAVAILABLE", "The local Recipe library could not be read."
            ) from error
        entries: list[StoredRecipe] = []
        invalid_count = 0
        aggregate_bytes = 0
        names: set[str] = set()
        for member_path in members:
            if member_path.suffix.casefold() != ".json":
                continue
            recipe_id = member_path.stem
            if _RECIPE_ID_PATTERN.fullmatch(recipe_id) is None:
                invalid_count += 1
                continue
            if len(entries) >= self._maximum:
                invalid_count += 1
                continue
            try:
                member_status = os.lstat(member_path)
                if not stat.S_ISREG(member_status.st_mode):
                    raise RecipeLibraryError(
                        "RECIPE_LIBRARY_ENTRY_INVALID",
                        "A saved setup is not a regular file.",
                    )
                next_aggregate = aggregate_bytes + member_status.st_size
                if next_aggregate > MAX_LOCAL_RECIPE_AGGREGATE_BYTES:
                    raise RecipeLibraryError(
                        "RECIPE_LIBRARY_BOUNDS_EXCEEDED",
                        "Saved setup files exceed the local aggregate size limit.",
                    )
                aggregate_bytes = next_aggregate
                recipe = load_recipe(member_path)
                if recipe.display_label is None:
                    raise RecipeLibraryError(
                        "RECIPE_NAME_INVALID", "A saved setup has no local display name."
                    )
                display_name = normalize_recipe_name(recipe.display_label)
            except (OSError, OrdifileError, RecipeLibraryError):
                invalid_count += 1
                continue
            name_key = display_name.casefold()
            if name_key in names:
                invalid_count += 1
                continue
            names.add(name_key)
            revision = sha256(recipe.to_json().encode("utf-8")).hexdigest()
            entries.append(StoredRecipe(recipe_id, display_name, recipe, revision))
        entries.sort(key=lambda item: (item.display_name.casefold(), item.recipe_id))
        return RecipeLibrarySnapshot(tuple(entries), invalid_count)

    def _name_conflict(self, name: str, *, excluding_id: str | None = None) -> StoredRecipe | None:
        comparison = normalize_recipe_name(name).casefold()
        for entry in self.snapshot().entries:
            if entry.recipe_id != excluding_id and entry.display_name.casefold() == comparison:
                return entry
        return None

    def semantic_match(self, recipe: ConversionRecipe) -> StoredRecipe | None:
        """Return an existing semantic match without considering local display labels."""
        for entry in self.snapshot().entries:
            if entry.recipe.semantic_sha256 == recipe.semantic_sha256:
                return entry
        return None

    def create(self, recipe: ConversionRecipe, display_name: str) -> StoredRecipe:
        """Add one named Recipe using a new opaque identifier."""
        if type(recipe) is not ConversionRecipe:
            raise TypeError("recipe must be a ConversionRecipe")
        name = normalize_recipe_name(display_name)
        with self._mutation_lock():
            return self._create_locked(recipe, name)

    def _create_locked(self, recipe: ConversionRecipe, name: str) -> StoredRecipe:
        """Create one entry while the library mutation lock is held."""
        snapshot = self.snapshot()
        if self._name_conflict(name) is not None:
            raise RecipeLibraryError("RECIPE_NAME_EXISTS", "A saved setup already uses this name.")
        if len(snapshot.entries) >= self._maximum:
            raise RecipeLibraryError(
                "RECIPE_LIBRARY_FULL",
                f"The local saved setup library is limited to {self._maximum} setups.",
            )
        self._ensure_directory()
        stored_recipe = replace(recipe, display_label=name)
        for _attempt in range(8):
            recipe_id = uuid4().hex
            destination = self._path(recipe_id)
            try:
                save_recipe(stored_recipe, destination, overwrite=False)
            except OrdifileError as error:
                if destination.exists():
                    continue
                raise RecipeLibraryError(
                    "RECIPE_LIBRARY_WRITE_FAILED", "The saved setup could not be written."
                ) from error
            revision = sha256(stored_recipe.to_json().encode("utf-8")).hexdigest()
            return StoredRecipe(recipe_id, name, stored_recipe, revision)
        raise RecipeLibraryError(
            "RECIPE_LIBRARY_WRITE_FAILED", "A unique saved setup identifier was unavailable."
        )

    def update(
        self,
        recipe_id: str,
        recipe: ConversionRecipe,
        *,
        expected_revision_sha256: str | None = None,
    ) -> StoredRecipe:
        """Explicitly replace settings while preserving identifier and display name."""
        with self._mutation_lock():
            current = self.get(recipe_id)
            if (
                expected_revision_sha256 is not None
                and current.revision_sha256 != expected_revision_sha256
            ):
                raise RecipeLibraryError(
                    "RECIPE_LIBRARY_CHANGED",
                    "The saved setup changed in another process. Refresh the setup list.",
                )
            stored_recipe = replace(recipe, display_label=current.display_name)
            try:
                save_recipe(stored_recipe, self._path(recipe_id), overwrite=True)
            except OrdifileError as error:
                raise RecipeLibraryError(
                    "RECIPE_LIBRARY_WRITE_FAILED", "The saved setup could not be updated."
                ) from error
            revision = sha256(stored_recipe.to_json().encode("utf-8")).hexdigest()
            return StoredRecipe(recipe_id, current.display_name, stored_recipe, revision)

    def rename(self, recipe_id: str, display_name: str) -> StoredRecipe:
        """Change only local display metadata, preserving conversion semantics."""
        name = normalize_recipe_name(display_name)
        with self._mutation_lock():
            current = self.get(recipe_id)
            if self._name_conflict(name, excluding_id=recipe_id) is not None:
                raise RecipeLibraryError(
                    "RECIPE_NAME_EXISTS", "A saved setup already uses this name."
                )
            renamed = replace(current.recipe, display_label=name)
            try:
                save_recipe(renamed, self._path(recipe_id), overwrite=True)
            except OrdifileError as error:
                raise RecipeLibraryError(
                    "RECIPE_LIBRARY_WRITE_FAILED", "The saved setup could not be renamed."
                ) from error
            revision = sha256(renamed.to_json().encode("utf-8")).hexdigest()
            return StoredRecipe(recipe_id, name, renamed, revision)

    def duplicate(self, recipe_id: str, display_name: str) -> StoredRecipe:
        """Copy semantic settings under a new opaque identifier and explicit name."""
        name = normalize_recipe_name(display_name)
        with self._mutation_lock():
            return self._create_locked(self.get(recipe_id).recipe, name)

    def get(self, recipe_id: str) -> StoredRecipe:
        """Return one current validated member."""
        for entry in self.snapshot().entries:
            if entry.recipe_id == recipe_id:
                return entry
        raise RecipeLibraryError(
            "RECIPE_LIBRARY_ENTRY_MISSING", "The selected saved setup is unavailable."
        )

    def delete(self, recipe_id: str, *, expected_revision_sha256: str | None = None) -> None:
        """Delete exactly one validated regular library member after UI confirmation."""
        with self._mutation_lock():
            current = self.get(recipe_id)
            if (
                expected_revision_sha256 is not None
                and current.revision_sha256 != expected_revision_sha256
            ):
                raise RecipeLibraryError(
                    "RECIPE_LIBRARY_CHANGED",
                    "The saved setup changed in another process. Refresh the setup list.",
                )
            destination = self._path(recipe_id)
            try:
                status = os.lstat(destination)
                if not stat.S_ISREG(status.st_mode):
                    raise RecipeLibraryError(
                        "RECIPE_LIBRARY_ENTRY_INVALID",
                        "The selected saved setup is not a regular file.",
                    )
                destination.unlink()
            except RecipeLibraryError:
                raise
            except OSError as error:
                raise RecipeLibraryError(
                    "RECIPE_LIBRARY_WRITE_FAILED", "The saved setup could not be deleted."
                ) from error
