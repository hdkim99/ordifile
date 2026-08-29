# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded reader for one evidence-backed Shimadzu ``.QGD`` TIC profile.

The reader is an independent implementation based on public fixture observations.
It validates the MS1 stream structurally, one scan at a time, but intentionally does
not materialize or export the mass-spectrum rows.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import olefile

from ordifile.adapters._shimadzu_gcmssolution_qgd_peak_table import (
    MAX_PEAK_INFO_BYTES as MAX_MC_PEAK_INFO_BYTES,
)
from ordifile.adapters._shimadzu_gcmssolution_qgd_peak_table import (
    MAX_PEAK_TABLE_BYTES as MAX_MC_PEAK_TABLE_BYTES,
)

CFB_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
CFB_HEADER_BYTES = 4_096
MAX_QGD_FILE_BYTES = 64 * 1024 * 1024
MAX_DIRECTORY_ENTRIES = 512
# Two compound-document generations carry the same QGD streams: CFB v4 with 4096-byte
# sectors and the older CFB v3 with 512-byte sectors.
SUPPORTED_CFB_VERSIONS = frozenset({(3, 9), (4, 12)})
MAX_FILE_PROPERTY_BYTES = 64 * 1024
MAX_MS_RAW_BYTES = 48 * 1024 * 1024
MAX_MS1_POINTS_PER_SCAN = 4_096
MAX_MS1_LONG_ROWS = 20_000_000

FILE_PROPERTY_PATH = ("File Property",)
RAW_STORAGE_PATH = ("GCMS Raw Data",)
RETENTION_TIME_PATH = ("GCMS Raw Data", "Retention Time")
TIC_DATA_PATH = ("GCMS Raw Data", "TIC Data")
SPECTRUM_INDEX_PATH = ("GCMS Raw Data", "Spectrum Index")
MS_RAW_DATA_PATH = ("GCMS Raw Data", "MS Raw Data")
MC_PEAK_TABLE_PATH = ("GCMS Data Processing", "MC Peak Table")
MC_PEAK_INFO_PATH = ("GCMS Data Processing", "MC Peak Info")
REQUIRED_PATHS = frozenset(
    {
        FILE_PROPERTY_PATH,
        RAW_STORAGE_PATH,
        RETENTION_TIME_PATH,
        TIC_DATA_PATH,
        SPECTRUM_INDEX_PATH,
        MS_RAW_DATA_PATH,
    }
)

# Two generations carry the same QGD streams: File Property 2.00 written by
# GCMSsolution 2.x into CFB v3, and 4.00 written by 4.x into CFB v4.  Nothing is read
# out of File Property beyond this token; every array is validated on its own terms.
SUPPORTED_FILE_SCHEMAS = frozenset({"2.00", "4.00"})
# Two acquisition grids have fixture evidence (16,800 scans at 200 ms and 9,100 scans
# at 300 ms), so the grid is read from the document and checked for internal
# consistency instead of being pinned to a single observed acquisition.
MIN_SCAN_COUNT = 2
MAX_SCAN_COUNT = 200_000
EXPECTED_SCAN_TARGET = 0x01D60000
SUPPORTED_INTENSITY_WIDTHS = frozenset({2, 3})
SCAN_HEADER_BYTES = 32
# "Spectrum Index" appears in two observed encodings.  They can never be confused: a
# bare u32 array is a multiple of 4 bytes while the tagged u64 array is 2 modulo 4.
SPECTRUM_INDEX_U64_TAG = b"\x01\x00"
SPECTRUM_INDEX_WIDTHS = frozenset({4, 8})
# Offsets are canonicalised as big-endian u32, which both observed encodings fit.
MAX_CANONICAL_OFFSET = 2**32


class ShimadzuQgdStructureError(Exception):
    """Bounded structural error translated by the public adapter."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True, slots=True)
class ShimadzuQgdProfile:
    """Exact Stage A profile fields that have fixture evidence."""

    file_schema: str
    scan_count: int
    rt_start_ms: int
    rt_end_ms: int
    rt_interval_ms: int
    spectrum_index_offset_width: int = 4
    detector: str = "MS"
    channel: str = "TIC"


@dataclass(frozen=True, slots=True)
class ShimadzuQgdMs1Summary:
    """Bounded structural facts about MS1 data that was not exported."""

    stream_bytes: int
    long_row_count: int
    points_per_scan_min: int
    points_per_scan_max: int
    intensity_widths: tuple[int, ...]
    mass_raw_min: int
    mass_raw_max: int
    intensity_raw_min: int
    intensity_raw_max: int
    stream_sha256: str
    scan_summary_sha256: str


@dataclass(frozen=True, slots=True)
class ShimadzuQgdData:
    """Verified TIC coordinates plus structural MS1 validation results."""

    profile: ShimadzuQgdProfile
    retention_times_min: tuple[float, ...]
    tic_values: tuple[int, ...]
    ms1_summary: ShimadzuQgdMs1Summary | None
    file_property_stream_bytes: int
    file_property_stream_sha256: str
    retention_time_stream_sha256: str
    retention_time_canonical_be_u32_sha256: str
    retention_time_canonical_be_f64_sha256: str
    tic_stream_sha256: str
    tic_canonical_be_u64_sha256: str
    retention_time_tic_pairs_be_f64_u64_sha256: str
    spectrum_index_stream_sha256: str
    spectrum_index_canonical_be_u32_sha256: str
    mc_peak_table_payload: bytes | None = None
    mc_peak_info_payload: bytes | None = None


def _fail(code: str, message: str, **details: Any) -> ShimadzuQgdStructureError:
    return ShimadzuQgdStructureError(code, message, **details)


class _ReadableSeekable(Protocol):
    def seek(self, offset: int) -> int: ...

    def read(self, size: int = -1) -> bytes: ...


def _preflight_cfb(path: Path) -> int:
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            header = stream.read(CFB_HEADER_BYTES)
    except OSError as error:
        raise _fail(
            "SHIMADZU_QGD_HEADER_INVALID",
            "The input could not be read as a bounded compound document.",
        ) from error
    if size > MAX_QGD_FILE_BYTES:
        raise _fail(
            "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
            "The compound document exceeds the supported QGD profile size boundary.",
            maximum_bytes=MAX_QGD_FILE_BYTES,
            actual_bytes=size,
        )
    if size < CFB_HEADER_BYTES:
        raise _fail(
            "SHIMADZU_QGD_TRUNCATED",
            "The compound-document header is truncated.",
            expected_at_least=CFB_HEADER_BYTES,
            actual=size,
        )
    if header[:8] != CFB_MAGIC:
        raise _fail(
            "SHIMADZU_QGD_HEADER_INVALID",
            "The compound-document signature is invalid.",
        )
    minor_version = struct.unpack_from("<H", header, 24)[0]
    major_version = struct.unpack_from("<H", header, 26)[0]
    byte_order = header[28:30]
    sector_shift = struct.unpack_from("<H", header, 30)[0]
    mini_sector_shift = struct.unpack_from("<H", header, 32)[0]
    if (
        minor_version != 62
        or byte_order != b"\xfe\xff"
        or (major_version, sector_shift) not in SUPPORTED_CFB_VERSIONS
        or mini_sector_shift != 6
    ):
        raise _fail(
            "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
            "Only the validated little-endian CFB v3/512 and v4/4096 QGD profiles are supported.",
            minor_version=minor_version,
            major_version=major_version,
            sector_shift=sector_shift,
            mini_sector_shift=mini_sector_shift,
        )
    if size % (1 << sector_shift) != 0:
        raise _fail(
            "SHIMADZU_QGD_TRUNCATED",
            "The compound document ends inside a validated CFB sector.",
            sector_bytes=1 << sector_shift,
            actual_bytes=size,
        )
    return size


def _validate_inventory(container: olefile.OleFileIO[str]) -> None:
    listed = [
        tuple(component for component in item)
        for item in container.listdir(streams=True, storages=True)
    ]
    if len(listed) > MAX_DIRECTORY_ENTRIES:
        raise _fail(
            "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
            "The compound document has too many directory entries.",
            maximum_entries=MAX_DIRECTORY_ENTRIES,
            actual_entries=len(listed),
        )
    if getattr(container, "parsing_issues", ()):
        raise _fail(
            "SHIMADZU_QGD_HEADER_INVALID",
            "The compound document reported structural parsing defects.",
        )

    folded_paths: set[tuple[str, ...]] = set()
    for item in listed:
        if any(
            not component
            or any(ord(character) < 32 or ord(character) == 127 for character in component)
            for component in item
        ):
            raise _fail(
                "SHIMADZU_QGD_HEADER_INVALID",
                "The compound directory contains an unsafe name.",
            )
        folded = tuple(component.casefold() for component in item)
        if folded in folded_paths:
            raise _fail(
                "SHIMADZU_QGD_HEADER_INVALID",
                "The compound directory contains ambiguous case-folded names.",
            )
        folded_paths.add(folded)

    required_folded = {
        tuple(component.casefold() for component in item): item for item in REQUIRED_PATHS
    }
    if any(
        folded in required_folded and item != required_folded[folded]
        for item in listed
        for folded in (tuple(component.casefold() for component in item),)
    ):
        raise _fail(
            "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
            "A required stream name differs only by case from the exact QGD profile.",
        )
    if not REQUIRED_PATHS.issubset(set(listed)):
        raise _fail(
            "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
            "One or more case-exact QGD profile paths are absent.",
        )


def _read_stream(
    container: olefile.OleFileIO[str],
    path: tuple[str, ...],
    *,
    exact_size: int | None = None,
    maximum_size: int,
) -> bytes:
    try:
        size = container.get_size(path)
    except (OSError, ValueError, TypeError, IndexError) as error:
        raise _fail(
            "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
            "A required exact-profile stream is unavailable.",
        ) from error
    if size < 1 or size > maximum_size or (exact_size is not None and size != exact_size):
        raise _fail(
            "SHIMADZU_QGD_ARRAY_INVALID",
            "A required QGD array stream has an unsupported size.",
            stream_bytes=size,
            expected_bytes=exact_size,
            maximum_bytes=maximum_size,
        )
    try:
        with container.openstream(path) as stream:
            data = stream.read(maximum_size + 1)
    except (OSError, ValueError, TypeError, IndexError) as error:
        raise _fail(
            "SHIMADZU_QGD_TRUNCATED",
            "A required QGD stream could not be read completely.",
        ) from error
    if len(data) != size:
        raise _fail(
            "SHIMADZU_QGD_TRUNCATED",
            "A required QGD stream ended before its directory-declared size.",
            expected_bytes=size,
            actual_bytes=len(data),
        )
    return data


def _read_processing_stream(
    container: olefile.OleFileIO[str],
    path: tuple[str, ...],
    *,
    maximum_size: int,
) -> bytes | None:
    """Return a bounded processing payload, or ``None`` when the stream is absent.

    One byte past the bound is returned deliberately so that an oversized stream is
    reported by the peak-table decoder as a capability-local failure instead of
    discarding the scientific signal the document also carries.
    """
    try:
        if not container.exists("/".join(path)):
            return None
        with container.openstream(path) as stream:
            return stream.read(maximum_size + 1)
    except (OSError, ValueError, TypeError, IndexError):
        return None


def _file_schema(data: bytes) -> str:
    if len(data) < 152:
        raise _fail(
            "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
            "The File Property stream is shorter than the validated profile header.",
        )
    try:
        schema = data[4:9].split(b"\x00", 1)[0].decode("ascii", errors="strict")
    except UnicodeDecodeError as error:
        raise _fail(
            "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
            "The File Property schema token is malformed.",
        ) from error
    if schema not in SUPPORTED_FILE_SCHEMAS:
        raise _fail(
            "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
            "Only the validated File Property 2.00 and 4.00 QGD profiles are supported.",
            file_schema=schema,
        )
    return schema


def _decode_spectrum_index(index_data: bytes, scan_count: int) -> tuple[int, tuple[int, ...]]:
    """Return the offset width and scan offsets for either observed index encoding."""
    if len(index_data) == scan_count * 4:
        return 4, tuple(value[0] for value in struct.iter_unpack("<I", index_data))
    tag = len(SPECTRUM_INDEX_U64_TAG)
    if len(index_data) == tag + scan_count * 8 and index_data.startswith(SPECTRUM_INDEX_U64_TAG):
        return 8, tuple(value[0] for value in struct.iter_unpack("<Q", index_data[tag:]))
    raise _fail(
        "SHIMADZU_QGD_ARRAY_INVALID",
        "The spectrum index is not one of the validated offset encodings.",
        stream_bytes=len(index_data),
        scan_count=scan_count,
    )


def _decode_arrays(
    retention_data: bytes,
    tic_data: bytes,
    index_data: bytes,
) -> tuple[tuple[int, ...], tuple[float, ...], tuple[int, ...], tuple[int, ...], int, int]:
    if len(retention_data) % 4:
        raise _fail(
            "SHIMADZU_QGD_ARRAY_INVALID",
            "The retention-time stream is not a whole number of 32-bit samples.",
            stream_bytes=len(retention_data),
        )
    scan_count = len(retention_data) // 4
    if not MIN_SCAN_COUNT <= scan_count <= MAX_SCAN_COUNT:
        raise _fail(
            "SHIMADZU_QGD_ARRAY_INVALID",
            "The QGD scan count is outside the bounded reader range.",
            scan_count=scan_count,
            minimum_scans=MIN_SCAN_COUNT,
            maximum_scans=MAX_SCAN_COUNT,
        )
    if len(tic_data) != scan_count * 8:
        raise _fail(
            "SHIMADZU_QGD_ARRAY_INVALID",
            "The QGD RT and TIC sample counts are inconsistent.",
        )
    offset_width, offsets = _decode_spectrum_index(index_data, scan_count)
    retention_ms = tuple(value[0] for value in struct.iter_unpack("<I", retention_data))
    tic_values = tuple(value[0] for value in struct.iter_unpack("<Q", tic_data))
    interval_ms = retention_ms[1] - retention_ms[0]
    if interval_ms <= 0 or any(
        right - left != interval_ms
        for left, right in zip(retention_ms, retention_ms[1:], strict=False)
    ):
        raise _fail(
            "SHIMADZU_QGD_ARRAY_INVALID",
            "The retention-time sequence is not a strictly increasing uniform grid.",
        )
    if offsets[0] != 0 or any(
        right <= left for left, right in zip(offsets, offsets[1:], strict=False)
    ):
        raise _fail(
            "SHIMADZU_QGD_ARRAY_INVALID",
            "The spectrum-index offsets are not a strict in-order partition.",
        )
    if offsets[-1] >= MAX_CANONICAL_OFFSET:
        raise _fail(
            "SHIMADZU_QGD_ARRAY_INVALID",
            "A spectrum-index offset is outside the canonical 32-bit export range.",
        )
    retention_min = tuple(value / 60_000.0 for value in retention_ms)
    return retention_ms, retention_min, tic_values, offsets, interval_ms, offset_width


def _read_scan(stream: _ReadableSeekable, offset: int, length: int) -> bytes:
    if length < SCAN_HEADER_BYTES:
        raise _fail(
            "SHIMADZU_QGD_MS1_INVALID",
            "An indexed MS1 scan is shorter than its validated header.",
        )
    try:
        stream.seek(offset)
        data = bytes(stream.read(length))
    except (OSError, ValueError, TypeError, IndexError) as error:
        raise _fail(
            "SHIMADZU_QGD_TRUNCATED",
            "An indexed MS1 scan could not be read completely.",
        ) from error
    if len(data) != length:
        raise _fail(
            "SHIMADZU_QGD_TRUNCATED",
            "An indexed MS1 scan ended before its validated boundary.",
            expected_bytes=length,
            actual_bytes=len(data),
        )
    return data


def _validate_ms1(
    container: olefile.OleFileIO[str],
    retention_ms: tuple[int, ...],
    tic_values: tuple[int, ...],
    offsets: tuple[int, ...],
) -> ShimadzuQgdMs1Summary:
    stream_size = _ms_raw_stream_size(container, offsets)

    stream_digest = hashlib.sha256()
    summary_digest = hashlib.sha256()
    long_row_count = 0
    points_min = MAX_MS1_POINTS_PER_SCAN + 1
    points_max = 0
    widths: set[int] = set()
    mass_min = 2**16
    mass_max = -1
    intensity_min = 2**24
    intensity_max = -1

    try:
        with container.openstream(MS_RAW_DATA_PATH) as stream:
            for scan_index, start in enumerate(offsets):
                end = offsets[scan_index + 1] if scan_index + 1 < len(offsets) else stream_size
                if end <= start or end > stream_size:
                    raise _fail(
                        "SHIMADZU_QGD_MS1_INVALID",
                        "The spectrum index does not partition the MS Raw Data stream.",
                    )
                data = _read_scan(stream, start, end - start)
                stream_digest.update(data)
                encoded_scan, encoded_rt, target = struct.unpack_from("<III", data, 0)
                scan_number, reserved_a_tail = struct.unpack_from("<II", data, 12)
                width, point_count = struct.unpack_from("<HH", data, 20)
                reserved_b = struct.unpack_from("<II", data, 24)
                if (
                    encoded_scan != scan_index
                    or encoded_rt != retention_ms[scan_index]
                    or target != EXPECTED_SCAN_TARGET
                    or scan_number not in (0, scan_index + 1)
                    or reserved_a_tail != 0
                    or reserved_b != (0, 0)
                    # An empty scan carries no points, so its width field is unused
                    # and is not required to name an observed intensity width.
                    or (point_count and width not in SUPPORTED_INTENSITY_WIDTHS)
                    or point_count > MAX_MS1_POINTS_PER_SCAN
                ):
                    raise _fail(
                        "SHIMADZU_QGD_MS1_INVALID",
                        "An MS1 scan header is outside the exact validated profile.",
                        scan_index=scan_index,
                    )
                expected_size = SCAN_HEADER_BYTES + point_count * (2 + width)
                if len(data) != expected_size:
                    raise _fail(
                        "SHIMADZU_QGD_MS1_INVALID",
                        "An MS1 scan count, intensity width, and indexed length are inconsistent.",
                        scan_index=scan_index,
                        expected_bytes=expected_size,
                        actual_bytes=len(data),
                    )
                long_row_count += point_count
                if long_row_count > MAX_MS1_LONG_ROWS:
                    raise _fail(
                        "SHIMADZU_QGD_MS1_INVALID",
                        "The MS1 long-row count exceeds the bounded Stage A validation limit.",
                        maximum_rows=MAX_MS1_LONG_ROWS,
                    )
                points_min = min(points_min, point_count)
                points_max = max(points_max, point_count)
                if point_count:
                    widths.add(width)

                previous_mass = -1
                intensity_sum = 0
                cursor = SCAN_HEADER_BYTES
                for _ in range(point_count):
                    mass_raw = struct.unpack_from("<H", data, cursor)[0]
                    intensity_raw = int.from_bytes(
                        data[cursor + 2 : cursor + 2 + width], "little", signed=False
                    )
                    cursor += 2 + width
                    if mass_raw == 0 or mass_raw <= previous_mass:
                        raise _fail(
                            "SHIMADZU_QGD_MS1_INVALID",
                            "An MS1 scan contains a malformed or non-monotonic raw mass sequence.",
                            scan_index=scan_index,
                        )
                    previous_mass = mass_raw
                    mass_min = min(mass_min, mass_raw)
                    mass_max = max(mass_max, mass_raw)
                    intensity_min = min(intensity_min, intensity_raw)
                    intensity_max = max(intensity_max, intensity_raw)
                    intensity_sum += intensity_raw
                    if intensity_sum > 2**64 - 1:
                        raise _fail(
                            "SHIMADZU_QGD_MS1_INVALID",
                            "An MS1 intensity sum exceeds its TIC representation bound.",
                            scan_index=scan_index,
                        )
                if intensity_sum != tic_values[scan_index]:
                    raise _fail(
                        "SHIMADZU_QGD_MS1_INVALID",
                        "An MS1 scan intensity sum does not equal its paired raw TIC value.",
                        scan_index=scan_index,
                    )
                summary_digest.update(
                    struct.pack(">IIQQ", scan_index, encoded_rt, point_count, intensity_sum)
                )
    except ShimadzuQgdStructureError:
        raise
    except (OSError, ValueError, TypeError, IndexError, struct.error) as error:
        raise _fail(
            "SHIMADZU_QGD_MS1_INVALID",
            "The bounded MS1 stream could not be validated safely.",
        ) from error

    if getattr(container, "parsing_issues", ()):
        raise _fail(
            "SHIMADZU_QGD_HEADER_INVALID",
            "The compound document reported structural parsing defects.",
        )
    return ShimadzuQgdMs1Summary(
        stream_bytes=stream_size,
        long_row_count=long_row_count,
        points_per_scan_min=points_min,
        points_per_scan_max=points_max,
        intensity_widths=tuple(sorted(widths)),
        mass_raw_min=mass_min,
        mass_raw_max=mass_max,
        intensity_raw_min=intensity_min,
        intensity_raw_max=intensity_max,
        stream_sha256=stream_digest.hexdigest(),
        scan_summary_sha256=summary_digest.hexdigest(),
    )


def _ms_raw_stream_size(container: olefile.OleFileIO[str], offsets: tuple[int, ...]) -> int:
    try:
        stream_size = container.get_size(MS_RAW_DATA_PATH)
    except (OSError, ValueError, TypeError, IndexError) as error:
        raise _fail(
            "SHIMADZU_QGD_PROFILE_UNSUPPORTED",
            "The required MS Raw Data stream is unavailable.",
        ) from error
    if stream_size < SCAN_HEADER_BYTES or stream_size > MAX_MS_RAW_BYTES:
        raise _fail(
            "SHIMADZU_QGD_MS1_INVALID",
            "The MS Raw Data stream is outside the bounded Stage A profile.",
            stream_bytes=stream_size,
            maximum_bytes=MAX_MS_RAW_BYTES,
        )
    if offsets[-1] >= stream_size:
        raise _fail(
            "SHIMADZU_QGD_MS1_INVALID",
            "A spectrum-index offset is outside the MS Raw Data stream.",
        )
    return stream_size


def has_qgd_stream_identity(path: Path) -> bool:
    """Return whether the exact case-sensitive QGD stream identity is present."""
    try:
        _preflight_cfb(path)
        with path.open("rb") as input_stream:
            with olefile.OleFileIO(
                input_stream,
                raise_defects=olefile.DEFECT_INCORRECT,
                write_mode=False,
            ) as container:
                listed = {
                    tuple(component for component in item)
                    for item in container.listdir(streams=True, storages=True)
                }
                return (
                    len(listed) <= MAX_DIRECTORY_ENTRIES
                    and not getattr(container, "parsing_issues", ())
                    and REQUIRED_PATHS.issubset(listed)
                )
    except (ShimadzuQgdStructureError, OSError, ValueError, TypeError, IndexError):
        return False


def read_qgd(path: Path, *, validate_ms1: bool = True) -> ShimadzuQgdData:
    """Read the exact QGD Stage A TIC profile and validate its MS1 structure."""
    _preflight_cfb(path)
    max_retention_bytes = MAX_SCAN_COUNT * 4
    max_tic_bytes = MAX_SCAN_COUNT * 8
    max_index_bytes = len(SPECTRUM_INDEX_U64_TAG) + MAX_SCAN_COUNT * 8
    try:
        with path.open("rb") as input_stream:
            with olefile.OleFileIO(
                input_stream,
                raise_defects=olefile.DEFECT_INCORRECT,
                write_mode=False,
            ) as container:
                _validate_inventory(container)
                file_property = _read_stream(
                    container,
                    FILE_PROPERTY_PATH,
                    maximum_size=MAX_FILE_PROPERTY_BYTES,
                )
                retention_data = _read_stream(
                    container,
                    RETENTION_TIME_PATH,
                    maximum_size=max_retention_bytes,
                )
                tic_data = _read_stream(
                    container,
                    TIC_DATA_PATH,
                    maximum_size=max_tic_bytes,
                )
                index_data = _read_stream(
                    container,
                    SPECTRUM_INDEX_PATH,
                    maximum_size=max_index_bytes,
                )
                schema = _file_schema(file_property)
                (
                    retention_ms,
                    retention_min,
                    tic_values,
                    offsets,
                    interval_ms,
                    offset_width,
                ) = _decode_arrays(retention_data, tic_data, index_data)
                mc_peak_table = _read_processing_stream(
                    container,
                    MC_PEAK_TABLE_PATH,
                    maximum_size=MAX_MC_PEAK_TABLE_BYTES,
                )
                mc_peak_info = _read_processing_stream(
                    container,
                    MC_PEAK_INFO_PATH,
                    maximum_size=MAX_MC_PEAK_INFO_BYTES,
                )
                summary = (
                    _validate_ms1(container, retention_ms, tic_values, offsets)
                    if validate_ms1
                    else None
                )
                if not validate_ms1:
                    _ms_raw_stream_size(container, offsets)
    except ShimadzuQgdStructureError:
        raise
    except (OSError, ValueError, TypeError, IndexError, struct.error) as error:
        raise _fail(
            "SHIMADZU_QGD_HEADER_INVALID",
            "The bounded compound document could not be parsed safely.",
        ) from error

    retention_be_u32 = b"".join(struct.pack(">I", value) for value in retention_ms)
    retention_be_f64 = b"".join(struct.pack(">d", value) for value in retention_min)
    tic_be_u64 = b"".join(struct.pack(">Q", value) for value in tic_values)
    pairs_be_f64_u64 = b"".join(
        struct.pack(">dQ", time_value, tic_value)
        for time_value, tic_value in zip(retention_min, tic_values, strict=True)
    )
    index_be_u32 = b"".join(struct.pack(">I", value) for value in offsets)
    profile = ShimadzuQgdProfile(
        file_schema=schema,
        scan_count=len(retention_ms),
        rt_start_ms=retention_ms[0],
        rt_end_ms=retention_ms[-1],
        rt_interval_ms=interval_ms,
        spectrum_index_offset_width=offset_width,
    )
    return ShimadzuQgdData(
        profile=profile,
        retention_times_min=retention_min,
        tic_values=tic_values,
        ms1_summary=summary,
        file_property_stream_bytes=len(file_property),
        file_property_stream_sha256=hashlib.sha256(file_property).hexdigest(),
        retention_time_stream_sha256=hashlib.sha256(retention_data).hexdigest(),
        retention_time_canonical_be_u32_sha256=hashlib.sha256(retention_be_u32).hexdigest(),
        retention_time_canonical_be_f64_sha256=hashlib.sha256(retention_be_f64).hexdigest(),
        tic_stream_sha256=hashlib.sha256(tic_data).hexdigest(),
        tic_canonical_be_u64_sha256=hashlib.sha256(tic_be_u64).hexdigest(),
        retention_time_tic_pairs_be_f64_u64_sha256=hashlib.sha256(pairs_be_f64_u64).hexdigest(),
        spectrum_index_stream_sha256=hashlib.sha256(index_data).hexdigest(),
        spectrum_index_canonical_be_u32_sha256=hashlib.sha256(index_be_u32).hexdigest(),
        mc_peak_table_payload=mc_peak_table,
        mc_peak_info_payload=mc_peak_info,
    )
