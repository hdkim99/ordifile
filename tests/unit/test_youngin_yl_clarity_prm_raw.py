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


def _write(path: Path, data: bytes | None = None) -> Path:
    path.write_bytes(synthetic_prm_bytes() if data is None else data)
    return path


def _error(path: Path) -> str:
    with pytest.raises(ParseError) as caught:
        YoungInYlClarityPrmRawAdapter().parse(path, ParseOptions())
    return caught.value.code


def test_descriptor_and_detection_are_exact_and_experimental(tmp_path: Path) -> None:
    adapter = YoungInYlClarityPrmRawAdapter()
    valid = _write(tmp_path / "FID_STD_001.prm")
    uppercase_extension = _write(tmp_path / "FID_STD_002.PRM")
    wrong_extension = _write(tmp_path / "FID_STD_001.bin")
    invalid = _write(tmp_path / "invalid.prm", b"not prm")

    assert adapter.descriptor.support_status is SupportStatus.EXPERIMENTAL
    assert adapter.descriptor.series_kinds == (SeriesKind.DECODED_RECORDS,)
    assert adapter.probe(valid).confidence == pytest.approx(0.99)
    assert adapter.probe(uppercase_extension).confidence == pytest.approx(0.99)
    assert adapter.parse(uppercase_extension, ParseOptions()).signals
    assert not adapter.probe(wrong_extension).matched
    assert not adapter.probe(invalid).matched
    assert _error(wrong_extension) == "YOUNGIN_PRM_EXTENSION_INVALID"


def test_single_channel_raw_records_and_user_label_are_not_detector_claims(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path / "FID_STD_001.prm")
    bundle = YoungInYlClarityPrmRawAdapter().parse(path, ParseOptions())

    assert bundle.samples[0].sample_id == "FID_STD_001"
    assert bundle.samples[0].channels == ("native_label_TCD",)
    assert bundle.samples[0].detectors == ()
    assert bundle.samples[0].acquired_at is None
    assert bundle.samples[0].runtime is None
    signal = bundle.signals[0]
    assert signal.channel == "native_label_TCD"
    assert signal.detector is None
    assert signal.x_values == (0, 1, 2)
    assert signal.y_values == pytest.approx((1.25, -2.5, 3.75))
    assert signal.x_label == "decoded_record_index"
    assert signal.x_unit is None
    assert signal.y_label == "decoded_raw_binary32"
    assert signal.y_unit is None
    assert signal.series_kind is SeriesKind.DECODED_RECORDS
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert metadata["user_supplied_group"] == "FID_STANDARD"
    assert metadata["detector_verified"] is False
    assert metadata["time_axis_status"] == "not_exposed"
    assert metadata["physical_scaling_status"] == "not_applied"
    assert metadata["signal_unit_status"] == "unresolved"
    assert bundle.samples[0].detectors == ()


@pytest.mark.parametrize(
    ("stem", "expected_group"),
    (
        ("FID_STD_010", "FID_STANDARD"),
        ("TCD_STD_010", "TCD_STANDARD"),
        ("MIXED_SAMPLE_003", "FID_TCD_SAMPLE"),
    ),
)
def test_exact_safe_aliases_preserve_user_group_only(
    tmp_path: Path, stem: str, expected_group: str
) -> None:
    bundle = YoungInYlClarityPrmRawAdapter().parse(_write(tmp_path / f"{stem}.prm"), ParseOptions())
    metadata = {entry.key: entry.value for entry in bundle.metadata}
    assert bundle.samples[0].sample_id == stem
    assert metadata["user_supplied_group"] == expected_group
    assert bundle.samples[0].detectors == ()


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


@pytest.mark.parametrize(
    ("data", "code"),
    (
        (
            synthetic_prm_bytes(producer_text="YL-Clarity 9.0.1.20 FULL, SN: SYNTHETIC"),
            "YOUNGIN_PRM_PROFILE_UNSUPPORTED",
        ),
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
        (synthetic_prm_bytes(d_step=2), "YOUNGIN_PRM_CHANNEL_METADATA_INVALID"),
        (synthetic_prm_bytes(min_ticks=601.0), "YOUNGIN_PRM_CHANNEL_METADATA_INVALID"),
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


def test_detname_is_required_only_as_opaque_source_order_structure(tmp_path: Path) -> None:
    valid = synthetic_prm_bytes(channels=((1.0,), (2.0,)))
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
