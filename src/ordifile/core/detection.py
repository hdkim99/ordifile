# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Evidence-recording adapter detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ordifile.adapters.base import DetectionResult, FormatAdapter, SourceIdentityPolicy
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


def _error_reason(result: DetectionResult, *, redact: bool) -> str:
    """Return safe error-only evidence without changing successful probe records."""
    return SOURCE_IDENTITY_PROBE_REASON if redact else result.reason


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
    redact_adapter_ids: frozenset[str] | None = None,
    redact_error_reasons: bool = False,
    excluded_adapter_ids: frozenset[str] | None = None,
) -> DetectionOutcome:
    """Probe adapters, optionally replacing selected reasons before any disclosure."""
    excluded = frozenset() if excluded_adapter_ids is None else excluded_adapter_ids
    adapters = (registry.get(forced_adapter),) if forced_adapter else registry.adapters()
    adapters = tuple(adapter for adapter in adapters if adapter.adapter_id not in excluded)
    reason_redactions = frozenset() if redact_adapter_ids is None else redact_adapter_ids
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
                    SOURCE_IDENTITY_PROBE_REASON
                    if redact_reasons or adapter.adapter_id in reason_redactions
                    else result.reason,
                ),
            )
        )
    matches = sorted(
        ((adapter_id, result) for adapter_id, result in probes if result.matched),
        key=lambda item: (-item[1].confidence, item[0]),
    )
    if not matches:
        reasons = "; ".join(
            f"{adapter_id}: {_error_reason(probe, redact=redact_error_reasons)}"
            for adapter_id, probe in probes
        )
        raise DetectionError(
            "FORMAT_NOT_DETECTED",
            _bounded_no_match_message(reasons),
        )
    private_matches = tuple(
        (adapter_id, result)
        for adapter_id, result in matches
        if registry.get(adapter_id).descriptor.source_identity_policy
        is SourceIdentityPolicy.SHA256_ALIAS
    )
    if private_matches:
        # A privacy-sensitive adapter uses a positive match to claim ownership even
        # when its exact parse will reject a malformed or unsupported profile. Never
        # let a broader relative-path parser win only by confidence and disclose the
        # basename or private fields that the matched owner requires us to withhold.
        matches = list(private_matches)
    if len(matches) > 1 and matches[0][1].confidence - matches[1][1].confidence <= AMBIGUITY_MARGIN:
        claims = ", ".join(
            f"{adapter_id} (confidence={result.confidence:.2f}; reason="
            f"{_error_reason(result, redact=redact_error_reasons)})"
            for adapter_id, result in matches
        )
        raise AdapterAmbiguityError(
            "FORMAT_AMBIGUOUS",
            f"Multiple adapters made similarly confident claims: {claims}. Choose --adapter.",
            details={
                f"claim_{index}": (
                    f"adapter={adapter_id};confidence={result.confidence:.6f};"
                    f"reason={_error_reason(result, redact=redact_error_reasons)}"
                )
                for index, (adapter_id, result) in enumerate(matches, start=1)
            },
        )
    return DetectionOutcome(registry.get(matches[0][0]), tuple(probes))
