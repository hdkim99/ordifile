# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Built-in-only registry for privileged local Result acquisition providers."""

from __future__ import annotations

import re

from ordifile.acquisition.base import (
    ACQUISITION_PROVIDER_API_VERSION,
    ResultAcquisitionProvider,
    ResultAcquisitionProviderDescriptor,
)
from ordifile.core.errors import OrdifileError
from ordifile.core.workbook_text import workbook_text_is_exact

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}\Z")
MAX_PROVIDER_NATIVE_ADAPTERS = 16


class ResultAcquisitionRegistry:
    """Deterministic provider collection with one owner per native adapter."""

    def __init__(self) -> None:
        self._providers: dict[str, ResultAcquisitionProvider] = {}
        self._owners: dict[str, str] = {}

    def register(self, provider: ResultAcquisitionProvider) -> None:
        """Register one built-in provider and reject ambiguous source ownership."""
        provider_id = getattr(provider, "provider_id", None)
        provider_version = getattr(provider, "provider_version", None)
        api_version = getattr(provider, "api_version", None)
        descriptor = getattr(provider, "descriptor", None)
        if type(provider_id) is not str or _IDENTIFIER.fullmatch(provider_id) is None:
            raise OrdifileError("ACQUISITION_PROVIDER_INVALID", "Provider ID is invalid.")
        if type(provider_version) is not str or _VERSION.fullmatch(provider_version) is None:
            raise OrdifileError("ACQUISITION_PROVIDER_INVALID", "Provider version is invalid.")
        if api_version != ACQUISITION_PROVIDER_API_VERSION:
            raise OrdifileError(
                "ACQUISITION_PROVIDER_API_INCOMPATIBLE",
                "Result acquisition provider API version is incompatible.",
            )
        if (
            type(descriptor) is not ResultAcquisitionProviderDescriptor
            or descriptor.provider_id != provider_id
            or descriptor.provider_version != provider_version
            or type(descriptor.display_name) is not str
            or not descriptor.display_name.strip()
            or len(descriptor.display_name) > 100
            or not workbook_text_is_exact(descriptor.display_name)
            or type(descriptor.native_adapter_ids) is not tuple
            or not 1 <= len(descriptor.native_adapter_ids) <= MAX_PROVIDER_NATIVE_ADAPTERS
            or len(set(descriptor.native_adapter_ids)) != len(descriptor.native_adapter_ids)
            or any(
                type(adapter_id) is not str or _IDENTIFIER.fullmatch(adapter_id) is None
                for adapter_id in descriptor.native_adapter_ids
            )
            or type(descriptor.result_adapter_id) is not str
            or _IDENTIFIER.fullmatch(descriptor.result_adapter_id) is None
        ):
            raise OrdifileError(
                "ACQUISITION_PROVIDER_DESCRIPTOR_INVALID",
                "Provider descriptor fields are invalid.",
            )
        if provider_id in self._providers:
            raise OrdifileError(
                "ACQUISITION_PROVIDER_ID_COLLISION",
                "Result acquisition provider ID is already registered.",
            )
        collisions = tuple(
            adapter_id for adapter_id in descriptor.native_adapter_ids if adapter_id in self._owners
        )
        if collisions:
            raise OrdifileError(
                "ACQUISITION_PROVIDER_OWNERSHIP_COLLISION",
                "More than one provider claims the same native adapter.",
            )
        self._providers[provider_id] = provider
        self._owners.update(
            (adapter_id, provider_id) for adapter_id in descriptor.native_adapter_ids
        )

    def for_adapter(self, adapter_id: str) -> ResultAcquisitionProvider | None:
        """Return the sole provider for a native adapter, if registered."""
        provider_id = self._owners.get(adapter_id)
        return None if provider_id is None else self._providers[provider_id]

    def providers(self) -> tuple[ResultAcquisitionProvider, ...]:
        """Return providers in deterministic registration order."""
        return tuple(self._providers.values())

    def signature(self) -> tuple[tuple[str, str, tuple[str, ...], str], ...]:
        """Return a stable configuration identity for future plan revalidation."""
        return tuple(
            (
                provider.provider_id,
                provider.provider_version,
                provider.descriptor.native_adapter_ids,
                provider.descriptor.result_adapter_id,
            )
            for provider in self._providers.values()
        )
