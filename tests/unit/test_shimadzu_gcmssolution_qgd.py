from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

import pytest

from ordifile.adapters.base import ParseOptions, SupportStatus
from ordifile.adapters.shimadzu_gcmssolution_qgd import ShimadzuGcmssolutionQgdAdapter
from ordifile.core.errors import ParseError
from ordifile.core.models import SeriesKind

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_cfb_v4 import build_cfb_v4  # noqa: E402
from generate_shimadzu_gcmssolution_qgd import (  # noqa: E402
    RT_INTERVAL_MS,
    RT_START_MS,
    SCAN_COUNT,
    synthetic_qgd_bytes,
    synthetic_qgd_streams,
)


def _write(path: Path, data: bytes | None = None) -> Path:
    path.write_bytes(synthetic_qgd_bytes() if data is None else data)
    return path


def _parse_error(path: Path) -> ParseError:
    with pytest.raises(ParseError) as caught:
        ShimadzuGcmssolutionQgdAdapter().parse(path, ParseOptions())
    return caught.value


def test_descriptor_declares_experimental_scientific_signal_and_stored_peaks() -> None:
    descriptor = ShimadzuGcmssolutionQgdAdapter.descriptor
    assert descriptor.adapter_id == "shimadzu_gcmssolution_qgd"
    assert descriptor.extensions == (".qgd",)
    assert descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert descriptor.series_kinds == (SeriesKind.SCIENTIFIC_SIGNAL,)
    assert descriptor.signals
    assert descriptor.peaks


def test_probe_requires_extension_and_exact_qgd_profile(tmp_path: Path) -> None:
    adapter = ShimadzuGcmssolutionQgdAdapter()
    source = _write(tmp_path / "synthetic.QGD")

    result = adapter.probe(source)

    assert result.matched
    assert result.confidence == pytest.approx(0.99)
    assert "4.00" in result.reason
    assert "16800" in result.reason
    assert not adapter.probe(_write(tmp_path / "synthetic.bin")).matched


def test_probe_preserves_identified_unsupported_profile(tmp_path: Path) -> None:
    source = _write(tmp_path / "unsupported.qgd", synthetic_qgd_bytes(file_schema="4.01"))

    result = ShimadzuGcmssolutionQgdAdapter().probe(source)

    assert result.matched
    assert result.confidence == pytest.approx(0.70)
    assert not result.routable
    assert result.failure_code == "SHIMADZU_QGD_PROFILE_UNSUPPORTED"


def test_parse_returns_uninterpolated_tic_and_structural_ms1_summary(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "stage-a.qgd",
        synthetic_qgd_bytes(
            intensity_width_overrides={7: 3},
            intensity_value_overrides={7: 4_000_000},
        ),
    )

    bundle = ShimadzuGcmssolutionQgdAdapter().parse(path, ParseOptions())

    assert bundle.samples[0].sample_id == "stage-a"
    assert bundle.samples[0].acquired_at is None
    assert bundle.samples[0].acquired_at_reliable is False
    assert bundle.samples[0].instrument.vendor == "Shimadzu"
    assert bundle.samples[0].instrument.instrument_type == "MS"
    assert bundle.samples[0].channels == ("TIC",)
    assert bundle.samples[0].detectors == ("MS",)
    assert bundle.samples[0].runtime is None
    assert bundle.peaks == ()
    signal = bundle.signals[0]
    assert signal.series_kind is SeriesKind.SCIENTIFIC_SIGNAL
    assert len(signal.x_values) == len(signal.y_values) == SCAN_COUNT
    assert signal.x_values[0] == pytest.approx(RT_START_MS / 60_000)
    assert signal.x_values[1] == pytest.approx((RT_START_MS + RT_INTERVAL_MS) / 60_000)
    assert signal.x_values[-1] == pytest.approx(3_599_800 / 60_000)
    assert signal.y_values[0] == 1_000
    assert signal.y_values[7] == 4_000_000
    assert signal.x_label == "retention_time"
    assert signal.x_unit == "min"
    assert signal.y_label == "raw_tic_intensity"
    assert signal.y_unit is None
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["file_property_schema"] == "4.00"
    assert metadata["scan_count"] == SCAN_COUNT
    assert metadata["ms1_present"] is True
    assert metadata["ms1_long_row_count"] == SCAN_COUNT
    assert metadata["ms1_intensity_widths_bytes"] == "2,3"
    assert metadata["ms1_intensity_raw_max"] == 4_000_000
    assert metadata["ms1_export_status"] == "unsupported"
    assert metadata["tic_signal_unit_status"] == "unknown"
    expected_time_hash = hashlib.sha256(
        b"".join(struct.pack(">d", value) for value in signal.x_values)
    ).hexdigest()
    expected_tic_hash = hashlib.sha256(
        b"".join(struct.pack(">Q", value) for value in signal.y_values)
    ).hexdigest()
    assert metadata["retention_time_canonical_be_f64_sha256"] == expected_time_hash
    assert metadata["tic_canonical_be_u64_sha256"] == expected_tic_hash
    assert {issue.code for issue in bundle.warnings} == {
        "SHIMADZU_QGD_EXPERIMENTAL_PROFILE",
        "QGD_MS1_NOT_EXPORTED",
    }


def test_wrong_extension_and_invalid_magic_are_structured(tmp_path: Path) -> None:
    assert _parse_error(_write(tmp_path / "sample.dat")).code == "SHIMADZU_QGD_EXTENSION_INVALID"

    invalid = bytearray(synthetic_qgd_bytes())
    invalid[:8] = b"not-cfb!"
    invalid_path = _write(tmp_path / "invalid.qgd", bytes(invalid))
    assert not ShimadzuGcmssolutionQgdAdapter().probe(invalid_path).matched
    assert _parse_error(invalid_path).code == "SHIMADZU_QGD_HEADER_INVALID"


def test_missing_and_wrong_case_required_streams_are_rejected(tmp_path: Path) -> None:
    missing = synthetic_qgd_streams()
    del missing[("GCMS Raw Data", "TIC Data")]
    assert (
        _parse_error(_write(tmp_path / "missing.qgd", build_cfb_v4(missing))).code
        == "SHIMADZU_QGD_PROFILE_UNSUPPORTED"
    )

    wrong_case = synthetic_qgd_bytes(
        path_replacements={("GCMS Raw Data", "Retention Time"): ("GCMS Raw Data", "retention time")}
    )
    assert (
        _parse_error(_write(tmp_path / "wrong-case.qgd", wrong_case)).code
        == "SHIMADZU_QGD_PROFILE_UNSUPPORTED"
    )


def test_case_ambiguous_and_control_named_directory_entries_are_rejected(
    tmp_path: Path,
) -> None:
    ambiguous = synthetic_qgd_streams()
    ambiguous[("GCMS Raw Data", "tic data")] = ambiguous[("GCMS Raw Data", "TIC Data")]
    assert (
        _parse_error(_write(tmp_path / "ambiguous.qgd", build_cfb_v4(ambiguous))).code
        == "SHIMADZU_QGD_HEADER_INVALID"
    )

    unsafe = synthetic_qgd_streams()
    unsafe[("Unsafe\nStorage", "Data")] = b"invented".ljust(4_096, b" ")
    assert (
        _parse_error(_write(tmp_path / "unsafe-name.qgd", build_cfb_v4(unsafe))).code
        == "SHIMADZU_QGD_HEADER_INVALID"
    )


@pytest.mark.parametrize(
    "data",
    (
        synthetic_qgd_bytes()[:100],
        synthetic_qgd_bytes()[:-1],
    ),
)
def test_truncated_container_is_rejected(tmp_path: Path, data: bytes) -> None:
    assert _parse_error(_write(tmp_path / "truncated.qgd", data)).code == "SHIMADZU_QGD_TRUNCATED"


def test_unsupported_file_property_profile_is_rejected(tmp_path: Path) -> None:
    error = _parse_error(
        _write(tmp_path / "unsupported.qgd", synthetic_qgd_bytes(file_schema="5.00"))
    )
    assert error.code == "SHIMADZU_QGD_PROFILE_UNSUPPORTED"


def test_rt_count_length_nonmonotonic_and_range_are_rejected(tmp_path: Path) -> None:
    streams = synthetic_qgd_streams()
    rt_path = ("GCMS Raw Data", "Retention Time")
    streams[rt_path] = streams[rt_path][:-4]
    assert (
        _parse_error(_write(tmp_path / "short-rt.qgd", build_cfb_v4(streams))).code
        == "SHIMADZU_QGD_ARRAY_INVALID"
    )

    retention = [RT_START_MS + index * RT_INTERVAL_MS for index in range(SCAN_COUNT)]
    retention[10] = retention[9]
    error = _parse_error(
        _write(
            tmp_path / "nonmonotonic.qgd",
            synthetic_qgd_bytes(retention_times_ms=tuple(retention)),
        )
    )
    assert error.code == "SHIMADZU_QGD_ARRAY_INVALID"


def test_index_out_of_range_and_nonmonotonic_are_rejected(tmp_path: Path) -> None:
    for name, replacement in (("out-of-range", 0xFFFFFFFF), ("nonmonotonic", 0)):
        streams = synthetic_qgd_streams()
        index_path = ("GCMS Raw Data", "Spectrum Index")
        offsets = list(struct.unpack(f"<{SCAN_COUNT}I", streams[index_path]))
        offsets[-1 if name == "out-of-range" else 10] = replacement
        streams[index_path] = struct.pack(f"<{SCAN_COUNT}I", *offsets)

        error = _parse_error(_write(tmp_path / f"{name}.qgd", build_cfb_v4(streams)))

        assert error.code in {"SHIMADZU_QGD_ARRAY_INVALID", "SHIMADZU_QGD_MS1_INVALID"}


@pytest.mark.parametrize(
    "kwargs",
    (
        {"header_scan_overrides": {10: 11}},
        {"header_rt_overrides": {10: 999_999}},
        {"header_target_overrides": {10: 1}},
        {"intensity_width_overrides": {10: 4}},
        {"header_point_count_overrides": {10: 2}},
        {"trailing_ms_bytes": b"\x00"},
    ),
)
def test_scan_header_width_count_and_terminal_boundary_are_rejected(
    tmp_path: Path, kwargs: dict[str, object]
) -> None:
    error = _parse_error(_write(tmp_path / "bad-ms1.qgd", synthetic_qgd_bytes(**kwargs)))
    assert error.code == "SHIMADZU_QGD_MS1_INVALID"


@pytest.mark.parametrize("width", (1, 4, 5))
def test_unobserved_intensity_widths_are_explicitly_rejected(tmp_path: Path, width: int) -> None:
    error = _parse_error(
        _write(
            tmp_path / f"width-{width}.qgd",
            synthetic_qgd_bytes(
                intensity_width_overrides={10: width},
                intensity_value_overrides={10: 200},
            ),
        )
    )

    assert error.code == "SHIMADZU_QGD_MS1_INVALID"


@pytest.mark.parametrize("impossible_count", (0, 4_097))
def test_impossible_ms1_point_count_is_rejected(tmp_path: Path, impossible_count: int) -> None:
    error = _parse_error(
        _write(
            tmp_path / "impossible-count.qgd",
            synthetic_qgd_bytes(header_point_count_overrides={10: impossible_count}),
        )
    )
    assert error.code == "SHIMADZU_QGD_MS1_INVALID"


def test_truncated_final_ms1_scan_is_rejected(tmp_path: Path) -> None:
    streams = synthetic_qgd_streams()
    ms_path = ("GCMS Raw Data", "MS Raw Data")
    streams[ms_path] = streams[ms_path][:-1]

    error = _parse_error(_write(tmp_path / "truncated-ms1.qgd", build_cfb_v4(streams)))

    assert error.code == "SHIMADZU_QGD_MS1_INVALID"


def test_malformed_raw_mass_sequence_is_rejected(tmp_path: Path) -> None:
    for records in (((0, 10),), ((700, 10), (699, 20))):
        error = _parse_error(
            _write(
                tmp_path / "bad-mass.qgd",
                synthetic_qgd_bytes(records_overrides={0: records}),
            )
        )
        assert error.code == "SHIMADZU_QGD_MS1_INVALID"


def test_tic_and_ms1_intensity_sum_mismatch_is_rejected(tmp_path: Path) -> None:
    streams = synthetic_qgd_streams()
    tic_path = ("GCMS Raw Data", "TIC Data")
    tic_values = list(struct.unpack(f"<{SCAN_COUNT}Q", streams[tic_path]))
    tic_values[0] += 1
    streams[tic_path] = struct.pack(f"<{SCAN_COUNT}Q", *tic_values)

    error = _parse_error(_write(tmp_path / "bad-tic.qgd", build_cfb_v4(streams)))

    assert error.code == "SHIMADZU_QGD_MS1_INVALID"


def test_three_byte_large_intensity_is_preserved_without_overflow(tmp_path: Path) -> None:
    bundle = ShimadzuGcmssolutionQgdAdapter().parse(
        _write(
            tmp_path / "large-intensity.qgd",
            synthetic_qgd_bytes(
                intensity_width_overrides={0: 3},
                intensity_value_overrides={0: 0xFFFFFF},
            ),
        ),
        ParseOptions(),
    )

    assert bundle.signals[0].y_values[0] == 0xFFFFFF
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["ms1_intensity_raw_max"] == 0xFFFFFF


_ALTERNATE_GRID = tuple(390_000 + index * 300 for index in range(1_100))


def _alternate(path: Path, **kwargs: object) -> Path:
    kwargs.setdefault("retention_times_ms", _ALTERNATE_GRID)
    path.write_bytes(synthetic_qgd_bytes(**kwargs))
    return path


def test_a_second_acquisition_grid_and_tagged_u64_index_are_both_accepted(
    tmp_path: Path,
) -> None:
    source = _alternate(tmp_path / "alternate.qgd", spectrum_index_width=8, scan_number_field=True)

    bundle = ShimadzuGcmssolutionQgdAdapter().parse(source, ParseOptions())

    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["scan_count"] == len(_ALTERNATE_GRID)
    assert metadata["retention_time_start"] == 390_000
    assert metadata["retention_time_interval"] == 300
    assert metadata["spectrum_index_offset_width"] == 8
    assert len(bundle.signals[0].x_values) == len(_ALTERNATE_GRID)


def test_the_original_u32_spectrum_index_still_reads_the_same_grid(tmp_path: Path) -> None:
    bundle = ShimadzuGcmssolutionQgdAdapter().parse(
        _alternate(tmp_path / "u32.qgd"), ParseOptions()
    )

    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["spectrum_index_offset_width"] == 4
    assert metadata["retention_time_interval"] == 300


def test_a_non_uniform_retention_grid_fails_closed(tmp_path: Path) -> None:
    uneven = (*_ALTERNATE_GRID[:-1], _ALTERNATE_GRID[-1] + 100)

    error = _parse_error(_alternate(tmp_path / "uneven.qgd", retention_times_ms=uneven))

    assert error.code == "SHIMADZU_QGD_ARRAY_INVALID"


def test_a_spectrum_index_that_matches_neither_encoding_fails_closed(tmp_path: Path) -> None:
    streams = synthetic_qgd_streams(retention_times_ms=_ALTERNATE_GRID)
    key = ("GCMS Raw Data", "Spectrum Index")
    streams[key] = streams[key] + b"\x00" * 4

    error = _parse_error(_write(tmp_path / "index.qgd", build_cfb_v4(streams)))

    assert error.code == "SHIMADZU_QGD_ARRAY_INVALID"


def test_an_unobserved_per_scan_number_fails_closed(tmp_path: Path) -> None:
    error = _parse_error(
        _alternate(tmp_path / "scan-number.qgd", header_scan_number_overrides={7: 999})
    )

    assert error.code == "SHIMADZU_QGD_MS1_INVALID"


def test_the_older_file_property_schema_is_accepted(tmp_path: Path) -> None:
    bundle = ShimadzuGcmssolutionQgdAdapter().parse(
        _alternate(tmp_path / "schema-2.qgd", file_schema="2.00"), ParseOptions()
    )

    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["file_property_schema"] == "2.00"


def test_an_unobserved_file_property_schema_still_fails_closed(tmp_path: Path) -> None:
    error = _parse_error(_alternate(tmp_path / "schema-3.qgd", file_schema="3.00"))

    assert error.code == "SHIMADZU_QGD_PROFILE_UNSUPPORTED"


def test_an_empty_scan_is_accepted_and_contributes_no_intensity(tmp_path: Path) -> None:
    source = _alternate(
        tmp_path / "empty-scan.qgd",
        records_overrides={17: ()},
        intensity_width_overrides={17: 4},
    )

    bundle = ShimadzuGcmssolutionQgdAdapter().parse(source, ParseOptions())

    assert bundle.signals[0].y_values[17] == 0
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["ms1_points_per_scan_min"] == 0
    assert metadata["ms1_intensity_widths_bytes"] == "2"


def test_a_non_empty_scan_still_requires_an_observed_intensity_width(tmp_path: Path) -> None:
    error = _parse_error(_alternate(tmp_path / "width.qgd", intensity_width_overrides={17: 4}))

    assert error.code == "SHIMADZU_QGD_MS1_INVALID"
