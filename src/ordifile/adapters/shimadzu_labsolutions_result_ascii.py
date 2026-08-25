# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental standalone reader for one exact LabSolutions result ASCII profile."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ordifile.adapters._shimadzu_labsolutions_result_ascii import (
    ShimadzuResultAsciiStructureError,
    has_result_ascii_family_identity,
    read_result_ascii,
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
    Severity,
    SourceFile,
)

_NAMESPACE = "adapter:shimadzu_labsolutions_result_ascii"
_CANONICAL_DETECTOR = "FID"
_CANONICAL_CHANNEL = "Ch1"


def _parse_error(error: ShimadzuResultAsciiStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class ShimadzuLabsolutionsResultAsciiAdapter:
    """Read source-order peaks from the exact 5.82 GC-2014 SFID1/Ch1 export."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "shimadzu_labsolutions_result_ascii"
    adapter_version: ClassVar[str] = "0.1.1"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "Shimadzu LabSolutions result ASCII, 5.82 GC-2014 FID profile (Experimental)",
        (".txt",),
        True,
        True,
        False,
        True,
        SupportStatus.EXPERIMENTAL,
        (),
        SourceIdentityPolicy.SHA256_ALIAS,
    )

    def probe(self, path: Path) -> DetectionResult:
        """Require .txt plus bounded LabSolutions family and exact-profile evidence."""
        if path.suffix.casefold() != ".txt":
            return DetectionResult(False, 0.0, "the required .txt extension is absent")
        if not has_result_ascii_family_identity(path):
            return DetectionResult(False, 0.0, "bounded LabSolutions result markers are absent")
        try:
            read_result_ascii(path)
        except ShimadzuResultAsciiStructureError as error:
            return DetectionResult(
                True,
                0.70,
                error.message,
                routable=False,
                failure_code=error.code,
            )
        return DetectionResult(
            True,
            0.99,
            "exact LabSolutions 5.82 GC-2014 SFID1/Ch1 result ASCII profile matched",
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return only allowlisted result peaks; private run fields remain unexposed."""
        del options
        if path.suffix.casefold() != ".txt":
            raise ParseError(
                "SHIMADZU_RESULT_ASCII_EXTENSION_INVALID",
                "The exact experimental profile requires a .txt source extension.",
            )
        try:
            decoded = read_result_ascii(path)
        except ShimadzuResultAsciiStructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                "The result ASCII input could not be read.",
            ) from error

        source_sha256 = decoded.source_sha256
        sample_id = f"SHIMADZU_RESULT_{source_sha256[:16]}"
        safe_source = f"{sample_id}.txt"
        source = SourceFile(
            path,
            safe_source,
            safe_source,
            decoded.source_size,
            source_sha256,
            None,
            0,
        )
        sample = SampleRecord(
            sample_id,
            source,
            instrument=InstrumentMetadata("GC", "Shimadzu"),
            channels=(_CANONICAL_CHANNEL,),
            detectors=(_CANONICAL_DETECTOR,),
        )
        peaks = tuple(
            PeakRecord(
                sample_id,
                safe_source,
                channel=_CANONICAL_CHANNEL,
                detector=_CANONICAL_DETECTOR,
                peak_number=peak.peak_number,
                retention_time=peak.retention_time,
                retention_time_unit=decoded.retention_time_unit,
                area=peak.area,
                height=peak.height,
                compound=None,
                compound_source=None,
                status="experimental",
                observation_order=peak.observation_order,
                start_time=peak.start_time,
                end_time=peak.end_time,
                area_unit=None,
                height_unit=None,
            )
            for peak in decoded.peaks
        )
        values: tuple[tuple[str, object, str | None], ...] = (
            ("support_status", "experimental", None),
            ("profile", "LabSolutions 5.82 GC-2014 single SFID1/Ch1 result ASCII", None),
            ("representation", "peak_table_ch1_source_order", None),
            ("application_name", decoded.application_name, None),
            ("software_version", decoded.software_version, None),
            ("instrument_model", decoded.instrument_model, None),
            ("source_detector_label", decoded.source_detector_label, None),
            ("source_channel", decoded.source_channel, None),
            ("canonical_detector", _CANONICAL_DETECTOR, None),
            ("canonical_channel", _CANONICAL_CHANNEL, None),
            ("detector_verification_status", "source_explicit", None),
            ("peak_count", len(decoded.peaks), None),
            ("retention_time_unit", decoded.retention_time_unit, None),
            ("area_unit_status", "unresolved", None),
            ("height_unit_status", "unresolved", None),
            ("compound_identification_status", "not_present", None),
            ("same_file_chromatogram_point_count", decoded.chromatogram_point_count, None),
            ("same_file_chromatogram_interval", decoded.chromatogram_interval_ms, "ms"),
            ("raw_signal_export_status", "not_exported_result_only", None),
            ("raw_signal_pairing_status", "not_required_result_only", None),
        )
        metadata = tuple(
            MetadataEntry(sample_id, safe_source, _NAMESPACE, key, value, unit)
            for key, value, unit in values
        )
        warning = Issue(
            "SHIMADZU_RESULT_ASCII_EXPERIMENTAL_PROFILE",
            "Peak results are limited to the exact LabSolutions 5.82 GC-2014 single "
            "SFID1/Ch1 profile; area and height units remain unresolved.",
            Severity.WARNING,
            safe_source,
        )
        return DatasetBundle(
            (source,),
            (sample,),
            peaks=peaks,
            metadata=metadata,
            warnings=(warning,),
        )
