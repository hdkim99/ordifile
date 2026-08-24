# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""One authoritative input-routing decision shared by parsing and preflight."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ordifile.adapters._mapped_table import (
    GENERIC_PEAK_TABLE_ADAPTER_IDS,
    PeakMappingResolutionError,
    resolve_peak_table_mapping,
)
from ordifile.adapters.base import ADAPTER_API_VERSION, DetectionResult, ParseOptions
from ordifile.adapters.registry import AdapterRegistry
from ordifile.core.detection import DetectionOutcome, detect_adapter
from ordifile.core.errors import DetectionError, OrdifileError
from ordifile.core.peak_mapping import (
    PeakMappingDriftCategory,
    PeakMappingDriftDiagnostic,
    PeakTableFormat,
)


@dataclass(frozen=True, slots=True)
class InputRouteDecision:
    """A deterministic adapter/mapping selection without constructing canonical rows."""

    detection: DetectionOutcome
    parse_options: ParseOptions
    mapping_applied: bool = False
    mapping_route: str | None = None
    mapping_profile_id: str | None = None
    mapping_structure_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class InputRouteIdentity:
    """Private exact route identity asserted before planned parsing."""

    adapter_id: str
    adapter_version: str
    mapping_route: str | None
    mapping_profile_id: str | None
    mapping_structure_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class InputRouteExpectation:
    """Private reviewed success or fixed routing-failure identity."""

    identity: InputRouteIdentity | None = None
    error_code: str | None = None
    mapping_route: str | None = None


class InputRouteError(OrdifileError):
    """A structured routing failure carrying only bounded mapping diagnostics."""

    def __init__(
        self,
        error: OrdifileError,
        *,
        mapping_route: str | None = None,
        mapping_diagnostics: tuple[PeakMappingDriftDiagnostic, ...] = (),
    ) -> None:
        super().__init__(error.code, error.message, details=error.details)
        self.mapping_route = mapping_route
        self.mapping_diagnostics = mapping_diagnostics


def input_route_identity(decision: InputRouteDecision) -> InputRouteIdentity:
    """Return the exact behavior identity of one resolved route."""
    return InputRouteIdentity(
        decision.detection.adapter.adapter_id,
        decision.detection.adapter.adapter_version,
        decision.mapping_route,
        decision.mapping_profile_id,
        decision.mapping_structure_fingerprint,
    )


def registry_route_identity(registry: AdapterRegistry) -> tuple[tuple[str, str, str], ...]:
    """Return the ordered adapter inventory identity that can affect routing."""
    return tuple(
        (descriptor.adapter_id, descriptor.adapter_version, ADAPTER_API_VERSION)
        for descriptor in registry.descriptors()
    )


def mapped_adapter_id(path: Path, source_format: PeakTableFormat) -> str:
    """Select one existing audited generic reader without content inference."""
    suffix = path.suffix.casefold()
    contracts = {
        PeakTableFormat.CSV: ("generic_csv", frozenset((".csv",))),
        PeakTableFormat.TSV: ("generic_tsv", frozenset((".tsv", ".txt"))),
        PeakTableFormat.SEMICOLON: ("generic_semicolon", frozenset((".txt",))),
        PeakTableFormat.XLSX: ("generic_xlsx", frozenset((".xlsx",))),
    }
    adapter_id, extensions = contracts[source_format]
    if suffix not in extensions:
        raise DetectionError(
            "PEAK_MAPPING_FORMAT_MISMATCH",
            "The input extension does not match the mapping's audited source format.",
        )
    return adapter_id


def _require_routable_detection(detection: DetectionOutcome) -> DetectionOutcome:
    """Reject a matched owner that already proved its exact profile unusable."""
    selected = next(
        probe
        for adapter_id, probe in detection.probes
        if adapter_id == detection.adapter.adapter_id
    )
    if not selected.routable:
        raise DetectionError(
            selected.failure_code or "EXACT_PROFILE_UNSUPPORTED",
            "The matched format owner rejected this exact profile as unsupported or malformed.",
        )
    return detection


def resolve_input_route(
    path: Path,
    registry: AdapterRegistry,
    *,
    forced_adapter: str | None,
    parse_options: ParseOptions,
    preserve_exact_adapter_precedence: bool = False,
    redact_adapter_ids: frozenset[str] = frozenset(),
    redact_error_reasons: bool = False,
    require_routable: bool = False,
) -> InputRouteDecision:
    """Resolve exact ownership or an explicit mapping through one shared path."""
    mapping_requested = (
        parse_options.peak_table_mapping is not None
        or parse_options.peak_table_mapping_set is not None
    )
    if not mapping_requested:
        if forced_adapter is not None and preserve_exact_adapter_precedence:
            try:
                exact_owner = detect_adapter(
                    path,
                    registry,
                    redact_adapter_ids=redact_adapter_ids,
                    redact_error_reasons=redact_error_reasons,
                    excluded_adapter_ids=GENERIC_PEAK_TABLE_ADAPTER_IDS,
                )
            except DetectionError as error:
                if error.code != "FORMAT_NOT_DETECTED":
                    raise
            else:
                return InputRouteDecision(
                    _require_routable_detection(exact_owner) if require_routable else exact_owner,
                    parse_options,
                    mapping_route="EXACT_ADAPTER",
                )
        detection = detect_adapter(
            path,
            registry,
            forced_adapter=forced_adapter,
            redact_adapter_ids=redact_adapter_ids,
            redact_error_reasons=redact_error_reasons,
        )
        return InputRouteDecision(
            _require_routable_detection(detection) if require_routable else detection,
            parse_options,
        )

    try:
        exact = detect_adapter(
            path,
            registry,
            redact_adapter_ids=redact_adapter_ids,
            redact_error_reasons=True,
            excluded_adapter_ids=GENERIC_PEAK_TABLE_ADAPTER_IDS,
        )
    except DetectionError as error:
        if error.code != "FORMAT_NOT_DETECTED":
            raise
        exact = None
    if exact is not None:
        return InputRouteDecision(
            _require_routable_detection(exact) if require_routable else exact,
            replace(
                parse_options,
                peak_table_mapping=None,
                peak_table_mapping_set=None,
                peak_table_mapping_profile_id=None,
                peak_table_mapping_profile_fingerprint=None,
                peak_table_mapping_set_id=None,
            ),
            mapping_route="EXACT_ADAPTER",
        )

    if parse_options.peak_table_mapping is not None:
        adapter_id = mapped_adapter_id(path, parse_options.peak_table_mapping.source_format)
        adapter = registry.get(adapter_id)
        return InputRouteDecision(
            DetectionOutcome(
                adapter,
                (
                    (
                        adapter_id,
                        DetectionResult(
                            True,
                            1.0,
                            "Explicit user mapping selected an audited generic container.",
                        ),
                    ),
                ),
            ),
            parse_options,
            mapping_applied=True,
            mapping_route="USER_MAPPING",
        )

    assert parse_options.peak_table_mapping_set is not None
    try:
        resolved = resolve_peak_table_mapping(path, parse_options.peak_table_mapping_set)
    except PeakMappingResolutionError as error:
        diagnostics = error.diagnostics
        route = {
            "PEAK_MAPPING_PROFILE_NOT_MATCHED": (
                "SCHEMA_DRIFT_CANDIDATE"
                if any(
                    PeakMappingDriftCategory.INCOMPATIBLE_STRUCTURE not in diagnostic.categories
                    for diagnostic in diagnostics
                )
                else "NO_MAPPING_MATCH"
            ),
            "PEAK_MAPPING_PROFILE_AMBIGUOUS": "AMBIGUOUS_MAPPING_PROFILE",
            "PEAK_MAPPING_WORKSHEET_AMBIGUOUS": "AMBIGUOUS_WORKSHEET",
        }.get(error.code, "MAPPING_VALIDATION_FAILED")
        raise InputRouteError(
            error,
            mapping_route=route,
            mapping_diagnostics=diagnostics,
        ) from error
    except OrdifileError as error:
        raise InputRouteError(error, mapping_route="MAPPING_VALIDATION_FAILED") from error

    adapter = registry.get(resolved.adapter_id)
    return InputRouteDecision(
        DetectionOutcome(
            adapter,
            (
                (
                    resolved.adapter_id,
                    DetectionResult(
                        True,
                        1.0,
                        "A user-approved mapping profile exactly matched the generic table "
                        "structure.",
                    ),
                ),
            ),
        ),
        replace(
            parse_options,
            sheet=resolved.sheet,
            peak_table_mapping=resolved.profile.mapping,
            peak_table_mapping_set=None,
            peak_table_mapping_profile_id=resolved.profile.profile_id,
            peak_table_mapping_profile_fingerprint=(resolved.profile.structural_fingerprint_sha256),
            peak_table_mapping_set_id=parse_options.peak_table_mapping_set.set_id,
        ),
        mapping_applied=True,
        mapping_route="USER_MAPPING_PROFILE",
        mapping_profile_id=resolved.profile.profile_id,
        mapping_structure_fingerprint=resolved.profile.structural_fingerprint_sha256,
    )
