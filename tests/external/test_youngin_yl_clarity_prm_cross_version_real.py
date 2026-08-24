from __future__ import annotations

import hashlib
import os
import stat
import sys
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZipInfo

from ordifile.adapters._youngin_yl_clarity_prm_binary import (
    YoungInPrmStructureError,
    read_prm,
)
from ordifile.adapters._youngin_yl_clarity_result_csv import read_result_csv

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "local"))
import youngin_yl_clarity_prm_cross_version_probe as probe  # noqa: E402

RAW_ARCHIVE_SIZE = 3_083_937
RAW_ARCHIVE_SHA256 = "4af61e1aa8abef3694a4c24a28203b0a1d382a11b6442c3e9b43653487f97fe5"
SCIENTIFIC_ARCHIVE_SIZE = 1_604_581
SCIENTIFIC_ARCHIVE_SHA256 = "fff59de802b01d1d78e393b66b026fc79b9b736c5cb79b2d72f2b3e841ae72db"
MAX_ARCHIVE_MEMBERS = 64
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100.0
PAIRED_RESULT_PRM = {
    "d4987151cba83068b5143cf90c6b0e78f1fee6b3c9f04c38d8cb97441ddfadd7": (
        "db3a838ae0c69e0b6518a44deb10204f08f98ef6367a7ea40c88e98f39fcf2be"
    ),
    "0ceb70ba51e41607a5a6ca4476c9b77e6e2bce41d56e47b865085bb3ea71f67b": (
        "327fc24585b21d553967231238f1648cdd06012a592b4c3682cd31178d3c1d29"
    ),
}


def _fixture(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise AssertionError(f"{variable} is required")
    return Path(value)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_regular_member(info: ZipInfo) -> bool:
    pure = PurePosixPath(info.filename)
    mode = (info.external_attr >> 16) & 0xFFFF
    return (
        not info.is_dir()
        and not (info.flag_bits & 0x1)
        and "\\" not in info.filename
        and not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in pure.parts)
        and (mode == 0 or stat.S_ISREG(mode))
    )


def _safe_member_path(info: ZipInfo) -> bool:
    pure = PurePosixPath(info.filename)
    return (
        "\\" not in info.filename
        and not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in pure.parts)
    )


def _stage_prms(
    archive: Path,
    target: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> dict[str, Path]:
    if archive.stat().st_size != expected_size or _sha256(archive) != expected_sha256:
        raise AssertionError("external archive identity changed")
    target.mkdir()
    staged: dict[str, Path] = {}
    with ZipFile(archive) as source:
        infos = source.infolist()
        if (
            len(infos) > MAX_ARCHIVE_MEMBERS
            or sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES
            or source.testzip() is not None
        ):
            raise AssertionError("external archive failed bounded validation")
        names = [info.filename for info in infos]
        if len(set(names)) != len(names) or len({name.casefold() for name in names}) != len(names):
            raise AssertionError("external archive member identity is ambiguous")
        for info in infos:
            if not _safe_member_path(info):
                raise AssertionError("external archive member path is unsafe")
            if info.is_dir():
                continue
            if (
                not _safe_regular_member(info)
                or info.file_size > MAX_MEMBER_BYTES
                or info.compress_size < 1
                or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise AssertionError("external archive member failed bounded validation")
            data = source.read(info)
            if PurePosixPath(info.filename).suffix.casefold() != ".prm":
                continue
            digest = _sha256_bytes(data)
            path = target / f"source-{digest}.prm"
            path.write_bytes(data)
            staged[digest] = path
    if _sha256(archive) != expected_sha256:
        raise AssertionError("external archive changed during the read-only probe")
    return staged


def _candidate_grid_match(text: str, *, record_count: int, d_step: int, min_ticks: float) -> bool:
    value = Decimal(text)
    step = Decimal(d_step) / Decimal(str(min_ticks))
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise AssertionError("Result RT is not a finite exact decimal")
    printed_unit = Decimal(1).scaleb(exponent)
    tolerance = printed_unit / 2
    nearest_index = (value / step).to_integral_value(rounding=ROUND_HALF_EVEN)
    candidate = nearest_index * step
    last = Decimal(record_count - 1) * step
    return (
        Decimal(0) - tolerance <= value <= last + tolerance and abs(value - candidate) <= tolerance
    )


def test_cross_version_structural_probe_and_9_0_candidate_evidence(tmp_path: Path) -> None:
    raw_paths = _stage_prms(
        _fixture("ORDIFILE_YOUNGIN_PRM_ARCHIVE"),
        tmp_path / "raw",
        expected_size=RAW_ARCHIVE_SIZE,
        expected_sha256=RAW_ARCHIVE_SHA256,
    )
    scientific_paths = _stage_prms(
        _fixture("ORDIFILE_YOUNGIN_EXPANDED_ARCHIVE"),
        tmp_path / "scientific",
        expected_size=SCIENTIFIC_ARCHIVE_SIZE,
        expected_sha256=SCIENTIFIC_ARCHIVE_SHA256,
    )
    assert len(raw_paths) == 23
    assert len(scientific_paths) == 5

    raw = {digest: read_prm(path) for digest, path in raw_paths.items()}
    scientific = {digest: read_prm(path) for digest, path in scientific_paths.items()}
    raw_summary = probe.summarize_corpus(raw.values())
    scientific_summary = probe.summarize_corpus(scientific.values())
    assert (raw_summary.files, raw_summary.channels, raw_summary.records) == (23, 43, 563_240)
    assert (scientific_summary.files, scientific_summary.channels, scientific_summary.records) == (
        5,
        10,
        138_000,
    )
    assert raw_summary.size_equation_matches == 43
    assert scientific_summary.size_equation_matches == 10
    assert raw_summary.history_histogram == ((1, 5), (2, 7), (3, 11))
    assert scientific_summary.history_histogram == ((1, 5),)
    assert raw_summary.channel_layout_histogram == (("FID+TCD", 20), ("TCD", 3))
    assert scientific_summary.channel_layout_histogram == (("FID+TCD", 5),)
    assert raw_summary.normalized_structure_groups == 2
    assert scientific_summary.normalized_structure_groups == 1
    assert raw_summary.d_step_values == scientific_summary.d_step_values == (1,)
    assert raw_summary.min_ticks_values == scientific_summary.min_ticks_values == (600.0,)

    raw_fingerprints = {probe.normalized_structure_fingerprint(item) for item in raw.values()}
    scientific_fingerprints = {
        probe.normalized_structure_fingerprint(item) for item in scientific.values()
    }
    assert scientific_fingerprints <= raw_fingerprints

    replays = [
        probe.replay_validated_9_1_without_scientific_version_gate(path)
        for path in scientific_paths.values()
    ]
    assert len(replays) == 5
    assert sum(item.streams for item in replays) == 10
    assert sum(item.points for item in replays) == 138_000
    assert sum(item.retention_time_matches for item in replays) == 138_000
    assert sum(item.signal_matches for item in replays) == 138_000
    assert sum(item.channel_matches for item in replays) == 10
    assert sum(item.unit_matches for item in replays) == 10
    assert all(item.original_hash_preserved for item in replays)

    reverse_passes = 0
    reverse_rejections: dict[str, int] = {}
    for path in raw_paths.values():
        try:
            probe.read_version_masked(path, target_version="YL-Clarity 9.1.0.76")
        except YoungInPrmStructureError as error:
            reverse_rejections[error.code] = reverse_rejections.get(error.code, 0) + 1
        else:
            reverse_passes += 1
    assert reverse_passes + sum(reverse_rejections.values()) == 23
    assert reverse_passes == 5
    assert reverse_rejections == {"YOUNGIN_PRM_PROFILE_UNSUPPORTED": 18}

    result_sources = (
        _fixture("ORDIFILE_YOUNGIN_RESULT_CSV_A_FIXTURE"),
        _fixture("ORDIFILE_YOUNGIN_RESULT_CSV_B_FIXTURE"),
    )
    compared_rows = 0
    matching_rows = 0
    for result_path in result_sources:
        result = read_result_csv(result_path)
        paired_prm = raw[PAIRED_RESULT_PRM[result.source_sha256]]
        tcd = next(
            channel for channel in paired_prm.channels if channel.stored_detector_label == "TCD"
        )
        for peak in result.peaks:
            compared_rows += 1
            matching_rows += _candidate_grid_match(
                peak.retention_time_text,
                record_count=tcd.record_count,
                d_step=tcd.d_step_candidate,
                min_ticks=tcd.min_ticks_candidate,
            )
    assert compared_rows == matching_rows == 6

    assert all(
        channel.record_count > 0
        and channel.d_step_candidate > 0
        and channel.min_ticks_candidate > 0
        and (channel.record_count - 1) * channel.d_step_candidate / channel.min_ticks_candidate >= 0
        for item in raw.values()
        for channel in item.channels
    )
    assert _sha256(_fixture("ORDIFILE_YOUNGIN_PRM_ARCHIVE")) == RAW_ARCHIVE_SHA256
    assert _sha256(_fixture("ORDIFILE_YOUNGIN_EXPANDED_ARCHIVE")) == SCIENTIFIC_ARCHIVE_SHA256
