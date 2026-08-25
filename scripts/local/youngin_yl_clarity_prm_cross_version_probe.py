# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Research-only cross-version probe for exact observed YL-Clarity PRM files.

This module is not an Ordifile runtime feature. It creates a short-lived private
copy whose *typed producer Info field only* is replaced by the other exact known
producer prefix, then reuses the production structural reader. A successful masked
parse establishes counterfactual structural compatibility only. It does not validate
retention-time origin, detector identity, response scaling, physical units, or peaks.
"""

from __future__ import annotations

import hashlib
import tempfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ordifile.adapters import _youngin_yl_clarity_prm_binary as binary
from ordifile.adapters._youngin_yl_clarity_prm_binary import YoungInPrmData
from ordifile.adapters.base import ParseOptions
from ordifile.adapters.youngin_yl_clarity_prm_raw import YoungInYlClarityPrmRawAdapter

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_WORKTREE_LOCAL_ROOTS = frozenset({".external-fixtures", ".research-downloads", "fixture-cache"})
_KNOWN_PREFIXES = {
    "YL-Clarity 9.0.1.19": binary.PRODUCER_PREFIX,
    "YL-Clarity 9.1.0.76": binary.SCIENTIFIC_PRODUCER_PREFIX,
}
_VALIDATED_9_1_RESPONSE_UNITS = {"FID": "pA", "TCD": "mV"}


class ResearchProbeError(RuntimeError):
    """A research-only safety or comparison condition failed."""


@dataclass(frozen=True, slots=True)
class MaskedRead:
    """One exact source and its temporary counterfactual structural parse."""

    original: YoungInPrmData
    masked: YoungInPrmData
    replaced_info_values: int
    original_hash_preserved: bool


@dataclass(frozen=True, slots=True)
class ScientificReplay:
    """Aggregate comparison of production 9.1 signals and a version-masked replay."""

    streams: int
    points: int
    retention_time_matches: int
    signal_matches: int
    channel_matches: int
    unit_matches: int
    original_hash_preserved: bool


@dataclass(frozen=True, slots=True)
class CorpusSummary:
    """Privacy-safe aggregate structural facts for one exact producer cohort."""

    files: int
    channels: int
    records: int
    history_histogram: tuple[tuple[int, int], ...]
    channel_layout_histogram: tuple[tuple[str, int], ...]
    record_count_histogram: tuple[tuple[int, int], ...]
    size_equation_matches: int
    d_step_values: tuple[int, ...]
    min_ticks_values: tuple[float, ...]
    normalized_structure_groups: int

    def to_public_dict(self) -> dict[str, object]:
        """Return aggregate facts without names, paths, hashes, or measured values."""
        return {
            "files": self.files,
            "channels": self.channels,
            "records": self.records,
            "history_histogram": dict(self.history_histogram),
            "channel_layout_histogram": dict(self.channel_layout_histogram),
            "record_count_histogram": dict(self.record_count_histogram),
            "size_equation_matches": self.size_equation_matches,
            "d_step_values": list(self.d_step_values),
            "min_ticks_values": list(self.min_ticks_values),
            "normalized_structure_groups": self.normalized_structure_groups,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validated_temp_root(temp_root: Path | None) -> Path | None:
    if temp_root is None:
        return None
    resolved = temp_root.resolve()
    if _is_within(resolved, _PROJECT_ROOT):
        relative = resolved.relative_to(_PROJECT_ROOT)
        if not relative.parts or relative.parts[0] not in _WORKTREE_LOCAL_ROOTS:
            raise ResearchProbeError(
                "Temporary masked files must stay outside the worktree or in an ignored local root."
            )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _mask_typed_producer_values(
    data: bytes,
    *,
    source_version: str,
    target_version: str,
) -> tuple[bytes, int]:
    source_prefix = _KNOWN_PREFIXES.get(source_version)
    target_prefix = _KNOWN_PREFIXES.get(target_version)
    if source_prefix is None or target_prefix is None or source_version == target_version:
        raise ResearchProbeError("Masking requires two different exact observed producer versions.")
    if len(source_prefix) != len(target_prefix):
        raise ResearchProbeError("Exact producer prefixes do not have equal byte length.")

    masked = bytearray(data)
    replaced = 0
    start = 0
    seen = 0
    boundary = len(data) - binary.FOOTER_BYTES
    while True:
        offset = data.find(binary.INFO_VALUE_KEY, start, boundary)
        if offset < 0:
            break
        seen += 1
        if seen > binary.MAX_INFO_VALUE_COUNT:
            raise ResearchProbeError("The bounded Info frame count was exceeded.")
        length_offset = offset + len(binary.INFO_VALUE_KEY)
        if length_offset >= boundary:
            raise ResearchProbeError("A typed Info frame is truncated before its length.")
        value_start = length_offset + 1
        value_end = value_start + data[length_offset] * 2
        if value_end > boundary:
            raise ResearchProbeError("A typed Info frame exceeds the bounded source.")
        value = data[value_start:value_end]
        if value.startswith(binary.FAMILY_MARKER):
            if not value.startswith(source_prefix):
                raise ResearchProbeError(
                    "A framed YL-Clarity value conflicts with the source profile."
                )
            masked[value_start : value_start + len(source_prefix)] = target_prefix
            replaced += 1
        start = offset + 1
    if replaced < 1:
        raise ResearchProbeError("No exact typed producer value was available for masking.")
    return bytes(masked), replaced


def read_version_masked(
    source: Path,
    *,
    target_version: str,
    temp_root: Path | None = None,
) -> MaskedRead:
    """Parse an exact source and a temporary same-length producer-masked copy."""
    original_hash_before = _sha256(source)
    original = binary.read_prm(source)
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != original_hash_before:
        raise ResearchProbeError("The source changed during the bounded research read.")
    masked_data, replaced = _mask_typed_producer_values(
        data,
        source_version=original.producer_version,
        target_version=target_version,
    )
    root = _validated_temp_root(temp_root)
    with tempfile.TemporaryDirectory(prefix="ordifile-prm-mask-", dir=root) as directory:
        masked_path = Path(directory) / "masked-source.prm"
        masked_path.write_bytes(masked_data)
        masked = binary.read_prm(masked_path)
    original_hash_after = _sha256(source)
    if original_hash_after != original_hash_before:
        raise ResearchProbeError("The original PRM changed during version-masked replay.")
    if masked.producer_version != target_version:
        raise ResearchProbeError(
            "The temporary structural parse did not select the target profile."
        )
    return MaskedRead(original, masked, replaced, True)


def replay_validated_9_1_without_scientific_version_gate(
    source: Path,
    *,
    temp_root: Path | None = None,
) -> ScientificReplay:
    """Compare production 9.1 signals with a 9.0-masked structural replay at every point."""
    bundle = YoungInYlClarityPrmRawAdapter().parse(source, ParseOptions())
    masked = read_version_masked(
        source,
        target_version="YL-Clarity 9.0.1.19",
        temp_root=temp_root,
    )
    if masked.original.producer_version != "YL-Clarity 9.1.0.76":
        raise ResearchProbeError(
            "Scientific replay accepts only the exact validated 9.1.0.76 profile."
        )
    if len(bundle.signals) != len(masked.masked.channels):
        raise ResearchProbeError("Production and masked channel counts differ.")

    points = 0
    retention_time_matches = 0
    signal_matches = 0
    channel_matches = 0
    unit_matches = 0
    for signal, channel in zip(bundle.signals, masked.masked.channels, strict=True):
        if (
            signal.channel == channel.channel_id
            and signal.detector == channel.stored_detector_label
        ):
            channel_matches += 1
        if (
            signal.x_unit == "min"
            and signal.y_unit == _VALIDATED_9_1_RESPONSE_UNITS[channel.stored_detector_label]
        ):
            unit_matches += 1
        if (
            len(signal.x_values) != channel.record_count
            or len(signal.y_values) != channel.record_count
        ):
            raise ResearchProbeError("Production and masked point counts differ.")
        for index, (x_value, y_value, masked_y) in enumerate(
            zip(signal.x_values, signal.y_values, channel.values, strict=True)
        ):
            candidate_x = index * channel.d_step_candidate / channel.min_ticks_candidate
            retention_time_matches += x_value == candidate_x
            signal_matches += y_value == masked_y
            points += 1
    return ScientificReplay(
        len(bundle.signals),
        points,
        retention_time_matches,
        signal_matches,
        channel_matches,
        unit_matches,
        masked.original_hash_preserved,
    )


def normalized_structure_fingerprint(decoded: YoungInPrmData) -> tuple[object, ...]:
    """Return a research-only current-curve structural fingerprint.

    Absolute record counts, history cardinality, producer identity, payload hashes and
    measured values are intentionally excluded. Their aggregate distributions remain
    separately visible through :func:`summarize_corpus`.
    """
    counts = tuple(channel.record_count for channel in decoded.channels)
    return (
        "current-rawdata6-metadata-prmdata-detname",
        "single-exact-gzip-member",
        "little-endian-binary32-source-order",
        tuple(channel.stored_detector_label for channel in decoded.channels),
        all(
            channel.raw_size_candidate == channel.d_size_candidate == channel.record_count
            for channel in decoded.channels
        ),
        tuple(sorted({channel.d_step_candidate for channel in decoded.channels})),
        tuple(sorted({channel.min_ticks_candidate for channel in decoded.channels})),
        len(counts) < 2 or len(set(counts)) == 1,
    )


def summarize_corpus(decoded_files: Iterable[YoungInPrmData]) -> CorpusSummary:
    """Summarize an exact-profile corpus without exposing source-level identity."""
    decoded = tuple(decoded_files)
    if not decoded:
        raise ResearchProbeError("At least one exact PRM is required for a corpus summary.")
    histories = Counter(item.history_count for item in decoded)
    layouts = Counter(
        "+".join(channel.stored_detector_label for channel in item.channels) for item in decoded
    )
    record_counts = Counter(channel.record_count for item in decoded for channel in item.channels)
    channels = tuple(channel for item in decoded for channel in item.channels)
    return CorpusSummary(
        files=len(decoded),
        channels=len(channels),
        records=sum(channel.record_count for channel in channels),
        history_histogram=tuple(sorted(histories.items())),
        channel_layout_histogram=tuple(sorted(layouts.items())),
        record_count_histogram=tuple(sorted(record_counts.items())),
        size_equation_matches=sum(
            channel.raw_size_candidate == channel.d_size_candidate == channel.record_count
            for channel in channels
        ),
        d_step_values=tuple(sorted({channel.d_step_candidate for channel in channels})),
        min_ticks_values=tuple(sorted({channel.min_ticks_candidate for channel in channels})),
        normalized_structure_groups=len(
            {normalized_structure_fingerprint(item) for item in decoded}
        ),
    )
