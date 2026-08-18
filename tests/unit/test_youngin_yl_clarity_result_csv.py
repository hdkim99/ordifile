from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from ordifile.adapters import _youngin_yl_clarity_result_csv as reader
from ordifile.adapters.base import ParseOptions, SourceIdentityPolicy, SupportStatus
from ordifile.adapters.youngin_yl_clarity_result_csv import (
    YoungInYlClarityResultCsvAdapter,
)
from ordifile.core.errors import ParseError

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_youngin_yl_clarity_result_csv import (  # noqa: E402
    synthetic_result_csv_bytes,
)


def _write(path: Path, data: bytes | None = None) -> Path:
    path.write_bytes(synthetic_result_csv_bytes() if data is None else data)
    return path


def _replace(data: bytes, old: bytes, new: bytes) -> bytes:
    assert data.count(old) == 1
    return data.replace(old, new, 1)


def _parse_error(tmp_path: Path, data: bytes, code: str) -> None:
    with pytest.raises(ParseError) as caught:
        YoungInYlClarityResultCsvAdapter().parse(
            _write(tmp_path / "private-result.csv", data), ParseOptions()
        )
    assert caught.value.code == code


def test_descriptor_probe_and_content_detection_are_exact(tmp_path: Path) -> None:
    adapter = YoungInYlClarityResultCsvAdapter()
    descriptor = adapter.descriptor
    assert descriptor.adapter_id == "youngin_yl_clarity_result_csv"
    assert descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert descriptor.source_identity_policy is SourceIdentityPolicy.SHA256_ALIAS
    assert descriptor.peaks and descriptor.metadata and not descriptor.signals
    assert descriptor.series_kinds == ()
    valid = _write(tmp_path / "private-result.csv")
    assert adapter.probe(valid).matched
    assert adapter.probe(valid).confidence == pytest.approx(0.99)
    renamed = _write(tmp_path / "private-result.txt")
    assert adapter.probe(renamed).matched
    ordinary = _write(tmp_path / "ordinary.csv", b"sample_id,area\r\ngeneric,1\r\n")
    assert not adapter.probe(ordinary).matched


def test_identified_family_with_unsupported_profile_blocks_fallthrough(tmp_path: Path) -> None:
    data = synthetic_result_csv_bytes().replace(b"TCD", b"FID", 4)
    path = _write(tmp_path / "unsupported.csv", data)
    result = YoungInYlClarityResultCsvAdapter().probe(path)
    assert result.matched
    assert result.confidence == pytest.approx(0.70)


def test_parse_preserves_source_order_units_and_signal_without_detector_claim(
    tmp_path: Path,
) -> None:
    data = synthetic_result_csv_bytes()
    bundle = YoungInYlClarityResultCsvAdapter().parse(
        _write(tmp_path / "private-owner-result.csv", data), ParseOptions()
    )

    assert bundle.signals == ()
    assert bundle.samples[0].instrument.vendor == "YoungIn"
    assert bundle.samples[0].instrument.instrument_type is None
    assert bundle.samples[0].channels == ("Signal 1: TCD",)
    assert bundle.samples[0].detectors == ()
    assert bundle.samples[0].sample_id.startswith("YOUNGIN_RESULT_")
    assert bundle.sources[0].sha256 == hashlib.sha256(data).hexdigest()
    assert tuple(peak.peak_number for peak in bundle.peaks) == (1, 2)
    assert tuple(peak.observation_order for peak in bundle.peaks) == (1, 2)
    assert tuple(peak.retention_time for peak in bundle.peaks) == (1.25, 2.5)
    assert tuple(peak.area for peak in bundle.peaks) == (100.5, 150.75)
    assert tuple(peak.height for peak in bundle.peaks) == (10.25, 30.75)
    assert all(peak.channel == "Signal 1: TCD" for peak in bundle.peaks)
    assert all(peak.detector is None for peak in bundle.peaks)
    assert all(peak.retention_time_unit == "min" for peak in bundle.peaks)
    assert all(peak.area_unit == "mV.s" and peak.height_unit == "mV" for peak in bundle.peaks)
    assert all(peak.start_time is None and peak.end_time is None for peak in bundle.peaks)
    assert all(peak.compound is None and peak.compound_source is None for peak in bundle.peaks)
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["source_signal_1_name"] == "TCD"
    assert metadata["detector_identification_status"] == "unresolved_signal_name_only"
    assert metadata["width_05_status"] == "validated_not_mapped_to_integration_boundaries"
    assert metadata["private_trailer_status"] == "shape_validated_values_excluded"
    assert not any(
        "private-owner-result" in repr(item) for item in (*bundle.metadata, *bundle.peaks)
    )


def test_multisignal_profile_preserves_explicit_empty_fid_and_populated_tcd(
    tmp_path: Path,
) -> None:
    data = synthetic_result_csv_bytes(
        variant="empty_fid_then_tcd",
        tcd_peaks=(
            ("1", "10", "2", "10", "20", "0.1"),
            ("2", "20", "3", "20", "30", "0.2"),
            ("3", "30", "4", "30", "40", "0.3"),
            ("4", "40", "5", "40", "10", "0.4"),
        ),
    )
    decoded = reader.read_result_csv(_write(tmp_path / "multi.csv", data))
    assert tuple((item.signal_number, item.signal_name) for item in decoded.signals) == (
        (1, "FID"),
        (2, "TCD"),
    )
    assert decoded.signals[0].no_peaks_reported and decoded.signals[0].peaks == ()
    assert not decoded.signals[1].no_peaks_reported and len(decoded.signals[1].peaks) == 4
    bundle = YoungInYlClarityResultCsvAdapter().parse(tmp_path / "multi.csv", ParseOptions())
    assert bundle.samples[0].channels == ("Signal 1: FID", "Signal 2: TCD")
    assert len(bundle.peaks) == 4
    assert {peak.channel for peak in bundle.peaks} == {"Signal 2: TCD"}
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["source_signal_1_status"] == "no_peaks_reported"
    assert metadata["source_signal_2_peak_count"] == 4


@pytest.mark.parametrize(
    ("old", "new", "code"),
    (
        (b"\t2\t2.5\t", b"\t3\t2.5\t", "YOUNGIN_RESULT_CSV_PEAK_ORDER_INVALID"),
        (b"\t1.25\t", b"\tNaN\t", "YOUNGIN_RESULT_CSV_NUMBER_INVALID"),
        (b"\t100.5\t", b"\t-1.0\t", "YOUNGIN_RESULT_CSV_RESPONSE_INVALID"),
        (b"\t10.25\t", b"\tInf\t", "YOUNGIN_RESULT_CSV_NUMBER_INVALID"),
        (b"\t0.05\r\n", b"\tbad\r\n", "YOUNGIN_RESULT_CSV_NUMBER_INVALID"),
        (b"\t251.25\t", b"\t999.0\t", "YOUNGIN_RESULT_CSV_TOTAL_MISMATCH"),
    ),
)
def test_peak_fields_and_totals_are_strict(
    tmp_path: Path, old: bytes, new: bytes, code: str
) -> None:
    _parse_error(tmp_path, _replace(synthetic_result_csv_bytes(), old, new), code)


def test_signal_identity_must_remain_sequential_and_consistent(tmp_path: Path) -> None:
    data = synthetic_result_csv_bytes(variant="empty_fid_then_tcd")
    changed = _replace(data, b"2\tTCD\t1\t", b"1\tTCD\t1\t")
    _parse_error(tmp_path, changed, "YOUNGIN_RESULT_CSV_SIGNAL_ORDER_INVALID")
    changed = _replace(data, b"2\tTCD\t2\t", b"2\tFID\t2\t")
    _parse_error(tmp_path, changed, "YOUNGIN_RESULT_CSV_SIGNAL_MISMATCH")


@pytest.mark.parametrize(
    ("transform", "code"),
    (
        (lambda data: data[:-4], "YOUNGIN_RESULT_CSV_LINE_ENDING_INVALID"),
        (lambda data: data.replace(b"\r\n", b"\n"), "YOUNGIN_RESULT_CSV_LINE_ENDING_INVALID"),
        (lambda data: b"\xef\xbb\xbf" + data, "YOUNGIN_RESULT_CSV_ENCODING_UNSUPPORTED"),
        (
            lambda data: data.replace(b"Signal No.", b"Signal\x00No.", 1),
            "YOUNGIN_RESULT_CSV_ENCODING_UNSUPPORTED",
        ),
        (
            lambda data: data.replace(b"Area [mV.s]", b"Peak Area", 1),
            "YOUNGIN_RESULT_CSV_HEADER_INVALID",
        ),
        (
            lambda data: data + b"unexpected\r\n\r\n",
            "YOUNGIN_RESULT_CSV_TRAILER_INVALID",
        ),
    ),
)
def test_encoding_header_truncation_and_append_are_rejected(
    tmp_path: Path, transform: object, code: str
) -> None:
    assert callable(transform)
    _parse_error(tmp_path, transform(synthetic_result_csv_bytes()), code)


def test_bounded_read_and_line_limits_apply_before_unbounded_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path / "bounded.csv")
    monkeypatch.setattr(reader, "MAX_RESULT_CSV_BYTES", len(path.read_bytes()) - 1)
    with pytest.raises(reader.YoungInResultCsvStructureError) as caught:
        reader.read_result_csv(path)
    assert caught.value.code == "YOUNGIN_RESULT_CSV_SIZE_INVALID"

    monkeypatch.setattr(reader, "MAX_RESULT_CSV_BYTES", 32 * 1024 * 1024)
    monkeypatch.setattr(reader, "MAX_RESULT_CSV_LINES", 10)
    with pytest.raises(reader.YoungInResultCsvStructureError) as caught:
        reader.read_result_csv(path)
    assert caught.value.code == "YOUNGIN_RESULT_CSV_LINE_LIMIT"
