from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

import pytest

from ordifile.adapters import _youngin_yl_clarity_prm_binary as binary
from ordifile.adapters.base import ParseOptions, SupportStatus
from ordifile.adapters.youngin_yl_clarity_prm_raw import YoungInYlClarityPrmRawAdapter
from ordifile.core.errors import ParseError
from ordifile.core.models import SeriesKind

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_youngin_yl_clarity_prm import (  # noqa: E402
    COUNT_KEY,
    FOOTER_MARKER,
    PRM_DATA_KEY,
    RAW_DATA_KEY,
    synthetic_prm_bytes,
)

MARKER_START = 0x20
MARKER_VALLEY = 0x40
MARKER_APEX = 0x50
MARKER_END = 0x80


def _write(path: Path, data: bytes | None = None) -> Path:
    path.write_bytes(synthetic_prm_bytes() if data is None else data)
    return path


def _error(path: Path) -> str:
    with pytest.raises(ParseError) as caught:
        YoungInYlClarityPrmRawAdapter().parse(path, ParseOptions())
    return caught.value.code


def _framed_info(text: str) -> bytes:
    if len(text) > 255:
        raise AssertionError("invented test Info value is too long")
    return binary.INFO_VALUE_KEY + bytes([len(text)]) + text.encode("utf-16-le")


def test_descriptor_and_detection_are_exact_and_experimental(tmp_path: Path) -> None:
    adapter = YoungInYlClarityPrmRawAdapter()
    valid = _write(tmp_path / "FID_STD_001.prm")
    uppercase_extension = _write(tmp_path / "FID_STD_002.PRM")
    wrong_extension = _write(tmp_path / "FID_STD_001.bin")
    invalid = _write(tmp_path / "invalid.prm", b"not prm")

    assert adapter.descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert adapter.descriptor.series_kinds == (
        SeriesKind.DECODED_RECORDS,
        SeriesKind.SCIENTIFIC_SIGNAL,
    )
    assert adapter.probe(valid).confidence == pytest.approx(0.99)
    assert adapter.probe(uppercase_extension).confidence == pytest.approx(0.99)
    assert adapter.parse(uppercase_extension, ParseOptions()).signals
    assert not adapter.probe(wrong_extension).matched
    assert not adapter.probe(invalid).matched
    assert _error(wrong_extension) == "YOUNGIN_PRM_EXTENSION_INVALID"


def test_validated_9_0_single_channel_exposes_scientific_time_and_millivolts(
    tmp_path: Path,
) -> None:
    data = synthetic_prm_bytes()
    path = _write(tmp_path / "FID_STD_001.prm", data)
    bundle = YoungInYlClarityPrmRawAdapter().parse(path, ParseOptions())

    assert bundle.samples[0].sample_id == f"PRM_{hashlib.sha256(data).hexdigest()[:16]}"
    assert bundle.samples[0].channels == ("native_label_TCD",)
    assert bundle.samples[0].detectors == ("TCD",)
    assert bundle.samples[0].acquired_at is None
    assert bundle.samples[0].runtime is None
    signal = bundle.signals[0]
    assert signal.channel == "native_label_TCD"
    assert signal.detector == "TCD"
    assert signal.x_values == pytest.approx((0, 1 / 600, 2 / 600))
    assert signal.y_values == pytest.approx((1.25, -2.5, 3.75))
    assert signal.x_label == "retention_time"
    assert signal.x_unit == "min"
    assert signal.y_label == "detector_response"
    assert signal.y_unit == "mV"
    assert signal.series_kind is SeriesKind.SCIENTIFIC_SIGNAL
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert "user_supplied_group" not in metadata
    assert metadata["detector_verified"] is True
    assert metadata["time_axis_status"] == "paired_curve_validated"
    assert metadata["physical_scaling_status"] == "identity_validated_at_export_precision"
    assert metadata["signal_unit_status"] == "paired_curve_validated"
    assert metadata["scientific_semantics_status"] == "direct_signal_validated"
    assert metadata["scientific_semantics_evidence_gap"] == "stored_peak_results"
    assert metadata["paired_curve_distinct_pair_count"] == 12
    assert metadata["paired_curve_compared_point_count"] == 316_220


def test_exact_profile_emits_transparent_ordifile_derived_area_when_markers_exist(
    tmp_path: Path,
) -> None:
    data = synthetic_prm_bytes(
        channels=((0.0, 1.0, 3.0, 1.0, 0.0),),
        marker_records=(((MARKER_START, 0), (MARKER_APEX, 1), (MARKER_END, 4)),),
    )
    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "derived-area.prm", data),
        ParseOptions(experimental_derived_area=True),
    )

    assert len(bundle.peaks) == 1
    peak = bundle.peaks[0]
    assert peak.detector == "TCD"
    assert peak.retention_time == pytest.approx(2 / 600)
    assert peak.area is None
    assert peak.area_unit is None
    assert peak.calculated_area == pytest.approx(0.5)
    assert peak.calculated_area_unit == "mV.s"
    assert peak.height is None
    assert peak.status == "ordifile_derived_experimental"
    assert peak.data_origin == "ordifile_marker_derived"
    assert peak.derivation_method_id == "youngin-prm-marker-timetable-hybrid-contact-envelope-v3"
    assert peak.derivation_evidence_profile is not None
    assert "boundary_rule=adjacent_contact_straight_baseline" in (peak.derivation_evidence_profile)
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["peak_table_status"] == "ordifile_marker_derived_experimental"
    assert metadata["derived_peak_count"] == 1
    assert metadata["derived_area_equivalence_status"] == "not_vendor_result_equivalent"
    assert "YOUNGIN_PRM_AREA_ORDIFILE_DERIVED_EXPERIMENTAL" in {
        issue.code for issue in bundle.warnings
    }


def test_stored_timetable_exclusion_removes_only_marker_candidates_inside_interval(
    tmp_path: Path,
) -> None:
    data = synthetic_prm_bytes(
        channels=((0.0, 2.0, 0.0, 0.0, 0.0, 3.0, 1.0, 0.0, 0.0),),
        marker_records=(
            (
                (MARKER_START, 0),
                (MARKER_APEX, 1),
                (MARKER_END, 2),
                (MARKER_START, 4),
                (MARKER_APEX, 5),
                (MARKER_END, 8),
            ),
        ),
        time_table_events=(((11, 0.0, 0.003, 0.0, 32),),),
    )

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "stored-exclusion.prm", data),
        ParseOptions(experimental_derived_area=True),
    )

    assert len(bundle.peaks) == 1
    assert bundle.peaks[0].retention_time == pytest.approx(5 / 600)
    assert bundle.peaks[0].peak_number == 1
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["structural_channel_001_marker_candidate_count"] == 2
    assert metadata["structural_channel_001_processing_time_table_excluded_candidate_count"] == 1
    assert metadata["structural_channel_001_processing_time_table_status"] == "matched"


def test_exclusion_does_not_reclassify_a_shared_cluster_as_single_peak(
    tmp_path: Path,
) -> None:
    data = synthetic_prm_bytes(
        channels=((0.0, 1.0, 3.0, 1.0, 0.0, 0.0, 0.0, 1.0, 4.0, 1.0, 0.0, 0.0),),
        marker_records=(
            (
                (MARKER_START, 0),
                (MARKER_APEX, 2),
                (MARKER_VALLEY, 5),
                (MARKER_APEX, 8),
                (MARKER_END, 11),
            ),
        ),
        time_table_events=(((11, 0.0, 0.005, 0.0, 32),),),
    )

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "shared-cluster-exclusion.prm", data),
        ParseOptions(experimental_derived_area=True),
    )

    assert len(bundle.peaks) == 1
    peak = bundle.peaks[0]
    assert peak.start_time == pytest.approx(5 / 600)
    assert peak.end_time == pytest.approx(11 / 600)
    assert peak.derivation_evidence_profile is not None
    assert "boundary_rule=cluster_envelope_partition" in peak.derivation_evidence_profile


def test_unknown_bound_timetable_opcode_preserves_signals_without_area(tmp_path: Path) -> None:
    data = synthetic_prm_bytes(
        channels=((0.0, 2.0, 0.0),),
        marker_records=(((MARKER_START, 0), (MARKER_APEX, 1), (MARKER_END, 2)),),
        time_table_events=(((99, 0.0, 1.0, 0.0, 32),),),
    )

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "unsupported-timetable.prm", data),
        ParseOptions(experimental_derived_area=True),
    )

    assert bundle.signals
    assert bundle.peaks == ()
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["structural_channel_001_processing_time_table_status"] == (
        "time_table_opcode_unsupported"
    )


@pytest.mark.parametrize(
    "events",
    (
        ((11, 0.0, 0.003, 1.0, 32),),
        ((32, 0.002, 0.001, 0.0, 32), (11, 0.0, 0.003, 0.0, 32)),
        ((12, 0.003, 0.001, 0.0, 32),),
        ((32, 0.001, 0.003, 0.0, 32),),
        ((11, 1.0, 2.0, 0.0, 32),),
    ),
)
def test_unobserved_optional_timetable_fingerprint_preserves_signals_without_area(
    tmp_path: Path,
    events: tuple[tuple[int, float, float, float, int], ...],
) -> None:
    data = synthetic_prm_bytes(
        channels=((0.0, 2.0, 0.0),),
        marker_records=(((MARKER_START, 0), (MARKER_APEX, 1), (MARKER_END, 2)),),
        time_table_events=(events,),
    )

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "unsupported-optional-event.prm", data),
        ParseOptions(experimental_derived_area=True),
    )

    assert bundle.signals
    assert bundle.peaks == ()
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["structural_channel_001_processing_time_table_status"] in {
        "time_table_opcode_unsupported",
        "time_table_optional_event_unsupported",
    }


@pytest.mark.parametrize(
    ("field_key", "replacement"),
    (
        (b"\x08GroupStr\x03\xff\xfe\xff\x01 \x00", b"\x08GroupStr\x03\xff\xfe\xff\x01X\x00"),
        (b"\x04GUID\x03\xff\xfe\xff\x26{\x00", b"\x04GUID\x03\xff\xfe\xff\x26Z\x00"),
    ),
)
def test_unobserved_timetable_text_fingerprint_preserves_signals_without_area(
    tmp_path: Path,
    field_key: bytes,
    replacement: bytes,
) -> None:
    data = bytearray(
        synthetic_prm_bytes(
            channels=((0.0, 2.0, 0.0),),
            marker_records=(((MARKER_START, 0), (MARKER_APEX, 1), (MARKER_END, 2)),),
        )
    )
    offset = data.index(field_key)
    data[offset : offset + len(field_key)] = replacement

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "unsupported-event-text.prm", bytes(data)),
        ParseOptions(experimental_derived_area=True),
    )

    assert bundle.signals
    assert bundle.peaks == ()
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["structural_channel_001_processing_time_table_status"] == (
        "time_table_fingerprint_unsupported"
    )


def test_malformed_timetable_text_frame_preserves_signals_without_area(tmp_path: Path) -> None:
    data = bytearray(
        synthetic_prm_bytes(
            channels=((0.0, 2.0, 0.0),),
            marker_records=(((MARKER_START, 0), (MARKER_APEX, 1), (MARKER_END, 2)),),
        )
    )
    text_key = b"\x04Text\x03"
    offset = data.index(text_key)
    data[offset + 1] = ord("X")

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "malformed-event-text.prm", bytes(data)),
        ParseOptions(experimental_derived_area=True),
    )

    assert bundle.signals
    assert bundle.peaks == ()
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["structural_channel_001_processing_time_table_status"] == "invalid"


def test_derived_area_is_not_calculated_without_explicit_opt_in(tmp_path: Path) -> None:
    data = synthetic_prm_bytes(
        channels=((0.0, 1.0, 3.0, 1.0, 0.0),),
        marker_records=(((MARKER_START, 0), (MARKER_APEX, 1), (MARKER_END, 4)),),
    )

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "default-signal-only.prm", data), ParseOptions()
    )

    assert bundle.signals
    assert bundle.peaks == ()
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["integration_marker_status"] == "not_requested"
    assert metadata["peak_table_status"] == "unsupported"


def test_exact_9_1_derived_area_uses_profile_specific_response_units(tmp_path: Path) -> None:
    markers = ((MARKER_START, 0), (MARKER_APEX, 2), (MARKER_END, 4))
    data = synthetic_prm_bytes(
        producer_text=binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SYNTHETIC",
        channels=((0.0, 1.0, 3.0, 1.0, 0.0), (0.0, 2.0, 4.0, 2.0, 0.0)),
        marker_records=(markers, markers),
        integration_type=0x1A,
    )

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "derived-area-9-1.prm", data),
        ParseOptions(experimental_derived_area=True),
    )

    assert tuple((peak.detector, peak.calculated_area_unit) for peak in bundle.peaks) == (
        ("FID", "pA.s"),
        ("TCD", "mV.s"),
    )


def test_unknown_family_profile_does_not_inherit_derived_area(tmp_path: Path) -> None:
    markers = ((MARKER_START, 0), (MARKER_APEX, 1), (MARKER_END, 2))
    data = synthetic_prm_bytes(
        producer_text="YL-Clarity 9.2.0.0 FULL, SN: SYNTHETIC",
        channels=((0.0, 1.0, 0.0), (0.0, 2.0, 0.0)),
        marker_records=(markers, markers),
    )

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "unknown-profile.prm", data),
        ParseOptions(experimental_derived_area=True),
    )

    assert bundle.signals
    assert bundle.peaks == ()
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["integration_marker_status"] == "matched"
    assert metadata["peak_table_status"] == "unsupported"
    assert "YOUNGIN_PRM_DERIVED_AREA_PROFILE_UNAVAILABLE" in {
        issue.code for issue in bundle.warnings
    }


def test_opted_in_exact_profile_without_markers_reports_area_unavailable(
    tmp_path: Path,
) -> None:
    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "no-markers.prm"),
        ParseOptions(experimental_derived_area=True),
    )

    assert bundle.signals
    assert bundle.peaks == ()
    assert "YOUNGIN_PRM_DERIVED_AREA_UNAVAILABLE" in {issue.code for issue in bundle.warnings}


def test_unsupported_integration_type_preserves_signals_without_area(tmp_path: Path) -> None:
    data = synthetic_prm_bytes(
        channels=((0.0, 1.0, 0.0),),
        marker_records=(((MARKER_START, 0), (MARKER_APEX, 1), (MARKER_END, 2)),),
        integration_type=0x99,
    )

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "unsupported-integration.prm", data),
        ParseOptions(experimental_derived_area=True),
    )

    assert bundle.signals
    assert bundle.peaks == ()
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["structural_channel_001_integration_marker_status"] == (
        "integration_type_unsupported"
    )
    assert "YOUNGIN_PRM_DERIVED_AREA_UNAVAILABLE" in {issue.code for issue in bundle.warnings}


@pytest.mark.parametrize("stem", ("FID_STD_010", "TCD_STD_010", "MIXED_SAMPLE_003"))
def test_former_group_alias_patterns_do_not_affect_runtime_identity(
    tmp_path: Path, stem: str
) -> None:
    data = synthetic_prm_bytes()
    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / f"{stem}.prm", data), ParseOptions()
    )
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert bundle.samples[0].sample_id == f"PRM_{hashlib.sha256(data).hexdigest()[:16]}"
    assert "user_supplied_group" not in metadata
    assert bundle.samples[0].detectors == ("TCD",)


def test_untrusted_basename_uses_content_hash_and_does_not_expose_embedded_text(
    tmp_path: Path,
) -> None:
    private_text = b"operator=PRIVATE;path=C:\\Private\\Method;host=PRIVATE-HOST"
    data = synthetic_prm_bytes(embedded_private_text=private_text)
    path = _write(tmp_path / "private-original-name.prm", data)
    bundle = YoungInYlClarityPrmRawAdapter().parse(path, ParseOptions())
    expected = f"PRM_{hashlib.sha256(data).hexdigest()[:16]}"

    assert bundle.samples[0].sample_id == expected
    public_values = [
        str(value)
        for entry in bundle.metadata
        for value in (entry.key, entry.value, entry.source_file)
    ]
    public_values.extend(issue.message for issue in bundle.warnings)
    rendered = "\n".join(public_values)
    assert "PRIVATE" not in rendered
    assert "private-original-name" not in rendered
    assert not any(entry.key == "user_supplied_group" for entry in bundle.metadata)


def test_two_channels_preserve_source_order_and_have_stable_digests(tmp_path: Path) -> None:
    data = synthetic_prm_bytes(channels=((1.0, 2.0), (9.0, 8.0, 7.0)), history_count=3)
    path = _write(tmp_path / "MIXED_SAMPLE_001.prm", data)
    adapter = YoungInYlClarityPrmRawAdapter()
    first = adapter.parse(path, ParseOptions())
    second = adapter.parse(path, ParseOptions())

    assert [signal.channel for signal in first.signals] == ["native_label_FID", "native_label_TCD"]
    assert [signal.y_values for signal in first.signals] == [(1.0, 2.0), (9.0, 8.0, 7.0)]
    first_meta = {entry.key: entry.value for entry in first.metadata}
    second_meta = {entry.key: entry.value for entry in second.metadata}
    assert first_meta["structural_channel_count"] == 2
    assert first_meta["history_count"] == 3
    assert first_meta["selected_history_version"] == 3
    assert first_meta["history_revision_exposure_status"] == "latest_revision_only"
    assert first_meta["prior_history_revision_count"] == 2
    assert first_meta["prior_history_revisions_exposed"] == 0
    assert first_meta["prior_rawdata6_block_count"] == 0
    assert first_meta["prior_prmdata_block_count"] == 0
    assert first_meta["detector_verified"] is False
    assert first_meta["detector_identity_status"] == "experimental_stored_native_label"
    assert first_meta["structural_channel_001_stored_detector_label"] == "FID"
    assert first_meta["structural_channel_002_stored_detector_label"] == "TCD"
    assert "YOUNGIN_PRM_PRIOR_HISTORY_NOT_EXPOSED" in {issue.code for issue in first.warnings}
    assert first_meta["aggregate_payload_sha256"] == second_meta["aggregate_payload_sha256"]
    assert (
        first_meta["aggregate_canonical_be_f32_sha256"]
        == second_meta["aggregate_canonical_be_f32_sha256"]
    )


def test_four_history_revisions_select_only_the_latest_bounded_revision(
    tmp_path: Path,
) -> None:
    data = synthetic_prm_bytes(
        channels=((1.0, 2.0), (9.0, 8.0)),
        history_count=4,
    )

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "four-history.prm", data), ParseOptions()
    )
    metadata = {entry.key: entry.value for entry in bundle.metadata}

    assert metadata["history_count"] == 4
    assert metadata["selected_history_version"] == 4
    assert metadata["prior_history_revision_count"] == 3
    assert [signal.y_values for signal in bundle.signals] == [(1.0, 2.0), (9.0, 8.0)]


def test_validated_9_1_profile_exposes_scientific_time_and_detector_response(
    tmp_path: Path,
) -> None:
    data = synthetic_prm_bytes(
        producer_text=binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SYNTHETIC",
        channels=((1.25, 2.5, 3.75), (10.0, 20.0, 30.0)),
    )
    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "scientific.prm", data), ParseOptions()
    )

    assert bundle.samples[0].detectors == ("FID", "TCD")
    assert bundle.peaks == ()
    assert [signal.channel for signal in bundle.signals] == [
        "native_label_FID",
        "native_label_TCD",
    ]
    for signal, detector, unit in zip(bundle.signals, ("FID", "TCD"), ("pA", "mV"), strict=True):
        assert signal.detector == detector
        assert signal.x_values == pytest.approx((0.0, 1 / 600, 2 / 600))
        assert signal.x_label == "retention_time"
        assert signal.x_unit == "min"
        assert signal.y_label == "detector_response"
        assert signal.y_unit == unit
        assert signal.series_kind is SeriesKind.SCIENTIFIC_SIGNAL
    assert bundle.signals[0].y_values == pytest.approx((1.25, 2.5, 3.75))
    assert bundle.signals[1].y_values == pytest.approx((10.0, 20.0, 30.0))
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["producer_version"] == "YL-Clarity 9.1.0.76"
    assert metadata["time_axis_status"] == "paired_curve_validated"
    assert metadata["physical_scaling_status"] == "identity_validated_at_export_precision"
    assert metadata["paired_curve_distinct_pair_count"] == 5
    assert metadata["paired_curve_compared_point_count"] == 138_000
    assert metadata["paired_curve_time_decimal_places"] == 5
    assert metadata["paired_curve_signal_decimal_places"] == 4
    assert metadata["peak_table_status"] == "unsupported"
    assert {issue.code for issue in bundle.warnings} == {
        "YOUNGIN_PRM_EXPERIMENTAL_SCIENTIFIC_SIGNAL"
    }


@pytest.mark.parametrize(
    "data",
    (
        synthetic_prm_bytes(producer_text=binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SYNTHETIC"),
        synthetic_prm_bytes(
            producer_text=binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SYNTHETIC",
            channels=((1.0,), (2.0,)),
            history_count=2,
        ),
        synthetic_prm_bytes(
            producer_text=binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SYNTHETIC",
            channels=((1.0,), (2.0, 3.0)),
        ),
    ),
)
def test_9_1_scientific_profile_rejects_unobserved_layouts(tmp_path: Path, data: bytes) -> None:
    assert _error(_write(tmp_path / "unsupported-9-1.prm", data)) == (
        "YOUNGIN_PRM_PROFILE_UNSUPPORTED"
    )


def test_known_prefix_outside_the_exact_producer_field_cannot_promote_a_profile(
    tmp_path: Path,
) -> None:
    data = synthetic_prm_bytes(
        producer_text="UNRELATED PRODUCT INFO",
        channels=((1.0, 2.0), (3.0, 4.0)),
        embedded_private_text=_framed_info(
            binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "NOT_THE_PRODUCER"
        ),
    )
    path = _write(tmp_path / "embedded-known-prefix.prm", data)

    assert YoungInYlClarityPrmRawAdapter().probe(path).confidence == pytest.approx(0.70)
    assert _error(path) == "YOUNGIN_PRM_PROFILE_UNSUPPORTED"


def test_framed_producer_values_are_consistent_and_fail_closed(tmp_path: Path) -> None:
    duplicate = synthetic_prm_bytes(
        embedded_private_text=_framed_info(binary.PRODUCER_PREFIX_TEXT + "DUPLICATE")
    )
    assert (
        YoungInYlClarityPrmRawAdapter()
        .parse(_write(tmp_path / "duplicate-info.prm", duplicate), ParseOptions())
        .signals
    )

    mixed = synthetic_prm_bytes(
        embedded_private_text=_framed_info(binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "CONFLICT")
    )
    assert _error(_write(tmp_path / "mixed-info.prm", mixed)) == ("YOUNGIN_PRM_PROFILE_UNSUPPORTED")

    raw_prefix_only = synthetic_prm_bytes(
        embedded_private_text=(binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "UNFRAMED").encode(
            "utf-16-le"
        )
    )
    raw_bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "unframed-prefix.prm", raw_prefix_only), ParseOptions()
    )
    assert all(signal.series_kind is SeriesKind.SCIENTIFIC_SIGNAL for signal in raw_bundle.signals)
    raw_metadata = {entry.key: entry.value for entry in raw_bundle.metadata}
    assert raw_metadata["producer_version"] == "YL-Clarity 9.0.1.19"
    assert {signal.y_unit for signal in raw_bundle.signals} == {"mV"}

    truncated = synthetic_prm_bytes(embedded_private_text=binary.INFO_VALUE_KEY + b"\xff")
    assert _error(_write(tmp_path / "truncated-info.prm", truncated)) == (
        "YOUNGIN_PRM_PROFILE_UNSUPPORTED"
    )


@pytest.mark.parametrize(
    ("data", "code"),
    (
        (synthetic_prm_bytes()[:3], "YOUNGIN_PRM_HEADER_INVALID"),
        (synthetic_prm_bytes()[:-21], "YOUNGIN_PRM_FILE_LENGTH_MISMATCH"),
        (synthetic_prm_bytes(trailing=b"x"), "YOUNGIN_PRM_FILE_LENGTH_MISMATCH"),
        (synthetic_prm_bytes(detector_count=0), "YOUNGIN_PRM_CHANNEL_COUNT_UNSUPPORTED"),
        (synthetic_prm_bytes(detector_count=2), "YOUNGIN_PRM_CHANNEL_COUNT_INVALID"),
        (
            synthetic_prm_bytes(history_count=2, history_versions=(1, 3)),
            "YOUNGIN_PRM_HISTORY_INVALID",
        ),
        (synthetic_prm_bytes(raw_size_override=4), "YOUNGIN_PRM_CHANNEL_METADATA_INVALID"),
        (synthetic_prm_bytes(d_size_override=4), "YOUNGIN_PRM_CHANNEL_METADATA_INVALID"),
        (
            synthetic_prm_bytes(duplicate_mismatch_channel=1),
            "YOUNGIN_PRM_DUPLICATE_MISMATCH",
        ),
        (synthetic_prm_bytes(channels=((float("inf"),),)), "YOUNGIN_PRM_NUMERIC_INVALID"),
        (synthetic_prm_bytes(payload_suffix=b"x"), "YOUNGIN_PRM_RECORD_COUNT_INVALID"),
        (
            synthetic_prm_bytes(gzip_trailing=b"x"),
            "YOUNGIN_PRM_COMPRESSION_TRAILING_DATA",
        ),
    ),
)
def test_unsupported_malformed_and_nonfinite_profiles_fail_boundedly(
    tmp_path: Path, data: bytes, code: str
) -> None:
    assert _error(_write(tmp_path / "FID_STD_001.prm", data)) == code


def test_duplicate_section_and_truncated_or_invalid_gzip_are_rejected(tmp_path: Path) -> None:
    valid = synthetic_prm_bytes()
    raw_offset = valid.index(RAW_DATA_KEY)
    prm_offset = valid.index(PRM_DATA_KEY)
    raw_duplicate = valid[:prm_offset] + valid[raw_offset:prm_offset] + valid[prm_offset:]
    assert _error(_write(tmp_path / "duplicate.prm", raw_duplicate)) in {
        "YOUNGIN_PRM_CHANNEL_COUNT_INVALID",
        "YOUNGIN_PRM_SECTION_AMBIGUOUS",
    }

    gzip_offset = raw_offset + len(RAW_DATA_KEY) + 4
    bad_gzip = bytearray(valid)
    bad_gzip[gzip_offset : gzip_offset + 2] = b"XX"
    assert _error(_write(tmp_path / "bad-gzip.prm", bytes(bad_gzip))) == (
        "YOUNGIN_PRM_COMPRESSION_INVALID"
    )

    raw_size = struct.unpack_from("<I", valid, raw_offset + len(RAW_DATA_KEY))[0]
    truncated = bytearray(valid)
    struct.pack_into("<I", truncated, raw_offset + len(RAW_DATA_KEY), raw_size + len(valid))
    assert _error(_write(tmp_path / "truncated.prm", bytes(truncated))) == (
        "YOUNGIN_PRM_DATA_BLOCK_TRUNCATED"
    )


def test_detname_is_required_as_bounded_source_order_structure(tmp_path: Path) -> None:
    valid = synthetic_prm_bytes(channels=((1.0,), (2.0,)), d_step=2)
    first_detname = valid.index(b"\x07DetName\x03")
    missing = valid[:first_detname] + b"\x07NotName\x03" + valid[first_detname + 9 :]
    assert _error(_write(tmp_path / "missing.prm", missing)) == (
        "YOUNGIN_PRM_CHANNEL_IDENTITY_INVALID"
    )

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "opaque.prm", valid), ParseOptions()
    )
    assert bundle.samples[0].detectors == ()
    assert not any("DetName" in entry.key for entry in bundle.metadata)


def test_compatible_unknown_profile_exposes_scientific_values_with_unresolved_units(
    tmp_path: Path,
) -> None:
    private_serial = "PRIVATE-SERIAL-SHOULD-NOT-APPEAR"
    data = synthetic_prm_bytes(
        producer_text=f"YL-Clarity 9.2.0.0 FULL, SN: {private_serial}",
        channels=((1.0, 2.0), (3.0, 4.0)),
    )
    adapter = YoungInYlClarityPrmRawAdapter()
    path = _write(tmp_path / "compatible.prm", data)

    assert adapter.probe(path).routable
    bundle = adapter.parse(path, ParseOptions())
    assert all(signal.series_kind is SeriesKind.SCIENTIFIC_SIGNAL for signal in bundle.signals)
    assert [signal.x_values for signal in bundle.signals] == [
        pytest.approx((0.0, 1 / 600)),
        pytest.approx((0.0, 1 / 600)),
    ]
    assert {signal.x_unit for signal in bundle.signals} == {"min"}
    assert {signal.y_unit for signal in bundle.signals} == {None}
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["producer_version"] == "YL-Clarity 9.2.0.0"
    assert metadata["producer_evidence_status"] == "compatible_unvalidated"
    assert metadata["producer_support_mode"] == "family_compatible_experimental"
    assert metadata["detector_verified"] is False
    assert metadata["signal_unit_status"] == "unresolved"
    assert metadata["scientific_semantics_status"] == "family_compatible_experimental"
    assert metadata["scientific_family_compared_point_count"] == 454_220
    assert "paired_curve_time_decimal_places" not in metadata
    assert "paired_curve_signal_decimal_places" not in metadata
    assert "paired_curve_distinct_pair_count" not in metadata
    assert "paired_curve_compared_point_count" not in metadata
    rendered = "\n".join(
        [
            *(str(entry.value) for entry in bundle.metadata),
            *(issue.message for issue in bundle.warnings),
        ]
    )
    assert private_serial not in rendered
    assert {issue.code for issue in bundle.warnings} == {
        "YOUNGIN_PRM_FAMILY_COMPATIBLE_SCIENTIFIC_UNIT_UNRESOLVED"
    }


@pytest.mark.parametrize(
    "producer_text",
    (
        "YL-Clarity 8.9.0.0 FULL, SN: SYNTHETIC",
        "YL-Clarity 10.0.0.0 FULL, SN: SYNTHETIC",
        "YL-Clarity 9.2.0 FULL, SN: SYNTHETIC",
        "YL-Clarity 9.2.0.0 SYNTHETIC",
    ),
)
def test_producer_outside_bounded_9_x_family_fails_closed(
    tmp_path: Path, producer_text: str
) -> None:
    assert (
        _error(
            _write(tmp_path / "unsupported.prm", synthetic_prm_bytes(producer_text=producer_text))
        )
        == "YOUNGIN_PRM_PROFILE_UNSUPPORTED"
    )


def test_scientific_fingerprint_incomplete_downgrades_9_0_and_unknown_to_records(
    tmp_path: Path,
) -> None:
    for index, producer_text in enumerate(
        (
            binary.PRODUCER_PREFIX_TEXT + "SYNTHETIC",
            "YL-Clarity 9.2.0.0 FULL, SN: SYNTHETIC",
        )
    ):
        bundle = YoungInYlClarityPrmRawAdapter().parse(
            _write(
                tmp_path / f"downgrade-{index}.prm",
                synthetic_prm_bytes(producer_text=producer_text, d_step=2),
            ),
            ParseOptions(),
        )
        assert all(signal.series_kind is SeriesKind.DECODED_RECORDS for signal in bundle.signals)
        metadata = {entry.key: entry.value for entry in bundle.metadata}
        assert metadata["scientific_family_fingerprint_status"] == (
            "time_metadata_outside_validated_family"
        )
        assert metadata["producer_support_mode"] == "structural_only"


def test_known_9_1_corrupted_scientific_fingerprint_is_rejected(tmp_path: Path) -> None:
    data = synthetic_prm_bytes(
        producer_text=binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SYNTHETIC",
        channels=((1.0,), (2.0,)),
        min_ticks=601.0,
    )
    assert _error(_write(tmp_path / "invalid-9-1.prm", data)) == ("YOUNGIN_PRM_PROFILE_UNSUPPORTED")


def test_stored_label_allowlist_and_exact_profile_sequence_are_enforced(tmp_path: Path) -> None:
    unsupported = synthetic_prm_bytes(stored_labels=("MSD",))
    assert _error(_write(tmp_path / "unsupported.prm", unsupported)) == (
        "YOUNGIN_PRM_CHANNEL_IDENTITY_UNSUPPORTED"
    )
    wrong_order = synthetic_prm_bytes(channels=((1.0,), (2.0,)), stored_labels=("TCD", "FID"))
    assert _error(_write(tmp_path / "wrong-order.prm", wrong_order)) == (
        "YOUNGIN_PRM_CHANNEL_PROFILE_UNSUPPORTED"
    )
    overlong = synthetic_prm_bytes(stored_labels=("FID2",))
    assert _error(_write(tmp_path / "overlong.prm", overlong)) == (
        "YOUNGIN_PRM_CHANNEL_IDENTITY_INVALID"
    )


def test_exact_channel_adjacency_tail_and_terminal_branch_are_enforced(tmp_path: Path) -> None:
    valid = synthetic_prm_bytes(channels=((1.0,), (2.0,)))
    raw_offset = valid.index(RAW_DATA_KEY)
    compressed_size = struct.unpack_from("<I", valid, raw_offset + len(RAW_DATA_KEY))[0]
    raw_end = raw_offset + len(RAW_DATA_KEY) + 4 + compressed_size
    with_gap = valid[:raw_end] + b"\x00" + valid[raw_end:]
    assert _error(_write(tmp_path / "gap.prm", with_gap)) == ("YOUNGIN_PRM_SECTION_AMBIGUOUS")

    tail = bytearray(valid)
    pda_offset = tail.index(b"\x0fPDASpectrumName\x03")
    tail[pda_offset + 1] ^= 1
    assert _error(_write(tmp_path / "tail.prm", bytes(tail))) == (
        "YOUNGIN_PRM_CHANNEL_IDENTITY_INVALID"
    )

    terminal = bytearray(synthetic_prm_bytes())
    branch_offset = terminal.index(b"\x09Detectors")
    terminal[branch_offset] = 0x08
    assert _error(_write(tmp_path / "terminal.prm", bytes(terminal))) == (
        "YOUNGIN_PRM_CHANNEL_IDENTITY_INVALID"
    )


def test_history_count_must_precede_its_paired_version(tmp_path: Path) -> None:
    valid = synthetic_prm_bytes()
    count_offset = valid.index(binary.COUNT_KEY)
    count_end = count_offset + len(binary.COUNT_KEY) + 4
    version_offset = valid.index(binary.VERSION_KEY, count_end)
    version_end = version_offset + len(binary.VERSION_KEY) + 4
    reordered = (
        valid[:count_offset]
        + valid[version_offset:version_end]
        + valid[count_offset:count_end]
        + valid[version_end:]
    )
    assert _error(_write(tmp_path / "history.prm", reordered)) == "YOUNGIN_PRM_HISTORY_INVALID"


def test_record_and_decompression_limits_are_checked_before_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path / "FID_STD_001.prm")
    monkeypatch.setattr(binary, "MAX_UNCOMPRESSED_BLOCK_BYTES", 4)
    assert _error(path) == "YOUNGIN_PRM_DECOMPRESSION_LIMIT"


def test_prior_history_raw_blocks_are_counted_and_explicitly_not_exposed(
    tmp_path: Path,
) -> None:
    data = synthetic_prm_bytes(history_count=2)
    first_count = data.index(COUNT_KEY)
    second_count = data.index(COUNT_KEY, first_count + 1)
    current_start = data.index(RAW_DATA_KEY)
    footer_start = data.rindex(FOOTER_MARKER)
    prior_section = data[current_start:footer_start]
    with_prior = data[:second_count] + prior_section + data[second_count:]

    bundle = YoungInYlClarityPrmRawAdapter().parse(
        _write(tmp_path / "history.prm", with_prior), ParseOptions()
    )
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["prior_history_revision_count"] == 1
    assert metadata["prior_rawdata6_block_count"] == 1
    assert metadata["prior_prmdata_block_count"] == 1
    assert metadata["prior_history_revisions_exposed"] == 0
    assert len(bundle.signals) == 1
    assert "YOUNGIN_PRM_PRIOR_HISTORY_NOT_EXPOSED" in {issue.code for issue in bundle.warnings}
