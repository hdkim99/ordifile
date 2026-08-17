# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Evidence-recording adapter detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ordifile.adapters.base import DetectionResult, FormatAdapter
from ordifile.adapters.registry import AdapterRegistry
from ordifile.core.errors import AdapterAmbiguityError, DetectionError

AMBIGUITY_MARGIN = 0.05
MAX_DETECTION_ERROR_MESSAGE_CHARACTERS = 512
SOURCE_IDENTITY_PROBE_REASON = "Probe reason withheld by source identity policy."


def _bounded_no_match_message(reasons: str) -> str:
    prefix = "No adapter matched bounded file content. Probe evidence: "
    if len(prefix) + len(reasons) <= MAX_DETECTION_ERROR_MESSAGE_CHARACTERS:
        return prefix + reasons
    suffix = " [truncated]"
    remaining = MAX_DETECTION_ERROR_MESSAGE_CHARACTERS - len(prefix) - len(suffix)
    return prefix + reasons[:remaining].rstrip() + suffix


@dataclass(frozen=True, slots=True)
class DetectionOutcome:
    """Selected adapter and all probe evidence."""

    adapter: FormatAdapter
    probes: tuple[tuple[str, DetectionResult], ...]


def detect_adapter(
    path: Path,
    registry: AdapterRegistry,
    *,
    forced_adapter: str | None = None,
    redact_reasons: bool = False,
) -> DetectionOutcome:
    """Probe adapters, optionally replacing untrusted reasons before any disclosure."""
    adapters = (registry.get(forced_adapter),) if forced_adapter else registry.adapters()
    probes: list[tuple[str, DetectionResult]] = []
    for adapter in adapters:
        try:
            result = adapter.probe(path)
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception as error:  # trusted plugins may raise arbitrary ordinary exceptions
            result = DetectionResult(
                False,
                0.0,
                f"probe failed with {type(error).__name__}",
            )
        confidence = max(0.0, min(1.0, result.confidence))
        probes.append(
            (
                adapter.adapter_id,
                DetectionResult(
                    result.matched,
                    confidence,
                    SOURCE_IDENTITY_PROBE_REASON if redact_reasons else result.reason,
                ),
            )
        )
    matches = sorted(
        ((adapter_id, result) for adapter_id, result in probes if result.matched),
        key=lambda item: (-item[1].confidence, item[0]),
    )
    if not matches:
        reasons = "; ".join(f"{adapter_id}: {probe.reason}" for adapter_id, probe in probes)
        raise DetectionError(
            "FORMAT_NOT_DETECTED",
            _bounded_no_match_message(reasons),
        )
    if len(matches) > 1 and matches[0][1].confidence - matches[1][1].confidence <= AMBIGUITY_MARGIN:
        claims = ", ".join(
            f"{adapter_id} (confidence={result.confidence:.2f}; reason={result.reason})"
            for adapter_id, result in matches
        )
        raise AdapterAmbiguityError(
            "FORMAT_AMBIGUOUS",
            f"Multiple adapters made similarly confident claims: {claims}. Choose --adapter.",
            details={
                f"claim_{index}": (
                    f"adapter={adapter_id};confidence={result.confidence:.6f};"
                    f"reason={result.reason}"
                )
                for index, (adapter_id, result) in enumerate(matches, start=1)
            },
        )
    return DetectionOutcome(registry.get(matches[0][0]), tuple(probes))
