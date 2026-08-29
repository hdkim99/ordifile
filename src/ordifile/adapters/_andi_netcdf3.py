# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Bounded reader for the classic netCDF-3 container.

netCDF-3 is a public, self-describing format (Unidata), so this module reads the
header it declares rather than assuming any layout.  It is deliberately minimal:
only what the ANDI chromatography profile needs, with every length checked against
the file size before it is used.

Files that actually carry records are refused.  Record values interleave on disk, and
no observed ANDI chromatography file uses them, so mis-handling them silently is not a
risk worth taking.  A zero-length dimension is read as an empty one, which is how ANDI
writers spell "this file stores no peaks"; with no records declared there are no record
values to lay out either way.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

MAGIC = b"CDF"
CLASSIC_VERSION = 1
OFFSET_64_VERSION = 2
SUPPORTED_VERSIONS = frozenset({CLASSIC_VERSION, OFFSET_64_VERSION})

NC_BYTE = 1
NC_CHAR = 2
NC_SHORT = 3
NC_INT = 4
NC_FLOAT = 5
NC_DOUBLE = 6
_TYPES: dict[int, tuple[str, int]] = {
    NC_BYTE: ("b", 1),
    NC_CHAR: ("c", 1),
    NC_SHORT: ("h", 2),
    NC_INT: ("i", 4),
    NC_FLOAT: ("f", 4),
    NC_DOUBLE: ("d", 8),
}

_NC_DIMENSION = 0x0A
_NC_VARIABLE = 0x0B
_NC_ATTRIBUTE = 0x0C
_ABSENT = 0x00

MAX_HEADER_BYTES = 4 * 1024 * 1024
MAX_NAME_BYTES = 256
MAX_DIMENSIONS = 512
MAX_VARIABLES = 4_096
MAX_ATTRIBUTES = 4_096
MAX_ATTRIBUTE_ELEMENTS = 65_536
MAX_ELEMENTS_PER_VARIABLE = 50_000_000


class NetCdf3Error(Exception):
    """Bounded structural error raised while reading a netCDF-3 header or values."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _fail(code: str, message: str, **details: Any) -> NetCdf3Error:
    return NetCdf3Error(code, message, **details)


@dataclass(frozen=True, slots=True)
class NetCdf3Variable:
    """One declared variable and where its contiguous values begin."""

    name: str
    dimension_ids: tuple[int, ...]
    nc_type: int
    begin: int
    element_count: int
    attributes: dict[str, object]


@dataclass(frozen=True, slots=True)
class NetCdf3File:
    """A decoded netCDF-3 header bound to the payload it describes."""

    version: int
    dimensions: tuple[tuple[str, int], ...]
    attributes: dict[str, object]
    variables: dict[str, NetCdf3Variable]
    payload: bytes

    def dimension_length(self, name: str) -> int | None:
        """Return a declared dimension length, or None when it is absent."""
        for declared, length in self.dimensions:
            if declared == name:
                return length
        return None


class _Cursor:
    """A bounds-checked forward reader over the header region."""

    __slots__ = ("_data", "_offset")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    @property
    def offset(self) -> int:
        return self._offset

    def take(self, count: int) -> bytes:
        if count < 0 or self._offset + count > len(self._data):
            raise _fail("NETCDF3_TRUNCATED", "The netCDF-3 header ended early.")
        chunk = self._data[self._offset : self._offset + count]
        self._offset += count
        return chunk

    def uint32(self) -> int:
        return int(struct.unpack(">I", self.take(4))[0])

    def uint64(self) -> int:
        return int(struct.unpack(">Q", self.take(8))[0])

    def padded(self, count: int) -> bytes:
        chunk = self.take(count)
        self.take(-count % 4)
        return chunk

    def name(self) -> str:
        length = self.uint32()
        if not 1 <= length <= MAX_NAME_BYTES:
            raise _fail(
                "NETCDF3_NAME_INVALID",
                "A netCDF-3 name length is outside the bounded reader range.",
                name_bytes=length,
            )
        raw = self.padded(length)
        try:
            decoded = raw.decode("ascii", errors="strict")
        except UnicodeDecodeError as error:
            raise _fail("NETCDF3_NAME_INVALID", "A netCDF-3 name is not ASCII.") from error
        if any(ord(character) < 32 or ord(character) == 127 for character in decoded):
            raise _fail("NETCDF3_NAME_INVALID", "A netCDF-3 name contains a control character.")
        return decoded


def _decode_attribute_values(nc_type: int, count: int, raw: bytes) -> object:
    if nc_type == NC_CHAR:
        text = raw.decode("latin-1", errors="replace")
        return text.split("\x00", 1)[0].strip()
    code, _ = _TYPES[nc_type]
    return tuple(struct.unpack(f">{count}{code}", raw))


def _read_attributes(cursor: _Cursor) -> dict[str, object]:
    tag = cursor.uint32()
    count = cursor.uint32()
    if tag == _ABSENT:
        if count:
            raise _fail("NETCDF3_HEADER_INVALID", "An absent attribute list declares members.")
        return {}
    if tag != _NC_ATTRIBUTE:
        raise _fail("NETCDF3_HEADER_INVALID", "An attribute list carries an unknown tag.")
    if count > MAX_ATTRIBUTES:
        raise _fail(
            "NETCDF3_HEADER_INVALID",
            "The netCDF-3 header declares too many attributes.",
            attribute_count=count,
        )
    attributes: dict[str, object] = {}
    for _ in range(count):
        name = cursor.name()
        nc_type = cursor.uint32()
        if nc_type not in _TYPES:
            raise _fail(
                "NETCDF3_TYPE_UNSUPPORTED",
                "An attribute declares an unsupported netCDF-3 type.",
                nc_type=nc_type,
            )
        elements = cursor.uint32()
        if elements > MAX_ATTRIBUTE_ELEMENTS:
            raise _fail(
                "NETCDF3_HEADER_INVALID",
                "An attribute declares too many elements.",
                elements=elements,
            )
        _, width = _TYPES[nc_type]
        raw = cursor.padded(elements * width)
        if name in attributes:
            raise _fail("NETCDF3_HEADER_INVALID", "An attribute name is declared twice.")
        attributes[name] = _decode_attribute_values(nc_type, elements, raw)
    return attributes


def read_header(data: bytes) -> NetCdf3File:
    """Decode a netCDF-3 header, validating every declared extent against the payload."""
    if len(data) < 8 or not data.startswith(MAGIC):
        raise _fail("NETCDF3_HEADER_INVALID", "The netCDF-3 signature is absent.")
    version = data[3]
    if version not in SUPPORTED_VERSIONS:
        raise _fail(
            "NETCDF3_VERSION_UNSUPPORTED",
            "Only netCDF-3 classic and 64-bit-offset files are supported.",
            version=version,
        )
    cursor = _Cursor(data[: min(len(data), MAX_HEADER_BYTES)])
    cursor.take(4)
    record_count = cursor.uint32()

    tag = cursor.uint32()
    declared = cursor.uint32()
    dimensions: list[tuple[str, int]] = []
    if tag == _NC_DIMENSION:
        if declared > MAX_DIMENSIONS:
            raise _fail(
                "NETCDF3_HEADER_INVALID",
                "The netCDF-3 header declares too many dimensions.",
                dimension_count=declared,
            )
        for _ in range(declared):
            name = cursor.name()
            length = cursor.uint32()
            dimensions.append((name, length))
    elif tag != _ABSENT or declared:
        raise _fail("NETCDF3_HEADER_INVALID", "A dimension list carries an unknown tag.")
    attributes = _read_attributes(cursor)

    tag = cursor.uint32()
    declared = cursor.uint32()
    variables: dict[str, NetCdf3Variable] = {}
    if tag == _NC_VARIABLE:
        if declared > MAX_VARIABLES:
            raise _fail(
                "NETCDF3_HEADER_INVALID",
                "The netCDF-3 header declares too many variables.",
                variable_count=declared,
            )
        for _ in range(declared):
            name = cursor.name()
            rank = cursor.uint32()
            if rank > len(dimensions):
                raise _fail("NETCDF3_HEADER_INVALID", "A variable declares too many dimensions.")
            dimension_ids: list[int] = []
            for _ in range(rank):
                dimension_id = cursor.uint32()
                if dimension_id >= len(dimensions):
                    raise _fail(
                        "NETCDF3_HEADER_INVALID",
                        "A variable names a dimension that was not declared.",
                    )
                dimension_ids.append(dimension_id)
            variable_attributes = _read_attributes(cursor)
            nc_type = cursor.uint32()
            if nc_type not in _TYPES:
                raise _fail(
                    "NETCDF3_TYPE_UNSUPPORTED",
                    "A variable declares an unsupported netCDF-3 type.",
                    nc_type=nc_type,
                )
            cursor.uint32()
            begin = cursor.uint32() if version == CLASSIC_VERSION else cursor.uint64()
            element_count = 1
            for dimension_id in dimension_ids:
                element_count *= dimensions[dimension_id][1]
                if element_count > MAX_ELEMENTS_PER_VARIABLE:
                    raise _fail(
                        "NETCDF3_HEADER_INVALID",
                        "A variable declares more elements than the bounded reader accepts.",
                        variable=name,
                    )
            _, width = _TYPES[nc_type]
            if begin < 0 or begin + element_count * width > len(data):
                raise _fail(
                    "NETCDF3_TRUNCATED",
                    "A variable's declared values extend past the end of the file.",
                    variable=name,
                )
            if name in variables:
                raise _fail("NETCDF3_HEADER_INVALID", "A variable name is declared twice.")
            variables[name] = NetCdf3Variable(
                name, tuple(dimension_ids), nc_type, begin, element_count, variable_attributes
            )
    elif tag != _ABSENT or declared:
        raise _fail("NETCDF3_HEADER_INVALID", "A variable list carries an unknown tag.")
    if record_count:
        raise _fail(
            "NETCDF3_RECORD_VARIABLES_UNSUPPORTED",
            "This reader does not support netCDF-3 record variables.",
            record_count=record_count,
        )
    return NetCdf3File(version, tuple(dimensions), attributes, variables, data)


def numeric_values(source: NetCdf3File, name: str) -> tuple[float, ...]:
    """Return one numeric variable's values, refusing character variables."""
    variable = source.variables[name]
    if variable.nc_type == NC_CHAR:
        raise _fail(
            "NETCDF3_TYPE_UNSUPPORTED",
            "A character variable was requested as numeric.",
            variable=name,
        )
    code, width = _TYPES[variable.nc_type]
    raw = source.payload[variable.begin : variable.begin + variable.element_count * width]
    return tuple(float(value) for value in struct.unpack(f">{variable.element_count}{code}", raw))


def text_values(source: NetCdf3File, name: str) -> tuple[str, ...]:
    """Return one character variable's rows, trimmed at their terminator.

    The row width is taken from the variable's own trailing dimension rather than
    assumed, because writers pick different fixed-width string dimensions.
    """
    variable = source.variables[name]
    if variable.nc_type != NC_CHAR or not variable.dimension_ids:
        raise _fail(
            "NETCDF3_TYPE_UNSUPPORTED",
            "A non-character variable was requested as text.",
            variable=name,
        )
    row_length = source.dimensions[variable.dimension_ids[-1]][1]
    if row_length < 1:
        return ()
    raw = source.payload[variable.begin : variable.begin + variable.element_count]
    rows = variable.element_count // row_length
    return tuple(
        raw[index * row_length : (index + 1) * row_length]
        .decode("latin-1", errors="replace")
        .split("\x00", 1)[0]
        .strip()
        for index in range(rows)
    )
