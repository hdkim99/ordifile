# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental Shimadzu GCsolution-compatible ``.GCD`` chromatogram reader."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import ClassVar

from ordifile.adapters._shimadzu_gcsolution_gcd_binary import (
    CFB_MAGIC,
    ShimadzuGcdStructureError,
    has_gcd_stream_identity,
    read_gcd,
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

_NAMESPACE = "adapter:shimadzu_gcsolution_gcd"


def _parse_error(error: ShimadzuGcdStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


def _canonical_signal_hashes(
    x_values: tuple[float, ...], y_values: tuple[float, ...]
) -> tuple[str, str, str]:
    time_digest = hashlib.sha256()
    signal_digest = hashlib.sha256()
    pair_digest = hashlib.sha256()
    for x_value, y_value in zip(x_values, y_values, strict=True):
        x_bytes = struct.pack(">d", x_value)
        y_bytes = struct.pack(">d", y_value)
        time_digest.update(x_bytes)
        signal_digest.update(y_bytes)
        pair_digest.update(x_bytes)
        pair_digest.update(y_bytes)
    return time_digest.hexdigest(), signal_digest.hexdigest(), pair_digest.hexdigest()


class ShimadzuGcsolutionGcdAdapter:
    """Read one exact LabSolutions 5.82, single-channel GC-FID GCD profile."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "shimadzu_gcsolution_gcd"
    adapter_version: ClassVar[str] = "0.2.1"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "Shimadzu GCsolution-compatible .GCD, LabSolutions 5.82 FID profile (Experimental)",
        (".gcd",),
        True,
        False,
        True,
        True,
        SupportStatus.EXPERIMENTAL,
        (SeriesKind.SCIENTIFIC_SIGNAL,),
    )

    def probe(self, path: Path) -> DetectionResult:
        """Match the exact extension, CFB boundary, producer, and FID signal profile."""
        if path.suffix.casefold() != ".gcd":
            return DetectionResult(False, 0.0, "the required .gcd extension is absent")
        try:
            with path.open("rb") as stream:
                recognized_container = stream.read(len(CFB_MAGIC)) == CFB_MAGIC
        except OSError:
            return DetectionResult(False, 0.0, "bounded header read failed")
        try:
            parsed = read_gcd(path, decode_signal=False)
        except ShimadzuGcdStructureError as error:
            if (
                recognized_container
                and has_gcd_stream_identity(path)
                and error.code
                in {
                    "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
                    "SHIMADZU_GCD_SIGNAL_BLOCK_INVALID",
                    "SHIMADZU_GCD_TRUNCATED",
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
            "bounded CFB v4 container, LabSolutions "
            f"{parsed.profile.software_version}, and single-channel FID profile matched",
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return the uninterpolated, scaled-as-stored FID chromatogram."""
        del options
        if path.suffix.casefold() != ".gcd":
            raise ParseError(
                "SHIMADZU_GCD_EXTENSION_INVALID",
                "The exact experimental profile requires a .gcd source extension.",
            )
        try:
            decoded = read_gcd(path)
            size = path.stat().st_size
        except ShimadzuGcdStructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                f"Could not stat the input ({type(error).__name__}).",
            ) from error

        profile = decoded.profile
        source = SourceFile(path, path.name, path.name, size, None, None, 0)
        sample = SampleRecord(
            profile.sample_id,
            source,
            acquired_at=profile.acquired_at_utc,
            acquired_at_reliable=True,
            instrument=InstrumentMetadata("GC", "Shimadzu"),
            channels=(profile.channel,),
            detectors=(profile.detector,),
            runtime=profile.acquisition_time_ms / 60_000.0,
        )
        x_values = tuple(
            (profile.delay_ms + index * profile.interval_ms) / 60_000.0
            for index in range(decoded.point_count)
        )
        time_sha256, signal_sha256, pair_sha256 = _canonical_signal_hashes(x_values, decoded.values)
        signal = SignalSeries(
            profile.sample_id,
            path.name,
            profile.channel,
            profile.detector,
            x_values,
            decoded.values,
            x_label="retention_time",
            x_unit="min",
            y_label="detector_response",
            y_unit=profile.axis_unit,
            series_kind=SeriesKind.SCIENTIFIC_SIGNAL,
        )
        values: list[tuple[str, object, str | None]] = [
            ("support_status", "experimental", None),
            ("profile", "LabSolutions 5.82 single-channel GC-FID GCD", None),
            ("file_property_schema", profile.file_schema, None),
            ("software_version", profile.software_version, None),
            ("sample_name", profile.sample_name, None),
            ("sample_id", profile.sample_id, None),
            ("sample_name_bytes_hex", profile.sample_name_bytes_hex, None),
            ("sample_id_bytes_hex", profile.sample_id_bytes_hex, None),
            ("instrument_model", profile.instrument_model, None),
            ("point_count", decoded.point_count, None),
            ("sampling_interval", profile.interval_ms, "ms"),
            ("acquisition_time", profile.acquisition_time_ms, "ms"),
            ("initial_delay", profile.delay_ms, "ms"),
            ("axis_value_factor", profile.axis_value_factor, None),
            ("correction_factor", profile.correction_factor, None),
            ("gain_factor", profile.gain_factor, None),
            ("data_source_id", profile.data_source_id, None),
            ("data_source_name", profile.data_source_name, None),
            ("user_data_source_name", profile.user_data_source_name, None),
            ("file_property_prefix_hex", profile.file_property_prefix_hex, None),
            ("sample_filetime_low_raw", profile.sample_filetime_low_raw, None),
            ("sample_filetime_high_raw", profile.sample_filetime_high_raw, None),
            ("timestamp_status", "verified_utc_filetime", None),
            ("time_canonical_be_f64_sha256", time_sha256, None),
            ("signal_canonical_be_f64_sha256", signal_sha256, None),
            ("time_signal_pairs_be_f64_sha256", pair_sha256, None),
        ]
        if profile.operator_name is not None:
            values.append(("operator_name", profile.operator_name, None))
        if profile.operator_name_bytes_hex is not None:
            values.append(("operator_name_bytes_hex", profile.operator_name_bytes_hex, None))
        if profile.injection_volume_raw is not None:
            values.append(("injection_volume_source_token", profile.injection_volume_raw, None))
        if profile.system_datetime_filetime_raw is not None:
            values.append(
                ("system_datetime_filetime_raw", profile.system_datetime_filetime_raw, None)
            )
        if profile.system_datetime_bias_minutes_raw is not None:
            values.append(
                (
                    "system_datetime_bias_minutes_raw",
                    profile.system_datetime_bias_minutes_raw,
                    None,
                )
            )
        metadata = tuple(
            MetadataEntry(profile.sample_id, path.name, _NAMESPACE, key, value, unit)
            for key, value, unit in values
        )
        warnings = (
            Issue(
                "SHIMADZU_GCD_EXPERIMENTAL_PROFILE",
                "The chromatogram is limited to the exact LabSolutions 5.82 single-channel "
                "FID profile; other GCD generations and detector profiles are unsupported.",
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
