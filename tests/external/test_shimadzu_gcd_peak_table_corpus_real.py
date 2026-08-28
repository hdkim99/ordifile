"""Corpus evidence that the stored GCD peak-table layout is not profile-specific.

The adapter itself accepts only the exact LabSolutions 5.82 single-channel FID profile.
This owner-approved external corpus carries other LabSolutions versions, so it validates
the bounded record layout rather than adapter support.  No member name is printed.
"""

from __future__ import annotations

import hashlib
import io
import os
import posixpath
import re
import zipfile
from pathlib import Path

import olefile
import pytest

from ordifile.adapters._shimadzu_gcsolution_gcd_peak_table import (
    PEAK_TABLE_NAME_PATTERN,
    PEAK_TABLE_STORAGE,
    ShimadzuGcdPeak,
    decode_peak_table,
)

EXPECTED_ARCHIVE_SIZE = 37_512_839
EXPECTED_ARCHIVE_SHA256 = "94d0267d47261ba612aa344d7253f26282973b65e9734a8697fb85ea8c728160"
EXPECTED_MEMBER_COUNT = 1_388
EXPECTED_STORED_TABLES = 320
EXPECTED_COMPARED_PAIRS = 318
EXPECTED_ROW_COUNT_AGREEMENT = 317
EXPECTED_COMPARED_ROWS = 1_548
EXPECTED_SOFTWARE_VERSIONS = {"5.71 SP2", "5.86"}
MAX_MEMBER_BYTES = 4_000_000
MAX_COMPRESSION_RATIO = 100.0
TIME_TOLERANCE_MINUTES = 6e-4


def _archive() -> Path:
    value = os.environ.get("ORDIFILE_SHIMADZU_GCD_CORPUS_ARCHIVE")
    if not value:
        raise AssertionError("ORDIFILE_SHIMADZU_GCD_CORPUS_ARCHIVE is required")
    return Path(value)


def _safe_member(info: zipfile.ZipInfo) -> bool:
    pure = posixpath.normpath(info.filename)
    return (
        not info.is_dir()
        and not info.filename.startswith("/")
        and ".." not in info.filename.split("/")
        and not pure.startswith("/")
        and info.file_size <= MAX_MEMBER_BYTES
        and (
            info.compress_size == 0
            or info.file_size / max(info.compress_size, 1) <= MAX_COMPRESSION_RATIO
        )
    )


def _column(columns: list[str], header: dict[str, int] | None, name: str) -> float | None:
    position = header.get(name) if header else None
    if position is None or position >= len(columns):
        return None
    try:
        return float(columns[position].strip())
    except ValueError:
        return None


def _ascii_peak_rows(text: str) -> list[dict[str, float | None]]:
    rows: list[dict[str, float | None]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if re.match(r"\[Peak Table\(.+?\)\]", lines[index]) is None:
            index += 1
            continue
        header: dict[str, int] | None = None
        index += 1
        while index < len(lines) and not lines[index].startswith("["):
            columns = lines[index].split("\t")
            if header is None:
                if columns[0].strip() == "Peak#":
                    header = {name.strip(): position for position, name in enumerate(columns)}
                index += 1
                continue
            if columns[0].strip().isdigit():
                rows.append(
                    {
                        key: _column(columns, header, name)
                        for key, name in (
                            ("rt", "R.Time"),
                            ("start", "I.Time"),
                            ("end", "F.Time"),
                            ("area", "Area"),
                            ("height", "Height"),
                        )
                    }
                )
            index += 1
    return rows


def _stored_rows(payload: bytes) -> list[ShimadzuGcdPeak] | None:
    with olefile.OleFileIO(io.BytesIO(payload)) as container:
        entries = [
            tuple(part for part in item)
            for item in container.listdir(streams=True)
            if len(item) == 2
            and item[0] == PEAK_TABLE_STORAGE
            and PEAK_TABLE_NAME_PATTERN.fullmatch(item[1]) is not None
        ]
        if len(entries) != 1:
            return None
        with container.openstream(entries[0]) as stream:
            raw = stream.read()
    table = decode_peak_table(raw)
    assert table.status == "matched", table.issue_code
    return list(table.peaks)


def test_stored_peak_table_layout_holds_across_the_owner_approved_corpus() -> None:
    archive = _archive()
    data = archive.read_bytes()
    assert len(data) == EXPECTED_ARCHIVE_SIZE
    assert hashlib.sha256(data).hexdigest() == EXPECTED_ARCHIVE_SHA256

    stored_tables = 0
    compared_pairs = 0
    row_count_agreement = 0
    compared_rows = 0
    versions: set[str] = set()
    with zipfile.ZipFile(archive) as source:
        infos = source.infolist()
        assert len(infos) == EXPECTED_MEMBER_COUNT
        assert source.testzip() is None
        by_stem: dict[tuple[str, str], dict[str, zipfile.ZipInfo]] = {}
        for info in infos:
            if info.is_dir():
                continue
            extension = posixpath.splitext(info.filename)[1].casefold()
            if extension not in {".gcd", ".txt"}:
                continue
            assert _safe_member(info)
            key = (
                posixpath.dirname(info.filename),
                posixpath.splitext(posixpath.basename(info.filename))[0],
            )
            by_stem.setdefault(key, {})[extension] = info

        for _key, pair in sorted(by_stem.items()):
            if ".gcd" not in pair:
                continue
            try:
                payload = source.read(pair[".gcd"])
            except (OSError, zipfile.BadZipFile):
                continue
            try:
                stored = _stored_rows(payload)
            except (OSError, ValueError, TypeError, IndexError):
                continue
            if stored is None:
                continue
            stored_tables += 1
            if ".txt" not in pair:
                continue
            text = source.read(pair[".txt"]).decode("utf-8", errors="replace")
            official = _ascii_peak_rows(text)
            if not official:
                continue
            match = re.search(r"^Version\t(.+)$", text, re.M)
            if match:
                versions.add(match.group(1).strip())
            compared_pairs += 1
            if len(official) != len(stored):
                # A stored table may predate a separately re-exported text file; the two
                # then describe different processing states of the same acquisition.
                continue
            row_count_agreement += 1
            for expected, actual in zip(official, stored, strict=True):
                compared_rows += 1
                expected_rt = expected["rt"]
                expected_start = expected["start"]
                expected_end = expected["end"]
                expected_area = expected["area"]
                expected_height = expected["height"]
                assert expected_rt is not None
                assert expected_start is not None
                assert expected_end is not None
                assert expected_area is not None
                assert expected_height is not None
                assert abs(actual.retention_time - expected_rt) <= TIME_TOLERANCE_MINUTES
                assert abs(actual.start_time - expected_start) <= TIME_TOLERANCE_MINUTES
                assert abs(actual.end_time - expected_end) <= TIME_TOLERANCE_MINUTES
                # The text export publishes these rounded; the stored value keeps every digit.
                assert round(actual.area) == expected_area
                assert round(actual.height) == expected_height
                assert abs(actual.area - expected_area) < 0.5
                assert abs(actual.height - expected_height) < 0.5

    assert stored_tables == EXPECTED_STORED_TABLES
    assert compared_pairs == EXPECTED_COMPARED_PAIRS
    assert row_count_agreement == EXPECTED_ROW_COUNT_AGREEMENT
    assert compared_rows == EXPECTED_COMPARED_ROWS
    assert versions == EXPECTED_SOFTWARE_VERSIONS


def test_corpus_archive_is_not_a_default_test_dependency() -> None:
    assert not (Path(__file__).resolve().parents[2] / "open_data.zip").exists()
    with pytest.raises(AssertionError):
        previous = os.environ.pop("ORDIFILE_SHIMADZU_GCD_CORPUS_ARCHIVE", None)
        try:
            _archive()
        finally:
            if previous is not None:
                os.environ["ORDIFILE_SHIMADZU_GCD_CORPUS_ARCHIVE"] = previous
