from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from ordifile.adapters import _leco_chromatof_472_gcgc_result_txt as reader
from ordifile.adapters.base import ParseOptions, SourceIdentityPolicy, SupportStatus
from ordifile.adapters.leco_chromatof_472_gcgc_result_txt import (
    LecoChromatof472GcgcResultTxtAdapter,
)
from ordifile.core.errors import ParseError
from ordifile.core.validation import validate_bundle

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_leco_chromatof_472_gcgc_result_txt import (  # noqa: E402
    synthetic_gcgc_result_bytes,
)


def _write(path: Path, data: bytes | None = None) -> Path:
    path.write_bytes(synthetic_gcgc_result_bytes() if data is None else data)
    return path


def _replace(data: bytes, old: bytes, new: bytes) -> bytes:
    assert data.count(old) == 1
    return data.replace(old, new, 1)


def _parse_error(tmp_path: Path, data: bytes, code: str) -> None:
    with pytest.raises(ParseError) as caught:
        LecoChromatof472GcgcResultTxtAdapter().parse(
            _write(tmp_path / "private-result.txt", data), ParseOptions()
        )
    assert caught.value.code == code


def test_descriptor_probe_and_exact_profile_detection(tmp_path: Path) -> None:
    adapter = LecoChromatof472GcgcResultTxtAdapter()
    descriptor = adapter.descriptor
    assert descriptor.adapter_id == "leco_chromatof_gcxgc_result_txt"
    assert descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert descriptor.source_identity_policy is SourceIdentityPolicy.SHA256_ALIAS
    assert descriptor.metadata and descriptor.peaks and not descriptor.signals
    assert descriptor.series_kinds == ()

    valid = _write(tmp_path / "private-result.txt")
    assert adapter.probe(valid).matched
    assert adapter.probe(valid).confidence == pytest.approx(0.99)
    assert not adapter.probe(_write(tmp_path / "renamed.tsv")).matched
    ordinary = _write(
        tmp_path / "ordinary.txt",
        b"sample_id\tretention_time\tarea\r\ngeneric\t1\t2\r\n",
    )
    assert not adapter.probe(ordinary).matched


def test_recognized_malformed_family_remains_owned(tmp_path: Path) -> None:
    data = synthetic_gcgc_result_bytes().replace(b"1st Dimension Time (s)", b"retention_time", 1)
    result = LecoChromatof472GcgcResultTxtAdapter().probe(
        _write(tmp_path / "private-malformed.txt", data)
    )
    assert result.matched
    assert result.confidence == pytest.approx(0.70)


def test_multiple_damaged_headers_still_retain_private_family_ownership(
    tmp_path: Path,
) -> None:
    data = synthetic_gcgc_result_bytes()
    for old, new in (
        (b"1st Dimension Time (s)", b"retention_time"),
        (b"2nd Dimension Time (s)", b"secondary_time"),
        (b"Spectra", b"signal_pairs"),
        (b"Retention Index", b"index"),
    ):
        data = data.replace(old, new, 1)

    result = LecoChromatof472GcgcResultTxtAdapter().probe(
        _write(tmp_path / "private-multiple-damage.txt", data)
    )

    assert result.matched
    assert result.confidence == pytest.approx(0.70)


def test_common_result_headers_without_a_gcgc_anchor_are_not_owned(tmp_path: Path) -> None:
    data = (
        b"sample_id\tretention_time\tName\tArea\tHeight\tSpectra\tRetention Index\r\n"
        b"ordinary\t1\tPeak A\t2\t3\t4:5\t100\r\n"
    )

    result = LecoChromatof472GcgcResultTxtAdapter().probe(
        _write(tmp_path / "ordinary-five-common-markers.txt", data)
    )

    assert not result.matched


def test_parse_preserves_two_coordinates_responses_names_and_extra_columns(
    tmp_path: Path,
) -> None:
    data = synthetic_gcgc_result_bytes()
    bundle = LecoChromatof472GcgcResultTxtAdapter().parse(
        _write(tmp_path / "private-owner-result.txt", data), ParseOptions()
    )

    assert validate_bundle(bundle) == ()
    assert bundle.signals == ()
    assert bundle.samples[0].instrument.vendor == "LECO"
    assert bundle.samples[0].instrument.instrument_type == "GCxGC"
    assert bundle.samples[0].channels == ()
    assert bundle.samples[0].detectors == ()
    assert bundle.sources[0].sha256 == hashlib.sha256(data).hexdigest()
    assert tuple(peak.peak_number for peak in bundle.peaks) == (None, None, None)
    assert tuple(peak.observation_order for peak in bundle.peaks) == (1, 2, 3)
    assert tuple(peak.retention_time for peak in bundle.peaks) == (120.0, 180.0, 240.0)
    assert tuple(peak.secondary_retention_time for peak in bundle.peaks) == (
        0.45,
        0.875,
        1.25,
    )
    assert tuple(peak.area for peak in bundle.peaks) == (100_000.0, 250_000.0, 400_000.0)
    assert tuple(peak.height for peak in bundle.peaks) == (5_000.0, 12_000.0, 18_000.0)
    assert tuple(peak.compound for peak in bundle.peaks) == (
        "Synthetic Alpha",
        "Synthetic Beta",
        "Synthetic Gamma",
    )
    assert all(
        peak.compound_source == "canonical:leco_chromatof_gcxgc_result_txt.name"
        for peak in bundle.peaks
    )
    assert all(peak.retention_time_unit == "s" for peak in bundle.peaks)
    assert all(peak.secondary_retention_time_unit == "s" for peak in bundle.peaks)
    assert all(peak.area_unit == "AU" and peak.height_unit == "AU" for peak in bundle.peaks)
    assert all(
        peak.detector is None
        and peak.channel is None
        and peak.start_time is None
        and peak.end_time is None
        for peak in bundle.peaks
    )
    metadata = {entry.key: entry for entry in bundle.metadata}
    assert metadata["profile_version_provenance"].value == "external_dataset_not_embedded"
    assert metadata["peak_000001_name"].value == "Synthetic Alpha"
    assert metadata["peak_000001_spectra"].value == "43:999 58:250"
    assert metadata["peak_000001_wb1"].value == "8"
    assert metadata["peak_000001_wb2"].value == "0.120"
    assert metadata["peak_000001_retention_index"].value == "850.0"
    assert metadata["peak_000001_spectra"].source is not None


def test_unknown_name_is_preserved_but_not_promoted_to_compound(tmp_path: Path) -> None:
    data = _replace(synthetic_gcgc_result_bytes(), b"Synthetic Alpha", b"Unknown")
    bundle = LecoChromatof472GcgcResultTxtAdapter().parse(
        _write(tmp_path / "unknown.txt", data), ParseOptions()
    )

    assert bundle.peaks[0].compound is None
    assert bundle.peaks[0].compound_source is None
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["peak_000001_name"] == "Unknown"


def test_auxiliary_decimals_remain_exact_lexemes_without_float_round_trip(
    tmp_path: Path,
) -> None:
    precise = "0.1200000000000000001"
    data = _replace(
        synthetic_gcgc_result_bytes(), b"\t0.120\t850.0", f"\t{precise}\t850.0".encode()
    )
    bundle = LecoChromatof472GcgcResultTxtAdapter().parse(
        _write(tmp_path / "precise-metadata.txt", data), ParseOptions()
    )

    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["peak_000001_wb2"] == precise


@pytest.mark.parametrize(
    ("old", "new", "code"),
    (
        (b"\t120\t0.450\t", b"\tNaN\t0.450\t", "LECO_GCGC_RESULT_NUMBER_INVALID"),
        (b"\t0.450\t100000\t", b"\tInf\t100000\t", "LECO_GCGC_RESULT_NUMBER_INVALID"),
        (b"\t100000\t5000\t", b"\t-1\t5000\t", "LECO_GCGC_RESULT_NUMBER_INVALID"),
        (b"\t5000\t43:999", b"\t1e400\t43:999", "LECO_GCGC_RESULT_NUMBER_INVALID"),
        (b"\t0.450\t", b"\t0.1234567890123456789\t", "LECO_GCGC_RESULT_LOSSY_FLOAT"),
        (b"43:999 58:250", b"invalid spectrum", "LECO_GCGC_RESULT_SPECTRUM_INVALID"),
        (b"Synthetic Alpha", b"", "LECO_GCGC_RESULT_FIELD_INVALID"),
    ),
)
def test_scientific_fields_are_strict(tmp_path: Path, old: bytes, new: bytes, code: str) -> None:
    _parse_error(tmp_path, _replace(synthetic_gcgc_result_bytes(), old, new), code)


@pytest.mark.parametrize(
    ("transform", "code"),
    (
        (lambda data: data[:-1], "LECO_GCGC_RESULT_LINE_ENDING_INVALID"),
        (lambda data: data.replace(b"\r\n", b"\n"), "LECO_GCGC_RESULT_LINE_ENDING_INVALID"),
        (lambda data: b"\xef\xbb\xbf" + data, "LECO_GCGC_RESULT_ENCODING_UNSUPPORTED"),
        (
            lambda data: data.replace(b"Name", b"N\x00me", 1),
            "LECO_GCGC_RESULT_ENCODING_UNSUPPORTED",
        ),
        (
            lambda data: data.replace(b"1st Dimension Time (s)", b"Retention Time", 1),
            "LECO_GCGC_RESULT_HEADER_INVALID",
        ),
        (
            lambda data: data.replace(b"\tRetention Index\r\n", b"\r\n", 1),
            "LECO_GCGC_RESULT_HEADER_INVALID",
        ),
        (
            lambda data: data.replace(b"\t850.0\r\n", b"\r\n", 1),
            "LECO_GCGC_RESULT_ROW_INVALID",
        ),
        (lambda data: data + b"unexpected\r\n", "LECO_GCGC_RESULT_ROW_INVALID"),
        (
            lambda data: data.split(b"\r\n", 1)[0] + b"\r\n",
            "LECO_GCGC_RESULT_EMPTY",
        ),
    ),
)
def test_encoding_header_shape_empty_and_truncation_are_rejected(
    tmp_path: Path, transform: object, code: str
) -> None:
    assert callable(transform)
    _parse_error(tmp_path, transform(synthetic_gcgc_result_bytes()), code)


def test_bounded_read_line_and_peak_limits_apply_before_unbounded_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path / "bounded.txt")
    monkeypatch.setattr(reader, "MAX_RESULT_BYTES", len(path.read_bytes()) - 1)
    with pytest.raises(reader.LecoGcgcResultStructureError) as caught:
        reader.read_gcgc_result(path)
    assert caught.value.code == "LECO_GCGC_RESULT_SIZE_INVALID"

    monkeypatch.setattr(reader, "MAX_RESULT_BYTES", 32 * 1024 * 1024)
    monkeypatch.setattr(reader, "MAX_RESULT_LINES", 2)
    with pytest.raises(reader.LecoGcgcResultStructureError) as caught:
        reader.read_gcgc_result(path)
    assert caught.value.code == "LECO_GCGC_RESULT_LINE_LIMIT"

    monkeypatch.setattr(reader, "MAX_RESULT_LINES", 100_001)
    monkeypatch.setattr(reader, "MAX_PEAKS", 2)
    with pytest.raises(reader.LecoGcgcResultStructureError) as caught:
        reader.read_gcgc_result(path)
    assert caught.value.code == "LECO_GCGC_RESULT_PEAK_LIMIT"


def test_extension_is_required_for_forced_parse(tmp_path: Path) -> None:
    with pytest.raises(ParseError) as caught:
        LecoChromatof472GcgcResultTxtAdapter().parse(
            _write(tmp_path / "renamed.tsv"), ParseOptions()
        )
    assert caught.value.code == "LECO_GCGC_RESULT_EXTENSION_INVALID"
