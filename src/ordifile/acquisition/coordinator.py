# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Core-owned lifecycle for optional official Result acquisition."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from ordifile.acquisition.base import (
    AcquiredResultArtifact,
    AcquisitionAvailability,
    AcquisitionEnvironment,
    AcquisitionRequest,
    AcquisitionSource,
)
from ordifile.acquisition.registry import ResultAcquisitionRegistry
from ordifile.adapters.base import ParseOptions
from ordifile.adapters.registry import AdapterRegistry
from ordifile.core.errors import OrdifileError
from ordifile.core.logical_source import merge_acquired_result
from ordifile.core.models import (
    DatasetBundle,
    Issue,
    ResultAcquisitionMode,
    ResultAcquisitionRecord,
    ResultAcquisitionStatus,
    Severity,
)
from ordifile.core.validation import validate_bundle, validate_bundle_structure
from ordifile.core.workbook_text import workbook_text_is_exact

MAX_ACQUIRED_RESULT_BYTES = 64 * 1024 * 1024
_COPY_BUFFER_BYTES = 1024 * 1024
_REASON_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")


@dataclass(frozen=True, slots=True)
class AcquisitionOutcome:
    """Direct bundle plus privacy-safe acquisition provenance and warnings."""

    bundle: DatasetBundle
    record: ResultAcquisitionRecord
    issues: tuple[Issue, ...] = ()


def _is_link_or_reparse(path: Path, value: os.stat_result) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(value.st_mode) or bool(attributes & reparse_flag)


def _hash_regular_file(path: Path, *, maximum_bytes: int) -> tuple[str, int]:
    try:
        path_stat = os.lstat(path)
        if _is_link_or_reparse(path, path_stat) or not stat.S_ISREG(path_stat.st_mode):
            raise OrdifileError(
                "AUTO_RESULT_ARTIFACT_INVALID",
                "The acquired Result must be one regular file.",
            )
        if not 0 < path_stat.st_size <= maximum_bytes:
            raise OrdifileError(
                "AUTO_RESULT_ARTIFACT_SIZE_INVALID",
                "The acquired Result violates its byte-size bound.",
            )
        digest = hashlib.sha256()
        total = 0
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not os.path.samestat(path_stat, before):
                raise OrdifileError(
                    "AUTO_RESULT_ARTIFACT_CHANGED",
                    "The acquired Result changed before validation.",
                )
            while chunk := stream.read(_COPY_BUFFER_BYTES):
                total += len(chunk)
                if total > maximum_bytes:
                    raise OrdifileError(
                        "AUTO_RESULT_ARTIFACT_SIZE_INVALID",
                        "The acquired Result violates its byte-size bound.",
                    )
                digest.update(chunk)
            after = os.fstat(stream.fileno())
    except OrdifileError:
        raise
    except OSError as error:
        raise OrdifileError(
            "AUTO_RESULT_ARTIFACT_UNREADABLE",
            "The acquired Result could not be read.",
        ) from error
    if (
        not os.path.samestat(before, after)
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or total != after.st_size
    ):
        raise OrdifileError(
            "AUTO_RESULT_ARTIFACT_CHANGED",
            "The acquired Result changed during validation.",
        )
    return digest.hexdigest(), total


def _stage_source(source: AcquisitionSource, workspace: Path) -> Path:
    target = workspace / f"source-{source.sha256[:16]}{source.path.suffix.casefold()}"
    try:
        source_stat = os.lstat(source.path)
        if _is_link_or_reparse(source.path, source_stat) or not stat.S_ISREG(source_stat.st_mode):
            raise OrdifileError(
                "AUTO_RESULT_SOURCE_INVALID",
                "The native source must be one regular file.",
            )
        digest = hashlib.sha256()
        total = 0
        with source.path.open("rb") as input_stream, target.open("xb") as output_stream:
            before = os.fstat(input_stream.fileno())
            if not os.path.samestat(source_stat, before):
                raise OrdifileError(
                    "AUTO_RESULT_SOURCE_CHANGED",
                    "The native source changed before staging.",
                )
            while chunk := input_stream.read(_COPY_BUFFER_BYTES):
                total += len(chunk)
                digest.update(chunk)
                output_stream.write(chunk)
            after = os.fstat(input_stream.fileno())
    except OrdifileError:
        raise
    except OSError as error:
        raise OrdifileError(
            "AUTO_RESULT_SOURCE_UNREADABLE",
            "The native source could not be staged.",
        ) from error
    if (
        not os.path.samestat(before, after)
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or total != source.size
        or digest.hexdigest() != source.sha256
    ):
        raise OrdifileError(
            "AUTO_RESULT_SOURCE_CHANGED",
            "The native source changed or did not match discovery provenance.",
        )
    return target


def _assert_source_unchanged(source: AcquisitionSource) -> None:
    try:
        identity = _hash_regular_file(
            source.path,
            maximum_bytes=max(source.size, 1),
        )
    except OrdifileError as error:
        raise OrdifileError(
            "AUTO_RESULT_SOURCE_CHANGED",
            "The native source changed during Result acquisition.",
        ) from error
    if identity != (source.sha256, source.size):
        raise OrdifileError(
            "AUTO_RESULT_SOURCE_CHANGED",
            "The native source changed during Result acquisition.",
        )


def _parse_acquired_result(
    artifact: AcquiredResultArtifact,
    provider_result_adapter_id: str,
    registry: AdapterRegistry,
) -> tuple[DatasetBundle, str]:
    if artifact.result_adapter_id != provider_result_adapter_id:
        raise OrdifileError(
            "AUTO_RESULT_ADAPTER_MISMATCH",
            "The provider returned an unexpected Result adapter identity.",
        )
    digest, size = _hash_regular_file(
        artifact.path,
        maximum_bytes=MAX_ACQUIRED_RESULT_BYTES,
    )
    if digest != artifact.sha256 or size != artifact.size:
        raise OrdifileError(
            "AUTO_RESULT_ARTIFACT_CHANGED",
            "The acquired Result does not match provider provenance.",
        )
    adapter = registry.get(provider_result_adapter_id)
    probe = adapter.probe(artifact.path)
    if not probe.matched or not probe.routable:
        raise OrdifileError(
            probe.failure_code or "AUTO_RESULT_PROFILE_INVALID",
            "The official Result did not match the required exact Result profile.",
        )
    parsed = adapter.parse(artifact.path, ParseOptions())
    structure_issues = validate_bundle_structure(parsed)
    validation_issues = () if structure_issues else validate_bundle(parsed)
    if structure_issues or any(issue.severity is Severity.ERROR for issue in validation_issues):
        raise OrdifileError(
            "AUTO_RESULT_CANONICAL_INVALID",
            "The acquired Result failed canonical validation.",
        )
    if parsed.sources[0].sha256 != digest:
        raise OrdifileError(
            "AUTO_RESULT_SOURCE_INTEGRITY_MISMATCH",
            "The Result adapter did not preserve acquired-artifact integrity provenance.",
        )
    return parsed, adapter.adapter_version


def _warning(code: str, source: AcquisitionSource) -> Issue:
    messages = {
        "AUTO_RESULT_UNAVAILABLE": (
            "Official peak Result acquisition is unavailable; direct scientific data was preserved."
        ),
        "AUTO_RESULT_FAILED": (
            "Official peak Result acquisition failed; direct scientific data was preserved."
        ),
    }
    return Issue(code, messages[code], Severity.WARNING, source.public_reference)


def _validate_environment(environment: object) -> AcquisitionEnvironment:
    if type(environment) is not AcquisitionEnvironment:
        raise OrdifileError(
            "AUTO_RESULT_ENVIRONMENT_INVALID",
            "The provider returned invalid environment metadata.",
        )
    if type(environment.availability) is not AcquisitionAvailability:
        raise OrdifileError(
            "AUTO_RESULT_ENVIRONMENT_INVALID",
            "The provider returned invalid environment metadata.",
        )
    text_fields = (
        (environment.product, 100),
        (environment.product_version, 64),
    )
    if any(
        value is not None
        and (
            type(value) is not str
            or not 1 <= len(value) <= maximum
            or not workbook_text_is_exact(value)
        )
        for value, maximum in text_fields
    ) or (
        environment.reason_code is not None
        and (
            type(environment.reason_code) is not str
            or _REASON_CODE.fullmatch(environment.reason_code) is None
        )
    ):
        raise OrdifileError(
            "AUTO_RESULT_ENVIRONMENT_INVALID",
            "The provider returned invalid environment metadata.",
        )
    return environment


def _record(
    mode: ResultAcquisitionMode,
    status: ResultAcquisitionStatus,
    *,
    provider_id: str | None = None,
    provider_version: str | None = None,
    product: str | None = None,
    product_version: str | None = None,
    result_adapter_id: str | None = None,
    result_adapter_version: str | None = None,
    result_sha256: str | None = None,
    peak_count: int = 0,
    issue_code: str | None = None,
) -> ResultAcquisitionRecord:
    return ResultAcquisitionRecord(
        mode,
        status,
        provider_id,
        provider_version,
        product,
        product_version,
        result_adapter_id,
        result_adapter_version,
        result_sha256,
        peak_count,
        issue_code,
    )


def acquire_official_result(
    source: AcquisitionSource,
    native: DatasetBundle,
    *,
    mode: ResultAcquisitionMode,
    providers: ResultAcquisitionRegistry,
    adapters: AdapterRegistry,
) -> AcquisitionOutcome:
    """Attempt an enhancement without turning vendor unavailability into source failure."""
    has_source_explicit_peaks = any(
        peak.data_origin != "ordifile_marker_derived" for peak in native.peaks
    )
    if mode is ResultAcquisitionMode.DIRECT_ONLY or has_source_explicit_peaks:
        return AcquisitionOutcome(
            native,
            _record(mode, ResultAcquisitionStatus.NOT_APPLICABLE),
        )
    provider = providers.for_adapter(source.adapter_id)
    if provider is None:
        return AcquisitionOutcome(
            native,
            _record(mode, ResultAcquisitionStatus.NOT_APPLICABLE),
        )
    descriptor = provider.descriptor
    try:
        environment = _validate_environment(provider.inspect_environment())
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except Exception:
        code = "AUTO_RESULT_FAILED"
        return AcquisitionOutcome(
            native,
            _record(
                mode,
                ResultAcquisitionStatus.FAILED,
                provider_id=provider.provider_id,
                provider_version=provider.provider_version,
                result_adapter_id=descriptor.result_adapter_id,
                issue_code=code,
            ),
            (_warning(code, source),),
        )
    if environment.availability is AcquisitionAvailability.UNAVAILABLE:
        code = "AUTO_RESULT_UNAVAILABLE"
        return AcquisitionOutcome(
            native,
            _record(
                mode,
                ResultAcquisitionStatus.UNAVAILABLE,
                provider_id=provider.provider_id,
                provider_version=provider.provider_version,
                product=environment.product,
                product_version=environment.product_version,
                result_adapter_id=descriptor.result_adapter_id,
                issue_code=environment.reason_code or code,
            ),
            (_warning(code, source),),
        )
    try:
        with tempfile.TemporaryDirectory(prefix="ordifile-result-") as temporary:
            workspace = Path(temporary)
            staged = _stage_source(source, workspace)
            provider_source = replace(source, path=staged)
            artifact = provider.acquire(
                AcquisitionRequest(provider_source, staged),
                workspace,
            )
            if artifact.path.parent != workspace:
                raise OrdifileError(
                    "AUTO_RESULT_ARTIFACT_OUTSIDE_WORKSPACE",
                    "The provider returned an artifact outside its private workspace.",
                )
            parsed, result_adapter_version = _parse_acquired_result(
                artifact,
                descriptor.result_adapter_id,
                adapters,
            )
            merged = merge_acquired_result(native, parsed)
            final_issues = validate_bundle(merged)
            if any(issue.severity is Severity.ERROR for issue in final_issues):
                raise OrdifileError(
                    "AUTO_RESULT_MERGE_INVALID",
                    "The logical native/Result merge failed canonical validation.",
                )
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except OrdifileError as error:
        if error.code == "AUTO_RESULT_SOURCE_CHANGED":
            raise
        code = "AUTO_RESULT_FAILED"
        return AcquisitionOutcome(
            native,
            _record(
                mode,
                ResultAcquisitionStatus.FAILED,
                provider_id=provider.provider_id,
                provider_version=provider.provider_version,
                product=environment.product,
                product_version=environment.product_version,
                result_adapter_id=descriptor.result_adapter_id,
                issue_code=error.code,
            ),
            (_warning(code, source),),
        )
    except Exception:
        code = "AUTO_RESULT_FAILED"
        return AcquisitionOutcome(
            native,
            _record(
                mode,
                ResultAcquisitionStatus.FAILED,
                provider_id=provider.provider_id,
                provider_version=provider.provider_version,
                product=environment.product,
                product_version=environment.product_version,
                result_adapter_id=descriptor.result_adapter_id,
                issue_code=code,
            ),
            (_warning(code, source),),
        )
    finally:
        _assert_source_unchanged(source)
    return AcquisitionOutcome(
        merged,
        _record(
            mode,
            ResultAcquisitionStatus.SUCCESS,
            provider_id=provider.provider_id,
            provider_version=provider.provider_version,
            product=environment.product,
            product_version=environment.product_version,
            result_adapter_id=descriptor.result_adapter_id,
            result_adapter_version=result_adapter_version,
            result_sha256=artifact.sha256,
            peak_count=len(parsed.peaks),
        ),
    )
