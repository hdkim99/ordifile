# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Optional local acquisition of official vendor Result exports."""

from ordifile.acquisition.base import (
    ACQUISITION_PROVIDER_API_VERSION,
    AcquiredResultArtifact,
    AcquisitionAvailability,
    AcquisitionEnvironment,
    AcquisitionRequest,
    AcquisitionSource,
    ResultAcquisitionProvider,
    ResultAcquisitionProviderDescriptor,
)
from ordifile.acquisition.coordinator import AcquisitionOutcome, acquire_official_result
from ordifile.acquisition.registry import ResultAcquisitionRegistry

__all__ = [
    "ACQUISITION_PROVIDER_API_VERSION",
    "AcquiredResultArtifact",
    "AcquisitionAvailability",
    "AcquisitionEnvironment",
    "AcquisitionOutcome",
    "AcquisitionRequest",
    "AcquisitionSource",
    "ResultAcquisitionProvider",
    "ResultAcquisitionProviderDescriptor",
    "ResultAcquisitionRegistry",
    "acquire_official_result",
]
