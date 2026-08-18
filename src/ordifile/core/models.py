# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Immutable canonical data model shared by adapters and exporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

MAX_CANONICAL_INTEGER_DECIMAL_DIGITS: int = 1_000
MAX_CANONICAL_INTEGER_LEXEME_CHARACTERS: int = 4_096
MAX_CANONICAL_INTEGER_ABS: int = 10**MAX_CANONICAL_INTEGER_DECIMAL_DIGITS


def integer_is_within_canonical_bound(value: int) -> bool:
    """Bound integers without converting attacker-controlled values to decimal text."""
    if isinstance(value, bool):
        return True
    # The bit check rejects extreme values before the more exact numeric comparison.
    if value.bit_length() > MAX_CANONICAL_INTEGER_ABS.bit_length():
        return False
    return -MAX_CANONICAL_INTEGER_ABS < value < MAX_CANONICAL_INTEGER_ABS


class Severity(StrEnum):
    """Severity of a structured issue."""

    WARNING = "warning"
    ERROR = "error"


class FileStatus(StrEnum):
    """Outcome of processing one discovered input."""

    SUCCESS = "success"
    WARNING = "warning"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"


class BatchOutcome(StrEnum):
    """Presentation-neutral outcome shared by CLI and desktop interfaces."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class SortMode(StrEnum):
    """Supported batch ordering modes."""

    AUTO = "auto"
    ACQUIRED_AT = "acquired_at"
    SEQUENCE = "sequence"
    FILENAME = "filename"
    INPUT_ORDER = "input_order"


class SeriesKind(StrEnum):
    """Semantic boundary between scientific signals and structural records."""

    SCIENTIFIC_SIGNAL = "scientific_signal"
    DECODED_RECORDS = "decoded_records"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """A stable, presentation-neutral batch progress notification."""

    stage: str
    completed: int
    total: int
    source_file: str | None = None
    status: FileStatus | None = None


@dataclass(frozen=True, slots=True)
class Issue:
    """A warning or error that remains attached to its source."""

    code: str
    message: str
    severity: Severity
    source: str | None = None
    context: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class SourceFile:
    """Read-only identity and integrity metadata for one input path."""

    path: Path
    relative_path: str
    name: str
    size: int
    sha256: str | None
    modified_at: datetime | None
    input_order: int
    detected_format: str | None = None
    duplicate_of: int | None = None
    public_id: str | None = None

    @property
    def public_reference(self) -> str:
        """Return the core-owned public identity without changing the input path."""
        return self.relative_path if self.public_id is None else self.public_id


@dataclass(frozen=True, slots=True)
class InstrumentMetadata:
    """Explicit instrument identity fields only."""

    instrument_type: str | None = None
    vendor: str | None = None


@dataclass(frozen=True, slots=True)
class SampleRecord:
    """One logical sample produced from one input file."""

    sample_id: str
    source: SourceFile
    acquired_at: datetime | None = None
    acquired_at_reliable: bool = False
    sequence: int | None = None
    instrument: InstrumentMetadata = field(default_factory=InstrumentMetadata)
    channels: tuple[str, ...] = ()
    detectors: tuple[str, ...] = ()
    runtime: float | None = None
    status: FileStatus = FileStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class SignalSeries:
    """Uninterpolated scientific coordinates or structural records by ``series_kind``."""

    sample_id: str
    source_file: str
    channel: str | None
    detector: str | None
    x_values: tuple[int | float, ...]
    y_values: tuple[int | float, ...]
    x_label: str = "time"
    x_unit: str | None = None
    y_label: str = "signal"
    y_unit: str | None = None
    series_kind: SeriesKind = SeriesKind.SCIENTIFIC_SIGNAL


@dataclass(frozen=True, slots=True)
class PeakRecord:
    """One explicitly described peak; retention times are never compound identities."""

    sample_id: str
    source_file: str
    channel: str | None = None
    detector: str | None = None
    peak_number: int | None = None
    retention_time: float | None = None
    retention_time_unit: str | None = None
    area: float | None = None
    height: float | None = None
    compound: str | None = None
    compound_source: str | None = None
    status: str = "parsed"
    observation_order: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    area_unit: str | None = None
    height_unit: str | None = None


@dataclass(frozen=True, slots=True)
class MetadataEntry:
    """A source field preserved without inventing scientific semantics."""

    sample_id: str
    source_file: str
    namespace: str
    key: str
    value: Any
    unit: str | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetBundle:
    """Canonical result returned by one adapter."""

    sources: tuple[SourceFile, ...]
    samples: tuple[SampleRecord, ...]
    signals: tuple[SignalSeries, ...] = ()
    peaks: tuple[PeakRecord, ...] = ()
    metadata: tuple[MetadataEntry, ...] = ()
    warnings: tuple[Issue, ...] = ()
    errors: tuple[Issue, ...] = ()


@dataclass(frozen=True, slots=True)
class FileResult:
    """Complete processing record for one input, including failures."""

    source: SourceFile
    status: FileStatus
    adapter_id: str | None = None
    adapter_version: str | None = None
    bundle: DatasetBundle | None = None
    issues: tuple[Issue, ...] = ()
    sort_key: str | None = None
    probes: tuple[tuple[str, float, str], ...] = ()


@dataclass(frozen=True, slots=True)
class SortDecision:
    """Effective sort mode and transparent fallback provenance."""

    requested: SortMode
    effective: SortMode
    reason: str


@dataclass(frozen=True, slots=True)
class SidecarRecord:
    """Integrity record for data intentionally stored outside Excel."""

    relative_path: str
    row_count: int
    sha256: str
    formula_escape_count: int = 0


@dataclass(frozen=True, slots=True)
class ConversionOptions:
    """Immutable, privacy-safe snapshot of behavior-affecting conversion options."""

    recursive: bool = False
    extensions: tuple[str, ...] = ()
    sort: SortMode = SortMode.AUTO
    include_signals: bool = False
    adapter: str | None = None
    sheet: str | None = None
    include_hidden_sheets: bool = False
    on_error: str = "continue"
    overwrite: bool = False
    sidecar_mode: str = "error"
    output_name: str | None = None


@dataclass(frozen=True, slots=True)
class BatchResult:
    """Public conversion result."""

    files: tuple[FileResult, ...]
    sort: SortDecision
    output_path: Path | None = None
    sheets: tuple[str, ...] = ()
    sidecars: tuple[SidecarRecord, ...] = ()
    options: ConversionOptions = field(default_factory=ConversionOptions)

    @property
    def outcome(self) -> BatchOutcome:
        """Classify a batch without duplicating presentation-specific logic."""
        if self.success_count == 0:
            return BatchOutcome.FAILED
        if self.failure_count:
            return BatchOutcome.PARTIAL_SUCCESS
        return BatchOutcome.SUCCESS

    @property
    def success_count(self) -> int:
        """Return the number of inputs parsed successfully."""
        return sum(item.status in (FileStatus.SUCCESS, FileStatus.WARNING) for item in self.files)

    @property
    def warning_count(self) -> int:
        """Return the number of files with one or more warnings."""
        return sum(
            item.status is FileStatus.WARNING
            or any(issue.severity is Severity.WARNING for issue in item.issues)
            for item in self.files
        )

    @property
    def failure_count(self) -> int:
        """Return inputs that failed, excluding recorded duplicate paths."""
        return sum(item.status is FileStatus.FAILED for item in self.files)

    @property
    def duplicate_count(self) -> int:
        """Return repeated resolved paths intentionally not parsed twice."""
        return sum(item.status is FileStatus.DUPLICATE for item in self.files)


@dataclass(frozen=True, slots=True)
class InspectionResult:
    """Public inspection result without writing output."""

    file: FileResult
    probes: tuple[tuple[str, float, str], ...]
