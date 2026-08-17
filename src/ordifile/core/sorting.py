# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Deterministic sample ordering with recorded fallback decisions."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC

from ordifile.core.discovery import natural_key
from ordifile.core.models import FileResult, FileStatus, SortDecision, SortMode


def _success(item: FileResult) -> bool:
    return item.status in (FileStatus.SUCCESS, FileStatus.WARNING) and item.bundle is not None


def _filename_key(item: FileResult) -> tuple[object, ...]:
    if item.source.public_id is not None:
        return (item.source.public_reference.casefold(), item.source.input_order)
    return (
        natural_key(item.source.name),
        natural_key(item.source.relative_path),
        item.source.input_order,
    )


def _timestamp_key(item: FileResult) -> tuple[object, ...]:
    if not _success(item):
        return (1, 0.0, *_filename_key(item))
    sample = item.bundle.samples[0]  # type: ignore[union-attr]
    if sample.acquired_at is None or not sample.acquired_at_reliable:
        return (1, 0.0, *_filename_key(item))
    try:
        timestamp = sample.acquired_at.astimezone(UTC)
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except Exception:
        return (1, 0.0, *_filename_key(item))
    return (0, timestamp, *_filename_key(item))


def _sequence_key(item: FileResult) -> tuple[object, ...]:
    if not _success(item):
        return (1, 0, *_filename_key(item))
    sample = item.bundle.samples[0]  # type: ignore[union-attr]
    if sample.sequence is None:
        return (1, 0, *_filename_key(item))
    return (0, sample.sequence, *_filename_key(item))


def _sort_key_text(item: FileResult, mode: SortMode) -> str:
    public_reference = item.source.public_reference
    if mode is SortMode.ACQUIRED_AT:
        if not _success(item):
            return f"fallback:{public_reference}"
        sample = item.bundle.samples[0]  # type: ignore[union-attr]
        if sample.acquired_at is not None and sample.acquired_at_reliable:
            try:
                return sample.acquired_at.isoformat()
            except (KeyboardInterrupt, SystemExit, MemoryError):
                raise
            except Exception:
                pass
        return f"fallback:{public_reference}"
    if mode is SortMode.SEQUENCE:
        if not _success(item):
            return f"fallback:{public_reference}"
        sample = item.bundle.samples[0]  # type: ignore[union-attr]
        return (
            str(sample.sequence) if sample.sequence is not None else f"fallback:{public_reference}"
        )
    if mode is SortMode.INPUT_ORDER:
        return str(item.source.input_order)
    return public_reference


def sort_file_results(
    files: tuple[FileResult, ...], requested: SortMode | str = SortMode.AUTO
) -> tuple[tuple[FileResult, ...], SortDecision]:
    """Sort every file outcome by the effective criterion and record fallback provenance."""
    mode = requested if isinstance(requested, SortMode) else SortMode(requested)
    successful = [item for item in files if _success(item)]
    all_acquired = bool(successful) and all(
        item.bundle is not None
        and item.bundle.samples[0].acquired_at is not None
        and item.bundle.samples[0].acquired_at_reliable
        for item in successful
    )
    all_sequence = bool(successful) and all(
        item.bundle is not None and item.bundle.samples[0].sequence is not None
        for item in successful
    )
    has_unavailable_outcomes = len(successful) != len(files)

    if mode is SortMode.AUTO:
        if all_acquired:
            effective = SortMode.ACQUIRED_AT
            reason = "All successful files have reliable, timezone-aware acquisition times."
            if has_unavailable_outcomes:
                reason += " Unavailable outcomes use natural filename fallback."
        elif all_sequence:
            effective = SortMode.SEQUENCE
            reason = "Acquisition times were incomplete or unreliable; sequence is complete."
            if has_unavailable_outcomes:
                reason += " Unavailable outcomes use natural filename fallback."
        else:
            effective = SortMode.FILENAME
            reason = (
                "Acquisition time and sequence were not complete; natural filename fallback used."
            )
    else:
        effective = mode
        if mode is SortMode.ACQUIRED_AT and (not all_acquired or has_unavailable_outcomes):
            reason = (
                "Requested acquisition-time ordering; missing or unreliable values sort after "
                "available "
                "values using natural filename ties."
            )
        elif mode is SortMode.SEQUENCE and (not all_sequence or has_unavailable_outcomes):
            reason = (
                "Requested sequence ordering; missing values sort after available values using "
                "natural "
                "filename ties."
            )
        else:
            reason = f"User requested {mode.value} ordering."

    if effective is SortMode.ACQUIRED_AT:
        ordered = sorted(files, key=_timestamp_key)
    elif effective is SortMode.SEQUENCE:
        ordered = sorted(files, key=_sequence_key)
    elif effective is SortMode.FILENAME:
        ordered = sorted(files, key=_filename_key)
    else:
        ordered = sorted(files, key=lambda item: item.source.input_order)
    with_keys = tuple(replace(item, sort_key=_sort_key_text(item, effective)) for item in ordered)
    return with_keys, SortDecision(mode, effective, reason)
