# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from ordifile.adapters import _youngin_yl_clarity_prm_binary as binary
from ordifile.adapters._youngin_yl_clarity_prm_binary import read_prm

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "local"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
import youngin_yl_clarity_prm_cross_version_probe as probe  # noqa: E402
from generate_youngin_yl_clarity_prm import synthetic_prm_bytes  # noqa: E402


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_version_masked_replay_preserves_every_synthetic_9_1_point(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "scientific.prm",
        synthetic_prm_bytes(
            producer_text=binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SYNTHETIC",
            channels=((1.25, 2.5, 3.75), (10.0, 20.0, 30.0)),
        ),
    )
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    replay = probe.replay_validated_9_1_without_scientific_version_gate(source)

    assert replay == probe.ScientificReplay(2, 6, 6, 6, 2, 2, True)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_masking_changes_only_typed_family_info_values(tmp_path: Path) -> None:
    duplicate = (
        binary.INFO_VALUE_KEY
        + bytes([len(binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SECOND")])
        + (binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SECOND").encode("utf-16-le")
    )
    source = _write(
        tmp_path / "scientific.prm",
        synthetic_prm_bytes(
            producer_text=binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SYNTHETIC",
            channels=((1.0,), (2.0,)),
            embedded_private_text=duplicate,
        ),
    )

    original = source.read_bytes()
    masked_bytes, replacement_count = probe._mask_typed_producer_values(
        original,
        source_version="YL-Clarity 9.1.0.76",
        target_version="YL-Clarity 9.0.1.19",
    )
    changed = {
        index
        for index, pair in enumerate(zip(original, masked_bytes, strict=True))
        if pair[0] != pair[1]
    }
    allowed: set[int] = set()
    start = 0
    for _ in range(2):
        offset = original.index(binary.INFO_VALUE_KEY, start)
        value_start = offset + len(binary.INFO_VALUE_KEY) + 1
        allowed.update(range(value_start, value_start + len(binary.SCIENTIFIC_PRODUCER_PREFIX)))
        start = value_start

    assert replacement_count == 2
    assert len(masked_bytes) == len(original)
    assert changed
    assert changed <= allowed

    masked = probe.read_version_masked(source, target_version="YL-Clarity 9.0.1.19")

    assert masked.replaced_info_values == 2
    assert masked.original.producer_version == "YL-Clarity 9.1.0.76"
    assert masked.masked.producer_version == "YL-Clarity 9.0.1.19"
    assert masked.original.aggregate_payload_sha256 == masked.masked.aggregate_payload_sha256
    assert masked.original.aggregate_canonical_be_f32_sha256 == (
        masked.masked.aggregate_canonical_be_f32_sha256
    )


def test_compatible_unknown_profile_is_not_an_exact_masking_oracle(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "unknown.prm",
        synthetic_prm_bytes(producer_text="YL-Clarity 9.2.0.1 FULL, SN: SYNTHETIC"),
    )

    with pytest.raises(probe.ResearchProbeError, match="two different exact observed"):
        probe.read_version_masked(source, target_version="YL-Clarity 9.1.0.76")


def test_worktree_temp_output_is_rejected_but_external_temp_root_is_allowed(
    tmp_path: Path,
) -> None:
    source = _write(
        tmp_path / "scientific.prm",
        synthetic_prm_bytes(
            producer_text=binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SYNTHETIC",
            channels=((1.0,), (2.0,)),
        ),
    )
    with pytest.raises(probe.ResearchProbeError, match="outside the worktree"):
        probe.read_version_masked(
            source,
            target_version="YL-Clarity 9.0.1.19",
            temp_root=PROJECT_ROOT / "unsafe-research-output",
        )

    external = tmp_path / "probe-output"
    result = probe.read_version_masked(
        source,
        target_version="YL-Clarity 9.0.1.19",
        temp_root=external,
    )
    assert result.original_hash_preserved
    assert list(external.iterdir()) == []


def test_summary_excludes_identity_and_measured_values(tmp_path: Path) -> None:
    raw = read_prm(_write(tmp_path / "raw.prm", synthetic_prm_bytes(channels=((1.0, 2.0),))))
    scientific = read_prm(
        _write(
            tmp_path / "scientific.prm",
            synthetic_prm_bytes(
                producer_text=binary.SCIENTIFIC_PRODUCER_PREFIX_TEXT + "SYNTHETIC",
                channels=((3.0, 4.0), (5.0, 6.0)),
            ),
        )
    )

    summary = probe.summarize_corpus((raw, scientific))
    public = summary.to_public_dict()

    assert summary.files == 2
    assert summary.channels == 3
    assert summary.records == 6
    assert summary.size_equation_matches == 3
    assert summary.normalized_structure_groups == 2
    rendered = repr(public)
    assert "sha" not in rendered.casefold()
    assert str(tmp_path) not in rendered
    assert "3.0" not in rendered
