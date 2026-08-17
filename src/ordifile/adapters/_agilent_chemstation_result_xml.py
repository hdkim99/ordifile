# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded reader for one exact Agilent ChemStation Result XML profile."""

from __future__ import annotations

import hashlib
import io
import os
import re
import xml.etree.ElementTree as stdlib_etree
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import Any, cast

from defusedxml import ElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]

from ordifile.core.workbook_text import workbook_text_is_exact

UTF16_LE_BOM = b"\xff\xfe"
ROOT_MARKER = "<ChemStationResult".encode("utf-16-le")
XML_DECLARATION = '<?xml version = "1.0" encoding="utf-16"?>'
XSI_SCHEMA_ATTRIBUTE = "{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation"
PROFILE_REVISION = "C.01.10 [201]"
VERSION_TEXT = "Rev. C.01.10 [201] Copyright © Agilent Technologies"
MAX_RESULT_XML_BYTES = 16 * 1024 * 1024
MAX_XML_ELEMENTS = 250_000
MAX_XML_DEPTH = 64
MAX_PEAKS = 100_000
MAX_TEXT_CHARACTERS = 32_767
MAX_NUMERIC_LEXEME_CHARACTERS = 128
_CHECKSUM = re.compile(r"[0-9a-f]{32}\Z")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")
_SIGNAL_PREFIX_TAGS = (
    "Title",
    "Description",
    "Detector",
    "SignalId",
    "Operator",
    "DateTime",
    "DerivOrder",
    "RawdataFile",
    "Start",
    "End",
    "XUnits",
    "YUnits",
)
_INTEGRATION_TAGS = (
    "RetTime",
    "Area",
    "AreaPercent",
    "AreaSum",
    "Height",
    "HeightPercent",
    "HeightSum",
    "Width",
    "Symmetry",
    "Baseline",
    "TimeStart",
    "LevelStart",
    "BaselineStart",
    "TimeEnd",
    "LevelEnd",
    "BaselineEnd",
)
_PEAK_TAGS = (
    "CompoundID",
    "SignalDesc",
    "PeakType",
    "ExpRetTime",
    "MeasRetTime",
    "Area",
    "Height",
    "Width",
    "Symmetry",
    "Name",
    "Amount",
)


class AgilentResultXmlStructureError(Exception):
    """Privacy-safe structural error translated by the public adapter."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True, slots=True)
class ResultPeak:
    """One canonical ResultsGroup/Peak observation with integration boundaries."""

    observation_order: int
    retention_time_text: str
    retention_time: float
    area_text: str
    area: float
    height_text: str
    height: float
    start_time_text: str
    start_time: float
    end_time_text: str
    end_time: float
    compound: str | None


@dataclass(frozen=True, slots=True)
class AgilentResultXmlData:
    """Allowlisted scientific facts from the exact supported profile."""

    revision: str
    signal_description: str
    detector: str
    channel: str
    retention_time_unit: str
    area_unit: str
    height_unit: str
    quant_calculation: str
    quant_base: str
    signal_start: float
    signal_end: float
    peaks: tuple[ResultPeak, ...]
    source_size: int
    source_sha256: str


def _fail(code: str, message: str, **details: Any) -> AgilentResultXmlStructureError:
    return AgilentResultXmlStructureError(code, message, **details)


def _read_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            if size < len(UTF16_LE_BOM) + len(ROOT_MARKER) or size > MAX_RESULT_XML_BYTES:
                raise _fail(
                    "AGILENT_RESULT_XML_SIZE_INVALID",
                    "The Result XML file size is outside the supported bounded profile.",
                    size_bytes=size,
                    maximum_bytes=MAX_RESULT_XML_BYTES,
                )
            data = stream.read(MAX_RESULT_XML_BYTES + 1)
            extra = stream.read(1)
    except AgilentResultXmlStructureError:
        raise
    except OSError as error:
        raise _fail(
            "INPUT_READ_FAILED",
            "The Result XML input could not be read.",
        ) from error
    if len(data) > MAX_RESULT_XML_BYTES or extra or len(data) != size:
        raise _fail(
            "AGILENT_RESULT_XML_SIZE_CHANGED",
            "The Result XML size changed during its bounded read.",
        )
    return data


def has_result_xml_family_identity(path: Path) -> bool:
    """Return whether the bounded prefix identifies the ChemStation XML family."""
    try:
        with path.open("rb") as stream:
            prefix = stream.read(8_192)
    except OSError:
        return False
    return prefix.startswith(UTF16_LE_BOM) and ROOT_MARKER in prefix


def _parse_xml(data: bytes) -> stdlib_etree.Element:
    if not data.startswith(UTF16_LE_BOM):
        raise _fail(
            "AGILENT_RESULT_XML_ENCODING_UNSUPPORTED",
            "The exact supported Result XML profile requires a UTF-16LE byte-order mark.",
        )
    try:
        text = data[len(UTF16_LE_BOM) :].decode("utf-16-le", errors="strict")
    except UnicodeDecodeError as error:
        raise _fail(
            "AGILENT_RESULT_XML_ENCODING_INVALID",
            "The Result XML is not well-formed UTF-16LE text.",
        ) from error
    if not text.startswith(XML_DECLARATION):
        raise _fail(
            "AGILENT_RESULT_XML_DECLARATION_UNSUPPORTED",
            "The Result XML declaration is outside the exact supported profile.",
        )
    folded = text.casefold()
    if "<!doctype" in folded or "<!entity" in folded:
        raise _fail(
            "AGILENT_RESULT_XML_UNSAFE",
            "DTD and entity declarations are not allowed in Result XML.",
        )
    count = 0
    depth = 0
    try:
        for event, element in ElementTree.iterparse(
            io.BytesIO(data),
            events=("start", "end"),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        ):
            if event == "start":
                count += 1
                depth += 1
                if count > MAX_XML_ELEMENTS:
                    raise _fail(
                        "AGILENT_RESULT_XML_ELEMENT_LIMIT",
                        "The Result XML exceeds the bounded element limit.",
                        maximum_elements=MAX_XML_ELEMENTS,
                    )
                if depth > MAX_XML_DEPTH:
                    raise _fail(
                        "AGILENT_RESULT_XML_DEPTH_LIMIT",
                        "The Result XML exceeds the bounded nesting depth.",
                        maximum_depth=MAX_XML_DEPTH,
                    )
            else:
                if (len(element) and element.text and element.text.strip()) or (
                    element.tail and element.tail.strip()
                ):
                    raise _fail(
                        "AGILENT_RESULT_XML_MIXED_CONTENT",
                        "Mixed XML text is outside the exact element-only Result profile.",
                    )
                depth -= 1
                element.clear()
    except (DefusedXmlException, stdlib_etree.ParseError) as error:
        raise _fail(
            "AGILENT_RESULT_XML_MALFORMED",
            "The Result XML is malformed or uses an unsafe XML construct.",
        ) from error
    try:
        root = cast(
            stdlib_etree.Element,
            ElementTree.fromstring(
                data,
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            ),
        )
    except (DefusedXmlException, stdlib_etree.ParseError) as error:
        raise _fail(
            "AGILENT_RESULT_XML_MALFORMED",
            "The Result XML is malformed or uses an unsafe XML construct.",
        ) from error
    return root


def _children(element: stdlib_etree.Element, tag: str) -> tuple[stdlib_etree.Element, ...]:
    return tuple(child for child in element if child.tag == tag)


def _one(element: stdlib_etree.Element, tag: str) -> stdlib_etree.Element:
    matches = _children(element, tag)
    if len(matches) != 1:
        raise _fail(
            "AGILENT_RESULT_XML_FIELD_CARDINALITY",
            "A required Result XML field is missing or duplicated.",
            field=tag,
            observed_count=len(matches),
        )
    return matches[0]


def _text(
    element: stdlib_etree.Element,
    tag: str,
    *,
    allow_blank: bool = False,
) -> str:
    field = _one(element, tag)
    if field.attrib or len(field):
        raise _fail(
            "AGILENT_RESULT_XML_FIELD_INVALID",
            "A scalar Result XML field has unexpected nested structure.",
            field=tag,
        )
    value = "" if field.text is None else field.text
    if len(value) > MAX_TEXT_CHARACTERS or not workbook_text_is_exact(value):
        raise _fail(
            "AGILENT_RESULT_XML_TEXT_INVALID",
            "A Result XML scalar contains unsupported text.",
            field=tag,
        )
    if not allow_blank and not value:
        raise _fail(
            "AGILENT_RESULT_XML_FIELD_EMPTY",
            "A required Result XML field is empty.",
            field=tag,
        )
    return value


def _optional_text(element: stdlib_etree.Element, tag: str) -> str:
    matches = _children(element, tag)
    if not matches:
        return ""
    if len(matches) != 1:
        raise _fail(
            "AGILENT_RESULT_XML_FIELD_CARDINALITY",
            "An optional Result XML field is duplicated.",
            field=tag,
            observed_count=len(matches),
        )
    field = matches[0]
    if field.attrib or len(field):
        raise _fail(
            "AGILENT_RESULT_XML_FIELD_INVALID",
            "An optional Result XML field has unexpected nested structure.",
            field=tag,
        )
    value = "" if field.text is None else field.text
    if len(value) > MAX_TEXT_CHARACTERS or not workbook_text_is_exact(value):
        raise _fail(
            "AGILENT_RESULT_XML_TEXT_INVALID",
            "An optional Result XML field contains unsupported text.",
            field=tag,
        )
    return value


def _unit_text(element: stdlib_etree.Element, tag: str, unit: str) -> str:
    field = _one(element, tag)
    if (
        field.attrib != {"Unit": unit}
        or len(field)
        or not field.text
        or len(field.text) > MAX_TEXT_CHARACTERS
        or not workbook_text_is_exact(field.text)
    ):
        raise _fail(
            "AGILENT_RESULT_XML_UNIT_UNSUPPORTED",
            "A Result XML scientific field has an unsupported unit or shape.",
            field=tag,
        )
    return field.text


def _decimal(text: str, field: str) -> tuple[Decimal, float]:
    if len(text) > MAX_NUMERIC_LEXEME_CHARACTERS or _DECIMAL.fullmatch(text) is None:
        raise _fail(
            "AGILENT_RESULT_XML_NUMBER_INVALID",
            "A Result XML scientific field is not an exact finite decimal string.",
            field=field,
        )
    try:
        decimal_value = Decimal(text)
        value = float(decimal_value)
    except (InvalidOperation, OverflowError) as error:
        raise _fail(
            "AGILENT_RESULT_XML_NUMBER_INVALID",
            "A Result XML scientific field is outside the supported numeric profile.",
            field=field,
        ) from error
    if not decimal_value.is_finite() or not isfinite(value):
        raise _fail(
            "AGILENT_RESULT_XML_NUMBER_NONFINITE",
            "A Result XML scientific field is non-finite.",
            field=field,
        )
    if Decimal(str(value)) != decimal_value:
        raise _fail(
            "AGILENT_RESULT_XML_LOSSY_FLOAT",
            "A Result XML scientific decimal cannot be represented exactly in the canonical "
            "numeric model.",
            field=field,
        )
    return decimal_value, value


def _validate_root(root: stdlib_etree.Element) -> None:
    if root.tag != "ChemStationResult":
        raise _fail(
            "AGILENT_RESULT_XML_ROOT_INVALID",
            "The XML root is not the required ChemStationResult element.",
        )
    if set(root.attrib) != {"checksum", XSI_SCHEMA_ATTRIBUTE}:
        raise _fail(
            "AGILENT_RESULT_XML_ROOT_INVALID",
            "The ChemStationResult root attributes do not match the supported profile.",
        )
    if _CHECKSUM.fullmatch(root.attrib["checksum"]) is None:
        raise _fail(
            "AGILENT_RESULT_XML_CHECKSUM_SHAPE_INVALID",
            "The Result XML checksum does not have the required 32-hex shape.",
        )
    schema = root.attrib[XSI_SCHEMA_ATTRIBUTE].replace("\\", "/").rsplit("/", 1)[-1]
    if schema != "export.xsd":
        raise _fail(
            "AGILENT_RESULT_XML_SCHEMA_UNSUPPORTED",
            "The Result XML schema basename is not the supported export.xsd profile.",
        )
    if tuple(child.tag for child in root) != (
        "Acquisition",
        "ModuleInformation",
        "SampleInformation",
        "Chromatograms",
        "Results",
        "CustomResults",
    ):
        raise _fail(
            "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
            "The Result XML top-level section order is outside the supported profile.",
        )
    if any(child.attrib for child in root):
        raise _fail(
            "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
            "Top-level Result XML sections must not carry attributes in the exact profile.",
        )
    custom_results = _one(root, "CustomResults")
    if custom_results.attrib or len(custom_results) or custom_results.text not in {None, ""}:
        raise _fail(
            "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
            "CustomResults must be empty in the exact supported profile.",
        )


def _validate_version(root: stdlib_etree.Element) -> str:
    acquisition_version = _text(_one(root, "Acquisition"), "Version")
    sample_version = _text(_one(root, "SampleInformation"), "Version")
    if acquisition_version != sample_version:
        raise _fail(
            "AGILENT_RESULT_XML_VERSION_CONFLICT",
            "The Acquisition and SampleInformation revisions do not agree.",
        )
    if acquisition_version != VERSION_TEXT:
        raise _fail(
            "AGILENT_RESULT_XML_VERSION_UNSUPPORTED",
            "The Result XML revision is outside the exact supported profile.",
        )
    return PROFILE_REVISION


def read_result_xml(path: Path) -> AgilentResultXmlData:
    """Read the exact C.01.10 single-FID Percent/Area result profile."""
    data = _read_bytes(path)
    root = _parse_xml(data)
    _validate_root(root)
    revision = _validate_version(root)

    chromatograms = _one(root, "Chromatograms")
    signal = _one(chromatograms, "Signal")
    if chromatograms.attrib or tuple(child.tag for child in chromatograms) != ("Signal",):
        raise _fail(
            "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
            "The Chromatograms section is outside the exact single-signal profile.",
        )
    if signal.attrib:
        raise _fail(
            "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
            "The Signal container has unsupported attributes.",
        )
    signal_tags = tuple(child.tag for child in signal)
    if signal_tags[: len(_SIGNAL_PREFIX_TAGS)] != _SIGNAL_PREFIX_TAGS or any(
        tag != "IntegrationResults" for tag in signal_tags[len(_SIGNAL_PREFIX_TAGS) :]
    ):
        raise _fail(
            "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
            "The Result XML signal field layout is outside the exact supported profile.",
        )
    signal_values = {tag: _text(signal, tag) for tag in _SIGNAL_PREFIX_TAGS}
    detector = signal_values["Detector"]
    channel = signal_values["SignalId"]
    description = signal_values["Description"]
    x_unit = signal_values["XUnits"]
    y_unit = signal_values["YUnits"]
    if (detector, channel, description, x_unit, y_unit) != (
        "FID1",
        "A",
        "FID1 A, ",
        "min",
        "pA",
    ):
        raise _fail(
            "AGILENT_RESULT_XML_SIGNAL_UNSUPPORTED",
            "The Result XML signal is outside the exact FID1/A min/pA profile.",
        )
    signal_start_decimal, signal_start = _decimal(signal_values["Start"], "Signal/Start")
    signal_end_decimal, signal_end = _decimal(signal_values["End"], "Signal/End")
    if signal_start_decimal > signal_end_decimal:
        raise _fail(
            "AGILENT_RESULT_XML_SIGNAL_RANGE_INVALID",
            "The Result XML signal start exceeds its end.",
        )

    results = _one(root, "Results")
    if results.attrib or tuple(child.tag for child in results) != (
        "QuantCalc",
        "QuantBase",
        "ResultsGroup",
    ):
        raise _fail(
            "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
            "The Result XML results layout is outside the exact supported profile.",
        )
    quant_calculation = _text(results, "QuantCalc")
    quant_base = _text(results, "QuantBase")
    if (quant_calculation, quant_base) != ("Percent", "Area"):
        raise _fail(
            "AGILENT_RESULT_XML_QUANTITATION_UNSUPPORTED",
            "The Result XML quantitation mode is outside the Percent/Area profile.",
        )
    group = _one(results, "ResultsGroup")
    group_tags = tuple(child.tag for child in group)
    if (
        group.attrib
        or not group_tags
        or group_tags[0] != "ResultsGroupDescription"
        or any(tag != "Peak" for tag in group_tags[1:])
    ):
        raise _fail(
            "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
            "The Result XML result-group layout is outside the exact supported profile.",
        )
    if _text(group, "ResultsGroupDescription") != description:
        raise _fail(
            "AGILENT_RESULT_XML_SIGNAL_DESCRIPTION_MISMATCH",
            "The result group does not reference the validated signal description.",
        )

    integrations = _children(signal, "IntegrationResults")
    source_peaks = _children(group, "Peak")
    if not source_peaks or len(source_peaks) > MAX_PEAKS:
        raise _fail(
            "AGILENT_RESULT_XML_PEAK_COUNT_INVALID",
            "The Result XML peak count is outside the supported nonempty bound.",
            observed_count=len(source_peaks),
            maximum_count=MAX_PEAKS,
        )
    if len(integrations) != len(source_peaks):
        raise _fail(
            "AGILENT_RESULT_XML_PEAK_COUNT_MISMATCH",
            "IntegrationResults and ResultsGroup/Peak counts do not agree.",
            integration_count=len(integrations),
            result_count=len(source_peaks),
        )

    peaks: list[ResultPeak] = []
    previous_rt: Decimal | None = None
    for observation_order, (integration, peak) in enumerate(
        zip(integrations, source_peaks, strict=True), start=1
    ):
        if integration.attrib or tuple(child.tag for child in integration) != _INTEGRATION_TAGS:
            raise _fail(
                "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
                "An integration row is outside the exact supported field layout.",
                observation_order=observation_order,
            )
        integration_values = {tag: _text(integration, tag) for tag in _INTEGRATION_TAGS}
        peak_tags = tuple(child.tag for child in peak)
        if peak.attrib or peak_tags not in (
            _PEAK_TAGS,
            tuple(tag for tag in _PEAK_TAGS if tag != "Name"),
        ):
            raise _fail(
                "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
                "A result peak is outside the exact supported field layout.",
                observation_order=observation_order,
            )
        for tag in ("CompoundID", "SignalDesc", "PeakType", "Symmetry"):
            _text(peak, tag)
        _unit_text(peak, "ExpRetTime", "min")
        _unit_text(peak, "Width", "min")
        _unit_text(peak, "Amount", "%")
        integration_rt = integration_values["RetTime"]
        integration_area = integration_values["Area"]
        integration_height = integration_values["Height"]
        retention_text = _unit_text(peak, "MeasRetTime", "min")
        area_text = _unit_text(peak, "Area", "pA*s")
        height_text = _unit_text(peak, "Height", "pA")
        if (integration_rt, integration_area, integration_height) != (
            retention_text,
            area_text,
            height_text,
        ):
            raise _fail(
                "AGILENT_RESULT_XML_DUPLICATE_VALUE_MISMATCH",
                "The duplicate integration and canonical result values do not agree exactly.",
                observation_order=observation_order,
            )
        if _text(peak, "SignalDesc") != description:
            raise _fail(
                "AGILENT_RESULT_XML_SIGNAL_DESCRIPTION_MISMATCH",
                "A result peak does not reference the validated signal description.",
                observation_order=observation_order,
            )
        retention_decimal, retention_time = _decimal(retention_text, "Peak/MeasRetTime")
        _area_decimal, area = _decimal(area_text, "Peak/Area")
        _height_decimal, height = _decimal(height_text, "Peak/Height")
        start_text = integration_values["TimeStart"]
        end_text = integration_values["TimeEnd"]
        start_decimal, start_time = _decimal(start_text, "IntegrationResults/TimeStart")
        end_decimal, end_time = _decimal(end_text, "IntegrationResults/TimeEnd")
        if not start_decimal <= retention_decimal <= end_decimal:
            raise _fail(
                "AGILENT_RESULT_XML_PEAK_BOUNDARY_INVALID",
                "A result peak retention time is outside its integration boundaries.",
                observation_order=observation_order,
            )
        if not signal_start_decimal <= retention_decimal <= signal_end_decimal:
            raise _fail(
                "AGILENT_RESULT_XML_SIGNAL_RANGE_INVALID",
                "A result peak retention time is outside the signal range.",
                observation_order=observation_order,
            )
        if previous_rt is not None and retention_decimal <= previous_rt:
            raise _fail(
                "AGILENT_RESULT_XML_RETENTION_ORDER_INVALID",
                "Result peak retention times must be strictly increasing.",
                observation_order=observation_order,
            )
        previous_rt = retention_decimal
        compound_text = _optional_text(peak, "Name")
        compound = compound_text if compound_text.strip() else None
        peaks.append(
            ResultPeak(
                observation_order,
                retention_text,
                retention_time,
                area_text,
                area,
                height_text,
                height,
                start_text,
                start_time,
                end_text,
                end_time,
                compound,
            )
        )
    return AgilentResultXmlData(
        revision,
        description,
        detector,
        channel,
        x_unit,
        "pA*s",
        y_unit,
        quant_calculation,
        quant_base,
        signal_start,
        signal_end,
        tuple(peaks),
        len(data),
        hashlib.sha256(data).hexdigest(),
    )
