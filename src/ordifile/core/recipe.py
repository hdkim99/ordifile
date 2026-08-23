# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Strict local conversion recipes for repeated laboratory workflows."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ordifile.adapters.registry import (
    MAX_EXTENSION_FILTER_MANIFEST_CHARACTERS,
    MAX_EXTENSION_FILTERS,
    normalize_extension_token,
)
from ordifile.core.errors import OrdifileError
from ordifile.core.file_publish import rename_no_replace
from ordifile.core.models import SortMode
from ordifile.core.peak_mapping import (
    MAX_PEAK_MAPPING_SET_BYTES,
    PeakTableFormat,
    PeakTableMapping,
    PeakTableMappingSet,
)

CONVERSION_RECIPE_SCHEMA_VERSION = 1
MAX_CONVERSION_RECIPE_BYTES = 8 * 1024 * 1024
MAX_CONVERSION_RECIPE_LABEL_CHARACTERS = 128
MAX_CONVERSION_RECIPE_LABEL_BYTES = 512
MAX_CONVERSION_RECIPE_TEXT_CHARACTERS = 512


def _recipe_error(message: str, *, code: str = "CONVERSION_RECIPE_INVALID") -> OrdifileError:
    return OrdifileError(code, message)


def _strict_text(
    name: str,
    value: object,
    *,
    optional: bool,
    maximum: int = MAX_CONVERSION_RECIPE_TEXT_CHARACTERS,
) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str or not value or len(value) > maximum:
        suffix = " or null" if optional else ""
        raise _recipe_error(f"{name} must be nonempty bounded text{suffix}.")
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for character in value
    ):
        raise _recipe_error(f"{name} cannot contain control or directional format characters.")
    return value


def _normalize_recipe_extensions(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise _recipe_error("options.extensions must be an array of normalized text values.")
    items = cast(list[object], value)
    if len(items) > MAX_EXTENSION_FILTERS:
        raise _recipe_error(f"options.extensions supports at most {MAX_EXTENSION_FILTERS} filters.")
    normalized: list[str] = []
    for item in items:
        if type(item) is not str:
            raise _recipe_error("options.extensions must contain only exact text values.")
        token = normalize_extension_token(item)
        if token is None or token != item:
            raise _recipe_error(
                "options.extensions must contain canonical lowercase ASCII extension tokens."
            )
        normalized.append(token)
    if len(normalized) != len(set(normalized)):
        raise _recipe_error("options.extensions cannot contain duplicate filters.")
    if len("; ".join(normalized)) > MAX_EXTENSION_FILTER_MANIFEST_CHARACTERS:
        raise _recipe_error("options.extensions exceeds the bounded Manifest representation.")
    return tuple(normalized)


def _mapping_public_payload(mapping: PeakTableMapping) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": mapping.schema_version,
        "source_format": mapping.source_format.value,
        "column_count": len(mapping.declared_headers),
        "roles": list(mapping.structural_roles),
        "unit_presence": {
            "retention_time": True,
            "area": mapping.area_unit is not None,
            "height": mapping.height_unit is not None,
            "secondary_retention_time": mapping.secondary_retention_time_unit is not None,
        },
    }
    if not mapping.import_settings.is_default:
        payload["import_settings"] = mapping.import_settings.to_dict()
    return payload


def _mapping_set_semantic_payload(mapping_set: PeakTableMappingSet) -> dict[str, object]:
    """Return exact local behavior while excluding non-behavior display labels."""
    return {
        "schema_version": mapping_set.schema_version,
        "set_id": mapping_set.set_id,
        "profiles": [
            {
                "schema_version": profile.schema_version,
                "profile_id": profile.profile_id,
                "worksheet_title": profile.worksheet_title,
                "mapping": profile.mapping.to_dict(),
            }
            for profile in mapping_set.profiles
        ],
    }


@dataclass(frozen=True, slots=True)
class ConversionRecipe:
    """Portable data-only conversion behavior without runtime inputs or output paths.

    Embedded mappings can contain local headers, labels, worksheet titles, and user
    declarations. Recipe JSON is therefore local privacy-bearing configuration.
    """

    recursive: bool = False
    extensions: tuple[str, ...] = ()
    sort: SortMode = SortMode.AUTO
    include_signals: bool = False
    adapter: str | None = None
    sheet: str | None = field(default=None, repr=False)
    include_hidden_sheets: bool = False
    peak_table_mapping: PeakTableMapping | None = field(default=None, repr=False)
    peak_table_mapping_set: PeakTableMappingSet | None = field(default=None, repr=False)
    on_error: str = "continue"
    sidecar_mode: str = "error"
    display_label: str | None = field(default=None, repr=False, compare=False)
    schema_version: int = CONVERSION_RECIPE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise _recipe_error("schema_version must be exactly 1.")
        for name, value in (
            ("recursive", self.recursive),
            ("include_signals", self.include_signals),
            ("include_hidden_sheets", self.include_hidden_sheets),
        ):
            if type(value) is not bool:
                raise _recipe_error(f"{name} must be an exact boolean value.")
        if type(self.extensions) is not tuple or any(
            type(item) is not str for item in self.extensions
        ):
            raise _recipe_error("extensions must be a tuple of canonical text values.")
        normalized = _normalize_recipe_extensions(list(self.extensions))
        if normalized != self.extensions:
            raise _recipe_error("extensions must already be canonical and deterministic.")
        if type(self.sort) is not SortMode:
            raise _recipe_error("sort must be a SortMode value.")
        _strict_text("adapter", self.adapter, optional=True)
        _strict_text("sheet", self.sheet, optional=True)
        if self.display_label is not None:
            label = _strict_text(
                "display_label",
                self.display_label,
                optional=False,
                maximum=MAX_CONVERSION_RECIPE_LABEL_CHARACTERS,
            )
            assert label is not None
            if len(label.encode("utf-8", errors="strict")) > MAX_CONVERSION_RECIPE_LABEL_BYTES:
                raise _recipe_error("display_label exceeds its UTF-8 byte limit.")
        if (
            self.peak_table_mapping is not None
            and type(self.peak_table_mapping) is not PeakTableMapping
        ):
            raise _recipe_error("peak_table_mapping must be a PeakTableMapping or null.")
        if (
            self.peak_table_mapping_set is not None
            and type(self.peak_table_mapping_set) is not PeakTableMappingSet
        ):
            raise _recipe_error("peak_table_mapping_set must be a PeakTableMappingSet or null.")
        if self.peak_table_mapping is not None and self.peak_table_mapping_set is not None:
            raise _recipe_error("A recipe cannot contain both a single mapping and a mapping set.")
        mapping_requested = (
            self.peak_table_mapping is not None or self.peak_table_mapping_set is not None
        )
        if self.adapter is not None and mapping_requested:
            raise _recipe_error("An adapter fallback cannot be combined with embedded mappings.")
        if self.peak_table_mapping_set is not None and (
            self.sheet is not None or self.include_hidden_sheets
        ):
            raise _recipe_error(
                "Mapping profiles own worksheet selection and cannot use recipe sheet options."
            )
        if (
            self.peak_table_mapping is not None
            and self.peak_table_mapping.source_format is not PeakTableFormat.XLSX
            and self.sheet is not None
        ):
            raise _recipe_error("sheet is available only for XLSX peak-table mappings.")
        if type(self.on_error) is not str or self.on_error not in {"continue", "stop"}:
            raise _recipe_error("on_error must be 'continue' or 'stop'.")
        if type(self.sidecar_mode) is not str or self.sidecar_mode not in {"error", "csv"}:
            raise _recipe_error("sidecar_mode must be 'error' or 'csv'.")
        if len(self.to_json().encode("utf-8")) > MAX_CONVERSION_RECIPE_BYTES:
            raise _recipe_error("The normalized recipe exceeds its byte limit.")

    def __repr__(self) -> str:
        mapping_mode = (
            "MAPPING_SET"
            if self.peak_table_mapping_set is not None
            else "SINGLE_MAPPING"
            if self.peak_table_mapping is not None
            else "NONE"
        )
        return (
            f"ConversionRecipe(schema_version={self.schema_version}, mapping_mode={mapping_mode!r})"
        )

    @property
    def semantic_sha256(self) -> str:
        """Return an exact local equality digest; never expose it as public provenance."""
        mapping: object
        if self.peak_table_mapping is not None:
            mapping = {"single": self.peak_table_mapping.to_dict(), "set": None}
        elif self.peak_table_mapping_set is not None:
            mapping = {
                "single": None,
                "set": _mapping_set_semantic_payload(self.peak_table_mapping_set),
            }
        else:
            mapping = {"single": None, "set": None}
        payload = {
            "domain": "ordifile-conversion-recipe-semantic-v1",
            "schema_version": self.schema_version,
            "options": self._options_dict(),
            "mapping": mapping,
        }
        canonical = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @property
    def public_fingerprint_sha256(self) -> str:
        """Return a privacy-safe configuration summary, not exact mapping identity."""
        mapping_payload: object
        if self.peak_table_mapping is not None:
            mapping_payload = {
                "mode": "SINGLE_MAPPING",
                "mapping": _mapping_public_payload(self.peak_table_mapping),
            }
        elif self.peak_table_mapping_set is not None:
            mapping_payload = {
                "mode": "MAPPING_SET",
                "schema_version": self.peak_table_mapping_set.schema_version,
                "profile_count": len(self.peak_table_mapping_set.profiles),
                "structural_fingerprint": (
                    self.peak_table_mapping_set.structural_fingerprint_sha256
                ),
            }
        else:
            mapping_payload = {"mode": "NONE"}
        payload = {
            "domain": "ordifile-conversion-recipe-public-v1",
            "schema_version": self.schema_version,
            "options": {
                "recursive": self.recursive,
                "extensions": list(self.extensions),
                "sort": self.sort.value,
                "include_signals": self.include_signals,
                "adapter": self.adapter,
                "sheet_selected": self.sheet is not None,
                "include_hidden_sheets": self.include_hidden_sheets,
                "on_error": self.on_error,
                "sidecar_mode": self.sidecar_mode,
            },
            "mapping": mapping_payload,
        }
        canonical = json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("ascii")
        return hashlib.sha256(canonical).hexdigest()

    def _options_dict(self) -> dict[str, object]:
        return {
            "recursive": self.recursive,
            "extensions": list(self.extensions),
            "sort": self.sort.value,
            "include_signals": self.include_signals,
            "adapter": self.adapter,
            "sheet": self.sheet,
            "include_hidden_sheets": self.include_hidden_sheets,
            "on_error": self.on_error,
            "sidecar_mode": self.sidecar_mode,
        }

    def to_dict(self) -> dict[str, object]:
        """Return the explicit local JSON representation."""
        return {
            "schema_version": self.schema_version,
            "display_label": self.display_label,
            "options": self._options_dict(),
            "mapping": {
                "single": (
                    self.peak_table_mapping.to_dict()
                    if self.peak_table_mapping is not None
                    else None
                ),
                "set": (
                    self.peak_table_mapping_set.to_dict()
                    if self.peak_table_mapping_set is not None
                    else None
                ),
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, value: object) -> ConversionRecipe:
        if type(value) is not dict:
            raise _recipe_error("The recipe root must be an object.")
        payload = cast(dict[object, object], value)
        if set(payload) != {"schema_version", "display_label", "options", "mapping"}:
            raise _recipe_error("The recipe has missing or unsupported root fields.")
        if type(payload["schema_version"]) is not int:
            raise _recipe_error("schema_version must be an integer.")
        display_label = payload["display_label"]
        if display_label is not None and type(display_label) is not str:
            raise _recipe_error("display_label must be text or null.")
        raw_options = payload["options"]
        if type(raw_options) is not dict:
            raise _recipe_error("options must be an object.")
        options = cast(dict[object, object], raw_options)
        expected_options = {
            "recursive",
            "extensions",
            "sort",
            "include_signals",
            "adapter",
            "sheet",
            "include_hidden_sheets",
            "on_error",
            "sidecar_mode",
        }
        if set(options) != expected_options:
            raise _recipe_error("options has missing or unsupported fields.")
        for name in ("recursive", "include_signals", "include_hidden_sheets"):
            if type(options[name]) is not bool:
                raise _recipe_error(f"options.{name} must be an exact boolean value.")
        if type(options["sort"]) is not str:
            raise _recipe_error("options.sort must be text.")
        try:
            sort = SortMode(options["sort"])
        except ValueError as error:
            raise _recipe_error("options.sort is not supported.") from error
        for name in ("adapter", "sheet"):
            if options[name] is not None and type(options[name]) is not str:
                raise _recipe_error(f"options.{name} must be text or null.")
        for name in ("on_error", "sidecar_mode"):
            if type(options[name]) is not str:
                raise _recipe_error(f"options.{name} must be text.")
        raw_mapping = payload["mapping"]
        if type(raw_mapping) is not dict:
            raise _recipe_error("mapping must be an object.")
        mapping = cast(dict[object, object], raw_mapping)
        if set(mapping) != {"single", "set"}:
            raise _recipe_error("mapping must contain exactly single and set fields.")
        single = mapping["single"]
        mapping_set = mapping["set"]
        return cls(
            recursive=cast(bool, options["recursive"]),
            extensions=_normalize_recipe_extensions(options["extensions"]),
            sort=sort,
            include_signals=cast(bool, options["include_signals"]),
            adapter=cast(str | None, options["adapter"]),
            sheet=cast(str | None, options["sheet"]),
            include_hidden_sheets=cast(bool, options["include_hidden_sheets"]),
            peak_table_mapping=(PeakTableMapping.from_dict(single) if single is not None else None),
            peak_table_mapping_set=(
                PeakTableMappingSet.from_dict(mapping_set) if mapping_set is not None else None
            ),
            on_error=cast(str, options["on_error"]),
            sidecar_mode=cast(str, options["sidecar_mode"]),
            display_label=display_label,
            schema_version=payload["schema_version"],
        )

    @classmethod
    def from_json(cls, text: str) -> ConversionRecipe:
        if type(text) is not str:
            raise _recipe_error("Recipe JSON must be text.")
        try:
            encoded = text.encode("utf-8", errors="strict")
        except UnicodeError as error:
            raise _recipe_error("Recipe JSON must be valid Unicode text.") from error
        if len(encoded) > MAX_CONVERSION_RECIPE_BYTES:
            raise _recipe_error("Recipe JSON exceeds its byte limit.")

        def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in pairs:
                if key in result:
                    raise _recipe_error("Recipe JSON contains a duplicate object key.")
                result[key] = item
            return result

        def invalid_constant(_value: str) -> None:
            raise _recipe_error("Recipe JSON contains a non-standard numeric constant.")

        try:
            decoded = json.loads(
                text,
                object_pairs_hook=object_pairs,
                parse_constant=invalid_constant,
            )
        except OrdifileError:
            raise
        except (UnicodeError, ValueError, RecursionError) as error:
            raise _recipe_error("Recipe JSON is malformed or exceeds nesting limits.") from error
        return cls.from_dict(decoded)


def load_conversion_recipe(path: str | os.PathLike[str]) -> ConversionRecipe:
    """Load one bounded regular-file recipe without exposing its local path."""
    candidate = Path(path)
    if candidate.is_symlink():
        raise _recipe_error("Recipe files must not be symbolic links.")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(candidate, flags)
    except OSError as error:
        raise _recipe_error("Recipe file could not be read.") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise _recipe_error("Recipe input must be a regular file.")
        if before.st_size > MAX_CONVERSION_RECIPE_BYTES:
            raise _recipe_error("Recipe file exceeds its byte limit.")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(MAX_CONVERSION_RECIPE_BYTES + 1)
        after = os.fstat(descriptor)
        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if len(data) > MAX_CONVERSION_RECIPE_BYTES or before_identity != after_identity:
            raise _recipe_error("Recipe file changed while it was being read.")
    except OSError as error:
        raise _recipe_error("Recipe file could not be read safely.") from error
    finally:
        os.close(descriptor)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise _recipe_error("Recipe file must be valid UTF-8 JSON.") from error
    return ConversionRecipe.from_json(text)


def save_conversion_recipe(
    recipe: ConversionRecipe,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> None:
    """Save a recipe atomically without persisting runtime paths or scientific rows."""
    if type(recipe) is not ConversionRecipe:
        raise _recipe_error("recipe must be a ConversionRecipe.")
    if type(overwrite) is not bool:
        raise _recipe_error("overwrite must be an exact boolean value.")
    destination = Path(path)
    if destination.suffix.casefold() != ".json":
        raise _recipe_error("Recipe files must use the .json extension.")
    if not destination.parent.is_dir():
        raise _recipe_error("The recipe destination directory does not exist.")

    def destination_status() -> os.stat_result | None:
        try:
            return os.lstat(destination)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise _recipe_error("The recipe destination could not be inspected.") from error

    current = destination_status()
    if current is not None:
        if not stat.S_ISREG(current.st_mode):
            raise _recipe_error("The recipe destination must be a regular file.")
        if not overwrite:
            raise _recipe_error("The recipe file already exists.", code="CONVERSION_RECIPE_EXISTS")
    encoded = recipe.to_json().encode("utf-8")
    if len(encoded) > MAX_CONVERSION_RECIPE_BYTES:
        raise _recipe_error("The normalized recipe exceeds its byte limit.")
    descriptor = -1
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".ordifile-conversion-recipe-",
            suffix=".tmp",
            dir=destination.parent,
        )
        created = os.fstat(descriptor)
        if not stat.S_ISREG(created.st_mode):
            raise _recipe_error("The owned recipe temporary file is not regular.")
        temporary_identity = (created.st_dev, created.st_ino)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        temporary = Path(temporary_name)
        if overwrite:
            current = destination_status()
            if current is not None and not stat.S_ISREG(current.st_mode):
                raise _recipe_error("The recipe destination must be a regular file.")
            os.replace(temporary, destination)
            temporary_name = None
        else:
            try:
                rename_no_replace(temporary, destination)
            except FileExistsError as error:
                raise _recipe_error(
                    "The recipe file already exists.", code="CONVERSION_RECIPE_EXISTS"
                ) from error
            published = os.lstat(destination)
            if (
                not stat.S_ISREG(published.st_mode)
                or (published.st_dev, published.st_ino) != temporary_identity
            ):
                raise _recipe_error("Recipe destination changed during publication.")
            temporary_name = None
    except (OrdifileError, KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except OSError as error:
        raise _recipe_error("Recipe file could not be written safely.") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None and temporary_identity is not None:
            try:
                remaining = os.lstat(temporary_name)
                if (
                    stat.S_ISREG(remaining.st_mode)
                    and (remaining.st_dev, remaining.st_ino) == temporary_identity
                ):
                    for _attempt in range(2):
                        try:
                            os.unlink(temporary_name)
                            break
                        except OSError:
                            pass
            except OSError:
                pass


assert MAX_CONVERSION_RECIPE_BYTES > MAX_PEAK_MAPPING_SET_BYTES
