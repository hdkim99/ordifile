# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental converter for the validated YL-Clarity PRM scientific family."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from ordifile.adapters._youngin_yl_clarity_prm_binary import (
    YoungInPrmData,
    YoungInPrmStructureError,
    has_prm_family_identity,
    read_prm,
)
from ordifile.adapters._youngin_yl_clarity_prm_derived_peaks import (
    DERIVATION_METHOD_ID_V2,
    DERIVATION_METHOD_ID_V3,
    DERIVATION_ORIGIN,
    derive_marker_peaks,
)
from ordifile.adapters._youngin_yl_clarity_prm_markers import (
    PrmMarkerDecode,
    PrmPeakWindow,
    build_peak_windows,
    read_prm_markers,
)
from ordifile.adapters._youngin_yl_clarity_prm_time_tables import (
    DEFAULT_EVENT_OPCODES,
    OBSERVED_OPTIONAL_OPCODES,
    PrmCurrentMethod,
    PrmTimeTable,
    read_prm_time_tables,
)
from ordifile.adapters.base import (
    AdapterDescriptor,
    DetectionResult,
    ParseOptions,
    SourceIdentityPolicy,
    SupportStatus,
)
from ordifile.core.errors import ParseError
from ordifile.core.models import (
    DatasetBundle,
    InstrumentMetadata,
    Issue,
    MetadataEntry,
    PeakRecord,
    SampleRecord,
    SeriesKind,
    Severity,
    SignalSeries,
    SourceFile,
)

_NAMESPACE = "adapter:youngin_yl_clarity_prm_raw"
_VALIDATED_PROFILE_UNITS = {
    "YL-Clarity 9.0.1.19": {"FID": "mV", "TCD": "mV"},
    "YL-Clarity 9.1.0.76": {"FID": "pA", "TCD": "mV"},
}
_VALIDATED_PROFILE_EVIDENCE = {
    "YL-Clarity 9.0.1.19": (12, 316_220),
    "YL-Clarity 9.1.0.76": (5, 138_000),
}
_SCIENTIFIC_FAMILY_COMPARED_POINTS = 454_220
_VALIDATED_INTEGRATION_TYPES = {
    "YL-Clarity 9.0.1.19": 0x17,
    "YL-Clarity 9.1.0.76": 0x1A,
}
_DEFAULT_TIME_TABLE_VALUES = (0.1, 0.1, 1.0, 0.0, 0.0, 0.0)
_TIME_TABLE_EXCLUSION_OPCODE = 11
_OBSERVED_OPTIONAL_EVENT_SEQUENCES = frozenset(
    {
        (),
        (11,),
        (12,),
        (11, 12),
        (11, 32),
        (12, 11),
        (11, 11, 32),
        (11, 32, 32),
    }
)
_EVENT_GUID_PATTERN = re.compile(
    r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}"
)


@dataclass(frozen=True, slots=True)
class _PrmCapability:
    scientific_signal: bool
    support_mode: str
    known_validated_profile: bool
    detector_verified: bool
    response_units: tuple[str | None, ...]
    paired_curve_count: int | None
    paired_curve_point_count: int | None


@dataclass(frozen=True, slots=True)
class _DerivedPeakBuild:
    peaks: tuple[PeakRecord, ...]
    channel_statuses: tuple[str, ...]
    ignored_marker_counts: tuple[int, ...]
    marker_candidate_counts: tuple[int, ...]
    time_table_excluded_counts: tuple[int, ...]
    time_table_statuses: tuple[str, ...]


def _evaluate_capability(decoded: YoungInPrmData) -> _PrmCapability:
    producer_version = decoded.producer_version
    channels = decoded.channels
    scientific_signal = decoded.scientific_family_fingerprint.matched
    known_units = _VALIDATED_PROFILE_UNITS.get(producer_version)
    known_validated = known_units is not None
    if not scientific_signal:
        return _PrmCapability(
            False,
            "structural_only",
            known_validated,
            False,
            tuple(None for _ in channels),
            None,
            None,
        )
    evidence = _VALIDATED_PROFILE_EVIDENCE.get(producer_version)
    return _PrmCapability(
        True,
        "validated_profile" if known_validated else "family_compatible_experimental",
        known_validated,
        known_validated,
        tuple(
            known_units.get(channel.stored_detector_label) if known_units is not None else None
            for channel in channels
        ),
        evidence[0] if evidence is not None else None,
        evidence[1] if evidence is not None else None,
    )


def _derived_area_method_id(producer_version: str) -> str:
    return (
        DERIVATION_METHOD_ID_V3
        if producer_version == "YL-Clarity 9.0.1.19"
        else DERIVATION_METHOD_ID_V2
    )


def _build_signals(
    decoded: YoungInPrmData,
    sample_id: str,
    safe_source: str,
    capability: _PrmCapability,
) -> tuple[SignalSeries, ...]:
    channels = decoded.channels
    if capability.scientific_signal:
        return tuple(
            SignalSeries(
                sample_id,
                safe_source,
                channel.channel_id,
                channel.stored_detector_label,
                tuple(
                    index * channel.d_step_candidate / channel.min_ticks_candidate
                    for index in range(channel.record_count)
                ),
                channel.values,
                x_label="retention_time",
                x_unit="min",
                y_label="detector_response",
                y_unit=response_unit,
                series_kind=SeriesKind.SCIENTIFIC_SIGNAL,
            )
            for channel, response_unit in zip(channels, capability.response_units, strict=True)
        )
    return tuple(
        SignalSeries(
            sample_id,
            safe_source,
            channel.channel_id,
            None,
            tuple(range(channel.record_count)),
            channel.values,
            x_label="decoded_record_index",
            x_unit=None,
            y_label="decoded_raw_binary32",
            y_unit=None,
            series_kind=SeriesKind.DECODED_RECORDS,
        )
        for channel in channels
    )


def _time_table_fingerprint_status(table: PrmTimeTable, *, last_time: float) -> str:
    events = table.events
    if (
        len(events) < len(DEFAULT_EVENT_OPCODES)
        or tuple(event.opcode for event in events[: len(DEFAULT_EVENT_OPCODES)])
        != DEFAULT_EVENT_OPCODES
        or tuple(event.value for event in events[: len(DEFAULT_EVENT_OPCODES)])
        != _DEFAULT_TIME_TABLE_VALUES
        or any(
            event.a_time != 0.0 or event.b_time != 0.0
            for event in events[: len(DEFAULT_EVENT_OPCODES)]
        )
        or any(event.group != 32 for event in events)
        or any(
            event.text != ""
            or event.group_text != " "
            or _EVENT_GUID_PATTERN.fullmatch(event.guid) is None
            for event in events
        )
        or tuple(event.source_order for event in events) != tuple(range(1, len(events) + 1))
    ):
        return "time_table_fingerprint_unsupported"
    optional = events[len(DEFAULT_EVENT_OPCODES) :]
    optional_opcodes = tuple(event.opcode for event in optional)
    if (
        any(event.opcode not in OBSERVED_OPTIONAL_OPCODES for event in optional)
        or optional_opcodes not in _OBSERVED_OPTIONAL_EVENT_SEQUENCES
    ):
        return "time_table_opcode_unsupported"
    if any(
        event.value != 0.0
        or not 0.0 <= event.a_time <= last_time
        or not 0.0 <= event.b_time <= last_time
        or (event.opcode in {_TIME_TABLE_EXCLUSION_OPCODE, 12} and event.a_time >= event.b_time)
        or (event.opcode == 32 and event.a_time <= event.b_time)
        for event in optional
    ):
        return "time_table_optional_event_unsupported"
    return "matched"


def _exclude_stored_timetable_candidates(
    values: tuple[float, ...],
    windows: tuple[PrmPeakWindow, ...],
    table: PrmTimeTable,
    *,
    d_step: int,
    min_ticks: float,
) -> tuple[tuple[PrmPeakWindow, ...], int]:
    intervals = tuple(
        (event.a_time, event.b_time)
        for event in table.events
        if event.opcode == _TIME_TABLE_EXCLUSION_OPCODE
    )
    if not intervals:
        return windows, 0
    selected: list[PrmPeakWindow] = []
    excluded = 0
    dt_minutes = d_step / min_ticks
    for window in windows:
        apex_index = max(
            range(window.start_index, window.end_index + 1),
            key=values.__getitem__,
        )
        apex_time = apex_index * dt_minutes
        if any(start <= apex_time <= end for start, end in intervals):
            excluded += 1
        else:
            selected.append(window)
    return tuple(selected), excluded


def _build_derived_peaks(
    decoded: YoungInPrmData,
    sample_id: str,
    safe_source: str,
    capability: _PrmCapability,
    marker_decode: PrmMarkerDecode,
    current_method: PrmCurrentMethod,
) -> _DerivedPeakBuild:
    """Return capability-local Ordifile calculations, never a vendor Result table."""
    channel_statuses = [marker_decode.status for _ in decoded.channels]
    ignored_counts = [0 for _ in decoded.channels]
    candidate_counts = [0 for _ in decoded.channels]
    excluded_counts = [0 for _ in decoded.channels]
    time_table_statuses = [current_method.status for _ in decoded.channels]
    expected_integration_type = _VALIDATED_INTEGRATION_TYPES.get(decoded.producer_version)
    if (
        not capability.known_validated_profile
        or not capability.scientific_signal
        or marker_decode.status != "matched"
        or marker_decode.integration_type != expected_integration_type
        or current_method.status != "matched"
        or current_method.integration_type != expected_integration_type
        or len(current_method.tables) < len(decoded.channels)
    ):
        if marker_decode.status == "matched" and (
            marker_decode.integration_type != expected_integration_type
        ):
            channel_statuses = ["integration_type_unsupported" for _ in decoded.channels]
        elif current_method.status != "matched":
            channel_statuses = ["time_table_unavailable" for _ in decoded.channels]
        elif current_method.integration_type != expected_integration_type:
            channel_statuses = ["time_table_integration_type_unsupported" for _ in decoded.channels]
        return _DerivedPeakBuild(
            (),
            tuple(channel_statuses),
            tuple(ignored_counts),
            tuple(candidate_counts),
            tuple(excluded_counts),
            tuple(time_table_statuses),
        )

    peaks: list[PeakRecord] = []
    for channel_index, (channel, response_unit, markers, time_table) in enumerate(
        zip(
            decoded.channels,
            capability.response_units,
            marker_decode.channels,
            current_method.tables[: len(decoded.channels)],
            strict=True,
        )
    ):
        window_result = build_peak_windows(markers)
        ignored_counts[channel_index] = window_result.ignored_marker_count
        if window_result.status != "matched":
            channel_statuses[channel_index] = "marker_sequence_invalid"
            continue
        candidate_counts[channel_index] = len(window_result.windows)
        cluster_counts: dict[tuple[int, int], int] = {}
        for window in window_result.windows:
            cluster = (window.cluster_start_index, window.cluster_end_index)
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
        original_single_peak_clusters = frozenset(
            cluster for cluster, count in cluster_counts.items() if count == 1
        )
        dt_minutes = channel.d_step_candidate / channel.min_ticks_candidate
        table_status = _time_table_fingerprint_status(
            time_table,
            last_time=(channel.record_count - 1) * dt_minutes,
        )
        time_table_statuses[channel_index] = table_status
        if table_status != "matched":
            channel_statuses[channel_index] = table_status
            continue
        selected_windows, excluded_count = _exclude_stored_timetable_candidates(
            channel.values,
            window_result.windows,
            time_table,
            d_step=channel.d_step_candidate,
            min_ticks=channel.min_ticks_candidate,
        )
        excluded_counts[channel_index] = excluded_count
        try:
            refine_single_peak_clusters = decoded.producer_version == "YL-Clarity 9.0.1.19"
            derived = derive_marker_peaks(
                channel.values,
                selected_windows,
                d_step=channel.d_step_candidate,
                min_ticks=channel.min_ticks_candidate,
                refine_single_peak_clusters=refine_single_peak_clusters,
                original_single_peak_clusters=(
                    original_single_peak_clusters if refine_single_peak_clusters else None
                ),
            )
        except ValueError:
            channel_statuses[channel_index] = "calculation_invalid"
            continue
        channel_statuses[channel_index] = (
            "ordifile_derived_experimental" if derived else "no_peak_markers"
        )
        area_unit = None if response_unit is None else f"{response_unit}.s"
        derivation_method_id = _derived_area_method_id(decoded.producer_version)
        evidence_profile_prefix = (
            f"{decoded.producer_version}; integration_type=0x{marker_decode.integration_type:02x}; "
            f"time_table_slot={time_table.slot_number}; "
            f"time_table_sha256={time_table.payload_sha256}"
        )
        peaks.extend(
            PeakRecord(
                sample_id,
                safe_source,
                channel=channel.channel_id,
                detector=channel.stored_detector_label,
                peak_number=peak_number,
                retention_time=item.retention_index * dt_minutes,
                retention_time_unit="min",
                area=None,
                height=None,
                compound=None,
                compound_source=None,
                status="ordifile_derived_experimental",
                observation_order=peak_number,
                start_time=item.start_index * dt_minutes,
                end_time=item.end_index * dt_minutes,
                area_unit=None,
                height_unit=None,
                data_origin=DERIVATION_ORIGIN,
                derivation_method_id=derivation_method_id,
                derivation_evidence_profile=(
                    f"{evidence_profile_prefix}; boundary_rule={item.boundary_rule}"
                ),
                calculated_area=item.area,
                calculated_area_unit=area_unit,
            )
            for peak_number, item in enumerate(derived, start=1)
        )
    return _DerivedPeakBuild(
        tuple(peaks),
        tuple(channel_statuses),
        tuple(ignored_counts),
        tuple(candidate_counts),
        tuple(excluded_counts),
        tuple(time_table_statuses),
    )


def _parse_error(error: YoungInPrmStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class YoungInYlClarityPrmRawAdapter:
    """Expose validated or fingerprint-compatible YL-Clarity scientific signals."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "youngin_yl_clarity_prm_raw"
    adapter_version: ClassVar[str] = "0.5.0"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "YoungIn PRM: RT min; 9.0 mV; 9.1 FID pA/TCD mV; compatible 9.x unit "
        "unresolved; calc Area!=Result",
        (".prm",),
        True,
        True,
        True,
        True,
        SupportStatus.EXPERIMENTAL,
        (SeriesKind.DECODED_RECORDS, SeriesKind.SCIENTIFIC_SIGNAL),
        SourceIdentityPolicy.SHA256_ALIAS,
    )

    def probe(self, path: Path) -> DetectionResult:
        """Require the case-insensitive .prm extension and bounded profile markers."""
        if path.suffix.casefold() != ".prm":
            return DetectionResult(False, 0.0, "the required .prm extension is absent")
        recognized = has_prm_family_identity(path)
        if not recognized:
            return DetectionResult(False, 0.0, "bounded YL-Clarity PRM family markers are absent")
        try:
            parsed = read_prm(path)
        except YoungInPrmStructureError as error:
            return DetectionResult(
                True,
                0.70,
                error.message,
                routable=False,
                failure_code=error.code,
            )
        capability = _evaluate_capability(parsed)
        if capability.known_validated_profile and capability.scientific_signal:
            notice_codes = ("YOUNGIN_PRM_VALIDATED_SCIENTIFIC_SIGNAL",)
        elif capability.scientific_signal:
            notice_codes = ("YOUNGIN_PRM_FAMILY_COMPATIBLE_SCIENTIFIC_UNIT_UNRESOLVED",)
        else:
            notice_codes = ("YOUNGIN_PRM_FAMILY_COMPATIBLE_STRUCTURAL_ONLY",)
        return DetectionResult(
            True,
            0.99,
            f"{parsed.producer_evidence_status} {parsed.producer_version} PRM profile "
            f"matched with "
            f"{parsed.structural_channel_count} structural channel(s)",
            notice_codes=notice_codes,
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return current-revision binary32 values in file and channel order."""
        if path.suffix.casefold() != ".prm":
            raise ParseError(
                "YOUNGIN_PRM_EXTENSION_INVALID",
                "The exact experimental profile requires a .prm source extension.",
            )
        try:
            decoded = read_prm(path)
            size = path.stat().st_size
        except YoungInPrmStructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                f"Could not stat the input ({type(error).__name__}).",
            ) from error

        sample_id = f"PRM_{decoded.source_sha256[:16]}"
        safe_source = f"{sample_id}.prm"
        source = SourceFile(path, safe_source, safe_source, size, decoded.source_sha256, None, 0)
        channel_ids = tuple(channel.channel_id for channel in decoded.channels)
        capability = _evaluate_capability(decoded)
        sample = SampleRecord(
            sample_id,
            source,
            acquired_at=None,
            acquired_at_reliable=False,
            sequence=None,
            instrument=InstrumentMetadata(None, "YoungIn"),
            channels=channel_ids,
            detectors=(
                tuple(channel.stored_detector_label for channel in decoded.channels)
                if capability.scientific_signal
                else ()
            ),
            runtime=None,
        )
        signals = _build_signals(decoded, sample_id, safe_source, capability)
        marker_decode = (
            read_prm_markers(
                path,
                expected_sha256=decoded.source_sha256,
                layout=decoded.current_revision_layout,
                record_counts=tuple(channel.record_count for channel in decoded.channels),
            )
            if options.experimental_derived_area
            else PrmMarkerDecode(
                "not_requested",
                None,
                tuple(() for _ in decoded.channels),
            )
        )
        current_method = (
            read_prm_time_tables(
                path,
                expected_sha256=decoded.source_sha256,
                layout=decoded.current_revision_layout,
                history_count=decoded.history_count,
            )
            if options.experimental_derived_area
            else PrmCurrentMethod("not_requested", None, ())
        )
        derived_build = _build_derived_peaks(
            decoded,
            sample_id,
            safe_source,
            capability,
            marker_decode,
            current_method,
        )
        peaks = derived_build.peaks
        values: list[tuple[str, object, str | None]] = [
            ("support_status", "experimental", None),
            (
                "representation",
                "scientific_signal" if capability.scientific_signal else "decoded_records",
                None,
            ),
            ("profile", decoded.profile, None),
            ("producer_version", decoded.producer_version, None),
            ("producer_evidence_status", decoded.producer_evidence_status, None),
            ("producer_support_mode", capability.support_mode, None),
            (
                "scientific_family_fingerprint_schema",
                decoded.scientific_family_fingerprint.schema_id,
                None,
            ),
            (
                "scientific_family_fingerprint_status",
                decoded.scientific_family_fingerprint.status,
                None,
            ),
            ("history_count", decoded.history_count, None),
            ("selected_history_version", decoded.selected_history_version, None),
            ("history_revision_exposure_status", "latest_revision_only", None),
            ("prior_history_revision_count", decoded.prior_history_revision_count, None),
            ("prior_history_revisions_exposed", 0, None),
            ("prior_rawdata6_block_count", decoded.prior_rawdata6_block_count, None),
            ("prior_prmdata_block_count", decoded.prior_prmdata_block_count, None),
            ("structural_channel_count", decoded.structural_channel_count, None),
            ("source_sha256", decoded.source_sha256, None),
            ("aggregate_payload_sha256", decoded.aggregate_payload_sha256, None),
            (
                "aggregate_canonical_be_f32_sha256",
                decoded.aggregate_canonical_be_f32_sha256,
                None,
            ),
            ("detector_verified", capability.detector_verified, None),
            (
                "detector_identity_status",
                "paired_curve_validated"
                if capability.detector_verified
                else "stored_native_label"
                if capability.scientific_signal
                else "experimental_stored_native_label",
                None,
            ),
            (
                "channel_identity_status",
                "paired_curve_validated"
                if capability.known_validated_profile and capability.scientific_signal
                else "family_fingerprint_stored_native_label"
                if capability.scientific_signal
                else "experimental_stored_native_label",
                None,
            ),
            (
                "time_axis_status",
                "paired_curve_validated"
                if capability.known_validated_profile and capability.scientific_signal
                else "family_compatible_experimental"
                if capability.scientific_signal
                else "not_exposed",
                None,
            ),
            (
                "time_unit_status",
                "scientific_family_validated" if capability.scientific_signal else "unavailable",
                None,
            ),
            (
                "physical_scaling_status",
                "identity_validated_at_export_precision"
                if capability.known_validated_profile and capability.scientific_signal
                else "family_compatible_identity_experimental"
                if capability.scientific_signal
                else "not_applied",
                None,
            ),
            (
                "signal_unit_status",
                "paired_curve_validated"
                if capability.known_validated_profile and capability.scientific_signal
                else "unresolved",
                None,
            ),
            ("capability_structural_records", "go", None),
            (
                "capability_time_axis",
                "go" if capability.scientific_signal else "unavailable",
                None,
            ),
            (
                "capability_numeric_signal",
                "go" if capability.scientific_signal else "unavailable",
                None,
            ),
            (
                "capability_physical_signal_unit",
                "go"
                if capability.scientific_signal
                and all(unit is not None for unit in capability.response_units)
                else "unresolved"
                if capability.scientific_signal
                else "unavailable",
                None,
            ),
            (
                "peak_table_status",
                "ordifile_marker_derived_experimental" if peaks else "unsupported",
                None,
            ),
            ("integration_marker_status", marker_decode.status, None),
            ("processing_time_table_status", current_method.status, None),
            ("processing_method_span_sha256", current_method.method_span_sha256, None),
            (
                "stored_integration_type",
                marker_decode.integration_type,
                None,
            ),
            ("derived_peak_count", len(peaks), None),
            (
                "derived_area_method_id",
                _derived_area_method_id(decoded.producer_version) if peaks else None,
                None,
            ),
            (
                "derived_area_origin",
                DERIVATION_ORIGIN if peaks else None,
                None,
            ),
            (
                "derived_area_equivalence_status",
                "not_vendor_result_equivalent" if peaks else "not_available",
                None,
            ),
            (
                "scientific_semantics_status",
                "direct_signal_validated"
                if capability.known_validated_profile and capability.scientific_signal
                else "family_compatible_experimental"
                if capability.scientific_signal
                else "structural_only",
                None,
            ),
            (
                "scientific_semantics_evidence_gap",
                "vendor_result_equivalence"
                if peaks
                else "stored_peak_results"
                if capability.known_validated_profile and capability.scientific_signal
                else "producer_version_and_response_unit_validation"
                if capability.scientific_signal
                else "scientific_family_fingerprint",
                None,
            ),
        ]
        if capability.scientific_signal:
            values.extend(
                [
                    (
                        "scientific_family_compared_point_count",
                        _SCIENTIFIC_FAMILY_COMPARED_POINTS,
                        None,
                    )
                ]
            )
            if capability.paired_curve_count is not None:
                values.extend(
                    [
                        ("paired_curve_time_decimal_places", 5, None),
                        ("paired_curve_signal_decimal_places", 4, None),
                        (
                            "paired_curve_distinct_pair_count",
                            capability.paired_curve_count,
                            None,
                        ),
                        (
                            "paired_curve_compared_point_count",
                            capability.paired_curve_point_count,
                            None,
                        ),
                    ]
                )
        for index, channel in enumerate(decoded.channels, start=1):
            prefix = f"structural_channel_{index:03d}"
            values.extend(
                [
                    (f"{prefix}_record_count", channel.record_count, None),
                    (f"{prefix}_stored_detector_label", channel.stored_detector_label, None),
                    (f"{prefix}_raw_size_candidate", channel.raw_size_candidate, None),
                    (f"{prefix}_d_step_candidate", channel.d_step_candidate, None),
                    (f"{prefix}_d_size_candidate", channel.d_size_candidate, None),
                    (f"{prefix}_min_ticks_candidate", channel.min_ticks_candidate, None),
                    (f"{prefix}_payload_sha256", channel.payload_sha256, None),
                    (
                        f"{prefix}_canonical_be_f32_sha256",
                        channel.canonical_be_f32_sha256,
                        None,
                    ),
                    (
                        f"{prefix}_integration_marker_status",
                        derived_build.channel_statuses[index - 1],
                        None,
                    ),
                    (
                        f"{prefix}_integration_marker_count",
                        len(marker_decode.channels[index - 1]),
                        None,
                    ),
                    (
                        f"{prefix}_ignored_incomplete_marker_count",
                        derived_build.ignored_marker_counts[index - 1],
                        None,
                    ),
                    (
                        f"{prefix}_marker_candidate_count",
                        derived_build.marker_candidate_counts[index - 1],
                        None,
                    ),
                    (
                        f"{prefix}_processing_time_table_status",
                        derived_build.time_table_statuses[index - 1],
                        None,
                    ),
                    (
                        f"{prefix}_processing_time_table_excluded_candidate_count",
                        derived_build.time_table_excluded_counts[index - 1],
                        None,
                    ),
                ]
            )
        metadata = tuple(
            MetadataEntry(sample_id, safe_source, _NAMESPACE, key, value, unit)
            for key, value, unit in values
        )
        if capability.known_validated_profile and capability.scientific_signal:
            warnings = [
                Issue(
                    "YOUNGIN_PRM_EXPERIMENTAL_SCIENTIFIC_SIGNAL",
                    "Retention-time and detector-response series were decoded for an exact "
                    "validated YL-Clarity profile. A vendor Result table is not decoded "
                    "from the PRM.",
                    Severity.WARNING,
                    sample_id,
                ),
            ]
            if peaks:
                warnings.append(
                    Issue(
                        "YOUNGIN_PRM_AREA_ORDIFILE_DERIVED_EXPERIMENTAL",
                        "Marker-region retention times and calculated Areas were produced by "
                        "Ordifile from stored PRM partitions and signal. The calculated_area "
                        "field is separate from source-explicit Area and is not a stored or "
                        "vendor-equivalent YL-Clarity Result table.",
                        Severity.WARNING,
                        sample_id,
                    )
                )
            derived_area_unavailable = options.experimental_derived_area and (
                marker_decode.status == "invalid"
                or not peaks
                or any(
                    status
                    in {
                        "integration_type_unsupported",
                        "time_table_unavailable",
                        "time_table_integration_type_unsupported",
                        "time_table_fingerprint_unsupported",
                        "time_table_opcode_unsupported",
                        "time_table_interval_invalid",
                        "time_table_optional_event_unsupported",
                        "marker_sequence_invalid",
                        "calculation_invalid",
                    }
                    for status in derived_build.channel_statuses
                )
            )
            if derived_area_unavailable:
                warnings.append(
                    Issue(
                        marker_decode.issue_code
                        or current_method.issue_code
                        or "YOUNGIN_PRM_DERIVED_AREA_UNAVAILABLE",
                        marker_decode.issue_message
                        or current_method.issue_message
                        or "Stored PRM markers are outside the validated derived-Area "
                        "capability; scientific signals were preserved without Peaks.",
                        Severity.WARNING,
                        sample_id,
                    )
                )
        elif capability.scientific_signal:
            warnings = [
                Issue(
                    "YOUNGIN_PRM_FAMILY_COMPATIBLE_SCIENTIFIC_UNIT_UNRESOLVED",
                    "The validated YL-Clarity scientific-family fingerprint matched an "
                    "unvalidated 9.x producer version. Retention time and numeric response "
                    "were preserved, but the physical response unit is unresolved and peak "
                    "RT, Area, and Height remain unsupported.",
                    Severity.WARNING,
                    sample_id,
                ),
            ]
            if options.experimental_derived_area:
                warnings.append(
                    Issue(
                        "YOUNGIN_PRM_DERIVED_AREA_PROFILE_UNAVAILABLE",
                        "Calculated Area is limited to the exact validated YL-Clarity "
                        "9.0.1.19 and 9.1.0.76 profiles; scientific signals were preserved "
                        "without calculated Peaks.",
                        Severity.WARNING,
                        sample_id,
                    )
                )
        else:
            warnings = [
                Issue(
                    "YOUNGIN_PRM_EXPERIMENTAL_RAW_RECORDS",
                    "Ordered binary32 records were decoded because the scientific-family "
                    "fingerprint was incomplete; no retention-time, physical response, unit, "
                    "or peak semantics were added.",
                    Severity.WARNING,
                    sample_id,
                ),
            ]
            if options.experimental_derived_area:
                warnings.append(
                    Issue(
                        "YOUNGIN_PRM_DERIVED_AREA_PROFILE_UNAVAILABLE",
                        "Calculated Area is unavailable for this structural-only PRM "
                        "profile; decoded records were preserved without calculated Peaks.",
                        Severity.WARNING,
                        sample_id,
                    )
                )
        if decoded.prior_history_revision_count:
            warnings.append(
                Issue(
                    "YOUNGIN_PRM_PRIOR_HISTORY_NOT_EXPOSED",
                    "Only raw blocks after the latest ChromVersion are exported; earlier "
                    "history revisions remain unsupported and their structural counts are "
                    "reported in Metadata.",
                    Severity.WARNING,
                    sample_id,
                )
            )
        return DatasetBundle(
            (source,),
            (sample,),
            signals=signals,
            peaks=peaks,
            metadata=metadata,
            warnings=tuple(warnings),
        )
