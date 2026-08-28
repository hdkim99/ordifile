# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental Agilent ChemStation ``.CH`` internal version 179 signal reader."""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from ordifile.adapters._agilent_ch_v179_records import (
    EXPECTED_VERSION,
    read_v179_signal,
    retention_times,
    scaled_responses,
)
from ordifile.adapters._agilent_ch_v181_records import (
    HEADER_BYTES,
    ChV181StructureError,
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
_NAMESPACE = "adapter:agilent_chemstation_ch_v179"

# Only the response unit observed in the validated corpus is promoted to a physical unit.
OBSERVED_RESPONSE_UNITS = frozenset({"pA"})


def _safe_text(value: str) -> str | None:
    if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    return value


def _sample_text(value: str) -> str | None:
    safe = _safe_text(value)
    if safe is None or safe.isspace():
        return None
    return safe


def _parse_error(error: ChV181StructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class AgilentChemStationChV179Adapter:
    """Expose the v179 signal with a file-derived retention axis."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "agilent_chemstation_ch_v179"
    adapter_version: ClassVar[str] = "0.1.0"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "Agilent ChemStation .CH v179 GC-FID signal (Experimental)",
        (".ch",),
        True,
        False,
        True,
        True,
        SupportStatus.EXPERIMENTAL,
        (SeriesKind.SCIENTIFIC_SIGNAL,),
    )

    def probe(self, path: Path) -> DetectionResult:
        """Inspect the bounded shared header; the extension is supporting evidence only."""
        try:
            file_size = path.stat().st_size
            with path.open("rb") as stream:
                header_bytes = stream.read(HEADER_BYTES)
            parsed = parse_v181_header(header_bytes, file_size, expected_version=EXPECTED_VERSION)
        except ChV181StructureError as error:
            return DetectionResult(False, 0.0, error.message)
        except OSError as error:
            return DetectionResult(False, 0.0, f"read failed ({type(error).__name__})")
        if _FID_CHANNEL.fullmatch(path.stem) is None:
            return DetectionResult(
                True,
                0.70,
                "bounded v179 structure matched, but the basename does not identify the "
                "supported FID profile",
                routable=False,
                failure_code="AGILENT_CH_DETECTOR_UNSUPPORTED",
            )
        confidence = 0.99 if path.suffix.casefold() == ".ch" else 0.98
        return DetectionResult(
            True,
            confidence,
            f"bounded GC data header and internal version {parsed.version} matched",
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return the uncompressed v179 signal on its file-derived retention axis."""
        del options
        channel_match = _FID_CHANNEL.fullmatch(path.stem)
        if channel_match is None:
            raise ParseError(
                "AGILENT_CH_DETECTOR_UNSUPPORTED",
                "Experimental v179 decoding requires an unrenamed FID<module><channel> "
                "basename from the official ChemStation filename convention.",
                details={"basename": path.stem},
            )
        try:
            decoded = read_v179_signal(path)
            size = path.stat().st_size
        except ChV181StructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                f"Could not stat the input ({type(error).__name__}).",
            ) from error

        header = decoded.header
        shared = header.shared
        source = SourceFile(path, path.name, path.name, size, None, None, 0)
        sample_id = _sample_text(shared.sample_text) or path.stem
        channel = channel_match.group(0).upper()
        detector = "FID"
        resolved_unit = (
            header.response_unit if header.response_unit in OBSERVED_RESPONSE_UNITS else None
        )
        sample = SampleRecord(
            sample_id,
            source,
            acquired_at=None,
            acquired_at_reliable=False,
            instrument=InstrumentMetadata("GC", "Agilent"),
            channels=(channel,),
            detectors=(detector,),
            runtime=(header.end_ms - header.start_ms) / 60_000.0,
        )
        signal = SignalSeries(
            sample_id,
            path.name,
            channel,
            detector,
            retention_times(decoded),
            scaled_responses(decoded),
            x_label="retention_time",
            x_unit="min",
            y_label="detector_response",
            y_unit=resolved_unit,
            series_kind=SeriesKind.SCIENTIFIC_SIGNAL,
        )
        values: list[tuple[str, object, str | None]] = [
            ("support_status", "experimental", None),
            ("profile", "ChemStation .CH internal version 179 GC-FID signal", None),
            ("internal_version", shared.version, None),
            ("payload_offset", shared.payload_offset, None),
            ("point_count", decoded.point_count, None),
            ("sampling_step", decoded.step_ms, "ms"),
            ("run_start", header.start_ms, "ms"),
            ("run_end", header.end_ms, "ms"),
            ("stored_signal_maximum", header.stored_maximum, None),
            ("stored_response_scale", header.response_scale, None),
            ("stored_response_unit_lexeme", header.response_unit, None),
            ("response_unit_status", "observed" if resolved_unit else "unresolved", None),
            ("response_scale_status", "stored_supported_not_proven", None),
            ("acquisition_source_text", shared.acquisition_local_text, None),
            ("method_source_text", shared.method_text, None),
            ("software_source_text", shared.software_text, None),
        ]
        metadata = tuple(
            MetadataEntry(sample_id, path.name, _NAMESPACE, key, value, unit)
            for key, value, unit in values
        )
        warnings = [
            Issue(
                "AGILENT_CH_V179_EXPERIMENTAL_SIGNAL",
                "Retention time is constructed from the stored run boundaries and point "
                "count, validated against paired vendor report exports. The response uses "
                "the scale and unit lexeme stored in the same header; that scale is "
                "supported by the same evidence but is not proven exact, so a derived Area "
                "is not a vendor Result.",
                Severity.WARNING,
                path.name,
            ),
        ]
        if resolved_unit is None:
            warnings.append(
                Issue(
                    "AGILENT_CH_V179_RESPONSE_UNIT_UNRESOLVED",
                    "The stored response unit lexeme is outside the observed corpus, so the "
                    "numeric response is preserved without a physical unit.",
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
