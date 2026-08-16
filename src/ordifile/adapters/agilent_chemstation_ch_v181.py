# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental structural decoder for Agilent ChemStation ``.CH`` v181."""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from ordifile.adapters._agilent_ch_v181_records import (
    HEADER_BYTES,
    ChV181StructureError,
    decode_v181_records,
    parse_v181_header,
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

_FID_CHANNEL = re.compile(r"FID[0-9]+[A-Z]\Z", re.IGNORECASE)
_NAMESPACE = "adapter:agilent_chemstation_ch_v181"


def _safe_source_text(value: str) -> str | None:
    """Return exact workbook-safe source text without trimming or normalization."""
    if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    return value


def _safe_sample_text(value: str) -> str | None:
    """Return an exact nonblank sample identifier or request a filename fallback."""
    safe_value = _safe_source_text(value)
    if safe_value is None or safe_value.isspace():
        return None
    return safe_value


def _parse_error(error: ChV181StructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class AgilentChemStationChV181Adapter:
    """Expose v181 structural decoded records without scientific reinterpretation."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "agilent_chemstation_ch_v181"
    adapter_version: ClassVar[str] = "0.2.0"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "Agilent ChemStation .CH v181 decoded records (Experimental)",
        (".ch",),
        True,
        False,
        True,
        True,
        SupportStatus.EXPERIMENTAL,
    )

    def probe(self, path: Path) -> DetectionResult:
        """Inspect the bounded v181 header; the extension is supporting evidence only."""
        try:
            file_size = path.stat().st_size
            with path.open("rb") as stream:
                header = stream.read(HEADER_BYTES)
            parsed = parse_v181_header(header, file_size)
        except ChV181StructureError as error:
            family_marker = "GC DATA FILE".encode("utf-16-le")
            family_recognized = (
                len(header) >= HEADER_BYTES
                and header[348 : 348 + len(family_marker)] == family_marker
            )
            recognized = error.code in {
                "AGILENT_CH_VERSION_UNSUPPORTED",
                "AGILENT_CH_VERSION_CONFLICT",
                "AGILENT_CH_PAYLOAD_MISSING",
                "AGILENT_CH_PAYLOAD_OFFSET_INVALID",
            }
            if recognized and family_recognized and path.suffix.casefold() == ".ch":
                return DetectionResult(True, 0.70, error.message)
            return DetectionResult(False, 0.0, error.message)
        except OSError as error:
            return DetectionResult(False, 0.0, f"read failed ({type(error).__name__})")
        if _FID_CHANNEL.fullmatch(path.stem) is None:
            return DetectionResult(
                True,
                0.70,
                "bounded v181 structure matched, but the basename does not identify the "
                "supported FID profile",
            )
        confidence = 0.99 if path.suffix.casefold() == ".ch" else 0.98
        return DetectionResult(
            True,
            confidence,
            f"bounded GC data header and internal version {parsed.version} matched"
            + ("; extension is consistent" if path.suffix.casefold() == ".ch" else ""),
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return every decoded record with ordinal x and unscaled integer y."""
        del options
        channel_match = _FID_CHANNEL.fullmatch(path.stem)
        if channel_match is None:
            raise ParseError(
                "AGILENT_CH_DETECTOR_UNSUPPORTED",
                "Experimental v181 decoding requires an unrenamed FID<module><channel> "
                "basename from the official ChemStation filename convention.",
                details={"basename": path.stem},
            )
        try:
            decoded = decode_v181_records(path)
            size = path.stat().st_size
        except ChV181StructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                f"Could not stat the input ({type(error).__name__}).",
            ) from error

        source = SourceFile(path, path.name, path.name, size, None, None, 0)
        header = decoded.header
        sample_id = _safe_sample_text(header.sample_text) or path.stem
        filename_channel = channel_match.group(0).upper()
        channel = filename_channel
        detector = "FID"
        sample = SampleRecord(
            sample_id,
            source,
            acquired_at=None,
            acquired_at_reliable=False,
            instrument=InstrumentMetadata("GC", "Agilent"),
            channels=(channel,) if channel else (),
            detectors=(detector,) if detector else (),
        )
        signal = SignalSeries(
            sample_id,
            path.name,
            channel,
            detector,
            tuple(range(len(decoded.values))),
            decoded.values,
            x_label="decoded_record_index",
            x_unit=None,
            y_label="decoded_raw_integer",
            y_unit=None,
            series_kind=SeriesKind.DECODED_RECORDS,
        )
        status_values: list[tuple[str, object]] = [
            ("support_status", "experimental"),
            ("representation", "decoded_records"),
            ("internal_version", header.version),
            ("payload_offset", header.payload_offset),
            ("decoded_record_count", len(decoded.values)),
            ("absolute_record_count", decoded.absolute_record_count),
            ("ordinary_record_count", decoded.ordinary_record_count),
            ("nonzero_ordinary_record_count", decoded.nonzero_ordinary_record_count),
            ("trailing_byte_count", decoded.trailing_byte_count),
            ("scientific_point_count_status", "unresolved"),
            (
                "ambiguous_final_zero_ordinary_record_included",
                decoded.final_zero_ordinary_record,
            ),
            ("retention_time_axis_status", "not_exposed"),
            ("physical_scaling_status", "not_applied"),
            ("signal_unit_status", "unresolved"),
            ("ordinary_recurrence_status", "experimental_candidate"),
            ("header_f32_0282_candidate_hex", header.header_f32_0282.hex()),
            ("header_f32_0286_candidate_hex", header.header_f32_0286.hex()),
            ("header_u16_4122_candidate", header.header_u16_4122),
            ("header_u16_4124_candidate", header.header_u16_4124),
            ("header_f64_4724_candidate_hex", header.header_f64_4724.hex()),
            ("header_f64_4732_candidate_hex", header.header_f64_4732.hex()),
        ]
        normalized_unit = _safe_source_text(header.raw_unit_lexeme.rstrip("\x00"))
        if normalized_unit is not None:
            status_values.append(("normalized_unit_lexeme_untrusted", normalized_unit))
        for key, value in (
            ("header_text_2492_candidate", header.header_text_2492),
            ("header_text_2533_candidate", header.header_text_2533),
            ("method_identifier", header.method_text),
            ("software_text", header.software_text),
            ("acquisition_local_text", header.acquisition_local_text),
        ):
            safe_value = _safe_source_text(value)
            if safe_value is not None:
                status_values.append((key, safe_value))
        status_values.extend(
            (f"{name}_bytes_hex", value) for name, value in header.raw_text_bytes_hex
        )
        status_values.extend(
            (f"{name}_bytes_hex", value) for name, value in header.raw_numeric_bytes_hex
        )
        metadata = tuple(
            MetadataEntry(sample_id, path.name, _NAMESPACE, key, value)
            for key, value in status_values
        )
        warnings = [
            Issue(
                "AGILENT_CH_V181_EXPERIMENTAL_RECORDS",
                "Experimental structural records were decoded without retention time, "
                "physical scaling, signal units, or scientific point classification.",
                Severity.WARNING,
                path.name,
            )
        ]
        if decoded.nonzero_ordinary_record_count:
            warnings.append(
                Issue(
                    "AGILENT_CH_V181_DELTA_RECURRENCE_UNVERIFIED",
                    "Nonzero relative-record recurrence is structurally decoded but lacks "
                    "validation against a real v181 fixture.",
                    Severity.WARNING,
                    path.name,
                )
            )
        if header.acquisition_local_text:
            warnings.append(
                Issue(
                    "AGILENT_CH_V181_TIMESTAMP_UNINTERPRETED",
                    "The local acquisition text has no verified century or timezone; it is "
                    "preserved as metadata and not mapped to acquired_at.",
                    Severity.WARNING,
                    path.name,
                )
            )
        if header.sample_text and _safe_sample_text(header.sample_text) is None:
            warnings.append(
                Issue(
                    "AGILENT_CH_V181_SAMPLE_TEXT_UNSAFE",
                    "The embedded sample text is blank or contains unsupported control "
                    "characters; the filename stem is used and exact source bytes remain in "
                    "Metadata.",
                    Severity.WARNING,
                    path.name,
                )
            )
        return DatasetBundle(
            (source,),
            (sample,),
            signals=(signal,),
            metadata=metadata,
            warnings=tuple(warnings),
        )
