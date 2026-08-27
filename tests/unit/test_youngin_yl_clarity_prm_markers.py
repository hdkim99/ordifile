from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

from ordifile.adapters._youngin_yl_clarity_prm_binary import read_prm
from ordifile.adapters._youngin_yl_clarity_prm_markers import (
    MARKER_APEX,
    MARKER_END,
    MARKER_START,
    MARKER_VALLEY,
    MARKERS_DATA_PREFIX,
    PrmMarker,
    build_peak_windows,
    read_prm_markers,
)

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_youngin_yl_clarity_prm import synthetic_prm_bytes  # noqa: E402


def test_marker_reader_preserves_source_order_and_builds_shared_valley_windows(
    tmp_path: Path,
) -> None:
    records = (
        (MARKER_START, 0),
        (MARKER_APEX, 2),
        (MARKER_VALLEY, 4),
        (MARKER_APEX, 6),
        (MARKER_END, 8),
    )
    data = synthetic_prm_bytes(
        channels=(tuple(float(index) for index in range(9)),),
        marker_records=(records,),
    )
    path = tmp_path / "synthetic.prm"
    path.write_bytes(data)

    decoded = read_prm_markers(
        path,
        expected_sha256=hashlib.sha256(data).hexdigest(),
        layout=read_prm(path).current_revision_layout,
        record_counts=(9,),
    )

    assert decoded.status == "matched"
    assert decoded.integration_type == 0x17
    assert tuple((item.marker_type, item.record_index) for item in decoded.channels[0]) == records
    windows = build_peak_windows(decoded.channels[0])
    assert windows.status == "matched"
    assert tuple(
        (
            item.start_index,
            item.stored_apex_index,
            item.end_index,
            item.cluster_start_index,
            item.cluster_end_index,
        )
        for item in windows.windows
    ) == ((0, 2, 4, 0, 8), (4, 6, 8, 0, 8))


def test_marker_capability_is_absent_without_optional_marker_array(tmp_path: Path) -> None:
    data = synthetic_prm_bytes()
    path = tmp_path / "synthetic.prm"
    path.write_bytes(data)

    decoded = read_prm_markers(
        path,
        expected_sha256=hashlib.sha256(data).hexdigest(),
        layout=read_prm(path).current_revision_layout,
        record_counts=(3,),
    )

    assert decoded.status == "absent"
    assert decoded.channels == ((),)


def test_marker_reader_rejects_out_of_range_index_without_affecting_raw_parser(
    tmp_path: Path,
) -> None:
    data = synthetic_prm_bytes(
        marker_records=(((MARKER_START, 0), (MARKER_APEX, 2), (MARKER_END, 4)),),
    )
    path = tmp_path / "synthetic.prm"
    path.write_bytes(data)

    decoded = read_prm_markers(
        path,
        expected_sha256=hashlib.sha256(data).hexdigest(),
        layout=read_prm(path).current_revision_layout,
        record_counts=(3,),
    )

    assert decoded.status == "invalid"
    assert decoded.issue_code == "YOUNGIN_PRM_MARKER_INDEX_INVALID"


def test_marker_sequence_rejects_apex_without_end_boundary() -> None:
    records = (
        PrmMarker(MARKER_START, 0),
        PrmMarker(MARKER_APEX, 1),
    )

    result = build_peak_windows(records)

    assert result.status == "invalid"
    assert result.issue_code == "YOUNGIN_PRM_MARKER_SEQUENCE_INVALID"


def test_marker_sequence_allows_only_observed_incomplete_patterns() -> None:
    complete = (
        PrmMarker(MARKER_START, 0),
        PrmMarker(MARKER_APEX, 1),
        PrmMarker(MARKER_END, 2),
    )

    repeated_end = build_peak_windows(
        (*complete, PrmMarker(MARKER_END, 3), PrmMarker(MARKER_START, 4))
    )
    detached_end = build_peak_windows((PrmMarker(MARKER_END, 0),))
    start_then_end = build_peak_windows((PrmMarker(MARKER_START, 0), PrmMarker(MARKER_END, 1)))
    incomplete_valley_cluster = build_peak_windows(
        (
            PrmMarker(MARKER_START, 0),
            PrmMarker(MARKER_APEX, 1),
            PrmMarker(MARKER_VALLEY, 2),
        )
    )

    assert repeated_end.status == "matched"
    assert len(repeated_end.windows) == 1
    assert repeated_end.ignored_marker_count == 2
    assert detached_end.status == "invalid"
    assert start_then_end.status == "invalid"
    assert incomplete_valley_cluster.status == "invalid"


def test_marker_reader_ignores_marker_like_bytes_inside_raw_payload(tmp_path: Path) -> None:
    raw_bytes = MARKERS_DATA_PREFIX + bytes((-len(MARKERS_DATA_PREFIX)) % 4)
    raw_values = struct.unpack(f"<{len(raw_bytes) // 4}f", raw_bytes)
    data = synthetic_prm_bytes(channels=(raw_values,))
    path = tmp_path / "synthetic.prm"
    path.write_bytes(data)

    parsed = read_prm(path)
    decoded = read_prm_markers(
        path,
        expected_sha256=hashlib.sha256(data).hexdigest(),
        layout=parsed.current_revision_layout,
        record_counts=(len(raw_values),),
    )

    assert decoded.status == "absent"


def test_marker_reader_rejects_payload_crossing_structural_raw_boundary(
    tmp_path: Path,
) -> None:
    data = bytearray(
        synthetic_prm_bytes(
            marker_records=(((MARKER_START, 0), (MARKER_APEX, 1), (MARKER_END, 2)),),
        )
    )
    path = tmp_path / "synthetic.prm"
    path.write_bytes(data)
    layout = read_prm(path).current_revision_layout
    marker_offset = data.index(MARKERS_DATA_PREFIX, layout.channels[0].metadata_start)
    length_offset = marker_offset + len(MARKERS_DATA_PREFIX)
    struct.pack_into(
        "<I",
        data,
        length_offset,
        layout.channels[0].raw_key_offset - length_offset,
    )
    path.write_bytes(data)

    decoded = read_prm_markers(
        path,
        expected_sha256=hashlib.sha256(data).hexdigest(),
        layout=layout,
        record_counts=(3,),
    )

    assert decoded.status == "invalid"
    assert decoded.issue_code == "YOUNGIN_PRM_MARKERS_TRUNCATED"
