# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Build small deterministic CFB v4 containers for structural tests.

This is a general container writer for invented test payloads.  It does not reproduce
any proprietary source bytes.  Streams are stored in regular 4096-byte sectors so the
builder does not need a mini-FAT implementation.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping

SECTOR_BYTES = 4_096
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF


def _directory_entry(
    name: str,
    entry_type: int,
    *,
    left: int = NOSTREAM,
    right: int = NOSTREAM,
    child: int = NOSTREAM,
    start_sector: int = ENDOFCHAIN,
    size: int = 0,
) -> bytes:
    encoded_name = (name + "\x00").encode("utf-16-le")
    if len(encoded_name) > 64:
        raise ValueError("CFB test entry name is too long")
    entry = bytearray(128)
    entry[: len(encoded_name)] = encoded_name
    struct.pack_into(
        "<HBBIII16sIQQIQ",
        entry,
        64,
        len(encoded_name),
        entry_type,
        1,
        left,
        right,
        child,
        bytes(16),
        0,
        0,
        0,
        start_sector,
        size,
    )
    return bytes(entry)


def _balanced_links(sids: list[int]) -> tuple[int, dict[int, tuple[int, int]]]:
    links: dict[int, tuple[int, int]] = {}

    def visit(items: list[int]) -> int:
        if not items:
            return NOSTREAM
        middle = len(items) // 2
        sid = items[middle]
        left = visit(items[:middle])
        right = visit(items[middle + 1 :])
        links[sid] = (left, right)
        return sid

    return visit(sids), links


def build_cfb_v4(streams: Mapping[tuple[str, ...], bytes]) -> bytes:
    """Return a deterministic CFB v4 file containing regular-sector streams."""
    if not streams or any(not path or len(path) > 4 for path in streams):
        raise ValueError("synthetic CFB streams must use one to four path components")
    regular_streams: dict[tuple[str, ...], bytes] = {}
    for path, content in streams.items():
        if len(content) < SECTOR_BYTES:
            raise ValueError("synthetic streams must be at least one regular CFB sector")
        regular_streams[path] = bytes(content)

    storage_paths = sorted(
        {path[:depth] for path in regular_streams for depth in range(1, len(path))}
    )
    object_paths: list[tuple[str, ...]] = [*storage_paths, *sorted(regular_streams)]
    if len(object_paths) + 1 > SECTOR_BYTES // 128:
        raise ValueError("synthetic CFB needs more than one directory sector")
    sid_by_path = {path: index for index, path in enumerate(object_paths, start=1)}

    children: dict[tuple[str, ...], list[tuple[str, ...]]] = {(): []}
    for storage in storage_paths:
        children.setdefault(storage, [])
        children.setdefault(storage[:-1], []).append(storage)
    for path in regular_streams:
        parent = path[:-1]
        children.setdefault(parent, []).append(path)
    links: dict[int, tuple[int, int]] = {}
    child_roots: dict[tuple[str, ...], int] = {}
    for parent, paths in children.items():
        ordered = sorted(paths, key=lambda path: path[-1].casefold())
        root_sid, subtree_links = _balanced_links([sid_by_path[path] for path in ordered])
        child_roots[parent] = root_sid
        links.update(subtree_links)

    allocations: dict[tuple[str, ...], tuple[int, int]] = {}
    next_sector = 2  # sector 0 is directory; sector 1 is the single FAT sector
    stream_sectors: dict[tuple[str, ...], list[int]] = {}
    for path in sorted(regular_streams):
        content = regular_streams[path]
        count = (len(content) + SECTOR_BYTES - 1) // SECTOR_BYTES
        chain = list(range(next_sector, next_sector + count))
        next_sector += count
        allocations[path] = (chain[0], len(content))
        stream_sectors[path] = chain
    if next_sector > SECTOR_BYTES // 4:
        raise ValueError("synthetic CFB exceeds one FAT sector")

    directory_entries = [
        _directory_entry(
            "Root Entry",
            5,
            child=child_roots.get((), NOSTREAM),
        )
    ]
    for path in object_paths:
        sid = sid_by_path[path]
        left, right = links.get(sid, (NOSTREAM, NOSTREAM))
        if path in regular_streams:
            start, size = allocations[path]
            directory_entries.append(
                _directory_entry(
                    path[-1],
                    2,
                    left=left,
                    right=right,
                    start_sector=start,
                    size=size,
                )
            )
        else:
            directory_entries.append(
                _directory_entry(
                    path[-1],
                    1,
                    left=left,
                    right=right,
                    child=child_roots.get(path, NOSTREAM),
                )
            )
    directory = b"".join(directory_entries).ljust(SECTOR_BYTES, b"\x00")

    fat = [FREESECT] * (SECTOR_BYTES // 4)
    fat[0] = ENDOFCHAIN
    fat[1] = FATSECT
    for chain in stream_sectors.values():
        for current, following in zip(chain, chain[1:], strict=False):
            fat[current] = following
        fat[chain[-1]] = ENDOFCHAIN
    fat_sector = struct.pack(f"<{len(fat)}I", *fat)

    header = bytearray(SECTOR_BYTES)
    header[:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<H", header, 24, 0x003E)
    struct.pack_into("<H", header, 26, 4)
    header[28:30] = b"\xfe\xff"
    struct.pack_into("<H", header, 30, 12)
    struct.pack_into("<H", header, 32, 6)
    struct.pack_into("<I", header, 40, 1)
    struct.pack_into("<I", header, 44, 1)
    struct.pack_into("<I", header, 48, 0)
    struct.pack_into("<I", header, 52, 0)
    struct.pack_into("<I", header, 56, 4096)
    struct.pack_into("<I", header, 60, ENDOFCHAIN)
    struct.pack_into("<I", header, 64, 0)
    struct.pack_into("<I", header, 68, ENDOFCHAIN)
    struct.pack_into("<I", header, 72, 0)
    struct.pack_into("<I", header, 76, 1)
    for offset in range(80, 512, 4):
        struct.pack_into("<I", header, offset, FREESECT)

    payload_sectors: dict[int, bytes] = {0: directory, 1: fat_sector}
    for path, chain in stream_sectors.items():
        content = regular_streams[path]
        padded = content.ljust(len(chain) * SECTOR_BYTES, b"\x00")
        for index, sector in enumerate(chain):
            start = index * SECTOR_BYTES
            payload_sectors[sector] = padded[start : start + SECTOR_BYTES]
    return bytes(header) + b"".join(payload_sectors[index] for index in range(next_sector))
