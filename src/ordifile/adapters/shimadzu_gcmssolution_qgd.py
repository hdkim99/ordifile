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
    SampleRecord,
    SeriesKind,
    Severity,
    SignalSeries,
    SourceFile,
)

_NAMESPACE = "adapter:shimadzu_gcmssolution_qgd"


def _parse_error(error: ShimadzuQgdStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class ShimadzuGcmssolutionQgdAdapter:
    """Read TIC from the exact evidence-backed QGD 4.00 Stage A profile."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "shimadzu_gcmssolution_qgd"
    adapter_version: ClassVar[str] = "0.1.1"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "Shimadzu GCMSsolution-compatible .QGD 4.00 TIC profile (Experimental)",
        (".qgd",),
        True,
        False,
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
        values: list[tuple[str, object, str | None]] = [
            ("support_status", "experimental", None),
            ("profile", "QGD File Property 4.00 exact TIC profile", None),
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
            ("spectrum_index_stream_sha256", decoded.spectrum_index_stream_sha256, None),
            (
                "spectrum_index_canonical_be_u32_sha256",
                decoded.spectrum_index_canonical_be_u32_sha256,
                None,
            ),
            ("tic_signal_unit_status", "unknown", None),
            ("ms1_export_status", "unsupported", None),
            ("timestamp_status", "unsupported_timezone_unresolved", None),
        ]
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
        warnings = (
            Issue(
                "SHIMADZU_QGD_EXPERIMENTAL_PROFILE",
                "TIC support is limited to the exact evidence-backed QGD 4.00 profile; "
                "other QGD generations and acquisition profiles are unsupported.",
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
        return DatasetBundle(
            (source,),
            (sample,),
            signals=(signal,),
            metadata=metadata,
            warnings=warnings,
        )
