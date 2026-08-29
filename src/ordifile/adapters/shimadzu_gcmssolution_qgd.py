# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental Shimadzu GCMSsolution-compatible ``.QGD`` TIC reader."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ordifile.adapters._shimadzu_gcmssolution_qgd_binary import (
    CFB_MAGIC,
    ShimadzuQgdStructureError,
    has_qgd_stream_identity,
    read_qgd,
)
from ordifile.adapters._shimadzu_gcmssolution_qgd_peak_table import decode_mc_peak_table
from ordifile.adapters.base import (
    AdapterDescriptor,
    DetectionResult,
    ParseOptions,
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

_NAMESPACE = "adapter:shimadzu_gcmssolution_qgd"
_COMPOUND_SOURCE = "source_file:shimadzu_gcmssolution_qgd.mc_peak_table.name"


def _parse_error(error: ShimadzuQgdStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class ShimadzuGcmssolutionQgdAdapter:
    """Read TIC and the stored peak table from the evidence-backed QGD 4.00 profile."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "shimadzu_gcmssolution_qgd"
    adapter_version: ClassVar[str] = "0.1.1"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "Shimadzu GCMSsolution-compatible .QGD 4.00 TIC and stored peak table (Experimental)",
        (".qgd",),
        True,
        True,
        True,
        True,
        SupportStatus.EXPERIMENTAL,
        (SeriesKind.SCIENTIFIC_SIGNAL,),
    )

    def probe(self, path: Path) -> DetectionResult:
        """Match the exact extension, CFB profile, stream identity, and TIC arrays."""
        if path.suffix.casefold() != ".qgd":
            return DetectionResult(False, 0.0, "the required .qgd extension is absent")
        try:
            with path.open("rb") as stream:
                recognized_container = stream.read(len(CFB_MAGIC)) == CFB_MAGIC
        except OSError:
            return DetectionResult(False, 0.0, "bounded header read failed")
        try:
            parsed = read_qgd(path, validate_ms1=False)
        except ShimadzuQgdStructureError as error:
            if (
                recognized_container
                and has_qgd_stream_identity(path)
                and error.code
                in {
                    "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
                    "SHIMADZU_QGD_ARRAY_INVALID",
                    "SHIMADZU_QGD_MS1_INVALID",
                    "SHIMADZU_QGD_TRUNCATED",
                }
            ):
                return DetectionResult(
                    True,
                    0.70,
                    error.message,
                    routable=False,
                    failure_code=error.code,
                )
            return DetectionResult(False, 0.0, error.message)
        return DetectionResult(
            True,
            0.99,
            "bounded CFB v4 container, File Property "
            f"{parsed.profile.file_schema}, and exact {parsed.profile.scan_count}-scan "
            "TIC profile matched",
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return the uninterpolated TIC and a bounded MS1 structural summary."""
        del options
        if path.suffix.casefold() != ".qgd":
            raise ParseError(
                "SHIMADZU_QGD_EXTENSION_INVALID",
                "The exact experimental profile requires a .qgd source extension.",
            )
        try:
            decoded = read_qgd(path)
            size = path.stat().st_size
        except ShimadzuQgdStructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                f"Could not stat the input ({type(error).__name__}).",
            ) from error

        profile = decoded.profile
        peak_table = decode_mc_peak_table(
            decoded.mc_peak_table_payload, decoded.mc_peak_info_payload
        )
        sample_id = path.stem
        source = SourceFile(path, path.name, path.name, size, None, None, 0)
        sample = SampleRecord(
            sample_id,
            source,
            acquired_at=None,
            acquired_at_reliable=False,
            instrument=InstrumentMetadata("MS", "Shimadzu"),
            channels=(profile.channel,),
            detectors=(profile.detector,),
            runtime=None,
        )
        signal = SignalSeries(
            sample_id,
            path.name,
            profile.channel,
            profile.detector,
            decoded.retention_times_min,
            decoded.tic_values,
            x_label="retention_time",
            x_unit="min",
            y_label="raw_tic_intensity",
            y_unit=None,
            series_kind=SeriesKind.SCIENTIFIC_SIGNAL,
        )
        peaks = tuple(
            PeakRecord(
                sample_id,
                path.name,
                channel=profile.channel,
                detector=profile.detector,
                peak_number=number,
                retention_time=peak.retention_time,
                retention_time_unit="min",
                area=peak.area,
                height=peak.height,
                compound=peak.compound,
                compound_source=_COMPOUND_SOURCE if peak.compound is not None else None,
                status="parsed",
                observation_order=number,
                start_time=peak.start_time,
                end_time=peak.end_time,
                area_unit=None,
                height_unit=None,
            )
            for number, peak in enumerate(peak_table.peaks, start=1)
        )
        values: list[tuple[str, object, str | None]] = [
            ("support_status", "experimental", None),
            ("profile", "QGD File Property 4.00 TIC profile", None),
            ("file_property_schema", profile.file_schema, None),
            ("file_property_stream_bytes", decoded.file_property_stream_bytes, "bytes"),
            ("file_property_stream_sha256", decoded.file_property_stream_sha256, None),
            ("scan_count", profile.scan_count, None),
            ("retention_time_start", profile.rt_start_ms, "ms"),
            ("retention_time_end", profile.rt_end_ms, "ms"),
            ("retention_time_interval", profile.rt_interval_ms, "ms"),
            ("retention_time_stream_sha256", decoded.retention_time_stream_sha256, None),
            (
                "retention_time_canonical_be_u32_sha256",
                decoded.retention_time_canonical_be_u32_sha256,
                None,
            ),
            (
                "retention_time_canonical_be_f64_sha256",
                decoded.retention_time_canonical_be_f64_sha256,
                None,
            ),
            ("tic_stream_sha256", decoded.tic_stream_sha256, None),
            ("tic_canonical_be_u64_sha256", decoded.tic_canonical_be_u64_sha256, None),
            (
                "retention_time_tic_pairs_be_f64_u64_sha256",
                decoded.retention_time_tic_pairs_be_f64_u64_sha256,
                None,
            ),
            ("spectrum_index_offset_width", profile.spectrum_index_offset_width, "bytes"),
            ("spectrum_index_stream_sha256", decoded.spectrum_index_stream_sha256, None),
            (
                "spectrum_index_canonical_be_u32_sha256",
                decoded.spectrum_index_canonical_be_u32_sha256,
                None,
            ),
            ("tic_signal_unit_status", "unknown", None),
            ("stored_peak_table_status", peak_table.status, None),
            ("stored_peak_count", len(peak_table.peaks), None),
            ("stored_peak_area_percent_consistent", peak_table.area_percent_consistent, None),
            ("stored_peak_value_validation", "internal_only_no_vendor_export", None),
            ("stored_peak_undecodable_name_count", peak_table.undecodable_name_count, None),
            ("ms1_export_status", "unsupported", None),
            ("timestamp_status", "unsupported_timezone_unresolved", None),
        ]
        if peak_table.declared_count is not None:
            values.append(("stored_peak_declared_count", peak_table.declared_count, None))
        if decoded.ms1_summary is not None:
            summary = decoded.ms1_summary
            values.extend(
                [
                    ("ms1_present", True, None),
                    ("ms1_stream_bytes", summary.stream_bytes, "bytes"),
                    ("ms1_long_row_count", summary.long_row_count, None),
                    ("ms1_points_per_scan_min", summary.points_per_scan_min, None),
                    ("ms1_points_per_scan_max", summary.points_per_scan_max, None),
                    (
                        "ms1_intensity_widths_bytes",
                        ",".join(str(value) for value in summary.intensity_widths),
                        None,
                    ),
                    ("ms1_mass_raw_min", summary.mass_raw_min, None),
                    ("ms1_mass_raw_max", summary.mass_raw_max, None),
                    ("ms1_intensity_raw_min", summary.intensity_raw_min, None),
                    ("ms1_intensity_raw_max", summary.intensity_raw_max, None),
                    ("ms1_stream_sha256", summary.stream_sha256, None),
                    ("ms1_scan_summary_sha256", summary.scan_summary_sha256, None),
                ]
            )
        metadata = tuple(
            MetadataEntry(sample_id, path.name, _NAMESPACE, key, value, unit)
            for key, value, unit in values
        )
        warnings: tuple[Issue, ...] = (
            Issue(
                "SHIMADZU_QGD_EXPERIMENTAL_PROFILE",
                "TIC support is limited to the evidence-backed QGD File Property 4.00 "
                "profile with a uniform scan grid; other QGD generations are unsupported.",
                Severity.WARNING,
                path.name,
            ),
            Issue(
                "QGD_MS1_NOT_EXPORTED",
                "MS1 records were structurally validated but are not materialized or exported "
                "by the Stage A adapter.",
                Severity.WARNING,
                path.name,
            ),
        )
        if peaks:
            warnings += (
                Issue(
                    "SHIMADZU_QGD_STORED_PEAK_TABLE_UNVALIDATED",
                    "Peaks are the stored vendor rows from GCMS Data Processing/MC Peak "
                    "Table; Ordifile did not integrate the signal. The field meanings were "
                    "established only against the same file's own TIC, because no Shimadzu "
                    "GCMSsolution export of any fixture carrying a populated table is "
                    "available. These values have not been compared against a vendor "
                    "report and may not reproduce one.",
                    Severity.WARNING,
                    path.name,
                ),
            )
            if peak_table.undecodable_name_count:
                warnings += (
                    Issue(
                        "SHIMADZU_QGD_PEAK_NAME_UNDECODABLE",
                        "One or more stored compound names are not ASCII and the document "
                        "does not record their code page, so those names were omitted "
                        "rather than guessed.",
                        Severity.WARNING,
                        path.name,
                    ),
                )
            if not peak_table.area_percent_consistent:
                warnings += (
                    Issue(
                        "SHIMADZU_QGD_PEAK_AREA_PERCENT_INCONSISTENT",
                        "The stored Area percentages are not a normalisation of the stored "
                        "Area column, so the Area field meaning is not corroborated for "
                        "this file.",
                        Severity.WARNING,
                        path.name,
                    ),
                )
        elif peak_table.status == "invalid":
            warnings += (
                Issue(
                    peak_table.issue_code or "SHIMADZU_QGD_PEAK_TABLE_UNAVAILABLE",
                    peak_table.issue_message
                    or "The stored peak table is outside the validated bounded layout; "
                    "the scientific TIC was preserved without Peaks.",
                    Severity.WARNING,
                    path.name,
                ),
            )
        return DatasetBundle(
            (source,),
            (sample,),
            signals=(signal,),
            peaks=peaks,
            metadata=metadata,
            warnings=warnings,
        )
