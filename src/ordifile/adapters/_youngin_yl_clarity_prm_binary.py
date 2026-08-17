# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded structural reader for one observed YoungIn YL-Clarity ``.PRM`` profile.

The reader exposes ordered IEEE-754 binary32 records and allowlisted stored channel
labels only. Candidate fields such as ``MinTicks`` are retained as structural metadata
and are deliberately not interpreted as time, verified detector identity, scaling, or
physical units.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

START_MAGIC = bytes.fromhex("5aa50008")
FOOTER_MARKER = bytes.fromhex("4d4bfa08")
FOOTER_BYTES = 20
PRODUCER_PREFIX_TEXT = "YL-Clarity 9.0.1.19 FULL, SN: "
PRODUCER_PREFIX = PRODUCER_PREFIX_TEXT.encode("utf-16-le")

COUNT_KEY = b"\x10CountOfDetectors\x01"
VERSION_KEY = b"\x0dChromVersion1\x01"
RAW_DATA_KEY = b"\x08RAWData6\x05"
PRM_DATA_KEY = b"\x07PRMData\x05"
DET_NAME_KEY = b"\x07DetName\x03"
DET_NAME_VALUE_PREFIX = bytes.fromhex("fffeff03")
STORED_DETECTOR_LABEL_BYTES = 6
DET_NAME_FOLLOWING_PROPERTY = b"\x0fPDASpectrumName\x03"
DET_NAME_FIXED_TAIL = (
    DET_NAME_FOLLOWING_PROPERTY
    + bytes.fromhex("fffeff00")
    + b"\x0eMSSpectrumName\x03"
    + bytes.fromhex("fffeff00")
    + b"\x09DetSigGen\x01"
    + bytes(4)
)
NONTERMINAL_CHANNEL_BRANCH = 0xFF
TERMINAL_CHANNEL_MARKER = b"\x09Detectors"
SUPPORTED_STORED_LABEL_PROFILES = frozenset({("TCD",), ("FID", "TCD")})
PRM_METADATA_BYTES = 53
DET_NAME_OFFSET_AFTER_PRM_PAYLOAD = 31

MAX_PRM_FILE_BYTES = 16 * 1024 * 1024
MAX_COMPRESSED_BLOCK_BYTES = 8 * 1024 * 1024
MAX_UNCOMPRESSED_BLOCK_BYTES = 8 * 1024 * 1024
MAX_RECORDS_PER_CHANNEL = MAX_UNCOMPRESSED_BLOCK_BYTES // 4
MAX_HISTORY_COUNT = 3
MAX_CHANNEL_COUNT = 2


class YoungInPrmStructureError(Exception):
    """Privacy-safe structural error translated by the public adapter."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True, slots=True)
class PrmRawChannel:
    """One ordered duplicate-validated raw binary32 channel."""

    channel_id: str
    stored_detector_label: str
    values: tuple[float, ...]
    record_count: int
    raw_size_candidate: int
    d_step_candidate: int
    d_size_candidate: int
    min_ticks_candidate: float
    payload_sha256: str
    canonical_be_f32_sha256: str


@dataclass(frozen=True, slots=True)
class YoungInPrmData:
    """Structural facts for the exact observed profile."""

    profile: str
    history_count: int
    selected_history_version: int
    prior_history_revision_count: int
    prior_rawdata6_block_count: int
    prior_prmdata_block_count: int
    structural_channel_count: int
    channels: tuple[PrmRawChannel, ...]
    aggregate_payload_sha256: str
    aggregate_canonical_be_f32_sha256: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class _EncodedBlock:
    key_offset: int
    data_offset: int
    end_offset: int
    compressed: bytes


def _fail(code: str, message: str, **details: Any) -> YoungInPrmStructureError:
    return YoungInPrmStructureError(code, message, **details)


def _find_all(data: bytes, marker: bytes, *, maximum: int) -> tuple[int, ...]:
    offsets: list[int] = []
    start = 0
    while True:
        offset = data.find(marker, start)
        if offset < 0:
            return tuple(offsets)
        offsets.append(offset)
        if len(offsets) > maximum:
            raise _fail(
                "YOUNGIN_PRM_SECTION_AMBIGUOUS",
                "The file contains more repeated structural markers than the supported profile.",
                maximum_occurrences=maximum,
            )
        start = offset + 1


def _u32_after(data: bytes, offset: int, marker: bytes) -> int:
    value_offset = offset + len(marker)
    if value_offset + 4 > len(data):
        raise _fail(
            "YOUNGIN_PRM_HEADER_TRUNCATED",
            "A structural property is missing its bounded unsigned value.",
            property_offset=offset,
        )
    return int(struct.unpack_from("<I", data, value_offset)[0])


def _parse_encoded_block(
    data: bytes,
    offset: int,
    marker: bytes,
    *,
    payload_boundary: int,
) -> _EncodedBlock:
    length_offset = offset + len(marker)
    if length_offset + 4 > payload_boundary:
        raise _fail(
            "YOUNGIN_PRM_DATA_BLOCK_TRUNCATED",
            "A raw data block is missing its bounded length field.",
            block_offset=offset,
        )
    compressed_size = int(struct.unpack_from("<I", data, length_offset)[0])
    if compressed_size < 1 or compressed_size > MAX_COMPRESSED_BLOCK_BYTES:
        raise _fail(
            "YOUNGIN_PRM_DATA_BLOCK_INVALID",
            "A compressed raw data block has an unsupported size.",
            compressed_bytes=compressed_size,
            maximum_bytes=MAX_COMPRESSED_BLOCK_BYTES,
        )
    data_offset = length_offset + 4
    end_offset = data_offset + compressed_size
    if end_offset > payload_boundary:
        raise _fail(
            "YOUNGIN_PRM_DATA_BLOCK_TRUNCATED",
            "A compressed raw data block extends beyond the validated data boundary.",
            compressed_bytes=compressed_size,
        )
    compressed = data[data_offset:end_offset]
    if not compressed.startswith(b"\x1f\x8b"):
        raise _fail(
            "YOUNGIN_PRM_COMPRESSION_INVALID",
            "A raw data block does not contain the required gzip member.",
        )
    return _EncodedBlock(offset, data_offset, end_offset, compressed)


def _decompress_exact_member(compressed: bytes) -> bytes:
    decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    try:
        payload = decoder.decompress(compressed, MAX_UNCOMPRESSED_BLOCK_BYTES + 1)
    except zlib.error as error:
        raise _fail(
            "YOUNGIN_PRM_COMPRESSION_INVALID",
            "A raw data gzip member could not be decoded safely.",
        ) from error
    if len(payload) > MAX_UNCOMPRESSED_BLOCK_BYTES or decoder.unconsumed_tail:
        raise _fail(
            "YOUNGIN_PRM_DECOMPRESSION_LIMIT",
            "A raw data gzip member exceeds the bounded decompression limit.",
            maximum_bytes=MAX_UNCOMPRESSED_BLOCK_BYTES,
        )
    try:
        payload += decoder.flush()
    except zlib.error as error:
        raise _fail(
            "YOUNGIN_PRM_COMPRESSION_INVALID",
            "A raw data gzip member could not be finalized safely.",
        ) from error
    if len(payload) > MAX_UNCOMPRESSED_BLOCK_BYTES:
        raise _fail(
            "YOUNGIN_PRM_DECOMPRESSION_LIMIT",
            "A raw data gzip member exceeds the bounded decompression limit.",
            maximum_bytes=MAX_UNCOMPRESSED_BLOCK_BYTES,
        )
    if not decoder.eof:
        raise _fail(
            "YOUNGIN_PRM_COMPRESSION_TRUNCATED",
            "A raw data gzip member ends before its checksum and length trailer.",
        )
    if decoder.unused_data:
        raise _fail(
            "YOUNGIN_PRM_COMPRESSION_TRAILING_DATA",
            "A raw data block contains a second gzip member or trailing bytes.",
        )
    return payload


def _metadata_before_prm(data: bytes, prm_offset: int) -> tuple[int, int, int, float]:
    start = prm_offset - PRM_METADATA_BYTES
    if start < 0:
        raise _fail(
            "YOUNGIN_PRM_CHANNEL_METADATA_INVALID",
            "A PRM data block lacks its exact bounded structural metadata prefix.",
        )
    cursor = start

    def property_value(marker: bytes) -> int:
        nonlocal cursor
        if data[cursor : cursor + len(marker)] != marker:
            raise _fail(
                "YOUNGIN_PRM_CHANNEL_METADATA_INVALID",
                "A channel structural property is absent or out of source order.",
            )
        cursor += len(marker)
        if cursor + 4 > prm_offset:
            raise _fail(
                "YOUNGIN_PRM_CHANNEL_METADATA_INVALID",
                "A channel structural property is truncated.",
            )
        value = int(struct.unpack_from("<I", data, cursor)[0])
        cursor += 4
        return value

    raw_size = property_value(b"\x07RAWSize\x01")
    d_step = property_value(b"\x05DStep\x01")
    d_size = property_value(b"\x05DSize\x01")
    min_ticks_marker = b"\x08MinTicks\x02"
    if data[cursor : cursor + len(min_ticks_marker)] != min_ticks_marker:
        raise _fail(
            "YOUNGIN_PRM_CHANNEL_METADATA_INVALID",
            "The channel MinTicks candidate property is absent or out of source order.",
        )
    cursor += len(min_ticks_marker)
    if cursor + 8 != prm_offset:
        raise _fail(
            "YOUNGIN_PRM_CHANNEL_METADATA_INVALID",
            "The channel MinTicks candidate property has an invalid boundary.",
        )
    min_ticks = float(struct.unpack_from("<d", data, cursor)[0])
    if not isfinite(min_ticks):
        raise _fail(
            "YOUNGIN_PRM_CHANNEL_METADATA_INVALID",
            "The channel MinTicks candidate is not finite.",
        )
    return raw_size, d_step, d_size, min_ticks


def _validate_nonoverlap(intervals: list[tuple[int, int]]) -> None:
    previous_end = -1
    for start, end in sorted(intervals):
        if start < previous_end:
            raise _fail(
                "YOUNGIN_PRM_SECTION_AMBIGUOUS",
                "Two structural data sections overlap.",
            )
        previous_end = end


def _canonical_aggregate(payloads: tuple[bytes, ...], *, domain: bytes) -> str:
    digest = hashlib.sha256(domain)
    for payload in payloads:
        digest.update(struct.pack(">I", len(payload)))
        digest.update(payload)
    return digest.hexdigest()


def read_prm(path: Path) -> YoungInPrmData:
    """Read ordered current-revision binary32 records from the observed profile."""
    try:
        size = path.stat().st_size
        if size > MAX_PRM_FILE_BYTES:
            raise _fail(
                "YOUNGIN_PRM_FILE_SIZE_UNSUPPORTED",
                "The file exceeds the bounded experimental PRM profile size.",
                maximum_bytes=MAX_PRM_FILE_BYTES,
                actual_bytes=size,
            )
        data = path.read_bytes()
    except OSError as error:
        raise _fail(
            "YOUNGIN_PRM_READ_FAILED",
            "The input could not be read as a bounded PRM file.",
        ) from error
    if len(data) != size:
        raise _fail(
            "YOUNGIN_PRM_FILE_CHANGED",
            "The input size changed during the bounded read.",
        )
    if size < len(START_MAGIC) + FOOTER_BYTES or data[:4] != START_MAGIC:
        raise _fail(
            "YOUNGIN_PRM_HEADER_INVALID",
            "The exact PRM start marker is absent.",
        )
    footer_offset = size - FOOTER_BYTES
    if data[footer_offset : footer_offset + len(FOOTER_MARKER)] != FOOTER_MARKER:
        raise _fail(
            "YOUNGIN_PRM_FILE_LENGTH_MISMATCH",
            "The exact footer marker is not at the validated end-relative boundary.",
        )
    if PRODUCER_PREFIX not in data[:footer_offset]:
        raise _fail(
            "YOUNGIN_PRM_PROFILE_UNSUPPORTED",
            "The exact observed YL-Clarity producer profile is absent.",
        )

    version_offsets = _find_all(data[:footer_offset], VERSION_KEY, maximum=MAX_HISTORY_COUNT)
    count_offsets = _find_all(data[:footer_offset], COUNT_KEY, maximum=MAX_HISTORY_COUNT)
    history_count = len(version_offsets)
    if history_count < 1 or len(count_offsets) != history_count:
        raise _fail(
            "YOUNGIN_PRM_HISTORY_INVALID",
            "Detector-count and chromatogram-version history entries are incomplete or ambiguous.",
            detector_count_entries=len(count_offsets),
            version_entries=history_count,
        )
    if any(
        count_offset >= version_offset
        for count_offset, version_offset in zip(count_offsets, version_offsets, strict=True)
    ):
        raise _fail(
            "YOUNGIN_PRM_HISTORY_INVALID",
            "Each structural channel count must precede its paired history version.",
        )
    versions = tuple(_u32_after(data, offset, VERSION_KEY) for offset in version_offsets)
    if versions != tuple(range(1, history_count + 1)):
        raise _fail(
            "YOUNGIN_PRM_HISTORY_INVALID",
            "Chromatogram history versions are not the exact supported source-order sequence.",
            history_entries=history_count,
        )
    detector_counts = tuple(_u32_after(data, offset, COUNT_KEY) for offset in count_offsets)
    if len(set(detector_counts)) != 1:
        raise _fail(
            "YOUNGIN_PRM_CHANNEL_COUNT_INVALID",
            "Structural channel counts disagree across chromatogram history entries.",
        )
    channel_count = detector_counts[0]
    if channel_count < 1 or channel_count > MAX_CHANNEL_COUNT:
        raise _fail(
            "YOUNGIN_PRM_CHANNEL_COUNT_UNSUPPORTED",
            "The structural channel count is outside the exact observed profile boundary.",
            structural_channel_count=channel_count,
            maximum_channels=MAX_CHANNEL_COUNT,
        )

    current_boundary = version_offsets[-1]
    all_raw_offsets = _find_all(
        data[:footer_offset], RAW_DATA_KEY, maximum=MAX_HISTORY_COUNT * MAX_CHANNEL_COUNT
    )
    all_prm_offsets = _find_all(
        data[:footer_offset], PRM_DATA_KEY, maximum=MAX_HISTORY_COUNT * MAX_CHANNEL_COUNT
    )
    raw_offsets = tuple(offset for offset in all_raw_offsets if offset > current_boundary)
    prm_offsets = tuple(offset for offset in all_prm_offsets if offset > current_boundary)
    if len(raw_offsets) != channel_count or len(prm_offsets) != channel_count:
        raise _fail(
            "YOUNGIN_PRM_CHANNEL_COUNT_INVALID",
            "Current raw data block counts do not match the structural channel count.",
            structural_channel_count=channel_count,
            raw_blocks=len(raw_offsets),
            prm_blocks=len(prm_offsets),
        )

    raw_blocks = tuple(
        _parse_encoded_block(data, offset, RAW_DATA_KEY, payload_boundary=footer_offset)
        for offset in raw_offsets
    )
    prm_blocks = tuple(
        _parse_encoded_block(data, offset, PRM_DATA_KEY, payload_boundary=footer_offset)
        for offset in prm_offsets
    )
    if any(
        raw_block.end_offset != prm_block.key_offset - PRM_METADATA_BYTES
        for raw_block, prm_block in zip(raw_blocks, prm_blocks, strict=True)
    ):
        raise _fail(
            "YOUNGIN_PRM_SECTION_AMBIGUOUS",
            "Each RAWData6 payload must be followed immediately by its exact channel metadata.",
        )
    det_name_offsets = tuple(
        offset
        for offset in _find_all(
            data[:footer_offset], DET_NAME_KEY, maximum=MAX_HISTORY_COUNT * MAX_CHANNEL_COUNT
        )
        if offset > current_boundary
    )
    if len(det_name_offsets) != channel_count or any(
        det_name_offset != prm_block.end_offset + DET_NAME_OFFSET_AFTER_PRM_PAYLOAD
        for det_name_offset, prm_block in zip(det_name_offsets, prm_blocks, strict=True)
    ):
        raise _fail(
            "YOUNGIN_PRM_CHANNEL_IDENTITY_INVALID",
            "Each current PRM data block must have one source-ordered DetName structural property.",
            structural_channel_count=channel_count,
            det_name_entries=len(det_name_offsets),
        )
    stored_labels: list[str] = []
    for index, offset in enumerate(det_name_offsets):
        value_offset = offset + len(DET_NAME_KEY)
        value_end = value_offset + len(DET_NAME_VALUE_PREFIX) + STORED_DETECTOR_LABEL_BYTES
        if (
            value_end > footer_offset
            or data[value_offset : value_offset + len(DET_NAME_VALUE_PREFIX)]
            != DET_NAME_VALUE_PREFIX
            or data[value_end : value_end + len(DET_NAME_FOLLOWING_PROPERTY)]
            != DET_NAME_FOLLOWING_PROPERTY
        ):
            raise _fail(
                "YOUNGIN_PRM_CHANNEL_IDENTITY_INVALID",
                "A DetName structural property has unsupported bounded value framing.",
            )
        raw_label = data[value_offset + len(DET_NAME_VALUE_PREFIX) : value_end]
        try:
            label = raw_label.decode("utf-16-le", errors="strict")
        except UnicodeDecodeError as error:
            raise _fail(
                "YOUNGIN_PRM_CHANNEL_IDENTITY_INVALID",
                "A DetName structural property is not valid bounded UTF-16LE.",
            ) from error
        if label not in {"FID", "TCD"}:
            raise _fail(
                "YOUNGIN_PRM_CHANNEL_IDENTITY_UNSUPPORTED",
                "A stored native channel label is outside the exact experimental allowlist.",
            )
        stored_labels.append(label)
        tail_end = value_end + len(DET_NAME_FIXED_TAIL)
        if data[value_end:tail_end] != DET_NAME_FIXED_TAIL:
            raise _fail(
                "YOUNGIN_PRM_CHANNEL_IDENTITY_INVALID",
                "A DetName structural property lacks the exact bounded empty/zero tail.",
            )
        if index + 1 < channel_count:
            next_raw_offset = raw_blocks[index + 1].key_offset
            if tail_end >= next_raw_offset or data[tail_end] != NONTERMINAL_CHANNEL_BRANCH:
                raise _fail(
                    "YOUNGIN_PRM_CHANNEL_IDENTITY_INVALID",
                    "A nonterminal channel does not lead to the next RAWData6 block "
                    "in source order.",
                )
        elif data[tail_end : tail_end + len(TERMINAL_CHANNEL_MARKER)] != (TERMINAL_CHANNEL_MARKER):
            raise _fail(
                "YOUNGIN_PRM_CHANNEL_IDENTITY_INVALID",
                "The terminal channel lacks the exact observed Detectors branch marker.",
            )
    if tuple(stored_labels) not in SUPPORTED_STORED_LABEL_PROFILES:
        raise _fail(
            "YOUNGIN_PRM_CHANNEL_PROFILE_UNSUPPORTED",
            "The stored native channel label sequence is outside the observed profiles.",
            structural_channel_count=channel_count,
        )
    _validate_nonoverlap(
        [(block.key_offset, block.end_offset) for block in raw_blocks]
        + [(block.key_offset - PRM_METADATA_BYTES, block.end_offset) for block in prm_blocks]
    )

    channels: list[PrmRawChannel] = []
    raw_payloads: list[bytes] = []
    canonical_payloads: list[bytes] = []
    for index, (raw_block, prm_block) in enumerate(
        zip(raw_blocks, prm_blocks, strict=True), start=1
    ):
        if raw_block.key_offset >= prm_block.key_offset:
            raise _fail(
                "YOUNGIN_PRM_SECTION_AMBIGUOUS",
                "A paired raw data block is not before its PRM duplicate in source order.",
            )
        if raw_block.compressed != prm_block.compressed:
            raise _fail(
                "YOUNGIN_PRM_DUPLICATE_MISMATCH",
                "The paired RAWData6 and PRMData compressed bytes differ.",
                structural_channel=index,
            )
        payload = _decompress_exact_member(prm_block.compressed)
        if not payload or len(payload) % 4:
            raise _fail(
                "YOUNGIN_PRM_RECORD_COUNT_INVALID",
                "A decoded raw data payload is empty or not divisible into binary32 records.",
                structural_channel=index,
                payload_bytes=len(payload),
            )
        record_count = len(payload) // 4
        if record_count > MAX_RECORDS_PER_CHANNEL:
            raise _fail(
                "YOUNGIN_PRM_RECORD_LIMIT",
                "A decoded raw channel exceeds the bounded record limit.",
                structural_channel=index,
                maximum_records=MAX_RECORDS_PER_CHANNEL,
            )
        raw_size, d_step, d_size, min_ticks = _metadata_before_prm(data, prm_block.key_offset)
        if raw_size != record_count or d_size != record_count or d_step != 1 or min_ticks != 600.0:
            raise _fail(
                "YOUNGIN_PRM_CHANNEL_METADATA_INVALID",
                "Candidate channel sizes or exact structural constants disagree with the payload.",
                structural_channel=index,
                record_count=record_count,
                raw_size_candidate=raw_size,
                d_size_candidate=d_size,
                d_step_candidate=d_step,
            )
        values = tuple(value[0] for value in struct.iter_unpack("<f", payload))
        if any(not isfinite(value) for value in values):
            raise _fail(
                "YOUNGIN_PRM_NUMERIC_INVALID",
                "A raw channel contains a non-finite decoded binary32 record.",
                structural_channel=index,
            )
        canonical = b"".join(struct.pack(">f", value) for value in values)
        raw_payloads.append(payload)
        canonical_payloads.append(canonical)
        channels.append(
            PrmRawChannel(
                channel_id=f"native_label_{stored_labels[index - 1]}",
                stored_detector_label=stored_labels[index - 1],
                values=values,
                record_count=record_count,
                raw_size_candidate=raw_size,
                d_step_candidate=d_step,
                d_size_candidate=d_size,
                min_ticks_candidate=min_ticks,
                payload_sha256=hashlib.sha256(payload).hexdigest(),
                canonical_be_f32_sha256=hashlib.sha256(canonical).hexdigest(),
            )
        )

    return YoungInPrmData(
        profile="YL-Clarity 9.0.1.19 observed PRM raw profile",
        history_count=history_count,
        selected_history_version=history_count,
        prior_history_revision_count=history_count - 1,
        prior_rawdata6_block_count=sum(offset < current_boundary for offset in all_raw_offsets),
        prior_prmdata_block_count=sum(offset < current_boundary for offset in all_prm_offsets),
        structural_channel_count=channel_count,
        channels=tuple(channels),
        aggregate_payload_sha256=_canonical_aggregate(
            tuple(raw_payloads), domain=b"ordifile-youngin-prm-raw-v1\0"
        ),
        aggregate_canonical_be_f32_sha256=_canonical_aggregate(
            tuple(canonical_payloads), domain=b"ordifile-youngin-prm-f32be-v1\0"
        ),
        source_sha256=hashlib.sha256(data).hexdigest(),
    )


def has_prm_family_identity(path: Path) -> bool:
    """Return whether bounded content contains both non-secret family markers."""
    try:
        size = path.stat().st_size
        if size < len(START_MAGIC) or size > MAX_PRM_FILE_BYTES:
            return False
        data = path.read_bytes()
    except OSError:
        return False
    return len(data) == size and data[:4] == START_MAGIC and PRODUCER_PREFIX in data
