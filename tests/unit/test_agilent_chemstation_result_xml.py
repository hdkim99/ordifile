from __future__ import annotations

import copy
import hashlib
import sys
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from defusedxml import ElementTree as DefusedElementTree  # type: ignore[import-untyped]

from ordifile.adapters import _agilent_chemstation_result_xml as reader
from ordifile.adapters.agilent_chemstation_result_xml import (
    AgilentChemStationResultXmlAdapter,
)
from ordifile.adapters.base import ParseOptions, SourceIdentityPolicy, SupportStatus
from ordifile.core.errors import ParseError

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_agilent_chemstation_result_xml import (  # noqa: E402
    XML_DECLARATION,
    synthetic_result_xml_bytes,
)


def _write(path: Path, data: bytes | None = None) -> Path:
    path.write_bytes(synthetic_result_xml_bytes() if data is None else data)
    return path


def _rewrite(data: bytes, change: Callable[[ElementTree.Element], None]) -> bytes:
    root = ElementTree.fromstring(data)
    change(root)
    text = XML_DECLARATION + "\r\n  " + ElementTree.tostring(root, encoding="unicode")
    return b"\xff\xfe" + text.encode("utf-16-le")


def _parse_error(tmp_path: Path, data: bytes, code: str) -> None:
    path = _write(tmp_path / "private-result.xml", data)
    with pytest.raises(ParseError) as caught:
        AgilentChemStationResultXmlAdapter().parse(path, ParseOptions())
    assert caught.value.code == code


def test_descriptor_and_probe_are_exact_and_private(tmp_path: Path) -> None:
    adapter = AgilentChemStationResultXmlAdapter()
    descriptor = adapter.descriptor
    assert descriptor.adapter_id == "agilent_chemstation_result_xml"
    assert descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert descriptor.source_identity_policy is SourceIdentityPolicy.SHA256_ALIAS
    assert descriptor.peaks and descriptor.metadata and not descriptor.signals
    valid = _write(tmp_path / "secret.xml")
    wrong_extension = _write(tmp_path / "secret.bin")
    invalid = _write(tmp_path / "invalid.xml", b"not xml")
    assert adapter.probe(valid).confidence == pytest.approx(0.99)
    assert not adapter.probe(wrong_extension).matched
    assert not adapter.probe(invalid).matched


def test_probe_preserves_non_routable_owner_for_unsupported_version(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "unsupported.xml",
        synthetic_result_xml_bytes(
            acquisition_version="Rev. C.01.09 [200] Copyright © Agilent Technologies",
            sample_version="Rev. C.01.09 [200] Copyright © Agilent Technologies",
        ),
    )

    result = AgilentChemStationResultXmlAdapter().probe(source)

    assert result.matched
    assert result.confidence == pytest.approx(0.70)
    assert not result.routable
    assert result.failure_code == "AGILENT_RESULT_XML_VERSION_UNSUPPORTED"


def test_parse_preserves_canonical_result_order_units_and_optional_name(tmp_path: Path) -> None:
    data = synthetic_result_xml_bytes(omit_name_index=2)
    path = _write(tmp_path / "private-result.xml", data)
    bundle = AgilentChemStationResultXmlAdapter().parse(path, ParseOptions())

    assert bundle.signals == ()
    assert bundle.samples[0].instrument.vendor == "Agilent"
    assert bundle.samples[0].instrument.instrument_type == "GC"
    assert bundle.samples[0].detectors == ("FID",)
    assert bundle.samples[0].channels == ("FID1A",)
    assert bundle.samples[0].sample_id.startswith("AGILENT_RESULT_")
    assert bundle.samples[0].sample_id not in path.name
    assert bundle.sources[0].sha256 == hashlib.sha256(data).hexdigest()
    assert tuple(peak.observation_order for peak in bundle.peaks) == (1, 2, 3)
    assert tuple(peak.retention_time for peak in bundle.peaks) == (1.25, 2.5, 3.75)
    assert tuple(peak.area for peak in bundle.peaks) == (100.5, 200.75, 300.0)
    assert tuple(peak.height for peak in bundle.peaks) == (10.25, 20.5, 30.0)
    assert tuple(peak.start_time for peak in bundle.peaks) == (1.2, 2.45, 3.7)
    assert tuple(peak.end_time for peak in bundle.peaks) == (1.3, 2.55, 3.8)
    assert tuple(peak.compound for peak in bundle.peaks) == (
        "compound-alpha",
        None,
        "compound-gamma",
    )
    assert bundle.peaks[0].compound_source == (
        "canonical:agilent_chemstation_result_xml.results_peak_name"
    )
    assert bundle.peaks[1].compound_source is None
    assert all(peak.peak_number is None for peak in bundle.peaks)
    assert all(peak.detector == "FID" and peak.channel == "FID1A" for peak in bundle.peaks)
    assert all(peak.retention_time_unit == "min" for peak in bundle.peaks)
    assert all(peak.area_unit == "pA*s" and peak.height_unit == "pA" for peak in bundle.peaks)
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["source_detector_label"] == "FID1"
    assert metadata["source_channel"] == "A"
    assert metadata["canonical_detector"] == "FID"
    assert metadata["detector_verification_status"] == "source_explicit"
    assert not any(
        private in str(value)
        for entry in bundle.metadata
        for value in (entry.key, entry.value, entry.source_file)
        for private in ("private-result", "synthetic.ch", "2000-01-01")
    )


def test_variable_nonempty_peak_count_is_supported(tmp_path: Path) -> None:
    peaks = (("1", "2", "3", "0.5", "1.5", None),)
    bundle = AgilentChemStationResultXmlAdapter().parse(
        _write(tmp_path / "one.xml", synthetic_result_xml_bytes(peaks=peaks)),
        ParseOptions(),
    )
    assert len(bundle.peaks) == 1
    assert bundle.peaks[0].observation_order == 1


@pytest.mark.parametrize(
    ("kwargs", "code"),
    (
        (
            {
                "acquisition_version": "Rev. C.01.10 [201] Agilent Technologies",
                "sample_version": "Rev. C.01.10 [201] Agilent Technologies",
            },
            "AGILENT_RESULT_XML_VERSION_UNSUPPORTED",
        ),
        (
            {"sample_version": "Rev. C.01.09 [200] Copyright © Agilent Technologies"},
            "AGILENT_RESULT_XML_VERSION_CONFLICT",
        ),
        ({"detector": "TCD1"}, "AGILENT_RESULT_XML_SIGNAL_UNSUPPORTED"),
        ({"channel": "B"}, "AGILENT_RESULT_XML_SIGNAL_UNSUPPORTED"),
        ({"description": "FID1 A,"}, "AGILENT_RESULT_XML_SIGNAL_UNSUPPORTED"),
        ({"x_unit": "sec"}, "AGILENT_RESULT_XML_SIGNAL_UNSUPPORTED"),
        ({"y_unit": "mV"}, "AGILENT_RESULT_XML_SIGNAL_UNSUPPORTED"),
        ({"area_unit": "mV*s"}, "AGILENT_RESULT_XML_UNIT_UNSUPPORTED"),
        ({"height_unit": "mV"}, "AGILENT_RESULT_XML_UNIT_UNSUPPORTED"),
        ({"quant_calculation": "ESTD"}, "AGILENT_RESULT_XML_QUANTITATION_UNSUPPORTED"),
        ({"quant_base": "Height"}, "AGILENT_RESULT_XML_QUANTITATION_UNSUPPORTED"),
        (
            {"checksum": "ABCDEFABCDEFABCDEFABCDEFABCDEFAB"},
            "AGILENT_RESULT_XML_CHECKSUM_SHAPE_INVALID",
        ),
        ({"schema": "other.xsd"}, "AGILENT_RESULT_XML_SCHEMA_UNSUPPORTED"),
    ),
)
def test_profile_variants_are_rejected(
    tmp_path: Path, kwargs: dict[str, object], code: str
) -> None:
    _parse_error(tmp_path, synthetic_result_xml_bytes(**kwargs), code)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    (
        ({"integration_rt_override": (2, "2.500")}, "AGILENT_RESULT_XML_DUPLICATE_VALUE_MISMATCH"),
        ({"integration_area_override": (2, "999")}, "AGILENT_RESULT_XML_DUPLICATE_VALUE_MISMATCH"),
        (
            {"integration_height_override": (2, "999")},
            "AGILENT_RESULT_XML_DUPLICATE_VALUE_MISMATCH",
        ),
        ({"peak_signal_override": (2, "other")}, "AGILENT_RESULT_XML_SIGNAL_DESCRIPTION_MISMATCH"),
        ({"duplicate_peak_area_index": 2}, "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED"),
    ),
)
def test_duplicate_tables_and_fields_must_agree(
    tmp_path: Path, kwargs: dict[str, object], code: str
) -> None:
    _parse_error(tmp_path, synthetic_result_xml_bytes(**kwargs), code)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("peaks", "code"),
    (
        ((), "AGILENT_RESULT_XML_PEAK_COUNT_INVALID"),
        (
            (("2", "1", "1", "1.9", "2.1", None), ("1", "2", "2", "0.9", "1.1", None)),
            "AGILENT_RESULT_XML_RETENTION_ORDER_INVALID",
        ),
        ((("1", "2", "3", "1.1", "1.2", None),), "AGILENT_RESULT_XML_PEAK_BOUNDARY_INVALID"),
        ((("NaN", "2", "3", "0", "4", None),), "AGILENT_RESULT_XML_NUMBER_INVALID"),
        ((("1", "2", "Infinity", "0", "4", None),), "AGILENT_RESULT_XML_NUMBER_INVALID"),
        ((("1", "9" * 129, "3", "0", "4", None),), "AGILENT_RESULT_XML_NUMBER_INVALID"),
        (
            (("1", "1.0000000000000000001", "3", "0", "4", None),),
            "AGILENT_RESULT_XML_LOSSY_FLOAT",
        ),
    ),
)
def test_scientific_values_are_bounded_and_ordered(
    tmp_path: Path,
    peaks: tuple[tuple[str, str, str, str, str, str | None], ...],
    code: str,
) -> None:
    _parse_error(tmp_path, synthetic_result_xml_bytes(peaks=peaks), code)


def test_missing_required_row_and_count_mismatch_are_rejected(tmp_path: Path) -> None:
    data = synthetic_result_xml_bytes()

    def remove_required(root: ElementTree.Element) -> None:
        peak = root.find("./Results/ResultsGroup/Peak")
        assert peak is not None
        area = peak.find("Area")
        assert area is not None
        peak.remove(area)

    _parse_error(
        tmp_path,
        _rewrite(data, remove_required),
        "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
    )

    def remove_integration(root: ElementTree.Element) -> None:
        signal = root.find("./Chromatograms/Signal")
        assert signal is not None
        integration = signal.findall("IntegrationResults")[-1]
        signal.remove(integration)

    _parse_error(
        tmp_path,
        _rewrite(data, remove_integration),
        "AGILENT_RESULT_XML_PEAK_COUNT_MISMATCH",
    )


def test_nested_scalar_field_is_rejected_with_a_structured_error(tmp_path: Path) -> None:
    data = synthetic_result_xml_bytes()

    def nest_detector(root: ElementTree.Element) -> None:
        detector = root.find("./Chromatograms/Signal/Detector")
        assert detector is not None
        detector.text = None
        ElementTree.SubElement(detector, "Unexpected").text = "FID1"

    _parse_error(
        tmp_path,
        _rewrite(data, nest_detector),
        "AGILENT_RESULT_XML_FIELD_INVALID",
    )


@pytest.mark.parametrize(
    "selector",
    (
        "./Chromatograms/Signal/IntegrationResults/AreaPercent",
        "./Results/ResultsGroup/Peak/CompoundID",
    ),
)
def test_unused_result_row_fields_must_still_be_scalar(tmp_path: Path, selector: str) -> None:
    data = synthetic_result_xml_bytes()

    def nest_unused_field(root: ElementTree.Element) -> None:
        field = root.find(selector)
        assert field is not None
        field.text = None
        ElementTree.SubElement(field, "Unexpected").text = "1"

    _parse_error(
        tmp_path,
        _rewrite(data, nest_unused_field),
        "AGILENT_RESULT_XML_FIELD_INVALID",
    )


@pytest.mark.parametrize(
    "selector",
    ("Acquisition", "./Results/ResultsGroup/Peak"),
)
def test_container_attributes_are_outside_the_exact_profile(tmp_path: Path, selector: str) -> None:
    data = synthetic_result_xml_bytes()

    def add_attribute(root: ElementTree.Element) -> None:
        container = root.find(selector)
        assert container is not None
        container.set("unexpected", "1")

    _parse_error(
        tmp_path,
        _rewrite(data, add_attribute),
        "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
    )


def test_mixed_container_text_and_nonwhitespace_tails_are_rejected(tmp_path: Path) -> None:
    data = synthetic_result_xml_bytes()

    def add_container_text(root: ElementTree.Element) -> None:
        group = root.find("./Results/ResultsGroup")
        assert group is not None
        group.text = "unexpected"

    _parse_error(
        tmp_path,
        _rewrite(data, add_container_text),
        "AGILENT_RESULT_XML_MIXED_CONTENT",
    )

    def add_scalar_tail(root: ElementTree.Element) -> None:
        compound_id = root.find("./Results/ResultsGroup/Peak/CompoundID")
        assert compound_id is not None
        compound_id.tail = "unexpected"

    _parse_error(
        tmp_path,
        _rewrite(data, add_scalar_tail),
        "AGILENT_RESULT_XML_MIXED_CONTENT",
    )


def test_multi_signal_and_nested_depth_are_rejected(tmp_path: Path) -> None:
    data = synthetic_result_xml_bytes()

    def duplicate_signal(root: ElementTree.Element) -> None:
        chromatograms = root.find("Chromatograms")
        signal = root.find("./Chromatograms/Signal")
        assert chromatograms is not None and signal is not None
        chromatograms.append(copy.deepcopy(signal))

    _parse_error(
        tmp_path,
        _rewrite(data, duplicate_signal),
        "AGILENT_RESULT_XML_FIELD_CARDINALITY",
    )

    def add_unknown_chromatogram(root: ElementTree.Element) -> None:
        chromatograms = root.find("Chromatograms")
        assert chromatograms is not None
        ElementTree.SubElement(chromatograms, "UnknownSignal")

    _parse_error(
        tmp_path,
        _rewrite(data, add_unknown_chromatogram),
        "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
    )

    def deepen(root: ElementTree.Element) -> None:
        current = root.find("ModuleInformation")
        assert current is not None
        for _index in range(reader.MAX_XML_DEPTH + 1):
            current = ElementTree.SubElement(current, "Nested")

    _parse_error(
        tmp_path,
        _rewrite(data, deepen),
        "AGILENT_RESULT_XML_DEPTH_LIMIT",
    )


def test_element_limit_is_enforced_before_full_tree_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = synthetic_result_xml_bytes()
    monkeypatch.setattr(reader, "MAX_XML_ELEMENTS", 1)

    def full_tree_must_not_run(_data: bytes, **_kwargs: object) -> ElementTree.Element:
        raise AssertionError("full-tree parser ran before the streaming element bound")

    monkeypatch.setattr(DefusedElementTree, "fromstring", full_tree_must_not_run)
    _parse_error(tmp_path, data, "AGILENT_RESULT_XML_ELEMENT_LIMIT")


def test_nonempty_custom_results_are_rejected(tmp_path: Path) -> None:
    data = synthetic_result_xml_bytes()

    def add_custom_result(root: ElementTree.Element) -> None:
        custom = root.find("CustomResults")
        assert custom is not None
        ElementTree.SubElement(custom, "UnexpectedResult").text = "1"

    _parse_error(
        tmp_path,
        _rewrite(data, add_custom_result),
        "AGILENT_RESULT_XML_PROFILE_UNSUPPORTED",
    )


def test_unsafe_malformed_truncated_and_wrong_declaration_are_rejected(tmp_path: Path) -> None:
    data = synthetic_result_xml_bytes()
    text = data[2:].decode("utf-16-le")
    unsafe = b"\xff\xfe" + text.replace(
        XML_DECLARATION,
        XML_DECLARATION + '<!DOCTYPE x [<!ENTITY e "unsafe">]>',
        1,
    ).encode("utf-16-le")
    _parse_error(tmp_path, unsafe, "AGILENT_RESULT_XML_UNSAFE")
    _parse_error(tmp_path, data[:-8], "AGILENT_RESULT_XML_MALFORMED")
    _parse_error(tmp_path, data + b"\x00\x00", "AGILENT_RESULT_XML_MALFORMED")
    _parse_error(
        tmp_path,
        data.replace("version =".encode("utf-16-le"), "version=".encode("utf-16-le"), 1),
        "AGILENT_RESULT_XML_DECLARATION_UNSUPPORTED",
    )
    _parse_error(tmp_path, data[2:], "AGILENT_RESULT_XML_ENCODING_UNSUPPORTED")


def test_file_size_and_growth_are_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = synthetic_result_xml_bytes()
    monkeypatch.setattr(reader, "MAX_RESULT_XML_BYTES", len(data) - 1)
    _parse_error(tmp_path, data, "AGILENT_RESULT_XML_SIZE_INVALID")


def test_open_file_size_change_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = synthetic_result_xml_bytes()
    path = _write(tmp_path / "private-result.xml", data)
    monkeypatch.setattr(
        "ordifile.adapters._agilent_chemstation_result_xml.os.fstat",
        lambda _fd: SimpleNamespace(st_size=len(data) - 2),
    )
    with pytest.raises(ParseError) as caught:
        AgilentChemStationResultXmlAdapter().parse(path, ParseOptions())
    assert caught.value.code == "AGILENT_RESULT_XML_SIZE_CHANGED"


def test_parse_wrong_extension_is_structured(tmp_path: Path) -> None:
    path = _write(tmp_path / "result.bin")
    with pytest.raises(ParseError) as caught:
        AgilentChemStationResultXmlAdapter().parse(path, ParseOptions())
    assert caught.value.code == "AGILENT_RESULT_XML_EXTENSION_INVALID"
