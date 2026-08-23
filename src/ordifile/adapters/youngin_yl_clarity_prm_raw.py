# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Experimental raw-record converter for one observed YoungIn YL-Clarity PRM profile."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ordifile.adapters._youngin_yl_clarity_prm_binary import (
    YoungInPrmStructureError,
    has_prm_family_identity,
    read_prm,
)
from ordifile.adapters.base import (
    AdapterDescriptor,
    DetectionResult,
    ParseOptions,
    SourceIdentityPolicy,
    SupportStatus,
)
from ordifile.core.errors import ParseError
from ordifile.core.models import (
    DatasetBundle,
    InstrumentMetadata,
    Issue,
    MetadataEntry,
    SampleRecord,
    SeriesKind,
    Severity,
    SignalSeries,
    SourceFile,
)

_NAMESPACE = "adapter:youngin_yl_clarity_prm_raw"


def _parse_error(error: YoungInPrmStructureError) -> ParseError:
    return ParseError(error.code, error.message, details=error.details)


class YoungInYlClarityPrmRawAdapter:
    """Expose ordered binary32 records without assigning scientific semantics."""

    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "youngin_yl_clarity_prm_raw"
    adapter_version: ClassVar[str] = "0.1.0"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "YoungIn YL-Clarity .PRM raw records, observed 9.0.1.19 profile (Experimental)",
        (".prm",),
        True,
        False,
        True,
        True,
        SupportStatus.EXPERIMENTAL,
        (SeriesKind.DECODED_RECORDS,),
        SourceIdentityPolicy.SHA256_ALIAS,
    )

    def probe(self, path: Path) -> DetectionResult:
        """Require the case-insensitive .prm extension and bounded profile markers."""
        if path.suffix.casefold() != ".prm":
            return DetectionResult(False, 0.0, "the required .prm extension is absent")
        recognized = has_prm_family_identity(path)
        if not recognized:
            return DetectionResult(False, 0.0, "bounded YL-Clarity PRM family markers are absent")
        try:
            parsed = read_prm(path)
        except YoungInPrmStructureError as error:
            return DetectionResult(True, 0.70, error.message)
        return DetectionResult(
            True,
            0.99,
            "exact observed YL-Clarity 9.0.1.19 PRM raw profile matched with "
            f"{parsed.structural_channel_count} structural channel(s)",
        )

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        """Return current-revision binary32 values in file and channel order."""
        del options
        if path.suffix.casefold() != ".prm":
            raise ParseError(
                "YOUNGIN_PRM_EXTENSION_INVALID",
                "The exact experimental profile requires a .prm source extension.",
            )
        try:
            decoded = read_prm(path)
            size = path.stat().st_size
        except YoungInPrmStructureError as error:
            raise _parse_error(error) from error
        except OSError as error:
            raise ParseError(
                "INPUT_READ_FAILED",
                f"Could not stat the input ({type(error).__name__}).",
            ) from error

        sample_id = f"PRM_{decoded.source_sha256[:16]}"
        safe_source = f"{sample_id}.prm"
        source = SourceFile(path, safe_source, safe_source, size, decoded.source_sha256, None, 0)
        channel_ids = tuple(channel.channel_id for channel in decoded.channels)
        sample = SampleRecord(
            sample_id,
            source,
            acquired_at=None,
            acquired_at_reliable=False,
            sequence=None,
            instrument=InstrumentMetadata(None, "YoungIn"),
            channels=channel_ids,
            detectors=(),
            runtime=None,
        )
        signals = tuple(
            SignalSeries(
                sample_id,
                safe_source,
                channel.channel_id,
                None,
                tuple(range(channel.record_count)),
                channel.values,
                x_label="decoded_record_index",
                x_unit=None,
                y_label="decoded_raw_binary32",
                y_unit=None,
                series_kind=SeriesKind.DECODED_RECORDS,
            )
            for channel in decoded.channels
        )
        values: list[tuple[str, object, str | None]] = [
            ("support_status", "experimental", None),
            ("representation", "decoded_records", None),
            ("profile", decoded.profile, None),
            ("producer_version", "YL-Clarity 9.0.1.19", None),
            ("history_count", decoded.history_count, None),
            ("selected_history_version", decoded.selected_history_version, None),
            ("history_revision_exposure_status", "latest_revision_only", None),
            ("prior_history_revision_count", decoded.prior_history_revision_count, None),
            ("prior_history_revisions_exposed", 0, None),
            ("prior_rawdata6_block_count", decoded.prior_rawdata6_block_count, None),
            ("prior_prmdata_block_count", decoded.prior_prmdata_block_count, None),
            ("structural_channel_count", decoded.structural_channel_count, None),
            ("source_sha256", decoded.source_sha256, None),
            ("aggregate_payload_sha256", decoded.aggregate_payload_sha256, None),
            (
                "aggregate_canonical_be_f32_sha256",
                decoded.aggregate_canonical_be_f32_sha256,
                None,
            ),
            ("detector_verified", False, None),
            ("detector_identity_status", "experimental_stored_native_label", None),
            ("channel_identity_status", "experimental_stored_native_label", None),
            ("time_axis_status", "not_exposed", None),
            ("physical_scaling_status", "not_applied", None),
            ("signal_unit_status", "unresolved", None),
            ("peak_table_status", "unsupported", None),
            ("scientific_semantics_status", "pending_paired_export", None),
            (
                "scientific_semantics_evidence_gap",
                "same_run_chromatogram_curve",
                None,
            ),
        ]
        for index, channel in enumerate(decoded.channels, start=1):
            prefix = f"structural_channel_{index:03d}"
            values.extend(
                [
                    (f"{prefix}_record_count", channel.record_count, None),
                    (f"{prefix}_stored_detector_label", channel.stored_detector_label, None),
                    (f"{prefix}_raw_size_candidate", channel.raw_size_candidate, None),
                    (f"{prefix}_d_step_candidate", channel.d_step_candidate, None),
                    (f"{prefix}_d_size_candidate", channel.d_size_candidate, None),
                    (f"{prefix}_min_ticks_candidate", channel.min_ticks_candidate, None),
                    (f"{prefix}_payload_sha256", channel.payload_sha256, None),
                    (
                        f"{prefix}_canonical_be_f32_sha256",
                        channel.canonical_be_f32_sha256,
                        None,
                    ),
                ]
            )
        metadata = tuple(
            MetadataEntry(sample_id, safe_source, _NAMESPACE, key, value, unit)
            for key, value, unit in values
        )
        warnings = [
            Issue(
                "YOUNGIN_PRM_EXPERIMENTAL_RAW_RECORDS",
                "Ordered binary32 records were decoded without verified detector identity, "
                "time axis, physical scaling, signal units, or peak semantics.",
                Severity.WARNING,
                sample_id,
            ),
        ]
        if decoded.prior_history_revision_count:
            warnings.append(
                Issue(
                    "YOUNGIN_PRM_PRIOR_HISTORY_NOT_EXPOSED",
                    "Only raw blocks after the latest ChromVersion are exported; earlier "
                    "history revisions remain unsupported and their structural counts are "
                    "reported in Metadata.",
                    Severity.WARNING,
                    sample_id,
                )
            )
        return DatasetBundle(
            (source,),
            (sample,),
            signals=signals,
            metadata=metadata,
            warnings=tuple(warnings),
        )
