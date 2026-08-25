from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from ordifile.adapters import _shimadzu_labsolutions_result_ascii as reader
from ordifile.adapters.base import ParseOptions, SourceIdentityPolicy, SupportStatus
from ordifile.adapters.shimadzu_labsolutions_result_ascii import (
    ShimadzuLabsolutionsResultAsciiAdapter,
)
from ordifile.core.errors import ParseError

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_shimadzu_labsolutions_result_ascii import (  # noqa: E402
    synthetic_result_ascii_bytes,
)


def _write(path: Path, data: bytes | None = None) -> Path:
    path.write_bytes(synthetic_result_ascii_bytes() if data is None else data)
    return path


def _replace(data: bytes, old: bytes, new: bytes) -> bytes:
    assert data.count(old) == 1
    return data.replace(old, new, 1)


def _parse_error(tmp_path: Path, data: bytes, code: str) -> None:
    with pytest.raises(ParseError) as caught:
        ShimadzuLabsolutionsResultAsciiAdapter().parse(
            _write(tmp_path / "private-result.txt", data), ParseOptions()
        )
    assert caught.value.code == code


def test_descriptor_probe_and_uppercase_extension_are_exact(tmp_path: Path) -> None:
    adapter = ShimadzuLabsolutionsResultAsciiAdapter()
    descriptor = adapter.descriptor
    assert descriptor.adapter_id == "shimadzu_labsolutions_result_ascii"
    assert descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert descriptor.source_identity_policy is SourceIdentityPolicy.SHA256_ALIAS
    assert descriptor.peaks and descriptor.metadata and not descriptor.signals
    assert descriptor.series_kinds == ()
    valid = _write(tmp_path / "private-result.TXT")
    assert adapter.probe(valid).matched
    assert adapter.probe(valid).confidence == pytest.approx(0.99)
    assert not adapter.probe(_write(tmp_path / "private-result.asc")).matched


def test_identified_family_with_unsupported_profile_blocks_generic_fallthrough(
    tmp_path: Path,
) -> None:
    adapter = ShimadzuLabsolutionsResultAsciiAdapter()
    unsupported = _write(
        tmp_path / "unsupported.txt",
        synthetic_result_ascii_bytes(software_version="5.81"),
    )
    result = adapter.probe(unsupported)
    assert result.matched
    assert result.confidence == pytest.approx(0.70)
    assert not result.routable
    assert result.failure_code == "SHIMADZU_RESULT_ASCII_PROFILE_UNSUPPORTED"


def test_parse_preserves_source_peak_number_order_and_unknown_response_units(
    tmp_path: Path,
) -> None:
    data = synthetic_result_ascii_bytes()
    path = _write(tmp_path / "private-person-result.txt", data)
    bundle = ShimadzuLabsolutionsResultAsciiAdapter().parse(path, ParseOptions())

    assert bundle.signals == ()
    assert bundle.samples[0].instrument.vendor == "Shimadzu"
    assert bundle.samples[0].instrument.instrument_type == "GC"
    assert bundle.samples[0].detectors == ("FID",)
    assert bundle.samples[0].channels == ("Ch1",)
    assert bundle.samples[0].sample_id.startswith("SHIMADZU_RESULT_")
    assert bundle.sources[0].sha256 == hashlib.sha256(data).hexdigest()
    assert tuple(peak.peak_number for peak in bundle.peaks) == (1, 2, 3)
    assert tuple(peak.observation_order for peak in bundle.peaks) == (1, 2, 3)
    assert tuple(peak.retention_time for peak in bundle.peaks) == (1.25, 2.5, 3.75)
    assert tuple(peak.start_time for peak in bundle.peaks) == (1.2, 2.45, 3.7)
    assert tuple(peak.end_time for peak in bundle.peaks) == (1.3, 2.55, 3.8)
    assert tuple(peak.area for peak in bundle.peaks) == (100.5, 200.75, 300.0)
    assert tuple(peak.height for peak in bundle.peaks) == (10.25, 20.5, 30.0)
    assert all(peak.retention_time_unit == "min" for peak in bundle.peaks)
    assert all(peak.area_unit is None and peak.height_unit is None for peak in bundle.peaks)
    assert all(peak.compound is None and peak.compound_source is None for peak in bundle.peaks)
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["software_version"] == "5.82"
    assert metadata["instrument_model"] == "GC-2014"
    assert metadata["source_detector_label"] == "SFID1"
    assert metadata["canonical_detector"] == "FID"
    assert metadata["peak_count"] == 3
    assert metadata["area_unit_status"] == "unresolved"
    assert not any(
        private in str(value)
        for entry in bundle.metadata
        for value in (entry.key, entry.value, entry.source_file)
        for private in ("private-person-result", "synthetic.gcd", "synthetic")
    )


def test_variable_positive_peak_count_is_supported(tmp_path: Path) -> None:
    peaks = (("1.0", "2", "3", "0.9", "1.1"),)
    bundle = ShimadzuLabsolutionsResultAsciiAdapter().parse(
        _write(tmp_path / "one.txt", synthetic_result_ascii_bytes(peaks=peaks)),
        ParseOptions(),
    )
    assert len(bundle.peaks) == 1
    assert bundle.peaks[0].peak_number == 1


@pytest.mark.parametrize(
    "kwargs",
    (
        {"application_name": "Other"},
        {"software_version": "5.81"},
        {"file_type": "Method File"},
        {"instrument_model": "GC-2030"},
        {"detector_count": "2"},
        {"detector_id": "DET#2"},
        {"detector_name": "STCD1"},
        {"channel_count": "2"},
    ),
)
def test_other_producers_instruments_detectors_and_channels_are_rejected(
    tmp_path: Path, kwargs: dict[str, object]
) -> None:
    _parse_error(
        tmp_path,
        synthetic_result_ascii_bytes(**kwargs),  # type: ignore[arg-type]
        "SHIMADZU_RESULT_ASCII_PROFILE_UNSUPPORTED",
    )


def test_deployment_numbers_and_positive_sampling_interval_are_not_profile_constants(
    tmp_path: Path,
) -> None:
    bundle = ShimadzuLabsolutionsResultAsciiAdapter().parse(
        _write(
            tmp_path / "deployment-values.txt",
            synthetic_result_ascii_bytes(
                instrument_number="7",
                line_number="3",
                interval_ms="80",
            ),
        ),
        ParseOptions(),
    )

    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["same_file_chromatogram_interval"] == 80
    assert "instrument_number" not in metadata
    assert "line_number" not in metadata


@pytest.mark.parametrize(
    ("kwargs", "code"),
    (
        ({"declared_peak_count": 4}, "SHIMADZU_RESULT_ASCII_PEAK_COUNT_MISMATCH"),
        ({"declared_peak_count": 0}, "SHIMADZU_RESULT_ASCII_COUNT_INVALID"),
        ({"declared_point_count": 5}, "SHIMADZU_RESULT_ASCII_CHROMATOGRAM_COUNT_MISMATCH"),
        ({"id_number": "1"}, "SHIMADZU_RESULT_ASCII_IDENTIFICATION_UNSUPPORTED"),
        ({"compound_name": "invented"}, "SHIMADZU_RESULT_ASCII_IDENTIFICATION_UNSUPPORTED"),
    ),
)
def test_counts_and_unverified_identification_are_rejected(
    tmp_path: Path, kwargs: dict[str, object], code: str
) -> None:
    _parse_error(
        tmp_path,
        synthetic_result_ascii_bytes(**kwargs),  # type: ignore[arg-type]
        code,
    )


@pytest.mark.parametrize(
    ("peaks", "code"),
    (
        ((), "SHIMADZU_RESULT_ASCII_COUNT_INVALID"),
        (
            (("2", "1", "1", "1.9", "2.1"), ("1", "2", "2", "0.9", "1.1")),
            "SHIMADZU_RESULT_ASCII_RETENTION_ORDER_INVALID",
        ),
        ((("1", "2", "3", "1.1", "1.2"),), "SHIMADZU_RESULT_ASCII_PEAK_BOUNDARY_INVALID"),
        ((("NaN", "2", "3", "0", "4"),), "SHIMADZU_RESULT_ASCII_NUMBER_INVALID"),
        ((("1", "-2", "3", "0", "4"),), "SHIMADZU_RESULT_ASCII_RESPONSE_INVALID"),
        (
            (("1", "1.0000000000000000001", "3", "0", "4"),),
            "SHIMADZU_RESULT_ASCII_LOSSY_FLOAT",
        ),
    ),
)
def test_scientific_values_are_bounded_ordered_and_lossless(
    tmp_path: Path,
    peaks: tuple[tuple[str, str, str, str, str], ...],
    code: str,
) -> None:
    _parse_error(tmp_path, synthetic_result_ascii_bytes(peaks=peaks), code)


def test_source_peak_numbers_must_be_contiguous(tmp_path: Path) -> None:
    data = synthetic_result_ascii_bytes()
    changed = _replace(data, b"\r\n2\t2.50\t", b"\r\n3\t2.50\t")
    _parse_error(tmp_path, changed, "SHIMADZU_RESULT_ASCII_PEAK_ORDER_INVALID")


def test_peak_times_must_fit_same_file_chromatogram_range(tmp_path: Path) -> None:
    _parse_error(
        tmp_path,
        synthetic_result_ascii_bytes(chromatogram_end="1.000"),
        "SHIMADZU_RESULT_ASCII_PEAK_RANGE_INVALID",
    )


@pytest.mark.parametrize(
    ("change", "code"),
    (
        (
            lambda data: data[:-2],
            "SHIMADZU_RESULT_ASCII_LINE_ENDING_INVALID",
        ),
        (
            lambda data: data.replace(b"\r\n", b"\n"),
            "SHIMADZU_RESULT_ASCII_LINE_ENDING_INVALID",
        ),
        (
            lambda data: b"\xef\xbb\xbf" + data,
            "SHIMADZU_RESULT_ASCII_ENCODING_UNSUPPORTED",
        ),
        (
            lambda data: _replace(
                data,
                b"[Compound Results(Ch1)]",
                b"[Peak Table(Ch2)]\r\n# of Peaks\t1\r\ninvalid\r\n\r\n[Compound Results(Ch1)]",
            ),
            "SHIMADZU_RESULT_ASCII_SECTION_INVALID",
        ),
        (
            lambda data: data + b"unexpected\r\n\r\n",
            "SHIMADZU_RESULT_ASCII_CHROMATOGRAM_COUNT_MISMATCH",
        ),
    ),
)
def test_truncated_encoding_multisection_and_appended_inputs_are_rejected(
    tmp_path: Path,
    change: object,
    code: str,
) -> None:
    transform = change
    assert callable(transform)
    _parse_error(tmp_path, transform(synthetic_result_ascii_bytes()), code)


def test_bounded_read_rejects_oversize_before_unbounded_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path / "large.txt")
    monkeypatch.setattr(reader, "MAX_RESULT_ASCII_BYTES", len(path.read_bytes()) - 1)
    with pytest.raises(reader.ShimadzuResultAsciiStructureError) as caught:
        reader.read_result_ascii(path)
    assert caught.value.code == "SHIMADZU_RESULT_ASCII_SIZE_INVALID"


def test_line_count_is_rejected_before_record_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path / "many-lines.txt")
    monkeypatch.setattr(reader, "MAX_RESULT_ASCII_LINES", 10)
    with pytest.raises(reader.ShimadzuResultAsciiStructureError) as caught:
        reader.read_result_ascii(path)
    assert caught.value.code == "SHIMADZU_RESULT_ASCII_LINE_LIMIT"
