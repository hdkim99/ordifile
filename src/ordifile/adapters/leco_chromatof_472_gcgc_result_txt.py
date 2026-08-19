# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental adapter for one exact ChromaTOF 4.72 GCxGC Result profile."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ordifile.adapters._leco_chromatof_472_gcgc_result_txt import (
    LecoGcgcResultStructureError,
    has_gcgc_result_family_identity,
    read_gcgc_result,
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

_NAMESPACE = "adapter:leco_chromatof_gcxgc_result_txt"
_COMPOUND_SOURCE = "canonical:leco_chromatof_gcxgc_result_txt.name"
_UNKNOWN_COMPOUND_SENTINEL = "unknown"


def _parse_error(error: LecoGcgcResultStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class LecoChromatof472GcgcResultTxtAdapter:
    """Read explicit RT1/RT2/area/height rows from the exact observed profile."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "leco_chromatof_gcxgc_result_txt"
    adapter_version: ClassVar[str] = "0.1.0"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "LECO ChromaTOF 4.72 GCxGC Result text profile (Experimental)",
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
        """Require .txt, bounded family identity, and then the complete exact grammar."""
        if path.suffix.casefold() != ".txt":
            return DetectionResult(False, 0.0, "the required .txt extension is absent")
        if not has_gcgc_result_family_identity(path):
            return DetectionResult(False, 0.0, "bounded GCxGC Result markers are absent")
        try:
            read_gcgc_result(path)
        except LecoGcgcResultStructureError as error:
            return DetectionResult(True, 0.70, error.message)
        return DetectionResult(
            True,
            0.99,
            "exact externally evidenced ChromaTOF 4.72 GCxGC Result profile matched",
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Map explicit source rows without deriving or normalizing scientific values."""
        del options
        if path.suffix.casefold() != ".txt":
            raise ParseError(
                "LECO_GCGC_RESULT_EXTENSION_INVALID",
                "The exact experimental profile requires a .txt source extension.",
            )
        try:
            decoded = read_gcgc_result(path)
        except LecoGcgcResultStructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                "The GCxGC result input could not be read.",
            ) from error

        sample_id = f"LECO_GCGC_{decoded.source_sha256[:16]}"
        safe_source = f"{sample_id}.txt"
        source = SourceFile(
            path,
            safe_source,
            safe_source,
            decoded.source_size,
            decoded.source_sha256,
            None,
            0,
        )
        sample = SampleRecord(
            sample_id,
            source,
            instrument=InstrumentMetadata("GCxGC", "LECO"),
            channels=(),
            detectors=(),
        )
        peaks = tuple(
            PeakRecord(
                sample_id,
                safe_source,
                channel=None,
                detector=None,
                peak_number=None,
                retention_time=peak.retention_time,
                retention_time_unit="s",
                area=peak.area,
                height=peak.height,
                compound=(
                    None if peak.name.casefold() == _UNKNOWN_COMPOUND_SENTINEL else peak.name
                ),
                compound_source=(
                    None if peak.name.casefold() == _UNKNOWN_COMPOUND_SENTINEL else _COMPOUND_SOURCE
                ),
                status="experimental",
                observation_order=peak.observation_order,
                start_time=None,
                end_time=None,
                area_unit="AU",
                height_unit="AU",
                secondary_retention_time=peak.secondary_retention_time,
                secondary_retention_time_unit="s",
            )
            for peak in decoded.peaks
        )
        profile_values: tuple[tuple[str, object, str | None], ...] = (
            ("support_status", "experimental", None),
            ("profile", "ChromaTOF 4.72.0.0 GCxGC observed Result text", None),
            ("profile_version_provenance", "external_dataset_not_embedded", None),
            ("representation", "gcgc_peak_table_source_order", None),
            ("encoding", "7-bit ASCII", None),
            ("delimiter", "tab", None),
            ("line_endings", "CRLF", None),
            ("peak_count", len(decoded.peaks), None),
            ("primary_retention_time_unit", "s", None),
            ("secondary_retention_time_unit", "s", None),
            ("area_unit", "AU", None),
            ("height_unit", "AU", None),
            ("detector_identification_status", "not_present", None),
            ("channel_identification_status", "not_present", None),
            ("peak_number_status", "not_present", None),
            ("compound_identity", "source_Name_NIST_library_assignment_or_unknown", None),
            ("raw_result_pairing_status", "not_required_result_only", None),
        )
        metadata = [
            MetadataEntry(sample_id, safe_source, _NAMESPACE, key, value, unit)
            for key, value, unit in profile_values
        ]
        for peak in decoded.peaks:
            prefix = f"peak_{peak.observation_order:06d}"
            metadata.extend(
                (
                    MetadataEntry(
                        sample_id,
                        safe_source,
                        _NAMESPACE,
                        f"{prefix}_name",
                        peak.name,
                        None,
                        f"table:row:{peak.source_row}:column:1",
                    ),
                    MetadataEntry(
                        sample_id,
                        safe_source,
                        _NAMESPACE,
                        f"{prefix}_spectra",
                        peak.spectra,
                        None,
                        f"table:row:{peak.source_row}:column:6",
                    ),
                    MetadataEntry(
                        sample_id,
                        safe_source,
                        _NAMESPACE,
                        f"{prefix}_wb1",
                        peak.wb1_text,
                        "s",
                        f"table:row:{peak.source_row}:column:7",
                    ),
                    MetadataEntry(
                        sample_id,
                        safe_source,
                        _NAMESPACE,
                        f"{prefix}_wb2",
                        peak.wb2_text,
                        "s",
                        f"table:row:{peak.source_row}:column:8",
                    ),
                    MetadataEntry(
                        sample_id,
                        safe_source,
                        _NAMESPACE,
                        f"{prefix}_retention_index",
                        peak.retention_index_text,
                        None,
                        f"table:row:{peak.source_row}:column:9",
                    ),
                )
            )
        warning = Issue(
            "LECO_CHROMATOF_GCGC_RESULT_EXPERIMENTAL_PROFILE",
            "Peak results are limited to the exact externally evidenced ChromaTOF 4.72 "
            "GCxGC Result text profile; the bytes contain no independent software-version, "
            "detector, or channel marker.",
            Severity.WARNING,
            safe_source,
        )
        return DatasetBundle(
            (source,),
            (sample,),
            peaks=peaks,
            metadata=tuple(metadata),
            warnings=(warning,),
        )
