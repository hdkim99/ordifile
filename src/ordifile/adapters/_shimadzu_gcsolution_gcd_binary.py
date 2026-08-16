# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded reader for one evidence-backed Shimadzu ``.GCD`` profile.

The implementation is based on independently observed container and value facts.  It
does not contain or translate code from OpenChrom or chromConverter.
"""

from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as stdlib_etree
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Any, cast

import olefile
from defusedxml import ElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]

CFB_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
CFB_HEADER_BYTES = 4_096
MAX_GCD_FILE_BYTES = 64 * 1024 * 1024
MAX_DIRECTORY_ENTRIES = 256
MAX_XML_STREAM_BYTES = 64 * 1024
MAX_SIGNAL_POINTS = 1_000_000

FILE_PROPERTY_PATH = ("File Property",)
SYSTEM_CHECK_PATH = ("SystemCheckResult", "SystemCheckResult")
SYSTEM_INFORMATION_PATH = ("GUMM_Information", "GUMMSubStg", "SystemInformation")
DATA_ITEM_PATH = ("LSS Raw Data", "2D Data Item U")
SIGNAL_PATH = ("LSS Raw Data", "Chromatogram Ch1")
REQUIRED_PATHS = frozenset(
    {FILE_PROPERTY_PATH, SYSTEM_CHECK_PATH, SYSTEM_INFORMATION_PATH, DATA_ITEM_PATH, SIGNAL_PATH}
)

EXPECTED_FILE_SCHEMA = "5.01"
EXPECTED_SOFTWARE_VERSION = "5.82"
EXPECTED_SIGNAL_MAGIC = 17_234
EXPECTED_INTERVAL_MS = 40
EXPECTED_DELAY_MS = 20.0
EXPECTED_AXIS_UNIT = "uV"
EXPECTED_CHANNEL = "Ch1"
EXPECTED_DETECTOR = "FID"

_HEX_64 = re.compile(r"[0-9A-F]{16}\Z")
_STOX = re.compile(r"@StoX@([0-9A-F]*)\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9_.#\[\]() -]{1,128}\Z")


class ShimadzuGcdStructureError(Exception):
    """Bounded structural error translated by the public adapter."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True, slots=True)
class ShimadzuGcdProfile:
    """Verified exact profile fields and optional source metadata."""

    file_schema: str
    software_version: str
    sample_name: str
    sample_id: str
    operator_name: str | None
    sample_name_bytes_hex: str
    sample_id_bytes_hex: str
    operator_name_bytes_hex: str | None
    injection_volume_raw: str | None
    instrument_model: str
    channel: str
    detector: str
    axis_unit: str
    axis_value_factor: float
    correction_factor: float
    gain_factor: float
    interval_ms: int
    acquisition_time_ms: float
    delay_ms: float
    data_source_id: str
    data_source_name: str
    user_data_source_name: str
    file_property_prefix_hex: str
    acquired_at_utc: datetime
    sample_filetime_low_raw: int
    sample_filetime_high_raw: int
    system_datetime_filetime_raw: str | None
    system_datetime_bias_minutes_raw: str | None


@dataclass(frozen=True, slots=True)
class ShimadzuGcdData:
    """One uninterpolated scientific chromatogram and its exact profile."""

    profile: ShimadzuGcdProfile
    values: tuple[float, ...]
    point_count: int


def _fail(code: str, message: str, **details: Any) -> ShimadzuGcdStructureError:
    return ShimadzuGcdStructureError(code, message, **details)


def _preflight_cfb(path: Path) -> int:
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            header = stream.read(CFB_HEADER_BYTES)
    except OSError as error:
        raise _fail(
            "SHIMADZU_GCD_HEADER_INVALID",
            "The input could not be read as a bounded compound document.",
        ) from error
    if size > MAX_GCD_FILE_BYTES:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The compound document exceeds the supported profile size boundary.",
            maximum_bytes=MAX_GCD_FILE_BYTES,
            actual_bytes=size,
        )
    if size < CFB_HEADER_BYTES:
        raise _fail(
            "SHIMADZU_GCD_TRUNCATED",
            "The compound-document header is truncated.",
            expected_at_least=CFB_HEADER_BYTES,
            actual=size,
        )
    if header[:8] != CFB_MAGIC:
        raise _fail(
            "SHIMADZU_GCD_HEADER_INVALID",
            "The compound-document signature is invalid.",
        )
    major_version = struct.unpack_from("<H", header, 26)[0]
    byte_order = header[28:30]
    sector_shift = struct.unpack_from("<H", header, 30)[0]
    mini_sector_shift = struct.unpack_from("<H", header, 32)[0]
    if (
        major_version != 4
        or byte_order != b"\xfe\xff"
        or sector_shift != 12
        or mini_sector_shift != 6
    ):
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "Only the validated little-endian CFB v4/4096 profile is supported.",
            major_version=major_version,
            sector_shift=sector_shift,
            mini_sector_shift=mini_sector_shift,
        )
    if size % (1 << sector_shift) != 0:
        raise _fail(
            "SHIMADZU_GCD_TRUNCATED",
            "The compound document ends inside a validated CFB sector.",
            sector_bytes=1 << sector_shift,
            actual_bytes=size,
        )
    return size


def _read_stream(container: olefile.OleFileIO[str], path: tuple[str, ...], maximum: int) -> bytes:
    try:
        size = container.get_size(path)
    except (OSError, ValueError, TypeError, IndexError) as error:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "A required exact-profile stream is unavailable.",
        ) from error
    if size < 1 or size > maximum:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "A required exact-profile stream has an unsupported size.",
            stream_bytes=size,
            maximum_bytes=maximum,
        )
    try:
        with container.openstream(path) as stream:
            data = stream.read(maximum + 1)
    except (OSError, ValueError, TypeError, IndexError) as error:
        raise _fail(
            "SHIMADZU_GCD_TRUNCATED",
            "A required stream could not be read completely.",
        ) from error
    if len(data) != size:
        raise _fail(
            "SHIMADZU_GCD_TRUNCATED",
            "A required stream ended before its directory-declared size.",
            expected_bytes=size,
            actual_bytes=len(data),
        )
    return data


def _parse_xml(data: bytes, *, encoding: str, root_name: str) -> stdlib_etree.Element:
    try:
        text = data.decode(encoding, errors="strict")
        root = cast(stdlib_etree.Element, ElementTree.fromstring(text))
    except (UnicodeError, stdlib_etree.ParseError, DefusedXmlException) as error:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "A required bounded metadata document is malformed.",
        ) from error
    if root.tag != root_name:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "A required bounded metadata document has an unsupported root.",
        )
    return root


def _concatenated_xml_document(data: bytes, root_name: str) -> stdlib_etree.Element:
    try:
        text = data.decode("ascii", errors="strict")
    except UnicodeDecodeError as error:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The bounded File Property stream is not strict ASCII.",
        ) from error
    start_token = f"<{root_name}>"
    end_token = f"</{root_name}>"
    if text.count(start_token) != 1 or text.count(end_token) != 1:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The bounded File Property stream has ambiguous metadata documents.",
        )
    start = text.find(start_token, 4)
    end = text.find(end_token, start + len(start_token))
    if start < 4 or end < 0:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The bounded File Property stream lacks a required metadata document.",
        )
    end += len(end_token)
    return _parse_xml(text[start:end].encode("ascii"), encoding="ascii", root_name=root_name)


def _required_text(root: stdlib_etree.Element, path: str) -> str:
    value = root.findtext(path)
    if value is None or not value or len(value) > 256:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "A required exact-profile metadata value is absent or out of bounds.",
        )
    return value


def _optional_text(root: stdlib_etree.Element, path: str) -> str | None:
    value = root.findtext(path)
    if value is None or value == "":
        return None
    if len(value) > 256:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "An exact-profile metadata value exceeds its bounded representation.",
        )
    return value


def _exactly_one(root: stdlib_etree.Element, path: str) -> stdlib_etree.Element:
    matches = root.findall(path)
    if len(matches) != 1:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "An exact-profile metadata element is absent or ambiguous.",
            element=path,
            actual_count=len(matches),
        )
    return matches[0]


def _decode_stox(value: str) -> str:
    match = _STOX.fullmatch(value)
    if match is None or len(match.group(1)) % 2:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "A bounded source-text token is malformed.",
        )
    try:
        decoded = bytes.fromhex(match.group(1)).decode("ascii", errors="strict")
    except (ValueError, UnicodeDecodeError) as error:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "A bounded source-text token is not strict ASCII.",
        ) from error
    if (
        not decoded
        or decoded.isspace()
        or len(decoded) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in decoded)
        or decoded.startswith(("/", "\\", "~"))
        or re.match(r"[A-Za-z]:[\\/]", decoded) is not None
    ):
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "A required source-text value is empty or unsafe.",
        )
    return decoded


def _stox_hex(value: str) -> str:
    match = _STOX.fullmatch(value)
    if match is None or len(match.group(1)) % 2:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "A bounded source-text token is malformed.",
        )
    return match.group(1).lower()


def _little_endian_f64_hex(value: str) -> float:
    if _HEX_64.fullmatch(value) is None:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "An exact-profile numeric token is malformed.",
        )
    number = float(struct.unpack("<d", bytes.fromhex(value))[0])
    if not isfinite(number):
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "An exact-profile numeric token is non-finite.",
        )
    return number


def _parse_filetime(low_text: str, high_text: str) -> tuple[datetime, int, int]:
    try:
        low = int(low_text, 10)
        high = int(high_text, 10)
    except ValueError as error:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The sample acquisition FILETIME fields are malformed.",
        ) from error
    if not -(2**31) <= low <= 2**31 - 1 or not 0 <= high <= 2**32 - 1:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The sample acquisition FILETIME fields exceed their encoded bounds.",
        )
    filetime = (high << 32) | (low & 0xFFFFFFFF)
    try:
        acquired = datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=filetime // 10)
    except OverflowError as error:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The sample acquisition FILETIME is outside the supported UTC range.",
        ) from error
    return acquired, low, high


def _parse_file_property(
    data: bytes,
) -> tuple[
    str,
    str,
    str | None,
    str | None,
    str,
    str,
    str,
    str | None,
    datetime,
    int,
    int,
]:
    file_property = _concatenated_xml_document(data, "FileProperty")
    encoded_schema = _required_text(file_property, "szVersion")
    schema = _decode_stox(encoded_schema)
    if schema != EXPECTED_FILE_SCHEMA:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The File Property schema is outside the exact validated profile.",
            expected=EXPECTED_FILE_SCHEMA,
            actual=schema,
        )
    sample_info = _concatenated_xml_document(data, "SampleInfo")
    sample_name_token = _required_text(sample_info, "smpl_name")
    sample_id_token = _required_text(sample_info, "smpl_id")
    sample_name = _decode_stox(sample_name_token)
    sample_id = _decode_stox(sample_id_token)
    operator_encoded = _optional_text(sample_info, "operator_name")
    operator_name = _decode_stox(operator_encoded) if operator_encoded else None
    injection_raw = _optional_text(sample_info, "inj_vol")
    if injection_raw is not None and not injection_raw.startswith("@FtoX@"):
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The injection-volume source token uses an unsupported representation.",
        )
    acquired, filetime_low, filetime_high = _parse_filetime(
        _required_text(sample_info, "dwLowDateTime"),
        _required_text(sample_info, "dwHighDateTime"),
    )
    return (
        sample_name,
        sample_id,
        operator_name,
        injection_raw,
        schema,
        _stox_hex(sample_name_token),
        _stox_hex(sample_id_token),
        _stox_hex(operator_encoded) if operator_encoded else None,
        acquired,
        filetime_low,
        filetime_high,
    )


def _parse_system_check(data: bytes) -> tuple[str, str | None, str | None]:
    root = _parse_xml(data, encoding="utf-8", root_name="SystemCheckResult")
    if root.attrib != {"version": "1.0"}:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The SystemCheckResult schema is outside the exact validated profile.",
        )
    summary = _exactly_one(root, "Summary")
    software_version_node = _exactly_one(summary, "SWVersion")
    software_version = software_version_node.text or ""
    if software_version != EXPECTED_SOFTWARE_VERSION:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The producer version is outside the exact validated profile.",
            expected=EXPECTED_SOFTWARE_VERSION,
            actual=software_version,
        )
    date_nodes = summary.findall("DateTime")
    if len(date_nodes) > 1:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The producer timestamp metadata is ambiguous.",
        )
    if not date_nodes:
        return software_version, None, None
    date_node = date_nodes[0]
    raw_filetime = date_node.text
    if raw_filetime is None:
        return software_version, None, None
    raw_bias = date_node.attrib.get("Bias")
    if len(raw_filetime) > 32 or not raw_filetime.isdecimal():
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The producer timestamp token is malformed.",
        )
    if raw_bias is not None and (len(raw_bias) > 8 or re.fullmatch(r"-?[0-9]+", raw_bias) is None):
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The producer timezone-bias token is malformed.",
        )
    return software_version, raw_filetime, raw_bias


def _parse_system_information(data: bytes) -> str:
    root = _parse_xml(data, encoding="utf-16-le", root_name="GUD")
    instrument_node = _exactly_one(root, "IN")
    if root.attrib != {"Type": "SI"} or instrument_node.text != "GC-2014":
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The instrument model is outside the exact validated GC-2014 profile.",
        )
    gc_entry = _exactly_one(root, "SGLI[@Name='GC'][@Idx='1']")
    gc_model_node = _exactly_one(gc_entry, "U")
    if gc_model_node.text != "GC-2014":
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The instrument inventory does not identify the exact GC-2014 profile.",
        )
    return "GC-2014"


def _parse_data_item(data: bytes) -> dict[str, str | int | float]:
    root = _parse_xml(data, encoding="utf-16-le", root_name="GUD")
    if root.attrib != {"Type": "2DDataItem", "Rev": "0", "RevSrc": "0"}:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The 2D data-item profile attributes are unsupported.",
        )
    item = _exactly_one(root, "DII")
    if item.attrib != {"Rev": "0", "RevSrc": "0"}:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The 2D data-item descriptor is absent or unsupported.",
        )
    for key, expected in (("DT", "18"), ("DK", "0"), ("LN", "1"), ("CN", "1")):
        if _required_text(item, key) != expected:
            raise _fail(
                "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
                "The 2D data-item channel/profile cardinality is unsupported.",
            )
    descriptor = _exactly_one(item, "DDI")
    axes = descriptor.findall("Axis")
    axis_ids = [axis.attrib.get("ID") for axis in axes]
    if len(axes) != 3 or set(axis_ids) != {"0", "1", "2"}:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The detector/time axis declarations are absent or ambiguous.",
        )
    axis0 = _exactly_one(descriptor, "Axis[@ID='0']")
    axis1 = _exactly_one(descriptor, "Axis[@ID='1']")
    if axis0.attrib.get("DUS") != "1":
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The validated detector/time axes are absent.",
        )
    units = axis0.findall("US")
    unit_ids = [unit.attrib.get("ID") for unit in units]
    if len(units) != 3 or set(unit_ids) != {"1", "2", "3"}:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The validated detector unit declaration is absent or ambiguous.",
        )
    units_by_id = {unit.attrib["ID"]: unit for unit in units}
    expected_units = {
        "1": ("uV", 1.0),
        "2": ("mV", 1_000.0),
        "3": ("V", 1_000_000.0),
    }
    if any(
        _required_text(units_by_id[unit_id], "Unit") != expected_name
        or _little_endian_f64_hex(_required_text(units_by_id[unit_id], "VF")) != expected_factor
        for unit_id, (expected_name, expected_factor) in expected_units.items()
    ):
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The detector unit alternatives are outside the exact validated profile.",
        )
    unit = units_by_id["1"]
    axis_unit = _required_text(unit, "Unit")
    axis_factor = _little_endian_f64_hex(_required_text(unit, "VF"))
    time_step = _little_endian_f64_hex(_required_text(axis1, "Rng/Step"))
    correction_factor = _little_endian_f64_hex(_required_text(item, "CF"))
    gain_factor = _little_endian_f64_hex(_required_text(item, "GF"))
    try:
        interval_ms = int(_required_text(item, "Rate"), 10)
    except ValueError as error:
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "The sampling-rate token is not an integer.",
        ) from error
    acquisition_time_ms = _little_endian_f64_hex(_required_text(item, "AT"))
    delay_ms = _little_endian_f64_hex(_required_text(item, "DLT"))
    data_source_id = _required_text(item, "DSID")
    data_source_name = _required_text(item, "DSN")
    user_data_source_name = _required_text(item, "UDDSN")
    analysis_trace_name = _required_text(item, "ATN")
    if any(
        _SAFE_ID.fullmatch(value) is None
        for value in (data_source_id, data_source_name, user_data_source_name, analysis_trace_name)
    ):
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "A channel identity token is unsafe or outside the exact profile.",
        )
    if (
        axis_unit != EXPECTED_AXIS_UNIT
        or axis_factor != 1.0
        or correction_factor != 1.0
        or gain_factor != 1.0
        or interval_ms != EXPECTED_INTERVAL_MS
        or time_step != float(EXPECTED_INTERVAL_MS)
        or delay_ms != EXPECTED_DELAY_MS
        or not data_source_id.endswith("DetCh")
        or data_source_name != "SFID1"
        or user_data_source_name != "SFID1"
        or analysis_trace_name != "[Chromatogram (Ch1)]"
    ):
        raise _fail(
            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
            "Detector, unit, scale, or time metadata is outside the exact FID profile.",
        )
    return {
        "axis_unit": axis_unit,
        "axis_factor": axis_factor,
        "correction_factor": correction_factor,
        "gain_factor": gain_factor,
        "interval_ms": interval_ms,
        "acquisition_time_ms": acquisition_time_ms,
        "delay_ms": delay_ms,
        "data_source_id": data_source_id,
        "data_source_name": data_source_name,
        "user_data_source_name": user_data_source_name,
    }


def _signal_header(data: bytes, stream_size: int, interval_ms: int) -> tuple[int, int]:
    if len(data) < 24:
        raise _fail(
            "SHIMADZU_GCD_SIGNAL_BLOCK_INVALID",
            "The chromatogram signal header is truncated.",
        )
    marker, encoded_interval, point_count, encoded_length, reserved1, reserved2 = (
        struct.unpack_from("<6I", data, 0)
    )
    if point_count < 1 or point_count > MAX_SIGNAL_POINTS:
        raise _fail(
            "SHIMADZU_GCD_SIGNAL_BLOCK_INVALID",
            "The chromatogram point count is outside the supported bound.",
            point_count=point_count,
            maximum_points=MAX_SIGNAL_POINTS,
        )
    expected_size = 24 + point_count * 8
    if (
        marker != EXPECTED_SIGNAL_MAGIC
        or encoded_interval != interval_ms
        or encoded_length != point_count * 8 + 5
        or reserved1 != 0
        or reserved2 != 0
        or stream_size != expected_size
    ):
        raise _fail(
            "SHIMADZU_GCD_SIGNAL_BLOCK_INVALID",
            "The chromatogram signal header and stream boundary are inconsistent.",
            point_count=point_count,
            stream_bytes=stream_size,
            expected_bytes=expected_size,
        )
    return point_count, expected_size


def has_gcd_stream_identity(path: Path) -> bool:
    """Return whether the exact Shimadzu stream inventory is present."""
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
    except (ShimadzuGcdStructureError, OSError, ValueError, TypeError, IndexError):
        return False


def read_gcd(path: Path, *, decode_signal: bool = True) -> ShimadzuGcdData:
    """Read one exact LabSolutions 5.82/GCsolution-compatible FID profile."""
    _preflight_cfb(path)
    try:
        with path.open("rb") as input_stream:
            with olefile.OleFileIO(
                input_stream,
                raise_defects=olefile.DEFECT_INCORRECT,
                write_mode=False,
            ) as container:
                listed = [
                    tuple(component for component in item)
                    for item in container.listdir(streams=True, storages=True)
                ]
                if len(listed) > MAX_DIRECTORY_ENTRIES:
                    raise _fail(
                        "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
                        "The compound document has too many directory entries.",
                        maximum_entries=MAX_DIRECTORY_ENTRIES,
                        actual_entries=len(listed),
                    )
                if getattr(container, "parsing_issues", ()):
                    raise _fail(
                        "SHIMADZU_GCD_HEADER_INVALID",
                        "The compound document reported structural parsing defects.",
                    )
                folded_paths: set[tuple[str, ...]] = set()
                for item in listed:
                    folded = tuple(component.casefold() for component in item)
                    if folded in folded_paths:
                        raise _fail(
                            "SHIMADZU_GCD_HEADER_INVALID",
                            "The compound directory contains ambiguous case-folded names.",
                        )
                    folded_paths.add(folded)
                listed_set = set(listed)
                required_folded = {
                    tuple(component.casefold() for component in item): item
                    for item in REQUIRED_PATHS
                }
                if any(
                    folded in required_folded and item != required_folded[folded]
                    for item in listed
                    for folded in (tuple(component.casefold() for component in item),)
                ):
                    raise _fail(
                        "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
                        "A required stream name differs only by case from the exact profile.",
                    )
                if not REQUIRED_PATHS.issubset(listed_set):
                    raise _fail(
                        "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
                        "One or more case-exact required streams are absent.",
                    )
                for item in listed:
                    if (
                        len(item) == 2
                        and item[0] == "LSS Raw Data"
                        and re.fullmatch(r"Chromatogram Ch[0-9]+", item[1]) is not None
                        and item != SIGNAL_PATH
                        and container.get_size(item) > 0
                    ):
                        raise _fail(
                            "SHIMADZU_GCD_PROFILE_UNSUPPORTED",
                            "Multiple nonempty chromatogram channels are not supported.",
                        )
                file_property_data = _read_stream(
                    container, FILE_PROPERTY_PATH, MAX_XML_STREAM_BYTES
                )
                system_check_data = _read_stream(container, SYSTEM_CHECK_PATH, MAX_XML_STREAM_BYTES)
                system_information_data = _read_stream(
                    container, SYSTEM_INFORMATION_PATH, MAX_XML_STREAM_BYTES
                )
                data_item_data = _read_stream(container, DATA_ITEM_PATH, MAX_XML_STREAM_BYTES)
                signal_size = container.get_size(SIGNAL_PATH)
                if signal_size > 24 + MAX_SIGNAL_POINTS * 8:
                    raise _fail(
                        "SHIMADZU_GCD_SIGNAL_BLOCK_INVALID",
                        "The chromatogram signal stream exceeds the supported bound.",
                    )
                with container.openstream(SIGNAL_PATH) as signal_stream:
                    signal_data = signal_stream.read(signal_size if decode_signal else 24)
                if getattr(container, "parsing_issues", ()):
                    raise _fail(
                        "SHIMADZU_GCD_HEADER_INVALID",
                        "The compound document reported structural parsing defects.",
                    )
    except ShimadzuGcdStructureError:
        raise
    except (OSError, ValueError, TypeError, IndexError, struct.error) as error:
        raise _fail(
            "SHIMADZU_GCD_HEADER_INVALID",
            "The bounded compound document could not be parsed safely.",
        ) from error

    (
        sample_name,
        sample_id,
        operator_name,
        injection_raw,
        file_schema,
        sample_name_hex,
        sample_id_hex,
        operator_name_hex,
        acquired_at_utc,
        filetime_low,
        filetime_high,
    ) = _parse_file_property(file_property_data)
    software_version, raw_filetime, raw_bias = _parse_system_check(system_check_data)
    instrument_model = _parse_system_information(system_information_data)
    data_item_fields = _parse_data_item(data_item_data)
    interval_ms = int(data_item_fields["interval_ms"])
    point_count, expected_size = _signal_header(signal_data, signal_size, interval_ms)
    acquisition_time_ms = float(data_item_fields["acquisition_time_ms"])
    if acquisition_time_ms != float(point_count * interval_ms):
        raise _fail(
            "SHIMADZU_GCD_SIGNAL_BLOCK_INVALID",
            "Acquisition duration, interval, and point count are inconsistent.",
            point_count=point_count,
            interval_ms=interval_ms,
        )
    if decode_signal:
        if len(signal_data) != expected_size:
            raise _fail(
                "SHIMADZU_GCD_TRUNCATED",
                "The chromatogram signal stream ended before its validated boundary.",
                expected_bytes=expected_size,
                actual_bytes=len(signal_data),
            )
        values = tuple(
            float(value) for value in struct.unpack_from(f"<{point_count}d", signal_data, 24)
        )
        if any(not isfinite(value) for value in values):
            raise _fail(
                "SHIMADZU_GCD_SIGNAL_BLOCK_INVALID",
                "The chromatogram signal contains a non-finite value.",
            )
    else:
        values = ()
    profile = ShimadzuGcdProfile(
        file_schema=file_schema,
        software_version=software_version,
        sample_name=sample_name,
        sample_id=sample_id,
        operator_name=operator_name,
        sample_name_bytes_hex=sample_name_hex,
        sample_id_bytes_hex=sample_id_hex,
        operator_name_bytes_hex=operator_name_hex,
        injection_volume_raw=injection_raw,
        instrument_model=instrument_model,
        channel=EXPECTED_CHANNEL,
        detector=EXPECTED_DETECTOR,
        axis_unit=str(data_item_fields["axis_unit"]),
        axis_value_factor=float(data_item_fields["axis_factor"]),
        correction_factor=float(data_item_fields["correction_factor"]),
        gain_factor=float(data_item_fields["gain_factor"]),
        interval_ms=interval_ms,
        acquisition_time_ms=acquisition_time_ms,
        delay_ms=float(data_item_fields["delay_ms"]),
        data_source_id=str(data_item_fields["data_source_id"]),
        data_source_name=str(data_item_fields["data_source_name"]),
        user_data_source_name=str(data_item_fields["user_data_source_name"]),
        file_property_prefix_hex=file_property_data[:4].hex(),
        acquired_at_utc=acquired_at_utc,
        sample_filetime_low_raw=filetime_low,
        sample_filetime_high_raw=filetime_high,
        system_datetime_filetime_raw=raw_filetime,
        system_datetime_bias_minutes_raw=raw_bias,
    )
    return ShimadzuGcdData(profile, values, point_count)
