# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Typed boundary for optional official vendor Result acquisition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

ACQUISITION_PROVIDER_API_VERSION = "1"


class AcquisitionAvailability(StrEnum):
    """Read-only environment assessment for one provider."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ResultAcquisitionProviderDescriptor:
    """Bounded provider metadata and deterministic native-adapter ownership."""

    provider_id: str
    provider_version: str
    display_name: str
    native_adapter_ids: tuple[str, ...]
    result_adapter_id: str


@dataclass(frozen=True, slots=True)
class AcquisitionEnvironment:
    """Installed vendor environment without paths, credentials, or private settings."""

    availability: AcquisitionAvailability
    product: str | None = None
    product_version: str | None = None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class AcquisitionSource:
    """Native logical-source identity offered to provider selection."""

    path: Path
    public_reference: str
    sha256: str
    size: int
    adapter_id: str
    adapter_version: str


@dataclass(frozen=True, slots=True)
class AcquisitionRequest:
    """Core-staged source passed to a provider inside a private workspace."""

    source: AcquisitionSource
    staged_source: Path


@dataclass(frozen=True, slots=True)
class AcquiredResultArtifact:
    """Private Result artifact returned to the coordinator for exact parsing."""

    path: Path
    result_adapter_id: str
    sha256: str
    size: int


@runtime_checkable
class ResultAcquisitionProvider(Protocol):
    """Acquire an official Result export without interpreting scientific values."""

    api_version: ClassVar[str]
    provider_id: ClassVar[str]
    provider_version: ClassVar[str]
    descriptor: ClassVar[ResultAcquisitionProviderDescriptor]

    def inspect_environment(self) -> AcquisitionEnvironment:
        """Inspect only documented local installation state."""
        ...

    def acquire(self, request: AcquisitionRequest, workspace: Path) -> AcquiredResultArtifact:
        """Create one official Result artifact inside ``workspace``."""
        ...
