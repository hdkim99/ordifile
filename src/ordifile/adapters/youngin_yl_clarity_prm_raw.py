# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental converter for the validated YL-Clarity PRM scientific family."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from ordifile.adapters._youngin_yl_clarity_prm_binary import (
    YoungInPrmData,
    YoungInPrmStructureError,
    has_prm_family_identity,
    read_prm,
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
    "YL-Clarity 9.0.1.19": (10, 263_520),
    "YL-Clarity 9.1.0.76": (5, 138_000),
}
_SCIENTIFIC_FAMILY_COMPARED_POINTS = 401_520


@dataclass(frozen=True, slots=True)
class _PrmCapability:
    scientific_signal: bool
    support_mode: str
    known_validated_profile: bool
    detector_verified: bool
    response_units: tuple[str | None, ...]
    paired_curve_count: int | None
    paired_curve_point_count: int | None


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


def _parse_error(error: YoungInPrmStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class YoungInYlClarityPrmRawAdapter:
    """Expose validated or fingerprint-compatible YL-Clarity scientific signals."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "youngin_yl_clarity_prm_raw"
    adapter_version: ClassVar[str] = "0.3.0"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "YoungIn PRM: RT min; 9.0 FID/TCD mV, 9.1 FID pA/TCD mV; compatible 9.x unit unresolved",
        (".prm",),
        True,
        False,
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
        del options
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
            ("peak_table_status", "unsupported", None),
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
                "stored_peak_results"
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
                    "validated YL-Clarity profile; stored peak RT, Area, and Height remain "
                    "unsupported.",
                    Severity.WARNING,
                    sample_id,
                ),
            ]
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
            metadata=metadata,
            warnings=tuple(warnings),
        )
