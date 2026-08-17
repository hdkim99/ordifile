# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate invented ChemStation Result XML for exact-profile parser tests."""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from collections.abc import Sequence

XSI = "http://www.w3.org/2001/XMLSchema-instance"
VERSION_TEXT = "Rev. C.01.10 [201] Copyright © Agilent Technologies"
XML_DECLARATION = '<?xml version = "1.0" encoding="utf-16"?>'


def _field(parent: ElementTree.Element, tag: str, text: str, **attributes: str) -> None:
    child = ElementTree.SubElement(parent, tag, attributes)
    child.text = text


def synthetic_result_xml_bytes(
    *,
    peaks: Sequence[tuple[str, str, str, str, str, str | None]] = (
        ("1.25", "100.5", "10.25", "1.20", "1.30", "compound-alpha"),
        ("2.50", "200.75", "20.5", "2.45", "2.55", None),
        ("3.75", "300.0", "30.0", "3.70", "3.80", "compound-gamma"),
    ),
    acquisition_version: str = VERSION_TEXT,
    sample_version: str = VERSION_TEXT,
    detector: str = "FID1",
    channel: str = "A",
    description: str = "FID1 A, ",
    x_unit: str = "min",
    y_unit: str = "pA",
    area_unit: str = "pA*s",
    height_unit: str = "pA",
    quant_calculation: str = "Percent",
    quant_base: str = "Area",
    signal_start: str = "0.0",
    signal_end: str = "10.0",
    integration_area_override: tuple[int, str] | None = None,
    integration_height_override: tuple[int, str] | None = None,
    integration_rt_override: tuple[int, str] | None = None,
    peak_signal_override: tuple[int, str] | None = None,
    omit_name_index: int | None = None,
    duplicate_peak_area_index: int | None = None,
    checksum: str = "0123456789abcdef0123456789abcdef",
    schema: str = "export.xsd",
) -> bytes:
    """Return deterministic synthetic bytes; values and metadata are invented."""
    ElementTree.register_namespace("xsi", XSI)
    root = ElementTree.Element(
        "ChemStationResult",
        {
            "checksum": checksum,
            f"{{{XSI}}}noNamespaceSchemaLocation": schema,
        },
    )
    acquisition = ElementTree.SubElement(root, "Acquisition")
    _field(acquisition, "Version", acquisition_version)
    module = ElementTree.SubElement(root, "ModuleInformation")
    _field(module, "SyntheticMarker", "invented")
    sample = ElementTree.SubElement(root, "SampleInformation")
    _field(sample, "Version", sample_version)
    chromatograms = ElementTree.SubElement(root, "Chromatograms")
    signal = ElementTree.SubElement(chromatograms, "Signal")
    for tag, text in (
        ("Title", "synthetic result"),
        ("Description", description),
        ("Detector", detector),
        ("SignalId", channel),
        ("Operator", "synthetic"),
        ("DateTime", "2000-01-01T00:00:00"),
        ("DerivOrder", "0"),
        ("RawdataFile", "synthetic.ch"),
        ("Start", signal_start),
        ("End", signal_end),
        ("XUnits", x_unit),
        ("YUnits", y_unit),
    ):
        _field(signal, tag, text)
    for index, (rt, area, height, start, end, _name) in enumerate(peaks, start=1):
        integration = ElementTree.SubElement(signal, "IntegrationResults")
        values = (
            (
                "RetTime",
                integration_rt_override[1]
                if integration_rt_override and integration_rt_override[0] == index
                else rt,
            ),
            (
                "Area",
                integration_area_override[1]
                if integration_area_override and integration_area_override[0] == index
                else area,
            ),
            ("AreaPercent", "0"),
            ("AreaSum", area),
            (
                "Height",
                integration_height_override[1]
                if integration_height_override and integration_height_override[0] == index
                else height,
            ),
            ("HeightPercent", "0"),
            ("HeightSum", height),
            ("Width", "0.10"),
            ("Symmetry", "1.0"),
            ("Baseline", "0"),
            ("TimeStart", start),
            ("LevelStart", "0"),
            ("BaselineStart", "0"),
            ("TimeEnd", end),
            ("LevelEnd", "0"),
            ("BaselineEnd", "0"),
        )
        for tag, text in values:
            _field(integration, tag, text)

    results = ElementTree.SubElement(root, "Results")
    _field(results, "QuantCalc", quant_calculation)
    _field(results, "QuantBase", quant_base)
    group = ElementTree.SubElement(results, "ResultsGroup")
    _field(group, "ResultsGroupDescription", description)
    for index, (rt, area, height, _start, _end, name) in enumerate(peaks, start=1):
        peak = ElementTree.SubElement(group, "Peak")
        _field(peak, "CompoundID", "0")
        _field(
            peak,
            "SignalDesc",
            peak_signal_override[1]
            if peak_signal_override and peak_signal_override[0] == index
            else description,
        )
        _field(peak, "PeakType", "BB")
        _field(peak, "ExpRetTime", rt, Unit=x_unit)
        _field(peak, "MeasRetTime", rt, Unit=x_unit)
        _field(peak, "Area", area, Unit=area_unit)
        if duplicate_peak_area_index == index:
            _field(peak, "Area", area, Unit=area_unit)
        _field(peak, "Height", height, Unit=height_unit)
        _field(peak, "Width", "0.10", Unit=x_unit)
        _field(peak, "Symmetry", "1.0")
        if omit_name_index != index:
            _field(peak, "Name", "" if name is None else name)
        _field(peak, "Amount", "0", Unit="%")
    ElementTree.SubElement(root, "CustomResults")
    text = XML_DECLARATION + "\r\n  " + ElementTree.tostring(root, encoding="unicode")
    return b"\xff\xfe" + text.encode("utf-16-le")
