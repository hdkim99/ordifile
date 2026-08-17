# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental reader for one exact Agilent ChemStation Result XML profile."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ordifile.adapters._agilent_chemstation_result_xml import (
    AgilentResultXmlStructureError,
    has_result_xml_family_identity,
    read_result_xml,
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

_NAMESPACE = "adapter:agilent_chemstation_result_xml"
_COMPOUND_SOURCE = "canonical:agilent_chemstation_result_xml.results_peak_name"
_CANONICAL_DETECTOR = "FID"
_CANONICAL_CHANNEL = "FID1A"


def _parse_error(error: AgilentResultXmlStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class AgilentChemStationResultXmlAdapter:
    """Read canonical result peaks from exact C.01.10 single-FID Result XML."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "agilent_chemstation_result_xml"
    adapter_version: ClassVar[str] = "0.1.0"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "Agilent ChemStation Result XML, C.01.10 single-FID profile (Experimental)",
        (".xml",),
        True,
        True,
        False,
        True,
        SupportStatus.EXPERIMENTAL,
        (),
        source_identity_policy=SourceIdentityPolicy.SHA256_ALIAS,
    )

    def probe(self, path: Path) -> DetectionResult:
        """Require .xml plus the bounded exact ChemStationResult profile."""
        if path.suffix.casefold() != ".xml":
            return DetectionResult(False, 0.0, "the required .xml extension is absent")
        recognized = has_result_xml_family_identity(path)
        if not recognized:
            return DetectionResult(False, 0.0, "bounded ChemStationResult markers are absent")
        try:
            read_result_xml(path)
        except AgilentResultXmlStructureError as error:
            return DetectionResult(True, 0.70, error.message)
        return DetectionResult(
            True,
            0.99,
            "exact ChemStation Result XML C.01.10 single-FID Percent/Area profile matched",
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return ResultsGroup/Peak observations without exporting private run fields."""
        del options
        if path.suffix.casefold() != ".xml":
            raise ParseError(
                "AGILENT_RESULT_XML_EXTENSION_INVALID",
                "The exact experimental profile requires a .xml source extension.",
            )
        try:
            decoded = read_result_xml(path)
        except AgilentResultXmlStructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                "The Result XML input could not be read.",
            ) from error
        source_sha256 = decoded.source_sha256
        sample_id = f"AGILENT_RESULT_{source_sha256[:16]}"
        safe_source = f"{sample_id}.xml"
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
            instrument=InstrumentMetadata("GC", "Agilent"),
            channels=(_CANONICAL_CHANNEL,),
            detectors=(_CANONICAL_DETECTOR,),
        )
        peaks = tuple(
            PeakRecord(
                sample_id,
                safe_source,
                channel=_CANONICAL_CHANNEL,
                detector=_CANONICAL_DETECTOR,
                peak_number=None,
                retention_time=peak.retention_time,
                retention_time_unit=decoded.retention_time_unit,
                area=peak.area,
                height=peak.height,
                compound=peak.compound,
                compound_source=_COMPOUND_SOURCE if peak.compound is not None else None,
                status="experimental",
                observation_order=peak.observation_order,
                start_time=peak.start_time,
                end_time=peak.end_time,
                area_unit=decoded.area_unit,
                height_unit=decoded.height_unit,
            )
            for peak in decoded.peaks
        )
        values: tuple[tuple[str, object, str | None], ...] = (
            ("support_status", "experimental", None),
            ("profile", "ChemStation Result XML C.01.10 [201] single FID1/A", None),
            ("representation", "canonical_results_group_peaks", None),
            ("revision", decoded.revision, None),
            ("signal_description", decoded.signal_description, None),
            ("source_detector_label", decoded.detector, None),
            ("source_channel", decoded.channel, None),
            ("canonical_detector", _CANONICAL_DETECTOR, None),
            ("canonical_channel", _CANONICAL_CHANNEL, None),
            ("detector_verification_status", "source_explicit", None),
            ("quant_calculation", decoded.quant_calculation, None),
            ("quant_base", decoded.quant_base, None),
            ("peak_count", len(decoded.peaks), None),
            ("signal_start", decoded.signal_start, decoded.retention_time_unit),
            ("signal_end", decoded.signal_end, decoded.retention_time_unit),
            ("retention_time_unit", decoded.retention_time_unit, None),
            ("area_unit", decoded.area_unit, None),
            ("height_unit", decoded.height_unit, None),
            ("integration_duplicate_validation", "exact_decimal_strings_by_index", None),
            ("raw_signal_pairing_status", "not_required_result_only", None),
        )
        metadata = tuple(
            MetadataEntry(sample_id, safe_source, _NAMESPACE, key, value, unit)
            for key, value, unit in values
        )
        warning = Issue(
            "AGILENT_RESULT_XML_EXPERIMENTAL_PROFILE",
            "Peak results are limited to the exact C.01.10 single-FID Percent/Area profile; "
            "other revisions, signals, detectors, and quantitation modes are unsupported.",
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
