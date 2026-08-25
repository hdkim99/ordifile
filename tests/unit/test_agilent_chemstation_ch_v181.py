from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

from ordifile.adapters import _agilent_ch_v181_records as records_module
from ordifile.adapters.agilent_chemstation_ch_v181 import (
    AgilentChemStationChV181Adapter,
)
from ordifile.adapters.base import ParseOptions, SupportStatus
from ordifile.core.errors import ParseError
from ordifile.core.models import SeriesKind

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_agilent_ch_v181 import synthetic_v181_bytes  # noqa: E402


def _write(path: Path, data: bytes | None = None) -> Path:
    path.write_bytes(synthetic_v181_bytes() if data is None else data)
    return path


def test_probe_uses_structure_and_version_not_extension_alone(tmp_path: Path) -> None:
    adapter = AgilentChemStationChV181Adapter()
    valid = _write(tmp_path / "FID1A.bin")
    invalid = _write(tmp_path / "random.CH", b"not a data file")

    result = adapter.probe(valid)
    assert result.matched
    assert result.confidence == pytest.approx(0.98)
    assert "version 181" in result.reason
    assert not adapter.probe(invalid).matched


def test_descriptor_is_explicitly_experimental() -> None:
    descriptor = AgilentChemStationChV181Adapter.descriptor
    assert descriptor.adapter_id == "agilent_chemstation_ch_v181"
    assert descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert descriptor.signals
    assert not descriptor.peaks


def test_parse_exposes_unscaled_decoded_records_and_no_time_axis(tmp_path: Path) -> None:
    path = _write(tmp_path / "FID1A.CH")
    bundle = AgilentChemStationChV181Adapter().parse(path, ParseOptions())

    assert bundle.samples[0].sample_id == "synthetic_sample"
    assert bundle.samples[0].detectors == ("FID",)
    assert bundle.samples[0].channels == ("FID1A",)
    assert bundle.samples[0].acquired_at_reliable is False
    assert bundle.peaks == ()
    signal = bundle.signals[0]
    assert signal.series_kind is SeriesKind.DECODED_RECORDS
    assert signal.x_values == (0, 1)
    assert signal.y_values == (100, 100)
    assert signal.x_label == "decoded_record_index"
    assert signal.y_label == "decoded_raw_integer"
    assert signal.x_unit is None
    assert signal.y_unit is None
    statuses = {entry.key: entry.value for entry in bundle.metadata}
    assert statuses["scientific_point_count_status"] == "unresolved"
    assert statuses["ambiguous_final_zero_ordinary_record_included"] is True
    assert statuses["physical_scaling_status"] == "not_applied"
    assert statuses["signal_unit_status"] == "unresolved"
    assert statuses["normalized_unit_lexeme_untrusted"] == "raw"
    assert statuses["unit_lexeme_bytes_hex"] == "720061007700"
    assert {issue.code for issue in bundle.warnings} == {
        "AGILENT_CH_V181_EXPERIMENTAL_RECORDS",
        "AGILENT_CH_V181_TIMESTAMP_UNINTERPRETED",
    }


@pytest.mark.parametrize("version_text", ("+181", "0181", " 181", "1_81", "181\x00"))
def test_version_text_aliases_are_not_accepted(tmp_path: Path, version_text: str) -> None:
    path = _write(tmp_path / "FID1A.CH", synthetic_v181_bytes(version_text=version_text))
    probe = AgilentChemStationChV181Adapter().probe(path)
    assert probe.matched
    assert not probe.routable
    assert probe.failure_code == "AGILENT_CH_VERSION_UNSUPPORTED"
    with pytest.raises(ParseError) as caught:
        AgilentChemStationChV181Adapter().parse(path, ParseOptions())
    assert caught.value.code == "AGILENT_CH_VERSION_UNSUPPORTED"


def test_text_whitespace_and_raw_unit_bytes_are_auditable(tmp_path: Path) -> None:
    data = bytearray(synthetic_v181_bytes())
    sample = " sample "
    data[858] = len(sample)
    data[859 : 859 + len(sample) * 2] = sample.encode("utf-16-le")
    raw_unit = "cou\x00\x00\x00"
    data[4172] = len(raw_unit)
    data[4173 : 4173 + len(raw_unit) * 2] = raw_unit.encode("utf-16-le")

    bundle = AgilentChemStationChV181Adapter().parse(
        _write(tmp_path / "FID1A.CH", bytes(data)), ParseOptions()
    )
    assert bundle.samples[0].sample_id == sample
    statuses = {entry.key: entry.value for entry in bundle.metadata}
    assert statuses["normalized_unit_lexeme_untrusted"] == "cou"
    assert statuses["unit_lexeme_bytes_hex"] == "63006f007500000000000000"
    assert statuses["sample_text_bytes_hex"] == sample.encode("utf-16-le").hex()


@pytest.mark.parametrize(
    "filename",
    ("renamed-FID1A.CH", "FID1.CH", "FID1AB.CH", "TCD1A.CH", "MSD1A.CH"),
)
def test_unsupported_detector_or_renamed_filename_is_rejected(
    tmp_path: Path, filename: str
) -> None:
    path = _write(tmp_path / filename)
    adapter = AgilentChemStationChV181Adapter()
    probe = adapter.probe(path)
    assert probe.matched
    assert probe.confidence == pytest.approx(0.70)
    assert not probe.routable
    assert probe.failure_code == "AGILENT_CH_DETECTOR_UNSUPPORTED"
    assert "basename" in probe.reason
    with pytest.raises(ParseError) as caught:
        adapter.parse(path, ParseOptions())
    assert caught.value.code == "AGILENT_CH_DETECTOR_UNSUPPORTED"


def test_detection_markers_are_exact_and_control_text_falls_back(tmp_path: Path) -> None:
    bad_marker = bytearray(synthetic_v181_bytes())
    marker = "GC DATA FILE\x00"
    bad_marker[347] = len(marker)
    bad_marker[348 : 348 + len(marker) * 2] = marker.encode("utf-16-le")
    with pytest.raises(ParseError) as marker_error:
        AgilentChemStationChV181Adapter().parse(
            _write(tmp_path / "FID1A.CH", bytes(bad_marker)), ParseOptions()
        )
    assert marker_error.value.code == "AGILENT_CH_HEADER_INVALID"

    bad_software = bytearray(synthetic_v181_bytes())
    software = "Not ChemStation data"
    bad_software[3089] = len(software)
    bad_software[3090 : 3090 + len(software) * 2] = software.encode("utf-16-le")
    with pytest.raises(ParseError) as software_error:
        AgilentChemStationChV181Adapter().parse(
            _write(tmp_path / "FID1A.CH", bytes(bad_software)), ParseOptions()
        )
    assert software_error.value.code == "AGILENT_CH_HEADER_INVALID"

    control_sample = bytearray(synthetic_v181_bytes())
    sample = "sample\x00"
    control_sample[858] = len(sample)
    control_sample[859 : 859 + len(sample) * 2] = sample.encode("utf-16-le")
    bundle = AgilentChemStationChV181Adapter().parse(
        _write(tmp_path / "FID1A.CH", bytes(control_sample)), ParseOptions()
    )
    assert bundle.samples[0].sample_id == "FID1A"
    statuses = {entry.key: entry.value for entry in bundle.metadata}
    assert statuses["sample_text_bytes_hex"] == sample.encode("utf-16-le").hex()
    assert "AGILENT_CH_V181_SAMPLE_TEXT_UNSAFE" in {issue.code for issue in bundle.warnings}

    blank_sample = bytearray(synthetic_v181_bytes())
    sample = "   "
    blank_sample[858] = len(sample)
    blank_sample[859 : 859 + len(sample) * 2] = sample.encode("utf-16-le")
    bundle = AgilentChemStationChV181Adapter().parse(
        _write(tmp_path / "FID1A.CH", bytes(blank_sample)), ParseOptions()
    )
    assert bundle.samples[0].sample_id == "FID1A"
    statuses = {entry.key: entry.value for entry in bundle.metadata}
    assert statuses["sample_text_bytes_hex"] == sample.encode("utf-16-le").hex()
    assert "AGILENT_CH_V181_SAMPLE_TEXT_UNSAFE" in {issue.code for issue in bundle.warnings}


@pytest.mark.parametrize(
    ("offset", "raw"),
    (
        (282, struct.pack(">f", float("nan"))),
        (286, struct.pack(">f", float("inf"))),
        (4724, struct.pack(">d", float("-inf"))),
        (4732, bytes.fromhex("7ff8000000000001")),
    ),
)
def test_nonfinite_candidate_header_values_are_rejected(
    tmp_path: Path, offset: int, raw: bytes
) -> None:
    data = bytearray(synthetic_v181_bytes())
    data[offset : offset + len(raw)] = raw
    with pytest.raises(ParseError) as caught:
        AgilentChemStationChV181Adapter().parse(
            _write(tmp_path / "FID1A.CH", bytes(data)), ParseOptions()
        )
    assert caught.value.code == "AGILENT_CH_HEADER_INVALID"


def test_candidate_relative_recurrence_is_deterministic_and_warned(tmp_path: Path) -> None:
    data = synthetic_v181_bytes(records=(("absolute", 100), ("relative", 2), ("relative", -1)))
    bundle = AgilentChemStationChV181Adapter().parse(
        _write(tmp_path / "FID1A.CH", data), ParseOptions()
    )
    assert bundle.signals[0].y_values == (100, 102, 103)
    assert "AGILENT_CH_V181_DELTA_RECURRENCE_UNVERIFIED" in {
        issue.code for issue in bundle.warnings
    }


@pytest.mark.parametrize(
    ("data", "code"),
    (
        (
            synthetic_v181_bytes(version_text="180", numeric_version=180),
            "AGILENT_CH_VERSION_UNSUPPORTED",
        ),
        (
            synthetic_v181_bytes(version_text="181", numeric_version=180),
            "AGILENT_CH_VERSION_CONFLICT",
        ),
        (synthetic_v181_bytes(data_page=12), "AGILENT_CH_PAYLOAD_OFFSET_INVALID"),
        (synthetic_v181_bytes(records=()), "AGILENT_CH_PAYLOAD_MISSING"),
        (b"short", "AGILENT_CH_HEADER_TRUNCATED"),
    ),
)
def test_structural_header_failures_are_actionable(tmp_path: Path, data: bytes, code: str) -> None:
    path = _write(tmp_path / "FID1A.CH", data)
    with pytest.raises(ParseError) as caught:
        AgilentChemStationChV181Adapter().parse(path, ParseOptions())
    assert caught.value.code == code


def test_required_gc_marker_and_metadata_encoding_are_validated(tmp_path: Path) -> None:
    bad_marker = bytearray(synthetic_v181_bytes())
    bad_marker[348:370] = "NOT GC DATA".encode("utf-16-le")
    with pytest.raises(ParseError) as marker_error:
        AgilentChemStationChV181Adapter().parse(
            _write(tmp_path / "FID1A.CH", bytes(bad_marker)), ParseOptions()
        )
    assert marker_error.value.code == "AGILENT_CH_HEADER_INVALID"

    bad_text = bytearray(synthetic_v181_bytes())
    bad_text[858] = 1
    bad_text[859:861] = b"\x00\xd8"
    with pytest.raises(ParseError) as text_error:
        AgilentChemStationChV181Adapter().parse(
            _write(tmp_path / "FID1A.CH", bytes(bad_text)), ParseOptions()
        )
    assert text_error.value.code == "AGILENT_CH_TEXT_ENCODING_INVALID"


def test_truncated_absolute_record_and_unmatched_byte_are_rejected(tmp_path: Path) -> None:
    base = synthetic_v181_bytes(records=(("absolute", 100),))
    for _name, data, expected in (
        ("marker", base[:-1], "AGILENT_CH_PAYLOAD_TRUNCATED"),
        ("odd", synthetic_v181_bytes(trailing=b"\x00"), "AGILENT_CH_FILE_LENGTH_MISMATCH"),
    ):
        with pytest.raises(ParseError) as caught:
            AgilentChemStationChV181Adapter().parse(
                _write(tmp_path / "FID1A.CH", data), ParseOptions()
            )
        assert caught.value.code == expected


def test_relative_record_before_absolute_and_integer_overflow_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = synthetic_v181_bytes(records=(("relative", 1),))
    overflow = synthetic_v181_bytes(records=(("absolute", 100), ("relative", 1)))
    with pytest.raises(ParseError) as relative_error:
        AgilentChemStationChV181Adapter().parse(
            _write(tmp_path / "FID1A.CH", relative), ParseOptions()
        )
    assert relative_error.value.code == "AGILENT_CH_HEADER_INVALID"

    monkeypatch.setattr(records_module, "MAX_I64", 100)
    with pytest.raises(ParseError) as overflow_error:
        AgilentChemStationChV181Adapter().parse(
            _write(tmp_path / "FID1A.CH", overflow), ParseOptions()
        )
    assert overflow_error.value.code == "AGILENT_CH_INTEGER_OVERFLOW"


def test_record_limit_is_enforced_before_unbounded_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(records_module, "MAX_DECODED_RECORDS", 1)
    path = _write(tmp_path / "FID1A.CH")
    with pytest.raises(ParseError) as caught:
        AgilentChemStationChV181Adapter().parse(path, ParseOptions())
    assert caught.value.code == "AGILENT_CH_RECORD_LIMIT"


def test_exact_big_endian_absolute_encoding_supports_negative_values(tmp_path: Path) -> None:
    data = synthetic_v181_bytes(records=(("absolute", -5),))
    bundle = AgilentChemStationChV181Adapter().parse(
        _write(tmp_path / "FID1A.CH", data), ParseOptions()
    )
    assert bundle.signals[0].y_values == (-5,)
    statuses = {entry.key: entry.value for entry in bundle.metadata}
    assert statuses["ambiguous_final_zero_ordinary_record_included"] is False
    assert struct.unpack(">h", data[6144:6146])[0] == 0x7FFF
