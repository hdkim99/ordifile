from __future__ import annotations

import hashlib
import math
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ordifile.adapters.base import ParseOptions, SupportStatus
from ordifile.adapters.shimadzu_gcsolution_gcd import ShimadzuGcsolutionGcdAdapter
from ordifile.core.errors import ParseError
from ordifile.core.models import SeriesKind

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_cfb_v4 import SECTOR_BYTES, build_cfb_v4  # noqa: E402
from generate_shimadzu_gcsolution_gcd import (  # noqa: E402
    synthetic_gcd_bytes,
    synthetic_gcd_streams,
    synthetic_peak_table,
)

# One CFB sector is 4,096 B, so a synthetic peak-table stream needs at least six
# 792 B records to be storable as a regular stream.
STORED_ROWS = (
    (110_580, 106_440, 112_560, 2042.3048071317419, 505.024730795506),
    (115_560, 112_560, 119_880, 2333.0625, 369.5),
) + tuple(
    (200_000 + 5_000 * step, 199_000 + 5_000 * step, 204_000 + 5_000 * step, 10.0 + step, 2.0)
    for step in range(4)
)


def _write(path: Path, data: bytes | None = None) -> Path:
    path.write_bytes(synthetic_gcd_bytes() if data is None else data)
    return path


def _parse_error(path: Path) -> ParseError:
    with pytest.raises(ParseError) as caught:
        ShimadzuGcsolutionGcdAdapter().parse(path, ParseOptions())
    return caught.value


def test_descriptor_declares_exact_experimental_scientific_profile() -> None:
    descriptor = ShimadzuGcsolutionGcdAdapter.descriptor
    assert descriptor.adapter_id == "shimadzu_gcsolution_gcd"
    assert descriptor.extensions == (".gcd",)
    assert descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert descriptor.series_kinds == (SeriesKind.SCIENTIFIC_SIGNAL,)
    assert descriptor.signals
    assert not descriptor.peaks


def test_probe_requires_extension_and_exact_profile(tmp_path: Path) -> None:
    adapter = ShimadzuGcsolutionGcdAdapter()
    source = _write(tmp_path / "sample.GCD")
    result = adapter.probe(source)
    assert result.matched
    assert result.confidence == pytest.approx(0.99)
    assert "5.82" in result.reason
    assert not adapter.probe(_write(tmp_path / "sample.bin")).matched


def test_probe_does_not_claim_an_unrelated_compound_file(tmp_path: Path) -> None:
    unrelated = _write(
        tmp_path / "renamed-office.gcd",
        build_cfb_v4({("WordDocument",): b"unrelated".ljust(SECTOR_BYTES, b" ")}),
    )
    assert not ShimadzuGcsolutionGcdAdapter().probe(unrelated).matched


def test_probe_preserves_structured_match_for_identified_unsupported_profile(
    tmp_path: Path,
) -> None:
    unsupported = _write(
        tmp_path / "unsupported.gcd",
        synthetic_gcd_bytes(software_version="5.81"),
    )
    result = ShimadzuGcsolutionGcdAdapter().probe(unsupported)
    assert result.matched
    assert result.confidence == pytest.approx(0.70)
    assert not result.routable
    assert result.failure_code == "SHIMADZU_GCD_PROFILE_UNSUPPORTED"


def test_parse_returns_uninterpolated_retention_time_and_stored_uv_values(
    tmp_path: Path,
) -> None:
    values = tuple(1.25 + index / 8 for index in range(512))
    path = _write(
        tmp_path / "sample.gcd",
        synthetic_gcd_bytes(
            sample_name="display_sample",
            sample_id="sample-007",
            values=values,
        ),
    )
    bundle = ShimadzuGcsolutionGcdAdapter().parse(path, ParseOptions())

    assert bundle.samples[0].sample_id == "sample-007"
    assert bundle.samples[0].instrument.vendor == "Shimadzu"
    assert bundle.samples[0].channels == ("Ch1",)
    assert bundle.samples[0].detectors == ("FID",)
    assert bundle.samples[0].runtime == pytest.approx(512 * 40 / 60_000)
    assert bundle.samples[0].acquired_at == datetime(2024, 1, 1, tzinfo=UTC)
    assert bundle.samples[0].acquired_at_reliable is True
    assert bundle.peaks == ()
    signal = bundle.signals[0]
    assert signal.series_kind is SeriesKind.SCIENTIFIC_SIGNAL
    assert signal.x_values[0] == pytest.approx(20 / 60_000)
    assert signal.x_values[1] == pytest.approx(60 / 60_000)
    assert signal.x_values[-1] == pytest.approx((20 + 511 * 40) / 60_000)
    assert signal.y_values == values
    assert signal.x_label == "retention_time"
    assert signal.x_unit == "min"
    assert signal.y_label == "detector_response"
    assert signal.y_unit == "uV"
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["file_property_schema"] == "5.01"
    assert metadata["software_version"] == "5.82"
    assert metadata["sample_name"] == "display_sample"
    assert metadata["sampling_interval"] == 40
    assert metadata["correction_factor"] == 1.0
    assert metadata["timestamp_status"] == "verified_utc_filetime"
    assert metadata["instrument_model"] == "GC-2014"
    assert metadata["sample_name_bytes_hex"] == "display_sample".encode("ascii").hex()
    expected_time_hash = hashlib.sha256(
        b"".join(struct.pack(">d", value) for value in signal.x_values)
    ).hexdigest()
    expected_signal_hash = hashlib.sha256(
        b"".join(struct.pack(">d", value) for value in values)
    ).hexdigest()
    expected_pair_hash = hashlib.sha256(
        b"".join(
            struct.pack(">dd", x_value, y_value)
            for x_value, y_value in zip(signal.x_values, values, strict=True)
        )
    ).hexdigest()
    assert metadata["time_canonical_be_f64_sha256"] == expected_time_hash
    assert metadata["signal_canonical_be_f64_sha256"] == expected_signal_hash
    assert metadata["time_signal_pairs_be_f64_sha256"] == expected_pair_hash
    assert {issue.code for issue in bundle.warnings} == {"SHIMADZU_GCD_EXPERIMENTAL_PROFILE"}


def test_wrong_extension_and_invalid_magic_are_structured(tmp_path: Path) -> None:
    wrong_extension = _write(tmp_path / "sample.dat")
    assert _parse_error(wrong_extension).code == "SHIMADZU_GCD_EXTENSION_INVALID"

    invalid = bytearray(synthetic_gcd_bytes())
    invalid[:8] = b"not-cfb!"
    invalid_path = _write(tmp_path / "invalid.gcd", bytes(invalid))
    assert not ShimadzuGcsolutionGcdAdapter().probe(invalid_path).matched
    assert _parse_error(invalid_path).code == "SHIMADZU_GCD_HEADER_INVALID"


@pytest.mark.parametrize(
    "kwargs",
    (
        {"software_version": "5.81"},
        {"file_schema": "5.00"},
        {"system_root_version": "2.0"},
        {"instrument_model": "GC-2030"},
        {"unit": "mV"},
        {"axis_factor": 2.0},
        {"correction_factor": 2.0},
        {"gain_factor": 2.0},
        {"interval_ms": 80},
        {"delay_ms": 0.0},
        {"data_source_id": "GC.1.1.DET.1"},
        {"data_source_name": "STCD1"},
        {"user_data_source_name": "STCD1"},
        {"analysis_trace_name": "[Chromatogram (Ch2)]"},
    ),
)
def test_other_versions_detectors_units_and_scale_profiles_are_rejected(
    tmp_path: Path, kwargs: dict[str, object]
) -> None:
    error = _parse_error(_write(tmp_path / "unsupported.gcd", synthetic_gcd_bytes(**kwargs)))
    assert error.code == "SHIMADZU_GCD_PROFILE_UNSUPPORTED"


def test_missing_and_wrong_case_required_streams_are_rejected(tmp_path: Path) -> None:
    missing = synthetic_gcd_streams()
    del missing[("LSS Raw Data", "2D Data Item U")]
    assert (
        _parse_error(_write(tmp_path / "missing.gcd", build_cfb_v4(missing))).code
        == "SHIMADZU_GCD_PROFILE_UNSUPPORTED"
    )

    wrong_case = synthetic_gcd_bytes(
        path_replacements={("LSS Raw Data", "2D Data Item U"): ("LSS Raw Data", "2d Data Item U")}
    )
    assert (
        _parse_error(_write(tmp_path / "wrong-case.gcd", wrong_case)).code
        == "SHIMADZU_GCD_PROFILE_UNSUPPORTED"
    )


def test_multichannel_profile_is_rejected(tmp_path: Path) -> None:
    data = synthetic_gcd_bytes(extra_ch2_values=tuple(float(index) for index in range(512)))
    assert (
        _parse_error(_write(tmp_path / "multi.gcd", data)).code
        == "SHIMADZU_GCD_PROFILE_UNSUPPORTED"
    )


@pytest.mark.parametrize(
    "data",
    (
        synthetic_gcd_bytes()[:100],
        synthetic_gcd_bytes()[:-1],
    ),
)
def test_truncated_container_is_rejected(tmp_path: Path, data: bytes) -> None:
    assert _parse_error(_write(tmp_path / "truncated.gcd", data)).code == "SHIMADZU_GCD_TRUNCATED"


def test_truncated_signal_stream_inside_valid_container_is_rejected(tmp_path: Path) -> None:
    streams = synthetic_gcd_streams()
    signal_path = ("LSS Raw Data", "Chromatogram Ch1")
    streams[signal_path] = streams[signal_path][:-8]
    error = _parse_error(_write(tmp_path / "truncated-signal.gcd", build_cfb_v4(streams)))
    assert error.code == "SHIMADZU_GCD_SIGNAL_BLOCK_INVALID"


@pytest.mark.parametrize(
    "kwargs",
    (
        {"signal_magic": 17_235},
        {"signal_interval_ms": 41},
        {"encoded_point_count": 513},
        {"encoded_signal_length": 4_102},
        {"acquisition_time_ms": 1.0},
    ),
)
def test_signal_header_count_duration_and_length_mismatch_are_rejected(
    tmp_path: Path, kwargs: dict[str, object]
) -> None:
    error = _parse_error(_write(tmp_path / "bad-signal.gcd", synthetic_gcd_bytes(**kwargs)))
    assert error.code == "SHIMADZU_GCD_SIGNAL_BLOCK_INVALID"


@pytest.mark.parametrize("nonfinite", (math.nan, math.inf, -math.inf))
def test_nonfinite_signal_value_is_rejected(tmp_path: Path, nonfinite: float) -> None:
    values = (nonfinite, *tuple(float(index) for index in range(511)))
    error = _parse_error(_write(tmp_path / "nonfinite.gcd", synthetic_gcd_bytes(values=values)))
    assert error.code == "SHIMADZU_GCD_SIGNAL_BLOCK_INVALID"


def test_malformed_file_property_xml_is_rejected(tmp_path: Path) -> None:
    streams = synthetic_gcd_streams()
    streams[("File Property",)] = b"\x00\x00\x00\x00<not-xml>".ljust(SECTOR_BYTES, b" ")
    error = _parse_error(_write(tmp_path / "bad-metadata.gcd", build_cfb_v4(streams)))
    assert error.code == "SHIMADZU_GCD_PROFILE_UNSUPPORTED"


@pytest.mark.parametrize(
    ("stream_path", "encoding", "needle", "replacement"),
    (
        (
            ("SystemCheckResult", "SystemCheckResult"),
            "utf-8",
            "<SWVersion>5.82</SWVersion>",
            "<SWVersion>5.82</SWVersion><SWVersion>5.82</SWVersion>",
        ),
        (
            ("LSS Raw Data", "2D Data Item U"),
            "utf-16-le",
            '<DII Rev="0" RevSrc="0">',
            '<DII Rev="0" RevSrc="0"></DII><DII Rev="0" RevSrc="0">',
        ),
        (
            ("LSS Raw Data", "2D Data Item U"),
            "utf-16-le",
            "</DDI>",
            "</DDI><DDI></DDI>",
        ),
        (
            ("LSS Raw Data", "2D Data Item U"),
            "utf-16-le",
            '<Axis ID="1" DUS="0">',
            '<Axis ID="1" DUS="0"></Axis><Axis ID="1" DUS="0">',
        ),
        (
            ("LSS Raw Data", "2D Data Item U"),
            "utf-16-le",
            '<US ID="1">',
            '<US ID="1"></US><US ID="1">',
        ),
    ),
)
def test_ambiguous_duplicate_profile_metadata_is_rejected(
    tmp_path: Path,
    stream_path: tuple[str, ...],
    encoding: str,
    needle: str,
    replacement: str,
) -> None:
    streams = synthetic_gcd_streams()
    text = streams[stream_path].decode(encoding)
    assert text.count(needle) == 1
    streams[stream_path] = text.replace(needle, replacement, 1).encode(encoding)

    error = _parse_error(_write(tmp_path / "ambiguous.gcd", build_cfb_v4(streams)))

    assert error.code == "SHIMADZU_GCD_PROFILE_UNSUPPORTED"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("sample_name", "   "),
        ("sample_id", "C:\\private\\sample"),
        ("operator_name", "/Users/private"),
        ("operator_name", "unsafe\x7foperator"),
    ),
)
def test_unsafe_blank_or_absolute_path_source_metadata_is_rejected(
    tmp_path: Path, field: str, value: str
) -> None:
    error = _parse_error(_write(tmp_path / "unsafe.gcd", synthetic_gcd_bytes(**{field: value})))
    assert error.code == "SHIMADZU_GCD_PROFILE_UNSUPPORTED"


def test_stored_peak_table_is_emitted_as_source_explicit_rows(tmp_path: Path) -> None:
    data = synthetic_gcd_bytes(peak_table=synthetic_peak_table(STORED_ROWS))

    bundle = ShimadzuGcsolutionGcdAdapter().parse(
        _write(tmp_path / "stored-peaks.gcd", data), ParseOptions()
    )

    assert len(bundle.peaks) == len(STORED_ROWS)
    peak = bundle.peaks[0]
    assert peak.peak_number == 1
    assert peak.status == "parsed"
    assert peak.retention_time == pytest.approx(110_580 / 60_000)
    assert peak.start_time == pytest.approx(106_440 / 60_000)
    assert peak.end_time == pytest.approx(112_560 / 60_000)
    # The vendor's own stored numbers, not an Ordifile calculation.
    assert peak.area == 2042.3048071317419
    assert peak.height == 505.024730795506
    assert peak.calculated_area is None
    assert peak.data_origin is None
    assert peak.area_unit is None and peak.height_unit is None
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["stored_peak_table_status"] == "matched"
    assert metadata["stored_peak_count"] == len(STORED_ROWS)
    assert metadata["stored_peak_table_revision"] == "0x53"
    assert metadata["area_unit_status"] == "unresolved"
    assert "SHIMADZU_GCD_STORED_PEAK_TABLE" in {issue.code for issue in bundle.warnings}


def test_document_without_a_stored_peak_table_keeps_its_signal(tmp_path: Path) -> None:
    bundle = ShimadzuGcsolutionGcdAdapter().parse(_write(tmp_path / "no-peaks.gcd"), ParseOptions())

    assert bundle.peaks == ()
    assert len(bundle.signals) == 1
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["stored_peak_table_status"] == "absent"
    assert metadata["stored_peak_count"] == 0
    assert "SHIMADZU_GCD_STORED_PEAK_TABLE" not in {issue.code for issue in bundle.warnings}


def test_unsupported_stored_peak_table_preserves_the_signal_without_peaks(
    tmp_path: Path,
) -> None:
    data = synthetic_gcd_bytes(peak_table=synthetic_peak_table(STORED_ROWS, revision=0x11))

    bundle = ShimadzuGcsolutionGcdAdapter().parse(
        _write(tmp_path / "unsupported-peaks.gcd", data), ParseOptions()
    )

    assert bundle.peaks == ()
    assert len(bundle.signals) == 1
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["stored_peak_table_status"] == "invalid"
    assert "SHIMADZU_GCD_PEAK_TABLE_REVISION_UNSUPPORTED" in {
        issue.code for issue in bundle.warnings
    }


def test_multiple_stored_peak_table_streams_fail_closed(tmp_path: Path) -> None:
    streams = synthetic_gcd_streams(peak_table=synthetic_peak_table(STORED_ROWS))
    streams[("LSS Data Processing", "PT-GC.1.1.DET.2.DetCh")] = synthetic_peak_table(STORED_ROWS)

    error = _parse_error(_write(tmp_path / "two-peak-tables.gcd", build_cfb_v4(streams)))

    assert error.code == "SHIMADZU_GCD_PROFILE_UNSUPPORTED"
