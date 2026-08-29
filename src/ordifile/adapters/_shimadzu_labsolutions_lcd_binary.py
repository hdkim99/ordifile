# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded reader for the Shimadzu LabSolutions ``.LCD`` TTFL raw-data profile.

``.LCD`` compound documents carry two unrelated internal architectures.  This reader
supports only the **TTFL** family, whose acquisition channels live under
``TTFL Raw Data``.  The other family, whose raw data lives under ``TLM Raw Data``,
has a different stream set and a non-uniform retention grid; it is refused here
rather than guessed at.

Nothing in this module integrates a signal or recalculates a vendor result.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import olefile

CFB_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
CFB_HEADER_BYTES = 4_096
MAX_LCD_FILE_BYTES = 512 * 1024 * 1024
MAX_DIRECTORY_ENTRIES = 1_024
MAX_FILE_PROPERTY_BYTES = 64 * 1024

RAW_STORAGE = "TTFL Raw Data"
FILE_PROPERTY_PATH = ("File Property",)
RETENTION_TIME_PATH = (RAW_STORAGE, "Retention Time")
DATA_INDEX_PATH = (RAW_STORAGE, "Data Index")
MS_RAW_DATA_PATH = (RAW_STORAGE, "MS Raw Data")
REQUIRED_PATHS = frozenset(
    {FILE_PROPERTY_PATH, RETENTION_TIME_PATH, DATA_INDEX_PATH, MS_RAW_DATA_PATH}
)
# The competing architecture, refused with a specific code so the reason is legible.
TLM_RAW_STORAGE = "TLM Raw Data"

# Channels occupy a fixed 32-slot array; unused slots exist as zero-byte streams.
CHANNEL_SLOT_COUNT = 32
CHANNEL_STREAM_PREFIX = "TIC Data "

MIN_SCAN_COUNT = 2
MAX_SCAN_COUNT = 1_000_000
CHANNEL_HEADER_BYTES = 768
CHANNEL_RECORD_BYTES = 16
INDEX_RECORD_BYTES = 16

MILLISECONDS_PER_MINUTE = 60_000.0


class ShimadzuLcdStructureError(Exception):
    """Bounded structural error translated by the public adapter."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _fail(code: str, message: str, **details: Any) -> ShimadzuLcdStructureError:
    return ShimadzuLcdStructureError(code, message, **details)


@dataclass(frozen=True, slots=True)
class ShimadzuLcdChannel:
    """One acquisition channel read from its fixed slot."""

    slot: int
    first_scan_index: int
    retention_times_min: tuple[float, ...]
    intensities: tuple[int, ...]
    secondary_intensities: tuple[int, ...]
    stored_scan_count: int
    spectrum_count: int


@dataclass(frozen=True, slots=True)
class ShimadzuLcdData:
    """Verified TTFL channels plus the structural facts that back them."""

    file_schema: str
    scan_count: int
    rt_start_ms: int
    rt_end_ms: int
    rt_interval_min_ms: int
    rt_interval_max_ms: int
    channels: tuple[ShimadzuLcdChannel, ...]
    index_record_count: int
    ms_raw_stream_bytes: int
    file_property_stream_sha256: str
    retention_time_stream_sha256: str
    data_index_stream_sha256: str


def _preflight_cfb(path: Path) -> int:
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            header = stream.read(CFB_HEADER_BYTES)
    except OSError as error:
        raise _fail(
            "SHIMADZU_LCD_HEADER_INVALID",
            "The input could not be read as a bounded compound document.",
        ) from error
    if size > MAX_LCD_FILE_BYTES:
        raise _fail(
            "SHIMADZU_LCD_PROFILE_UNSUPPORTED",
            "The compound document exceeds the supported LCD size boundary.",
            maximum_bytes=MAX_LCD_FILE_BYTES,
            actual_bytes=size,
        )
    if size < CFB_HEADER_BYTES:
        raise _fail("SHIMADZU_LCD_TRUNCATED", "The compound-document header is truncated.")
    if header[:8] != CFB_MAGIC:
        raise _fail("SHIMADZU_LCD_HEADER_INVALID", "The compound-document signature is invalid.")
    minor_version = struct.unpack_from("<H", header, 24)[0]
    major_version = struct.unpack_from("<H", header, 26)[0]
    byte_order = header[28:30]
    sector_shift = struct.unpack_from("<H", header, 30)[0]
    if (
        minor_version != 62
        or byte_order != b"\xfe\xff"
        or (major_version, sector_shift) not in {(3, 9), (4, 12)}
    ):
        raise _fail(
            "SHIMADZU_LCD_PROFILE_UNSUPPORTED",
            "Only the validated little-endian CFB v3/512 and v4/4096 profiles are supported.",
            major_version=major_version,
            sector_shift=sector_shift,
        )
    return size


def _read_stream(
    container: olefile.OleFileIO[str],
    path: tuple[str, ...],
    *,
    maximum_size: int,
) -> bytes:
    try:
        size = container.get_size(path)
    except (OSError, ValueError, TypeError, IndexError) as error:
        raise _fail(
            "SHIMADZU_LCD_PROFILE_UNSUPPORTED",
            "A required TTFL stream is unavailable.",
        ) from error
    if size < 1 or size > maximum_size:
        raise _fail(
            "SHIMADZU_LCD_ARRAY_INVALID",
            "A required TTFL stream has an unsupported size.",
            stream_bytes=size,
            maximum_bytes=maximum_size,
        )
    try:
        with container.openstream(path) as stream:
            data = stream.read(maximum_size + 1)
    except (OSError, ValueError, TypeError, IndexError) as error:
        raise _fail(
            "SHIMADZU_LCD_TRUNCATED",
            "A required TTFL stream could not be read completely.",
        ) from error
    if len(data) != size:
        raise _fail(
            "SHIMADZU_LCD_TRUNCATED",
            "A required TTFL stream ended before its directory-declared size.",
        )
    return data


def _is_safe_entry_name(name: str) -> bool:
    """Return whether a directory entry name is safe to list.

    MS-CFB reserves a leading character below 0x20 for the implementation, which real
    documents use for embedded-object streams such as ``\x02OlePres000``.  One such
    leading character is permitted; control characters anywhere else are not.
    """
    if not name:
        return False
    body = name[1:] if 1 <= ord(name[0]) < 32 else name
    return bool(body) and not any(ord(ch) < 32 or ord(ch) == 127 for ch in body)


def _validate_inventory(container: olefile.OleFileIO[str]) -> None:
    listed = [tuple(item) for item in container.listdir(streams=True, storages=True)]
    if len(listed) > MAX_DIRECTORY_ENTRIES:
        raise _fail(
            "SHIMADZU_LCD_PROFILE_UNSUPPORTED",
            "The compound document has too many directory entries.",
            actual_entries=len(listed),
        )
    if getattr(container, "parsing_issues", ()):
        raise _fail(
            "SHIMADZU_LCD_HEADER_INVALID",
            "The compound document reported structural parsing defects.",
        )
    for item in listed:
        if any(not _is_safe_entry_name(part) for part in item):
            raise _fail(
                "SHIMADZU_LCD_HEADER_INVALID",
                "The compound directory contains an unsafe name.",
            )
    if any(item and item[0] == TLM_RAW_STORAGE for item in listed):
        raise _fail(
            "SHIMADZU_LCD_ARCHITECTURE_UNSUPPORTED",
            "This document uses the TLM raw-data architecture, which this reader does "
            "not support; only the TTFL architecture is validated.",
        )
    if not REQUIRED_PATHS.issubset(set(listed)):
        raise _fail(
            "SHIMADZU_LCD_PROFILE_UNSUPPORTED",
            "One or more case-exact TTFL profile paths are absent.",
        )


def _file_schema(data: bytes) -> str:
    if len(data) < 16:
        raise _fail(
            "SHIMADZU_LCD_PROFILE_UNSUPPORTED",
            "The File Property stream is shorter than its validated header.",
        )
    try:
        schema = data[4:9].split(b"\x00", 1)[0].decode("ascii", errors="strict")
    except UnicodeDecodeError as error:
        raise _fail(
            "SHIMADZU_LCD_PROFILE_UNSUPPORTED",
            "The File Property schema token is malformed.",
        ) from error
    if not schema:
        raise _fail(
            "SHIMADZU_LCD_PROFILE_UNSUPPORTED",
            "The File Property schema token is empty.",
        )
    return schema


def _decode_retention(data: bytes) -> tuple[tuple[int, ...], int, int]:
    if len(data) % 4:
        raise _fail(
            "SHIMADZU_LCD_ARRAY_INVALID",
            "The retention-time stream is not a whole number of 32-bit samples.",
        )
    count = len(data) // 4
    if not MIN_SCAN_COUNT <= count <= MAX_SCAN_COUNT:
        raise _fail(
            "SHIMADZU_LCD_ARRAY_INVALID",
            "The TTFL scan count is outside the bounded reader range.",
            scan_count=count,
        )
    times = tuple(value[0] for value in struct.iter_unpack("<I", data))
    steps = [right - left for left, right in zip(times, times[1:], strict=False)]
    if any(step <= 0 for step in steps):
        raise _fail(
            "SHIMADZU_LCD_ARRAY_INVALID",
            "The retention-time sequence is not strictly increasing.",
        )
    # The grid is deliberately not required to be uniform.  A scan at which a second
    # channel also acquires costs extra time, so its step is longer; the number of long
    # steps matches that channel's spectrum count exactly in every observed file.
    return times, min(steps), max(steps)


def _decode_chains(
    data: bytes, scan_count: int, ms_raw_bytes: int
) -> tuple[tuple[int, int, int], ...]:
    """Return each chain's ``(first_scan, last_scan, record_count)``, in chain order.

    ``Data Index`` records are ``[u64 offset][i32 scan index][i32 previous record]``.
    Records form one linked chain per acquisition channel; a chain head stores ``-1``.
    """
    if len(data) % INDEX_RECORD_BYTES:
        raise _fail(
            "SHIMADZU_LCD_INDEX_INVALID",
            "The data index is not a whole number of validated records.",
        )
    count = len(data) // INDEX_RECORD_BYTES
    if not 1 <= count <= MAX_SCAN_COUNT:
        raise _fail(
            "SHIMADZU_LCD_INDEX_INVALID",
            "The data-index record count is outside the bounded reader range.",
            record_count=count,
        )
    offsets: list[int] = []
    scans: list[int] = []
    previous: list[int] = []
    for index in range(count):
        offset, scan, prior = struct.unpack_from("<Qii", data, index * INDEX_RECORD_BYTES)
        offsets.append(offset)
        scans.append(scan)
        previous.append(prior)
    if offsets[0] != 0 or any(
        right <= left for left, right in zip(offsets, offsets[1:], strict=False)
    ):
        raise _fail(
            "SHIMADZU_LCD_INDEX_INVALID",
            "The data-index offsets are not a strict in-order partition.",
        )
    if offsets[-1] >= ms_raw_bytes:
        raise _fail(
            "SHIMADZU_LCD_INDEX_INVALID",
            "A data-index offset is outside the MS Raw Data stream.",
        )
    if any(not 0 <= scan < scan_count for scan in scans):
        raise _fail(
            "SHIMADZU_LCD_INDEX_INVALID",
            "A data-index record names a scan outside the retention axis.",
        )
    if any(not -1 <= prior < count for prior in previous):
        raise _fail(
            "SHIMADZU_LCD_INDEX_INVALID",
            "A data-index record names a predecessor outside the record array.",
        )

    successor: dict[int, int] = {}
    for index, prior in enumerate(previous):
        if prior == -1:
            continue
        if prior in successor:
            raise _fail(
                "SHIMADZU_LCD_INDEX_INVALID",
                "A data-index record is claimed by two successors.",
            )
        successor[prior] = index

    chains: list[tuple[int, int, int]] = []
    visited = 0
    for head in (index for index, prior in enumerate(previous) if prior == -1):
        length = 0
        current: int | None = head
        first_scan = scans[head]
        last_scan = -1
        while current is not None:
            length += 1
            visited += 1
            if visited > count:
                raise _fail(
                    "SHIMADZU_LCD_INDEX_INVALID",
                    "The data-index chains revisit a record.",
                )
            if scans[current] <= last_scan:
                raise _fail(
                    "SHIMADZU_LCD_INDEX_INVALID",
                    "A data-index chain is not in strictly ascending scan order.",
                )
            last_scan = scans[current]
            current = successor.get(current)
        chains.append((first_scan, last_scan, length))
    if visited != count:
        raise _fail(
            "SHIMADZU_LCD_INDEX_INVALID",
            "The data-index chains do not cover every record exactly once.",
            covered=visited,
            record_count=count,
        )
    return tuple(chains)


def _decode_channel(
    payload: bytes,
    slot: int,
    chain: tuple[int, int, int],
    retention_ms: tuple[int, ...],
) -> ShimadzuLcdChannel:
    """Decode one ``TIC Data`` slot against the chain that fixes its retention window."""
    first_scan, last_scan, spectrum_count = chain
    if len(payload) < CHANNEL_HEADER_BYTES + CHANNEL_RECORD_BYTES:
        raise _fail(
            "SHIMADZU_LCD_CHANNEL_INVALID",
            "A channel stream is shorter than its validated header and first record.",
            slot=slot,
        )
    declared = struct.unpack_from("<Q", payload, 0)[0]
    if declared > MAX_SCAN_COUNT:
        raise _fail(
            "SHIMADZU_LCD_CHANNEL_INVALID",
            "A channel declares more scans than the bounded reader accepts.",
            slot=slot,
            declared=declared,
        )
    if len(payload) != CHANNEL_HEADER_BYTES + declared * CHANNEL_RECORD_BYTES:
        raise _fail(
            "SHIMADZU_LCD_CHANNEL_INVALID",
            "A channel stream length disagrees with its declared scan count.",
            slot=slot,
            declared=declared,
            stream_bytes=len(payload),
        )
    # The window a slot covers is exactly the scan span of its chain.
    if last_scan - first_scan + 1 != declared:
        raise _fail(
            "SHIMADZU_LCD_CHANNEL_INVALID",
            "A channel's declared scan count does not match its chain's scan span.",
            slot=slot,
            declared=declared,
            span=last_scan - first_scan + 1,
        )
    if last_scan >= len(retention_ms):
        raise _fail(
            "SHIMADZU_LCD_CHANNEL_INVALID",
            "A channel window extends past the retention axis.",
            slot=slot,
        )
    intensities: list[int] = []
    secondary: list[int] = []
    for index in range(declared):
        base = CHANNEL_HEADER_BYTES + index * CHANNEL_RECORD_BYTES
        primary = struct.unpack_from("<Q", payload, base)[0]
        second = struct.unpack_from("<I", payload, base + 8)[0]
        # The u32 at offset 12 has no established meaning and is deliberately not read.
        if second > primary:
            raise _fail(
                "SHIMADZU_LCD_CHANNEL_INVALID",
                "A channel record's secondary intensity exceeds its primary intensity.",
                slot=slot,
                record_index=index,
            )
        intensities.append(primary)
        secondary.append(second)
    times = tuple(
        retention_ms[first_scan + index] / MILLISECONDS_PER_MINUTE for index in range(declared)
    )
    return ShimadzuLcdChannel(
        slot=slot,
        first_scan_index=first_scan,
        retention_times_min=times,
        intensities=tuple(intensities),
        secondary_intensities=tuple(secondary),
        stored_scan_count=declared,
        spectrum_count=spectrum_count,
    )


def has_lcd_stream_identity(path: Path) -> bool:
    """Return whether the exact case-sensitive TTFL stream identity is present."""
    try:
        _preflight_cfb(path)
        with path.open("rb") as handle:
            with olefile.OleFileIO(
                handle, raise_defects=olefile.DEFECT_INCORRECT, write_mode=False
            ) as container:
                listed = {tuple(item) for item in container.listdir(streams=True, storages=True)}
                return REQUIRED_PATHS.issubset(listed)
    except (ShimadzuLcdStructureError, OSError, ValueError, TypeError, IndexError):
        return False


def read_lcd(path: Path) -> ShimadzuLcdData:
    """Read the validated TTFL multi-channel profile from an ``.LCD`` document."""
    _preflight_cfb(path)
    try:
        with path.open("rb") as handle:
            with olefile.OleFileIO(
                handle, raise_defects=olefile.DEFECT_INCORRECT, write_mode=False
            ) as container:
                _validate_inventory(container)
                file_property = _read_stream(
                    container, FILE_PROPERTY_PATH, maximum_size=MAX_FILE_PROPERTY_BYTES
                )
                schema = _file_schema(file_property)
                retention_data = _read_stream(
                    container, RETENTION_TIME_PATH, maximum_size=MAX_SCAN_COUNT * 4
                )
                retention_ms, interval_min, interval_max = _decode_retention(retention_data)
                index_data = _read_stream(
                    container,
                    DATA_INDEX_PATH,
                    maximum_size=MAX_SCAN_COUNT * INDEX_RECORD_BYTES,
                )
                ms_raw_bytes = container.get_size(MS_RAW_DATA_PATH)
                chains = _decode_chains(index_data, len(retention_ms), ms_raw_bytes)
                populated: list[tuple[int, bytes]] = []
                for slot in range(CHANNEL_SLOT_COUNT):
                    slot_path = (RAW_STORAGE, f"{CHANNEL_STREAM_PREFIX}{slot}")
                    if not container.exists("/".join(slot_path)):
                        continue
                    if container.get_size(slot_path) == 0:
                        continue
                    populated.append(
                        (
                            slot,
                            _read_stream(
                                container,
                                slot_path,
                                maximum_size=CHANNEL_HEADER_BYTES
                                + MAX_SCAN_COUNT * CHANNEL_RECORD_BYTES,
                            ),
                        )
                    )
                if len(populated) != len(chains):
                    raise _fail(
                        "SHIMADZU_LCD_CHANNEL_INVALID",
                        "The populated channel slots and the data-index chains disagree in number.",
                        populated_slots=len(populated),
                        chain_count=len(chains),
                    )
                channels = tuple(
                    _decode_channel(payload, slot, chain, retention_ms)
                    for (slot, payload), chain in zip(populated, chains, strict=True)
                )
    except ShimadzuLcdStructureError:
        raise
    except (OSError, ValueError, TypeError, IndexError, struct.error) as error:
        raise _fail(
            "SHIMADZU_LCD_HEADER_INVALID",
            "The bounded compound document could not be parsed safely.",
        ) from error

    return ShimadzuLcdData(
        file_schema=schema,
        scan_count=len(retention_ms),
        rt_start_ms=retention_ms[0],
        rt_end_ms=retention_ms[-1],
        rt_interval_min_ms=interval_min,
        rt_interval_max_ms=interval_max,
        channels=channels,
        index_record_count=len(index_data) // INDEX_RECORD_BYTES,
        ms_raw_stream_bytes=ms_raw_bytes,
        file_property_stream_sha256=hashlib.sha256(file_property).hexdigest(),
        retention_time_stream_sha256=hashlib.sha256(retention_data).hexdigest(),
        data_index_stream_sha256=hashlib.sha256(index_data).hexdigest(),
    )
