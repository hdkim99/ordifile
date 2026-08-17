# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Collision-safe registry for built-in and trusted external adapters."""

from __future__ import annotations

import inspect
import re
from collections.abc import Iterable
from importlib import metadata
from typing import Any, cast

from ordifile.adapters.agilent_chemstation_ch_v181 import AgilentChemStationChV181Adapter
from ordifile.adapters.agilent_chemstation_result_xml import (
    AgilentChemStationResultXmlAdapter,
)
from ordifile.adapters.base import (
    ADAPTER_API_VERSION,
    AdapterDescriptor,
    FormatAdapter,
    SourceIdentityPolicy,
    SupportStatus,
)
from ordifile.adapters.generic_csv import GenericCsvAdapter
from ordifile.adapters.generic_tsv import GenericTsvAdapter
from ordifile.adapters.generic_txt import GenericSemicolonAdapter
from ordifile.adapters.generic_xlsx import GenericXlsxAdapter
from ordifile.adapters.shimadzu_gcmssolution_qgd import ShimadzuGcmssolutionQgdAdapter
from ordifile.adapters.shimadzu_gcsolution_gcd import ShimadzuGcsolutionGcdAdapter
from ordifile.adapters.shimadzu_labsolutions_result_ascii import (
    ShimadzuLabsolutionsResultAsciiAdapter,
)
from ordifile.adapters.youngin_yl_clarity_prm_raw import YoungInYlClarityPrmRawAdapter
from ordifile.core.errors import OrdifileError
from ordifile.core.models import SeriesKind
from ordifile.core.workbook_text import workbook_audit_display, workbook_text_is_exact

ENTRY_POINT_GROUP = "ordifile.adapters"
_ADAPTER_ID = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_ADAPTER_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}\Z")
_ADAPTER_EXTENSION = re.compile(r"\.[0-9A-Za-z][0-9A-Za-z._+-]{0,31}\Z")
MAX_EXTENSION_FILTERS = 32
MAX_EXTENSION_FILTER_MANIFEST_CHARACTERS = 1_024


def normalize_extension_token(value: object) -> str | None:
    """Return one stable lowercase dotted extension, or None when it is unsafe."""
    if type(value) is not str:
        return None
    candidate = value if value.startswith(".") else f".{value}"
    candidate = candidate.casefold()
    return candidate if _ADAPTER_EXTENSION.fullmatch(candidate) is not None else None


def _safe_entry_point_name(value: str) -> str:
    """Return a bounded printable plugin label without leaking exception details."""
    display = workbook_audit_display(value)
    return display[:100] or "unnamed"


class AdapterRegistry:
    """An insertion-ordered adapter collection with stable public IDs."""

    def __init__(self) -> None:
        self._adapters: dict[str, FormatAdapter] = {}
        self._load_errors: list[str] = []

    def register(self, adapter: FormatAdapter) -> None:
        """Register a compatible adapter, rejecting IDs that are already owned."""
        adapter_id = getattr(adapter, "adapter_id", None)
        if type(adapter_id) is not str or _ADAPTER_ID.fullmatch(adapter_id) is None:
            raise OrdifileError(
                "ADAPTER_INVALID",
                "Adapter ID must use 1-64 lowercase ASCII letters, digits, and underscores.",
            )
        api_version = getattr(adapter, "api_version", None)
        if type(api_version) is not str or api_version != ADAPTER_API_VERSION:
            raise OrdifileError(
                "ADAPTER_API_INCOMPATIBLE",
                f"Adapter {adapter_id!r} does not implement API version {ADAPTER_API_VERSION}.",
            )
        adapter_version = getattr(adapter, "adapter_version", None)
        if type(adapter_version) is not str or _ADAPTER_VERSION.fullmatch(adapter_version) is None:
            raise OrdifileError(
                "ADAPTER_VERSION_INVALID",
                "Adapter version must be a bounded ASCII version identifier.",
            )
        descriptor = getattr(adapter, "descriptor", None)
        if (
            type(descriptor) is not AdapterDescriptor
            or type(descriptor.adapter_id) is not str
            or descriptor.adapter_id != adapter_id
            or type(descriptor.adapter_version) is not str
            or descriptor.adapter_version != adapter_version
            or type(descriptor.display_name) is not str
            or not descriptor.display_name.strip()
            or len(descriptor.display_name) > 100
            or not workbook_text_is_exact(descriptor.display_name)
            or type(descriptor.extensions) is not tuple
            or len(descriptor.extensions) > MAX_EXTENSION_FILTERS
            or any(
                normalize_extension_token(extension) is None for extension in descriptor.extensions
            )
            or len({extension.casefold() for extension in descriptor.extensions})
            != len(descriptor.extensions)
            or any(
                type(value) is not bool
                for value in (
                    descriptor.metadata,
                    descriptor.peaks,
                    descriptor.signals,
                    descriptor.tested_fixture,
                )
            )
            or type(descriptor.support_status) is not SupportStatus
            or type(descriptor.series_kinds) is not tuple
            or descriptor.signals
            and not descriptor.series_kinds
            or any(type(kind) is not SeriesKind for kind in descriptor.series_kinds)
            or len(set(descriptor.series_kinds)) != len(descriptor.series_kinds)
            or type(descriptor.source_identity_policy) is not SourceIdentityPolicy
        ):
            raise OrdifileError(
                "ADAPTER_DESCRIPTOR_INVALID",
                "Adapter descriptor fields have invalid types, bounds, or workbook text.",
            )
        if adapter_id in self._adapters:
            raise OrdifileError(
                "ADAPTER_ID_COLLISION", f"Adapter ID {adapter_id!r} is already registered."
            )
        self._adapters[adapter_id] = adapter

    def get(self, adapter_id: str) -> FormatAdapter:
        """Return a registered adapter or an actionable structured error."""
        try:
            return self._adapters[adapter_id]
        except KeyError as error:
            raise OrdifileError(
                "ADAPTER_NOT_FOUND", f"Adapter {adapter_id!r} is not registered."
            ) from error

    def adapters(self) -> tuple[FormatAdapter, ...]:
        """Return adapters in deterministic registration order."""
        return tuple(self._adapters.values())

    def descriptors(self) -> tuple[AdapterDescriptor, ...]:
        """Return public descriptors sorted by adapter ID."""
        return tuple(
            sorted(
                (adapter.descriptor for adapter in self._adapters.values()),
                key=lambda item: item.adapter_id,
            )
        )

    @property
    def load_errors(self) -> tuple[str, ...]:
        """Return external-plugin load failures without hiding them."""
        return tuple(self._load_errors)


def _entry_points() -> Iterable[metadata.EntryPoint]:
    points = metadata.entry_points()
    if hasattr(points, "select"):
        return points.select(group=ENTRY_POINT_GROUP)
    return ()  # pragma: no cover - Python 3.11+ always supports select


def load_external_adapters(
    registry: AdapterRegistry,
    *,
    entry_points: Iterable[metadata.EntryPoint] | None = None,
) -> None:
    """Load installed adapters as trusted code while isolating ordinary load failures."""
    points = _entry_points() if entry_points is None else entry_points
    for point in sorted(points, key=lambda item: item.name):
        try:
            loaded: Any = point.load()
            adapter = loaded() if inspect.isclass(loaded) else loaded
            registry.register(cast(FormatAdapter, adapter))
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception as error:  # plugin code can raise arbitrary ordinary exceptions
            registry._load_errors.append(
                f"{_safe_entry_point_name(point.name)}: {type(error).__name__}"
            )


def create_registry(*, include_external: bool = True) -> AdapterRegistry:
    """Create the built-in registry and optionally load installed entry points."""
    registry = AdapterRegistry()
    registry.register(AgilentChemStationChV181Adapter())
    registry.register(AgilentChemStationResultXmlAdapter())
    registry.register(GenericCsvAdapter())
    registry.register(GenericTsvAdapter())
    registry.register(GenericSemicolonAdapter())
    registry.register(GenericXlsxAdapter())
    registry.register(ShimadzuGcsolutionGcdAdapter())
    registry.register(ShimadzuGcmssolutionQgdAdapter())
    registry.register(ShimadzuLabsolutionsResultAsciiAdapter())
    registry.register(YoungInYlClarityPrmRawAdapter())
    if include_external:
        load_external_adapters(registry)
    return registry
