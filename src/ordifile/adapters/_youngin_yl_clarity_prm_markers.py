# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded reader for stored YL-Clarity PRM integration markers.

The marker stream is not a stored Result table.  It describes peak partitions that
Ordifile may use for an explicitly derived chromatographic calculation.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from ordifile.adapters._youngin_yl_clarity_prm_binary import PrmCurrentRevisionLayout

INT_TYPE_KEY = b"\x07IntType\x01"
MARKERS_DATA_PREFIX = (
    bytes.fromhex("fffeff07")
    + "Markers".encode("utf-16-le")
    + bytes(4)
    + struct.pack("<I", 1)
    + b"\x04Data\x04"
)

MARKER_START = 0x20
MARKER_VALLEY = 0x40
MARKER_APEX = 0x50
MARKER_END = 0x80
SUPPORTED_MARKER_TYPES = frozenset({MARKER_START, MARKER_VALLEY, MARKER_APEX, MARKER_END})

MAX_PRM_FILE_BYTES = 16 * 1024 * 1024
MAX_MARKERS_PER_CHANNEL = 100_000


@dataclass(frozen=True, slots=True)
class PrmMarker:
    """One source-ordered marker type and zero-based raw-record index."""

    marker_type: int
    record_index: int


@dataclass(frozen=True, slots=True)
class PrmMarkerDecode:
    """Optional marker capability decoded independently of the raw signal."""

    status: str
    integration_type: int | None
    channels: tuple[tuple[PrmMarker, ...], ...]
    issue_code: str | None = None
    issue_message: str | None = None


@dataclass(frozen=True, slots=True)
class PrmPeakWindow:
    """One stored marker partition used for an Ordifile-derived peak."""

    start_index: int
    stored_apex_index: int
    end_index: int
    cluster_start_index: int
    cluster_end_index: int


@dataclass(frozen=True, slots=True)
class PrmPeakWindows:
    """Validated peak windows or a capability-local marker grammar failure."""

    status: str
    windows: tuple[PrmPeakWindow, ...]
    ignored_marker_count: int = 0
    issue_code: str | None = None
    issue_message: str | None = None


def _invalid(code: str, message: str, channel_count: int) -> PrmMarkerDecode:
    return PrmMarkerDecode(
        "invalid",
        None,
        tuple(() for _ in range(channel_count)),
        code,
        message,
    )


def _find_all(data: bytes, marker: bytes, *, maximum: int) -> tuple[int, ...] | None:
    offsets: list[int] = []
    cursor = 0
    while True:
        offset = data.find(marker, cursor)
        if offset < 0:
            return tuple(offsets)
        offsets.append(offset)
        if len(offsets) > maximum:
            return None
        cursor = offset + 1


def read_prm_markers(
    path: Path,
    *,
    expected_sha256: str,
    layout: PrmCurrentRevisionLayout,
    record_counts: tuple[int, ...],
) -> PrmMarkerDecode:
    """Read current-revision marker arrays without changing the source file."""
    channel_count = len(record_counts)
    try:
        size = path.stat().st_size
        if size > MAX_PRM_FILE_BYTES:
            return _invalid(
                "YOUNGIN_PRM_MARKERS_FILE_SIZE_UNSUPPORTED",
                "The source exceeds the bounded PRM marker-reader size.",
                channel_count,
            )
        data = path.read_bytes()
    except OSError:
        return _invalid(
            "YOUNGIN_PRM_MARKERS_READ_FAILED",
            "The optional PRM integration markers could not be read.",
            channel_count,
        )
    if len(data) != size or hashlib.sha256(data).hexdigest() != expected_sha256:
        return _invalid(
            "YOUNGIN_PRM_MARKERS_SOURCE_CHANGED",
            "The source changed between structural and marker decoding.",
            channel_count,
        )

    if (
        layout.revision_header_start < 0
        or layout.revision_header_start >= layout.revision_body_start
        or layout.footer_offset > len(data)
        or layout.revision_body_start >= layout.footer_offset
        or len(layout.channels) != channel_count
        or any(
            channel.metadata_start < layout.revision_body_start
            or channel.metadata_start >= channel.raw_key_offset
            or channel.raw_key_offset > layout.footer_offset
            for channel in layout.channels
        )
    ):
        return _invalid(
            "YOUNGIN_PRM_MARKERS_LAYOUT_INVALID",
            "The structural parser did not provide valid current-channel marker boundaries.",
            channel_count,
        )

    marker_offsets_by_channel: list[int | None] = []
    for channel in layout.channels:
        relative_offsets = _find_all(
            data[channel.metadata_start : channel.raw_key_offset],
            MARKERS_DATA_PREFIX,
            maximum=1,
        )
        if relative_offsets is None:
            return _invalid(
                "YOUNGIN_PRM_MARKERS_AMBIGUOUS",
                "A current channel metadata span contains multiple marker arrays.",
                channel_count,
            )
        marker_offsets_by_channel.append(
            None if not relative_offsets else channel.metadata_start + relative_offsets[0]
        )
    if all(offset is None for offset in marker_offsets_by_channel):
        return PrmMarkerDecode(
            "absent",
            None,
            tuple(() for _ in range(channel_count)),
        )
    if any(offset is None for offset in marker_offsets_by_channel):
        return _invalid(
            "YOUNGIN_PRM_MARKERS_CHANNEL_COUNT_INVALID",
            "Marker-array count does not match the structural channel count.",
            channel_count,
        )

    int_type_offsets = _find_all(
        data[layout.revision_header_start : layout.revision_body_start],
        INT_TYPE_KEY,
        maximum=1,
    )
    if int_type_offsets is None or len(int_type_offsets) != 1:
        return _invalid(
            "YOUNGIN_PRM_INTEGRATION_TYPE_INVALID",
            "The current PRM revision does not contain one bounded integration type.",
            channel_count,
        )
    int_type_offset = layout.revision_header_start + int_type_offsets[0] + len(INT_TYPE_KEY)
    if int_type_offset + 4 > layout.revision_body_start:
        return _invalid(
            "YOUNGIN_PRM_INTEGRATION_TYPE_INVALID",
            "The current PRM integration type is truncated.",
            channel_count,
        )
    integration_type = int(struct.unpack_from("<I", data, int_type_offset)[0])

    channels: list[tuple[PrmMarker, ...]] = []
    for channel_index, candidate_offset in enumerate(marker_offsets_by_channel):
        assert candidate_offset is not None
        offset = candidate_offset
        channel_boundary = layout.channels[channel_index].raw_key_offset
        length_offset = offset + len(MARKERS_DATA_PREFIX)
        if length_offset + 4 > len(data):
            return _invalid(
                "YOUNGIN_PRM_MARKERS_TRUNCATED",
                "A PRM marker array lacks its bounded byte count.",
                channel_count,
            )
        payload_size = int(struct.unpack_from("<I", data, length_offset)[0])
        if payload_size % 4 or payload_size > MAX_MARKERS_PER_CHANNEL * 4:
            return _invalid(
                "YOUNGIN_PRM_MARKERS_SIZE_INVALID",
                "A PRM marker array has an unsupported bounded size.",
                channel_count,
            )
        payload_start = length_offset + 4
        payload_end = payload_start + payload_size
        if payload_end > channel_boundary:
            return _invalid(
                "YOUNGIN_PRM_MARKERS_TRUNCATED",
                "A PRM marker array extends beyond the source boundary.",
                channel_count,
            )
        markers: list[PrmMarker] = []
        previous_index = -1
        for (encoded,) in struct.iter_unpack("<I", data[payload_start:payload_end]):
            marker_type = (encoded >> 24) & 0xFF
            record_index = encoded & 0x00FF_FFFF
            if marker_type not in SUPPORTED_MARKER_TYPES:
                return _invalid(
                    "YOUNGIN_PRM_MARKER_TYPE_UNSUPPORTED",
                    "A PRM marker has an unsupported bounded type.",
                    channel_count,
                )
            if record_index < previous_index or record_index >= record_counts[channel_index]:
                return _invalid(
                    "YOUNGIN_PRM_MARKER_INDEX_INVALID",
                    "A PRM marker index is out of order or outside its raw channel.",
                    channel_count,
                )
            markers.append(PrmMarker(marker_type, record_index))
            previous_index = record_index
        channels.append(tuple(markers))
    return PrmMarkerDecode("matched", integration_type, tuple(channels))


def build_peak_windows(markers: tuple[PrmMarker, ...]) -> PrmPeakWindows:
    """Interpret the bounded start/apex/valley/end marker state machine."""
    windows: list[PrmPeakWindow] = []
    ignored = 0
    cursor = 0
    while cursor < len(markers):
        marker = markers[cursor]
        if marker.marker_type == MARKER_END:
            # Adjacent repeated end markers occur in the controlled corpus and do not
            # add a peak.  A leading or otherwise detached end marker is not accepted.
            if cursor == 0 or markers[cursor - 1].marker_type != MARKER_END:
                return PrmPeakWindows(
                    "invalid",
                    (),
                    ignored,
                    "YOUNGIN_PRM_MARKER_SEQUENCE_INVALID",
                    "A stored end marker is detached from a completed marker cluster.",
                )
            ignored += 1
            cursor += 1
            continue
        if marker.marker_type != MARKER_START:
            return PrmPeakWindows(
                "invalid",
                (),
                ignored,
                "YOUNGIN_PRM_MARKER_SEQUENCE_INVALID",
                "A marker cluster does not begin with a stored start marker.",
            )
        cluster_start = marker.record_index
        cursor += 1
        if cursor == len(markers):
            # A final start-only marker occurs in the controlled corpus and describes
            # no complete peak partition.
            ignored += 1
            break
        cluster_windows: list[tuple[int, int, int]] = []
        left_boundary = cluster_start
        while cursor < len(markers):
            apex = markers[cursor]
            if apex.marker_type == MARKER_END:
                return PrmPeakWindows(
                    "invalid",
                    (),
                    ignored,
                    "YOUNGIN_PRM_MARKER_SEQUENCE_INVALID",
                    "A stored start marker is followed by an end without an apex.",
                )
            if apex.marker_type != MARKER_APEX or cursor + 1 >= len(markers):
                return PrmPeakWindows(
                    "invalid",
                    (),
                    ignored,
                    "YOUNGIN_PRM_MARKER_SEQUENCE_INVALID",
                    "A marker cluster lacks an ordered apex and boundary pair.",
                )
            right_boundary = markers[cursor + 1]
            if right_boundary.marker_type not in {MARKER_VALLEY, MARKER_END}:
                return PrmPeakWindows(
                    "invalid",
                    (),
                    ignored,
                    "YOUNGIN_PRM_MARKER_SEQUENCE_INVALID",
                    "A stored apex is not followed by a valley or end marker.",
                )
            if not (left_boundary <= apex.record_index <= right_boundary.record_index):
                return PrmPeakWindows(
                    "invalid",
                    (),
                    ignored,
                    "YOUNGIN_PRM_MARKER_WINDOW_INVALID",
                    "A stored peak marker lies outside its bounded partition.",
                )
            cluster_windows.append((left_boundary, apex.record_index, right_boundary.record_index))
            cursor += 2
            if right_boundary.marker_type == MARKER_END:
                cluster_end = right_boundary.record_index
                windows.extend(
                    PrmPeakWindow(start, stored_apex, end, cluster_start, cluster_end)
                    for start, stored_apex, end in cluster_windows
                )
                break
            left_boundary = right_boundary.record_index
        else:
            return PrmPeakWindows(
                "invalid",
                (),
                ignored,
                "YOUNGIN_PRM_MARKER_SEQUENCE_INVALID",
                "A marker cluster ends without a stored end boundary.",
            )
    return PrmPeakWindows("matched", tuple(windows), ignored)
