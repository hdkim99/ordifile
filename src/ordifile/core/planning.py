# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Deterministic, non-canonicalizing conversion preflight and immutable local plans."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NoReturn, SupportsIndex

from ordifile.adapters._mapped_table import GENERIC_PEAK_TABLE_ADAPTER_IDS
from ordifile.adapters.base import ParseOptions
from ordifile.adapters.registry import AdapterRegistry
from ordifile.core.discovery import DiscoveryRecord, discover_files, sha256_file
from ordifile.core.errors import ExportError, OrdifileError
from ordifile.core.peak_mapping import (
    PeakMappingDriftDiagnostic,
    PeakTableMapping,
    PeakTableMappingSet,
)
from ordifile.core.pipeline import MAX_INPUT_FILE_BYTES, WARN_INPUT_FILE_BYTES
from ordifile.core.routing import (
    InputRouteError,
    InputRouteExpectation,
    input_route_identity,
    registry_route_identity,
    resolve_input_route,
)
from ordifile.exporters.excel import validate_primary_output_target

CONVERSION_PLAN_SCHEMA_VERSION = 1
MAX_CONVERSION_PLAN_INPUTS = 10_000
MAX_CONVERSION_PLAN_TOTAL_INPUT_BYTES = 64 * 1024 * 1024 * 1024
MAX_CONVERSION_PLAN_ISSUE_CODES = 32
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ConversionPlanRoute(StrEnum):
    """Non-scientific route selected by bounded ownership/structure inspection."""

    EXACT_ADAPTER = "EXACT_ADAPTER"
    USER_MAPPING = "USER_MAPPING"
    USER_MAPPING_PROFILE = "USER_MAPPING_PROFILE"
    GENERIC_INPUT = "GENERIC_INPUT"
    UNROUTED = "UNROUTED"


class ConversionPlanEntryStatus(StrEnum):
    """Preflight disposition; ROUTABLE does not claim parse success."""

    ROUTABLE = "ROUTABLE"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"
    EXCLUDED_ARTIFACT = "EXCLUDED_ARTIFACT"


class ConversionPlanProblem(StrEnum):
    """Fixed user-action category without private parser or path details."""

    NONE = "NONE"
    UNMAPPED_GENERIC_TABLE = "UNMAPPED_GENERIC_TABLE"
    MAPPING_SCHEMA_DRIFT = "MAPPING_SCHEMA_DRIFT"
    MAPPING_PROFILE_AMBIGUOUS = "MAPPING_PROFILE_AMBIGUOUS"
    WORKSHEET_AMBIGUOUS = "WORKSHEET_AMBIGUOUS"
    ADAPTER_AMBIGUOUS = "ADAPTER_AMBIGUOUS"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    MALFORMED_INPUT = "MALFORMED_INPUT"
    DUPLICATE_INPUT = "DUPLICATE_INPUT"
    INPUT_DISCOVERY_FAILED = "INPUT_DISCOVERY_FAILED"
    OUTPUT_CONFLICT = "OUTPUT_CONFLICT"


class ConversionPlanReadiness(StrEnum):
    """Whether current conversion policy can proceed after revalidation."""

    READY = "READY"
    READY_WITH_KNOWN_FAILURES = "READY_WITH_KNOWN_FAILURES"
    BLOCKED = "BLOCKED"


class ConversionPlanOutputDisposition(StrEnum):
    """Read-only primary output state observed during planning."""

    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class ConversionPlanEntry:
    """One privacy-safe input route without scientific rows or local paths."""

    input_order: int
    source_id: str
    size: int
    sha256: str | None
    status: ConversionPlanEntryStatus
    route: ConversionPlanRoute
    problem: ConversionPlanProblem = ConversionPlanProblem.NONE
    adapter_id: str | None = None
    adapter_version: str | None = None
    mapping_profile_id: str | None = None
    mapping_structure_fingerprint: str | None = None
    duplicate_of: int | None = None
    issue_codes: tuple[str, ...] = ()
    mapping_diagnostics: tuple[PeakMappingDriftDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if type(self.input_order) is not int or self.input_order < 0:
            raise OrdifileError("CONVERSION_PLAN_INVALID", "Plan input order is invalid.")
        if type(self.source_id) is not str or not self.source_id:
            raise OrdifileError("CONVERSION_PLAN_INVALID", "Plan source identity is invalid.")
        if type(self.size) is not int or self.size < 0:
            raise OrdifileError("CONVERSION_PLAN_INVALID", "Plan source size is invalid.")
        if self.sha256 is not None and (
            type(self.sha256) is not str or _SHA256.fullmatch(self.sha256) is None
        ):
            raise OrdifileError("CONVERSION_PLAN_INVALID", "Plan source digest is invalid.")
        if len(self.issue_codes) > MAX_CONVERSION_PLAN_ISSUE_CODES:
            raise OrdifileError("CONVERSION_PLAN_INVALID", "Plan issue codes exceed the bound.")


@dataclass(frozen=True, slots=True)
class ConversionPlanOptions:
    """Public-safe behavior snapshot; private sheet/mapping text is excluded."""

    recursive: bool
    extensions: tuple[str, ...]
    sort: str
    include_signals: bool
    adapter: str | None
    sheet_selected: bool
    include_hidden_sheets: bool
    on_error: str
    overwrite: bool
    sidecar_mode: str
    mapping_mode: str
    mapping_schema_version: int | None
    mapping_public_fingerprint: str | None
    mapping_set_id: str | None
    mapping_set_schema_version: int | None
    mapping_set_public_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class ConversionPlanSummary:
    """Aggregate, privacy-safe dry-run summary shared by API, CLI, and desktop."""

    total_inputs: int
    routable: int
    exact_adapters: int
    user_mappings: int
    mapping_profiles: int
    generic_inputs: int
    drifted: int
    unmapped: int
    ambiguous: int
    unsupported: int
    malformed: int
    duplicates: int
    excluded_artifacts: int
    failed: int


@dataclass(frozen=True, slots=True)
class PlanProgressEvent:
    """Progress event whose statuses never imply scientific parsing success."""

    stage: str
    completed: int
    total: int
    source_id: str | None = None
    status: ConversionPlanEntryStatus | None = None


@dataclass(frozen=True, slots=True)
class _SourceBinding:
    path: Path
    size: int
    sha256: str | None
    duplicate_of: int | None
    issue_codes: tuple[str, ...]
    route_expectation: InputRouteExpectation | None
    adapter_id: str | None
    adapter_version: str | None
    mapping_profile_id: str | None
    mapping_structure_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class _OutputBinding:
    exists: bool
    mode: int | None
    size: int | None
    modified_ns: int | None
    device: int | None
    inode: int | None


@dataclass(frozen=True, slots=True)
class _PlanBindings:
    inputs: tuple[Path, ...]
    output: Path
    recursive: bool
    extensions: tuple[str, ...] | None
    sort: str
    include_signals: bool
    adapter: str | None
    sheet: str | None
    include_hidden_sheets: bool
    peak_table_mapping: PeakTableMapping | None
    peak_table_mapping_set: PeakTableMappingSet | None
    on_error: str
    overwrite: bool
    sidecar_mode: str
    registry_signature: tuple[tuple[str, str, str], ...]
    mapping_signature: tuple[object, ...]
    sources: tuple[_SourceBinding, ...]
    output_snapshot: _OutputBinding


class ConversionPlan:
    """Immutable same-process execution plan with a deliberately private binding."""

    __slots__ = (
        "_bindings",
        "_entries",
        "_options",
        "_output_disposition",
        "_output_issue_code",
        "_public_summary_sha256",
        "_readiness",
        "_summary",
    )
    _bindings: _PlanBindings
    _entries: tuple[ConversionPlanEntry, ...]
    _options: ConversionPlanOptions
    _output_disposition: ConversionPlanOutputDisposition
    _output_issue_code: str | None
    _public_summary_sha256: str
    _readiness: ConversionPlanReadiness
    _summary: ConversionPlanSummary

    def __init__(
        self,
        *,
        entries: tuple[ConversionPlanEntry, ...],
        options: ConversionPlanOptions,
        output_disposition: ConversionPlanOutputDisposition,
        output_issue_code: str | None,
        readiness: ConversionPlanReadiness,
        public_summary_sha256: str,
        bindings: _PlanBindings,
    ) -> None:
        object.__setattr__(self, "_entries", entries)
        object.__setattr__(self, "_options", options)
        object.__setattr__(self, "_output_disposition", output_disposition)
        object.__setattr__(self, "_output_issue_code", output_issue_code)
        object.__setattr__(self, "_readiness", readiness)
        object.__setattr__(self, "_public_summary_sha256", public_summary_sha256)
        object.__setattr__(self, "_bindings", bindings)
        object.__setattr__(self, "_summary", _summarize(entries))

    def __setattr__(self, name: str, value: object) -> NoReturn:
        del name, value
        raise AttributeError("ConversionPlan is immutable.")

    def __repr__(self) -> str:
        return (
            "ConversionPlan("
            f"schema_version={self.schema_version}, readiness={self.readiness.value!r}, "
            f"total_inputs={self.summary.total_inputs}, "
            f"public_summary_sha256={self.public_summary_sha256!r})"
        )

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("ConversionPlan is a same-process object and cannot be serialized.")

    @property
    def schema_version(self) -> int:
        return CONVERSION_PLAN_SCHEMA_VERSION

    @property
    def entries(self) -> tuple[ConversionPlanEntry, ...]:
        return self._entries

    @property
    def options(self) -> ConversionPlanOptions:
        return self._options

    @property
    def output_disposition(self) -> ConversionPlanOutputDisposition:
        return self._output_disposition

    @property
    def output_issue_code(self) -> str | None:
        return self._output_issue_code

    @property
    def readiness(self) -> ConversionPlanReadiness:
        return self._readiness

    @property
    def public_summary_sha256(self) -> str:
        """Hash the privacy-safe public projection, not private path/config bindings."""
        return self._public_summary_sha256

    @property
    def summary(self) -> ConversionPlanSummary:
        return self._summary

    @property
    def is_executable(self) -> bool:
        return self.readiness is not ConversionPlanReadiness.BLOCKED


def _absolute_lexical(path: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _source_id(record: DiscoveryRecord) -> str:
    digest = record.source.sha256
    if type(digest) is str and _SHA256.fullmatch(digest) is not None:
        return f"source-{digest}"
    return f"source-input-{record.source.input_order + 1:06d}"


def _bounded_codes(codes: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(codes))[:MAX_CONVERSION_PLAN_ISSUE_CODES]


def _problem_for_route(route: str | None, error_code: str) -> ConversionPlanProblem:
    if route == "SCHEMA_DRIFT_CANDIDATE":
        return ConversionPlanProblem.MAPPING_SCHEMA_DRIFT
    if route == "NO_MAPPING_MATCH":
        return ConversionPlanProblem.UNMAPPED_GENERIC_TABLE
    if route == "AMBIGUOUS_MAPPING_PROFILE":
        return ConversionPlanProblem.MAPPING_PROFILE_AMBIGUOUS
    if route == "AMBIGUOUS_WORKSHEET":
        return ConversionPlanProblem.WORKSHEET_AMBIGUOUS
    if error_code == "FORMAT_NOT_DETECTED":
        return ConversionPlanProblem.UNSUPPORTED_FORMAT
    if "AMBIGUOUS" in error_code:
        return ConversionPlanProblem.ADAPTER_AMBIGUOUS
    return ConversionPlanProblem.MALFORMED_INPUT


def _public_route(adapter_id: str, mapping_route: str | None) -> ConversionPlanRoute:
    if mapping_route == "EXACT_ADAPTER":
        return ConversionPlanRoute.EXACT_ADAPTER
    if mapping_route == "USER_MAPPING":
        return ConversionPlanRoute.USER_MAPPING
    if mapping_route == "USER_MAPPING_PROFILE":
        return ConversionPlanRoute.USER_MAPPING_PROFILE
    if adapter_id in GENERIC_PEAK_TABLE_ADAPTER_IDS:
        return ConversionPlanRoute.GENERIC_INPUT
    return ConversionPlanRoute.EXACT_ADAPTER


def _mapping_public_fingerprint(mapping: PeakTableMapping) -> str:
    payload = {
        "domain": "ordifile-conversion-plan-mapping-v1",
        "schema_version": mapping.schema_version,
        "source_format": mapping.source_format.value,
        "column_count": len(mapping.declared_headers),
        "roles": mapping.structural_roles,
        "unit_presence": (
            True,
            mapping.area_unit is not None,
            mapping.height_unit is not None,
            mapping.secondary_retention_time_unit is not None,
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "ascii"
        )
    ).hexdigest()


def _mapping_signature(
    mapping: PeakTableMapping | None,
    mapping_set: PeakTableMappingSet | None,
) -> tuple[object, ...]:
    if mapping is not None:
        return ("single", mapping.semantic_sha256)
    if mapping_set is not None:
        return (
            "set",
            mapping_set.set_id,
            mapping_set.schema_version,
            tuple(
                (
                    profile.profile_id,
                    profile.semantic_sha256,
                    profile.structural_fingerprint_sha256,
                )
                for profile in mapping_set.profiles
            ),
        )
    return ("none",)


def output_binding(output: Path) -> _OutputBinding:
    try:
        status = output.stat(follow_symlinks=False)
    except FileNotFoundError:
        return _OutputBinding(False, None, None, None, None, None)
    except OSError as error:
        raise ExportError(
            "OUTPUT_INSPECTION_FAILED", "The output target could not be inspected safely."
        ) from error
    return _OutputBinding(
        True,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        status.st_dev,
        status.st_ino,
    )


def _diagnostic_payload(value: PeakMappingDriftDiagnostic) -> dict[str, object]:
    return {
        "schema": value.schema_version,
        "profile_id": value.profile_id,
        "profile_fingerprint": value.profile_structural_fingerprint,
        "format": value.source_format.value,
        "categories": [category.value for category in value.categories],
        "expected_columns": value.expected_column_count,
        "observed_columns": value.observed_column_count,
        "exact_position_matches": value.exact_position_matches,
        "changed": value.changed_column_count,
        "added": value.added_column_count,
        "removed": value.removed_column_count,
        "moved": value.moved_column_count,
        "total": value.total_difference_count,
        "required": list(value.unresolved_required_roles),
        "optional": list(value.unresolved_optional_roles),
    }


def _public_summary_digest(
    entries: tuple[ConversionPlanEntry, ...],
    options: ConversionPlanOptions,
    output_disposition: ConversionPlanOutputDisposition,
    output_issue_code: str | None,
    readiness: ConversionPlanReadiness,
) -> str:
    payload = {
        "domain": "ordifile-conversion-plan-v1",
        "schema_version": CONVERSION_PLAN_SCHEMA_VERSION,
        "options": {
            "recursive": options.recursive,
            "extensions": list(options.extensions),
            "sort": options.sort,
            "include_signals": options.include_signals,
            "adapter": options.adapter,
            "sheet_selected": options.sheet_selected,
            "include_hidden_sheets": options.include_hidden_sheets,
            "on_error": options.on_error,
            "overwrite": options.overwrite,
            "sidecar_mode": options.sidecar_mode,
            "mapping_mode": options.mapping_mode,
            "mapping_schema_version": options.mapping_schema_version,
            "mapping_public_fingerprint": options.mapping_public_fingerprint,
            "mapping_set_id": options.mapping_set_id,
            "mapping_set_schema_version": options.mapping_set_schema_version,
            "mapping_set_public_fingerprint": options.mapping_set_public_fingerprint,
        },
        "entries": [
            {
                "input_order": entry.input_order,
                "source_id": entry.source_id,
                "size": entry.size,
                "sha256": entry.sha256,
                "status": entry.status.value,
                "route": entry.route.value,
                "problem": entry.problem.value,
                "adapter_id": entry.adapter_id,
                "adapter_version": entry.adapter_version,
                "profile_id": entry.mapping_profile_id,
                "structure_fingerprint": entry.mapping_structure_fingerprint,
                "duplicate_of": entry.duplicate_of,
                "issue_codes": list(entry.issue_codes),
                "diagnostics": [
                    _diagnostic_payload(diagnostic) for diagnostic in entry.mapping_diagnostics
                ],
            }
            for entry in entries
        ],
        "output_disposition": output_disposition.value,
        "output_issue_code": output_issue_code,
        "readiness": readiness.value,
    }
    canonical = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def _summarize(entries: tuple[ConversionPlanEntry, ...]) -> ConversionPlanSummary:
    ambiguous_problems = {
        ConversionPlanProblem.MAPPING_PROFILE_AMBIGUOUS,
        ConversionPlanProblem.WORKSHEET_AMBIGUOUS,
        ConversionPlanProblem.ADAPTER_AMBIGUOUS,
    }
    return ConversionPlanSummary(
        total_inputs=len(entries),
        routable=sum(entry.status is ConversionPlanEntryStatus.ROUTABLE for entry in entries),
        exact_adapters=sum(entry.route is ConversionPlanRoute.EXACT_ADAPTER for entry in entries),
        user_mappings=sum(entry.route is ConversionPlanRoute.USER_MAPPING for entry in entries),
        mapping_profiles=sum(
            entry.route is ConversionPlanRoute.USER_MAPPING_PROFILE for entry in entries
        ),
        generic_inputs=sum(entry.route is ConversionPlanRoute.GENERIC_INPUT for entry in entries),
        drifted=sum(
            entry.problem is ConversionPlanProblem.MAPPING_SCHEMA_DRIFT for entry in entries
        ),
        unmapped=sum(
            entry.problem is ConversionPlanProblem.UNMAPPED_GENERIC_TABLE for entry in entries
        ),
        ambiguous=sum(entry.problem in ambiguous_problems for entry in entries),
        unsupported=sum(
            entry.problem is ConversionPlanProblem.UNSUPPORTED_FORMAT for entry in entries
        ),
        malformed=sum(entry.problem is ConversionPlanProblem.MALFORMED_INPUT for entry in entries),
        duplicates=sum(entry.status is ConversionPlanEntryStatus.DUPLICATE for entry in entries),
        excluded_artifacts=sum(
            entry.status is ConversionPlanEntryStatus.EXCLUDED_ARTIFACT for entry in entries
        ),
        failed=sum(entry.status is ConversionPlanEntryStatus.FAILED for entry in entries),
    )


def build_conversion_plan(
    inputs: Sequence[str | os.PathLike[str]],
    output: str | os.PathLike[str],
    registry: AdapterRegistry,
    *,
    recursive: bool,
    extensions: tuple[str, ...] | None,
    sort: str,
    include_signals: bool,
    adapter: str | None,
    sheet: str | None,
    include_hidden_sheets: bool,
    peak_table_mapping: PeakTableMapping | None,
    peak_table_mapping_set: PeakTableMappingSet | None,
    on_error: str,
    overwrite: bool,
    sidecar_mode: str,
    progress: Callable[[PlanProgressEvent], None] | None = None,
) -> ConversionPlan:
    """Build one bounded route-only plan without canonical rows or output artifacts."""
    frozen_inputs = tuple(_absolute_lexical(value) for value in inputs)
    frozen_output = _absolute_lexical(output)
    planned_registry_signature = registry_route_identity(registry)

    def require_stable_registry() -> None:
        if registry_route_identity(registry) != planned_registry_signature:
            raise OrdifileError(
                "CONVERSION_PLAN_ADAPTER_CHANGED",
                "The adapter inventory changed during conversion preflight; retry the plan.",
            )

    parse_options = ParseOptions(
        sheet=sheet,
        include_hidden_sheets=include_hidden_sheets,
        peak_table_mapping=peak_table_mapping,
        peak_table_mapping_set=peak_table_mapping_set,
    )
    records = discover_files(
        frozen_inputs,
        recursive=recursive,
        extensions=extensions,
        warn_file_bytes=WARN_INPUT_FILE_BYTES,
        max_file_bytes=MAX_INPUT_FILE_BYTES,
        artifact_output=frozen_output,
        max_discovered_files=MAX_CONVERSION_PLAN_INPUTS,
        max_total_bytes=MAX_CONVERSION_PLAN_TOTAL_INPUT_BYTES,
    )
    if not records:
        raise OrdifileError(
            "NO_DISCOVERED_FILES", "No files remained after discovery and extension filtering."
        )
    if progress is not None:
        progress(PlanProgressEvent("planning_discovery", len(records), len(records)))
    require_stable_registry()

    entries: list[ConversionPlanEntry] = []
    source_bindings: list[_SourceBinding] = []
    mapping_requested = peak_table_mapping is not None or peak_table_mapping_set is not None
    for completed, record in enumerate(records, start=1):
        require_stable_registry()
        source = record.source
        codes = _bounded_codes(issue.code for issue in record.issues)
        discovery_codes = codes
        diagnostics: tuple[PeakMappingDriftDiagnostic, ...] = ()
        route = ConversionPlanRoute.UNROUTED
        problem = ConversionPlanProblem.NONE
        adapter_id: str | None = None
        adapter_version: str | None = None
        profile_id: str | None = None
        structure_fingerprint: str | None = None
        private_route_expectation: InputRouteExpectation | None = None
        artifact = "ORDIFILE_ARTIFACT_EXCLUDED" in codes
        has_error = any(issue.severity.value == "error" for issue in record.issues)
        if artifact:
            status = ConversionPlanEntryStatus.EXCLUDED_ARTIFACT
        elif source.duplicate_of is not None:
            status = ConversionPlanEntryStatus.DUPLICATE
            problem = ConversionPlanProblem.DUPLICATE_INPUT
        elif has_error:
            status = ConversionPlanEntryStatus.FAILED
            problem = ConversionPlanProblem.INPUT_DISCOVERY_FAILED
        else:
            try:
                decision = resolve_input_route(
                    source.path,
                    registry,
                    forced_adapter=adapter,
                    parse_options=parse_options,
                )
                adapter_id = decision.detection.adapter.adapter_id
                adapter_version = decision.detection.adapter.adapter_version
                profile_id = decision.mapping_profile_id
                structure_fingerprint = decision.mapping_structure_fingerprint
                private_route_expectation = InputRouteExpectation(
                    identity=input_route_identity(decision)
                )
                route = _public_route(adapter_id, decision.mapping_route)
                if mapping_requested and decision.mapping_route == "EXACT_ADAPTER":
                    codes = _bounded_codes((*codes, "PEAK_MAPPING_NOT_APPLIED_EXACT_PROFILE"))
                current_sha256 = sha256_file(source.path)
                if current_sha256 != source.sha256:
                    raise OrdifileError(
                        "INPUT_CHANGED_DURING_PREFLIGHT",
                        "Input content changed while conversion preflight was running.",
                    )
                status = ConversionPlanEntryStatus.ROUTABLE
            except InputRouteError as error:
                diagnostics = error.mapping_diagnostics
                codes = _bounded_codes((*codes, error.code))
                private_route_expectation = InputRouteExpectation(
                    error_code=error.code,
                    mapping_route=error.mapping_route,
                )
                status = ConversionPlanEntryStatus.FAILED
                problem = _problem_for_route(error.mapping_route, error.code)
                if (
                    problem is ConversionPlanProblem.UNMAPPED_GENERIC_TABLE
                    and source.path.suffix.casefold() not in {".csv", ".tsv", ".txt", ".xlsx"}
                ):
                    problem = ConversionPlanProblem.UNSUPPORTED_FORMAT
            except (KeyboardInterrupt, SystemExit, MemoryError):
                raise
            except Exception as error:
                code = getattr(error, "code", "ROUTING_FAILED")
                safe_code = code if type(code) is str else "ROUTING_FAILED"
                codes = _bounded_codes((*codes, safe_code))
                private_route_expectation = InputRouteExpectation(error_code=safe_code)
                status = ConversionPlanEntryStatus.FAILED
                problem = _problem_for_route(None, safe_code)

        entry = ConversionPlanEntry(
            input_order=source.input_order,
            source_id=_source_id(record),
            size=source.size,
            sha256=source.sha256,
            status=status,
            route=route,
            problem=problem,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            mapping_profile_id=profile_id,
            mapping_structure_fingerprint=structure_fingerprint,
            duplicate_of=source.duplicate_of,
            issue_codes=codes,
            mapping_diagnostics=diagnostics,
        )
        entries.append(entry)
        source_bindings.append(
            _SourceBinding(
                source.path,
                source.size,
                source.sha256,
                source.duplicate_of,
                discovery_codes,
                private_route_expectation,
                adapter_id,
                adapter_version,
                profile_id,
                structure_fingerprint,
            )
        )
        if progress is not None:
            progress(
                PlanProgressEvent(
                    "planning_routing",
                    completed,
                    len(records),
                    entry.source_id,
                    entry.status,
                )
            )
        require_stable_registry()

    protected_inputs = tuple(
        record.source.path
        for record in records
        if not any(issue.code == "ORDIFILE_ARTIFACT_EXCLUDED" for issue in record.issues)
    )
    output_issue: str | None = None
    try:
        validate_primary_output_target(
            frozen_output,
            protected_inputs,
            overwrite=overwrite,
        )
        output_disposition = ConversionPlanOutputDisposition.AVAILABLE
    except ExportError as error:
        output_issue = error.code
        output_disposition = ConversionPlanOutputDisposition.BLOCKED

    entry_tuple = tuple(entries)
    any_failure = any(entry.status is ConversionPlanEntryStatus.FAILED for entry in entry_tuple)
    if output_disposition is ConversionPlanOutputDisposition.BLOCKED or (
        on_error == "stop" and any_failure
    ):
        readiness = ConversionPlanReadiness.BLOCKED
    elif any_failure:
        readiness = ConversionPlanReadiness.READY_WITH_KNOWN_FAILURES
    else:
        readiness = ConversionPlanReadiness.READY

    mapping_mode = (
        "SINGLE_MAPPING"
        if peak_table_mapping is not None
        else "MAPPING_SET"
        if peak_table_mapping_set is not None
        else "NONE"
    )
    public_options = ConversionPlanOptions(
        recursive=recursive,
        extensions=extensions or (),
        sort=sort,
        include_signals=include_signals,
        adapter=adapter,
        sheet_selected=sheet is not None,
        include_hidden_sheets=include_hidden_sheets,
        on_error=on_error,
        overwrite=overwrite,
        sidecar_mode=sidecar_mode,
        mapping_mode=mapping_mode,
        mapping_schema_version=(
            peak_table_mapping.schema_version if peak_table_mapping is not None else None
        ),
        mapping_public_fingerprint=(
            _mapping_public_fingerprint(peak_table_mapping)
            if peak_table_mapping is not None
            else None
        ),
        mapping_set_id=(
            peak_table_mapping_set.set_id if peak_table_mapping_set is not None else None
        ),
        mapping_set_schema_version=(
            peak_table_mapping_set.schema_version if peak_table_mapping_set is not None else None
        ),
        mapping_set_public_fingerprint=(
            peak_table_mapping_set.structural_fingerprint_sha256
            if peak_table_mapping_set is not None
            else None
        ),
    )
    public_summary_sha256 = _public_summary_digest(
        entry_tuple,
        public_options,
        output_disposition,
        output_issue,
        readiness,
    )
    bindings = _PlanBindings(
        inputs=frozen_inputs,
        output=frozen_output,
        recursive=recursive,
        extensions=extensions,
        sort=sort,
        include_signals=include_signals,
        adapter=adapter,
        sheet=sheet,
        include_hidden_sheets=include_hidden_sheets,
        peak_table_mapping=peak_table_mapping,
        peak_table_mapping_set=peak_table_mapping_set,
        on_error=on_error,
        overwrite=overwrite,
        sidecar_mode=sidecar_mode,
        registry_signature=planned_registry_signature,
        mapping_signature=_mapping_signature(peak_table_mapping, peak_table_mapping_set),
        sources=tuple(source_bindings),
        output_snapshot=output_binding(frozen_output),
    )
    plan = ConversionPlan(
        entries=entry_tuple,
        options=public_options,
        output_disposition=output_disposition,
        output_issue_code=output_issue,
        readiness=readiness,
        public_summary_sha256=public_summary_sha256,
        bindings=bindings,
    )
    if progress is not None:
        progress(PlanProgressEvent("planning_complete", len(records), len(records)))
    return plan


def plan_bindings(plan: ConversionPlan) -> _PlanBindings:
    """Return private bindings only to the public API execution boundary."""
    if type(plan) is not ConversionPlan:
        raise OrdifileError("CONVERSION_PLAN_INVALID", "plan must be a ConversionPlan.")
    return plan._bindings
