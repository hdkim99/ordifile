# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental adapter for one owner-provenance YL-Clarity Result Table profile."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ordifile.adapters._youngin_yl_clarity_result_csv import (
    YoungInResultCsvStructureError,
    has_result_csv_family_identity,
    read_result_csv,
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

_NAMESPACE = "adapter:youngin_yl_clarity_result_csv"


def _parse_error(error: YoungInResultCsvStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


def _channel(signal_number: int, signal_name: str) -> str:
    """Preserve source signal identity without asserting detector semantics."""
    return f"Signal {signal_number}: {signal_name}"


class YoungInYlClarityResultCsvAdapter:
    """Read exact source-order peaks from two owner-validated export variants."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "youngin_yl_clarity_result_csv"
    adapter_version: ClassVar[str] = "0.1.1"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "YoungIn YL-Clarity Result Table CSV, observed CP949/tab profile (Experimental)",
        (".csv",),
        True,
        True,
        False,
        True,
        SupportStatus.EXPERIMENTAL,
        (),
        SourceIdentityPolicy.SHA256_ALIAS,
    )

    def probe(self, path: Path) -> DetectionResult:
        """Require bounded family structure, then validate the complete exact profile."""
        if not has_result_csv_family_identity(path):
            return DetectionResult(False, 0.0, "bounded Result Table markers are absent")
        try:
            read_result_csv(path)
        except YoungInResultCsvStructureError as error:
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
            "exact owner-provenance YL-Clarity CP949/tab Result Table profile matched",
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return only allowlisted peaks; private trailer values remain unexposed."""
        del options
        try:
            decoded = read_result_csv(path)
        except YoungInResultCsvStructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                "The Result Table input could not be read.",
            ) from error

        source_sha256 = decoded.source_sha256
        sample_id = f"YOUNGIN_RESULT_{source_sha256[:16]}"
        safe_source = f"{sample_id}.csv"
        source = SourceFile(
            path,
            safe_source,
            safe_source,
            decoded.source_size,
            source_sha256,
            None,
            0,
        )
        channels = tuple(
            _channel(signal.signal_number, signal.signal_name) for signal in decoded.signals
        )
        sample = SampleRecord(
            sample_id,
            source,
            instrument=InstrumentMetadata(None, "YoungIn"),
            channels=channels,
            detectors=(),
        )
        peaks = tuple(
            PeakRecord(
                sample_id,
                safe_source,
                channel=_channel(peak.signal_number, peak.signal_name),
                detector=None,
                peak_number=peak.peak_number,
                retention_time=peak.retention_time,
                retention_time_unit="min",
                area=peak.area,
                height=peak.height,
                compound=None,
                compound_source=None,
                status="experimental",
                observation_order=peak.observation_order,
                start_time=None,
                end_time=None,
                area_unit="mV.s",
                height_unit="mV",
            )
            for peak in decoded.peaks
        )
        values: list[tuple[str, object, str | None]] = [
            ("support_status", "experimental", None),
            (
                "profile",
                "owner-provenance YL-Clarity CP949-compatible tab-delimited Result Table",
                None,
            ),
            ("representation", "signal_section_peak_result_table_source_order", None),
            ("encoding", "CP949-compatible; exact declaration absent", None),
            ("delimiter", "tab", None),
            ("line_endings", "CRLF", None),
            ("producer_marker_status", "not_present_in_export_bytes", None),
            ("software_version_marker_status", "not_present_in_export_bytes", None),
            ("result_section_count", len(decoded.signals), None),
            ("peak_count", len(decoded.peaks), None),
            ("retention_time_unit", "min", None),
            ("area_unit", "mV.s", None),
            ("height_unit", "mV", None),
            ("detector_identification_status", "unresolved_signal_name_only", None),
            ("compound_identification_status", "not_present", None),
            ("integration_boundary_status", "not_present", None),
            ("area_percent_status", "validated_not_exported", None),
            ("height_percent_status", "validated_not_exported", None),
            ("width_05_status", "validated_not_mapped_to_integration_boundaries", None),
            ("total_row_status", "validated_not_exported_as_peak", None),
            ("private_trailer_status", "shape_validated_values_excluded", None),
            ("raw_result_pairing_status", "not_required_result_only", None),
        ]
        for signal in decoded.signals:
            prefix = f"source_signal_{signal.signal_number}"
            values.extend(
                (
                    (f"{prefix}_number", signal.signal_number, None),
                    (f"{prefix}_name", signal.signal_name, None),
                    (f"{prefix}_channel", _channel(signal.signal_number, signal.signal_name), None),
                    (f"{prefix}_peak_count", len(signal.peaks), None),
                    (
                        f"{prefix}_status",
                        "no_peaks_reported" if signal.no_peaks_reported else "peaks_reported",
                        None,
                    ),
                )
            )
        metadata = tuple(
            MetadataEntry(sample_id, safe_source, _NAMESPACE, key, value, unit)
            for key, value, unit in values
        )
        warning = Issue(
            "YOUNGIN_RESULT_CSV_EXPERIMENTAL_PROFILE",
            "Peak results are limited to the two owner-validated CP949/tab Result Table "
            "section variants; the export bytes do not identify the OEM product or version, "
            "and Signal Name is not asserted as detector identity.",
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
