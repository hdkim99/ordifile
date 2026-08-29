# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental Shimadzu LabSolutions-compatible ``.LCD`` TTFL multi-channel reader."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ordifile.adapters._shimadzu_labsolutions_lcd_binary import (
    CFB_MAGIC,
    ShimadzuLcdStructureError,
    read_lcd,
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

_NAMESPACE = "adapter:shimadzu_labsolutions_lcd"
_DETECTOR = "MS"


def _parse_error(error: ShimadzuLcdStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class ShimadzuLabsolutionsLcdAdapter:
    """Read the acquisition channels an ``.LCD`` document stores under ``TTFL Raw Data``."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "shimadzu_labsolutions_lcd"
    adapter_version: ClassVar[str] = "0.1.0"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "Shimadzu LabSolutions-compatible .LCD, TTFL multi-channel profile (Experimental)",
        (".lcd",),
        True,
        False,
        True,
        True,
        SupportStatus.EXPERIMENTAL,
        (SeriesKind.SCIENTIFIC_SIGNAL,),
    )

    def probe(self, path: Path) -> DetectionResult:
        """Match the exact extension, the CFB profile, and the TTFL stream identity."""
        if path.suffix.casefold() != ".lcd":
            return DetectionResult(False, 0.0, "the required .lcd extension is absent")
        try:
            with path.open("rb") as stream:
                recognized_container = stream.read(len(CFB_MAGIC)) == CFB_MAGIC
        except OSError:
            return DetectionResult(False, 0.0, "bounded header read failed")
        try:
            decoded = read_lcd(path)
        except ShimadzuLcdStructureError as error:
            if recognized_container and error.code in {
                "SHIMADZU_LCD_ARCHITECTURE_UNSUPPORTED",
                "SHIMADZU_LCD_PROFILE_UNSUPPORTED",
                "SHIMADZU_LCD_ARRAY_INVALID",
                "SHIMADZU_LCD_INDEX_INVALID",
                "SHIMADZU_LCD_CHANNEL_INVALID",
                "SHIMADZU_LCD_TRUNCATED",
            }:
                return DetectionResult(
                    True,
                    0.70,
                    error.message,
                    routable=False,
                    failure_code=error.code,
                )
            return DetectionResult(False, 0.0, error.message)
        del recognized_container
        return DetectionResult(
            True,
            0.99,
            f"bounded CFB container, File Property {decoded.file_schema}, and "
            f"{len(decoded.channels)} validated TTFL channel(s) over "
            f"{decoded.scan_count} scans matched",
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return one uninterpolated series per populated acquisition channel."""
        del options
        if path.suffix.casefold() != ".lcd":
            raise ParseError(
                "SHIMADZU_LCD_EXTENSION_INVALID",
                "The experimental profile requires a .lcd source extension.",
            )
        try:
            decoded = read_lcd(path)
            size = path.stat().st_size
        except ShimadzuLcdStructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                f"Could not stat the input ({type(error).__name__}).",
            ) from error

        sample_id = path.stem
        source = SourceFile(path, path.name, path.name, size, None, None, 0)
        channel_names = tuple(f"TIC Data {channel.slot}" for channel in decoded.channels)
        sample = SampleRecord(
            sample_id,
            source,
            acquired_at=None,
            acquired_at_reliable=False,
            instrument=InstrumentMetadata(_DETECTOR, "Shimadzu"),
            channels=channel_names,
            detectors=(_DETECTOR,),
            runtime=None,
        )
        signals = tuple(
            SignalSeries(
                sample_id,
                path.name,
                name,
                _DETECTOR,
                channel.retention_times_min,
                channel.intensities,
                x_label="retention_time",
                x_unit="min",
                y_label="raw_tic_intensity",
                y_unit=None,
                series_kind=SeriesKind.SCIENTIFIC_SIGNAL,
            )
            for name, channel in zip(channel_names, decoded.channels, strict=True)
        )

        values: list[tuple[str, object, str | None]] = [
            ("support_status", "experimental", None),
            ("profile", "LabSolutions LCD TTFL multi-channel profile", None),
            ("raw_data_architecture", "TTFL", None),
            ("file_property_schema", decoded.file_schema, None),
            ("file_property_stream_sha256", decoded.file_property_stream_sha256, None),
            ("scan_count", decoded.scan_count, None),
            ("retention_time_start", decoded.rt_start_ms, "ms"),
            ("retention_time_end", decoded.rt_end_ms, "ms"),
            ("retention_time_interval_min", decoded.rt_interval_min_ms, "ms"),
            ("retention_time_interval_max", decoded.rt_interval_max_ms, "ms"),
            (
                "retention_time_grid_uniform",
                decoded.rt_interval_min_ms == decoded.rt_interval_max_ms,
                None,
            ),
            ("retention_time_stream_sha256", decoded.retention_time_stream_sha256, None),
            ("data_index_record_count", decoded.index_record_count, None),
            ("data_index_stream_sha256", decoded.data_index_stream_sha256, None),
            ("ms_raw_stream_bytes", decoded.ms_raw_stream_bytes, "bytes"),
            ("channel_count", len(decoded.channels), None),
            ("tic_signal_unit_status", "unknown", None),
            ("ms1_export_status", "unsupported", None),
            ("timestamp_status", "unsupported_timezone_unresolved", None),
        ]
        for channel in decoded.channels:
            prefix = f"channel_{channel.slot}"
            values.extend(
                [
                    (f"{prefix}_stored_scan_count", channel.stored_scan_count, None),
                    (f"{prefix}_first_scan_index", channel.first_scan_index, None),
                    (f"{prefix}_stored_spectrum_count", channel.spectrum_count, None),
                ]
            )
        metadata = tuple(
            MetadataEntry(sample_id, path.name, _NAMESPACE, key, value, unit)
            for key, value, unit in values
        )
        warnings: tuple[Issue, ...] = (
            Issue(
                "SHIMADZU_LCD_EXPERIMENTAL_PROFILE",
                "LCD support is limited to the evidence-backed TTFL multi-channel profile; "
                "the TLM raw-data architecture and other LCD generations are unsupported.",
                Severity.WARNING,
                path.name,
            ),
            Issue(
                "SHIMADZU_LCD_SIGNAL_UNIT_UNKNOWN",
                "The stored intensity has no recorded physical unit, so the series is "
                "preserved without one.",
                Severity.WARNING,
                path.name,
            ),
            Issue(
                "SHIMADZU_LCD_MS1_NOT_EXPORTED",
                "MS spectra are indexed by the reader but are not materialized or "
                "exported by this profile.",
                Severity.WARNING,
                path.name,
            ),
        )
        if any(channel.spectrum_count < channel.stored_scan_count for channel in decoded.channels):
            warnings += (
                Issue(
                    "SHIMADZU_LCD_SPARSE_CHANNEL",
                    "At least one channel is sampled sparsely across its retention window; "
                    "scans it did not acquire are preserved as stored zero intensities, "
                    "not interpolated.",
                    Severity.WARNING,
                    path.name,
                ),
            )
        return DatasetBundle(
            (source,),
            (sample,),
            signals=signals,
            metadata=metadata,
            warnings=warnings,
        )
