from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import ClassVar

import pytest

from ordifile.acquisition.base import (
    ACQUISITION_PROVIDER_API_VERSION,
    AcquiredResultArtifact,
    AcquisitionAvailability,
    AcquisitionEnvironment,
    AcquisitionRequest,
    AcquisitionSource,
    ResultAcquisitionProviderDescriptor,
)
from ordifile.acquisition.coordinator import acquire_official_result
from ordifile.acquisition.registry import ResultAcquisitionRegistry
from ordifile.adapters.base import ParseOptions
from ordifile.adapters.registry import create_registry
from ordifile.core.errors import OrdifileError
from ordifile.core.logical_source import merge_acquired_result
from ordifile.core.models import (
    DatasetBundle,
    InstrumentMetadata,
    MetadataEntry,
    ResultAcquisitionMode,
    ResultAcquisitionStatus,
    SampleRecord,
    SeriesKind,
    SignalSeries,
    SourceFile,
)

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures" / "synthetic"))
from generate_youngin_yl_clarity_result_csv import (  # noqa: E402
    synthetic_result_csv_bytes,
)


def _native_bundle(path: Path) -> tuple[DatasetBundle, str]:
    data = b"independently invented native PRM bytes"
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    public_reference = f"source-{digest}"
    source = SourceFile(
        path,
        path.name,
        path.name,
        len(data),
        digest,
        None,
        0,
        "youngin_yl_clarity_prm_raw",
        None,
        public_reference,
    )
    sample = SampleRecord(
        "PRM_SYNTHETIC",
        source,
        instrument=InstrumentMetadata(None, "YoungIn"),
        channels=("channel-001",),
        detectors=("TCD",),
    )
    signal = SignalSeries(
        sample.sample_id,
        public_reference,
        "channel-001",
        "TCD",
        (0.0, 1.0 / 600.0),
        (1.0, 2.0),
        "retention_time",
        "min",
        "detector_response",
        "mV",
        SeriesKind.SCIENTIFIC_SIGNAL,
    )
    metadata = MetadataEntry(
        sample.sample_id,
        public_reference,
        "adapter:youngin_yl_clarity_prm_raw",
        "peak_table_status",
        "unsupported",
    )
    return DatasetBundle((source,), (sample,), (signal,), metadata=(metadata,)), digest


class FakeProvider:
    api_version: ClassVar[str] = ACQUISITION_PROVIDER_API_VERSION
    provider_id: ClassVar[str] = "fake_youngin_result"
    provider_version: ClassVar[str] = "1.0"
    descriptor: ClassVar[ResultAcquisitionProviderDescriptor] = ResultAcquisitionProviderDescriptor(
        provider_id,
        provider_version,
        "Invented official Result provider",
        ("youngin_yl_clarity_prm_raw",),
        "youngin_yl_clarity_result_csv",
    )

    def __init__(self, output: bytes | None, *, available: bool = True) -> None:
        self.output = output
        self.available = available
        self.calls = 0
        self.workspace: Path | None = None
        self.staged_bytes: bytes | None = None

    def inspect_environment(self) -> AcquisitionEnvironment:
        if not self.available:
            return AcquisitionEnvironment(
                AcquisitionAvailability.UNAVAILABLE,
                "Invented YL-Clarity",
                "9.0.1.19",
                "FAKE_VENDOR_UNAVAILABLE",
            )
        return AcquisitionEnvironment(
            AcquisitionAvailability.AVAILABLE,
            "Invented YL-Clarity",
            "9.0.1.19",
        )

    def acquire(self, request: AcquisitionRequest, workspace: Path) -> AcquiredResultArtifact:
        self.calls += 1
        self.workspace = workspace
        assert request.source.path == request.staged_source
        self.staged_bytes = request.staged_source.read_bytes()
        if self.output is None:
            raise OrdifileError("FAKE_EXPORT_FAILED", "Invented export failure.")
        output = workspace / "private-intermediate.csv"
        output.write_bytes(self.output)
        return AcquiredResultArtifact(
            output,
            self.descriptor.result_adapter_id,
            hashlib.sha256(self.output).hexdigest(),
            len(self.output),
        )


def _providers(provider: FakeProvider) -> ResultAcquisitionRegistry:
    registry = ResultAcquisitionRegistry()
    registry.register(provider)
    return registry


def _source(path: Path, digest: str) -> AcquisitionSource:
    return AcquisitionSource(
        path,
        f"source-{digest}",
        digest,
        path.stat().st_size,
        "youngin_yl_clarity_prm_raw",
        "0.3.0",
    )


def test_registry_rejects_provider_id_and_native_ownership_collisions() -> None:
    registry = ResultAcquisitionRegistry()
    first = FakeProvider(synthetic_result_csv_bytes())
    registry.register(first)
    assert registry.for_adapter("youngin_yl_clarity_prm_raw") is first
    assert registry.signature() == (
        (
            "fake_youngin_result",
            "1.0",
            ("youngin_yl_clarity_prm_raw",),
            "youngin_yl_clarity_result_csv",
        ),
    )
    with pytest.raises(OrdifileError, match="already registered") as duplicate:
        registry.register(FakeProvider(synthetic_result_csv_bytes()))
    assert duplicate.value.code == "ACQUISITION_PROVIDER_ID_COLLISION"


def test_coordinator_merges_exact_result_into_one_native_logical_source(tmp_path: Path) -> None:
    native, digest = _native_bundle(tmp_path / "private-source.prm")
    original = native.sources[0].path.read_bytes()
    provider = FakeProvider(synthetic_result_csv_bytes())

    outcome = acquire_official_result(
        _source(native.sources[0].path, digest),
        native,
        mode=ResultAcquisitionMode.AUTO,
        providers=_providers(provider),
        adapters=create_registry(include_external=False),
    )

    assert outcome.record.status is ResultAcquisitionStatus.SUCCESS
    assert outcome.record.peak_count == 2
    assert outcome.record.result_adapter_id == "youngin_yl_clarity_result_csv"
    assert len(outcome.bundle.sources) == len(outcome.bundle.samples) == 1
    assert outcome.bundle.sources == native.sources
    assert outcome.bundle.samples == native.samples
    assert outcome.bundle.signals == native.signals
    assert len(outcome.bundle.peaks) == 2
    assert {peak.sample_id for peak in outcome.bundle.peaks} == {"PRM_SYNTHETIC"}
    assert {peak.source_file for peak in outcome.bundle.peaks} == {
        native.sources[0].public_reference
    }
    assert {peak.channel for peak in outcome.bundle.peaks} == {"Signal 1: TCD"}
    assert outcome.bundle.metadata[0].key == "peak_table_status"
    assert provider.calls == 1
    assert provider.staged_bytes == original
    assert provider.workspace is not None and not provider.workspace.exists()
    assert native.sources[0].path.read_bytes() == original
    assert "private-intermediate" not in repr(outcome)


@pytest.mark.parametrize(
    ("provider", "status", "issue_code"),
    (
        (
            FakeProvider(synthetic_result_csv_bytes(), available=False),
            ResultAcquisitionStatus.UNAVAILABLE,
            "FAKE_VENDOR_UNAVAILABLE",
        ),
        (
            FakeProvider(None),
            ResultAcquisitionStatus.FAILED,
            "FAKE_EXPORT_FAILED",
        ),
        (
            FakeProvider(b"not an exact Result export"),
            ResultAcquisitionStatus.FAILED,
            "AUTO_RESULT_PROFILE_INVALID",
        ),
    ),
)
def test_unavailable_or_failed_acquisition_preserves_direct_signals(
    tmp_path: Path,
    provider: FakeProvider,
    status: ResultAcquisitionStatus,
    issue_code: str,
) -> None:
    native, digest = _native_bundle(tmp_path / "private-source.prm")

    outcome = acquire_official_result(
        _source(native.sources[0].path, digest),
        native,
        mode=ResultAcquisitionMode.AUTO,
        providers=_providers(provider),
        adapters=create_registry(include_external=False),
    )

    assert outcome.bundle == native
    assert outcome.record.status is status
    assert outcome.record.issue_code == issue_code
    assert len(outcome.issues) == 1
    assert outcome.issues[0].severity.value == "warning"
    assert len(outcome.bundle.signals) == 1
    assert outcome.bundle.peaks == ()


def test_direct_only_mode_never_inspects_or_invokes_provider(tmp_path: Path) -> None:
    native, digest = _native_bundle(tmp_path / "private-source.prm")
    provider = FakeProvider(synthetic_result_csv_bytes())

    outcome = acquire_official_result(
        _source(native.sources[0].path, digest),
        native,
        mode=ResultAcquisitionMode.DIRECT_ONLY,
        providers=_providers(provider),
        adapters=create_registry(include_external=False),
    )

    assert outcome.bundle == native
    assert outcome.record.status is ResultAcquisitionStatus.NOT_APPLICABLE
    assert provider.calls == 0


def test_unexpected_provider_exception_isolated_to_direct_fallback(tmp_path: Path) -> None:
    native, digest = _native_bundle(tmp_path / "private-source.prm")
    provider = FakeProvider(synthetic_result_csv_bytes())

    def raise_unexpected(
        request: AcquisitionRequest,
        workspace: Path,
    ) -> AcquiredResultArtifact:
        del request, workspace
        raise ValueError("private provider detail")

    provider.acquire = raise_unexpected  # type: ignore[method-assign]
    outcome = acquire_official_result(
        _source(native.sources[0].path, digest),
        native,
        mode=ResultAcquisitionMode.AUTO,
        providers=_providers(provider),
        adapters=create_registry(include_external=False),
    )

    assert outcome.bundle == native
    assert outcome.record.status is ResultAcquisitionStatus.FAILED
    assert outcome.record.issue_code == "AUTO_RESULT_FAILED"
    assert "private provider detail" not in repr(outcome)


def test_invalid_provider_environment_isolated_to_direct_fallback(tmp_path: Path) -> None:
    native, digest = _native_bundle(tmp_path / "private-source.prm")
    provider = FakeProvider(synthetic_result_csv_bytes())

    def invalid_environment() -> AcquisitionEnvironment:
        return None  # type: ignore[return-value]

    provider.inspect_environment = invalid_environment  # type: ignore[method-assign]
    outcome = acquire_official_result(
        _source(native.sources[0].path, digest),
        native,
        mode=ResultAcquisitionMode.AUTO,
        providers=_providers(provider),
        adapters=create_registry(include_external=False),
    )

    assert outcome.bundle == native
    assert outcome.record.status is ResultAcquisitionStatus.FAILED
    assert outcome.record.issue_code == "AUTO_RESULT_FAILED"
    assert provider.calls == 0


def test_source_mutation_is_hard_failure_even_when_provider_fails(tmp_path: Path) -> None:
    native, digest = _native_bundle(tmp_path / "private-source.prm")
    original = native.sources[0].path
    provider = FakeProvider(synthetic_result_csv_bytes())

    def mutate_and_fail(
        request: AcquisitionRequest,
        workspace: Path,
    ) -> AcquiredResultArtifact:
        del request, workspace
        original.write_bytes(b"mutated owner source")
        raise OrdifileError("FAKE_EXPORT_FAILED", "Invented export failure.")

    provider.acquire = mutate_and_fail  # type: ignore[method-assign]
    with pytest.raises(OrdifileError) as changed:
        acquire_official_result(
            _source(original, digest),
            native,
            mode=ResultAcquisitionMode.AUTO,
            providers=_providers(provider),
            adapters=create_registry(include_external=False),
        )

    assert changed.value.code == "AUTO_RESULT_SOURCE_CHANGED"


def test_logical_merge_rejects_direct_peaks_and_vendor_mismatch(tmp_path: Path) -> None:
    native, _digest = _native_bundle(tmp_path / "private-source.prm")
    result_path = tmp_path / "result.csv"
    result_path.write_bytes(synthetic_result_csv_bytes())
    result_adapter = create_registry(include_external=False).get("youngin_yl_clarity_result_csv")
    acquired = result_adapter.parse(result_path, ParseOptions())
    with_peaks = DatasetBundle(
        native.sources,
        native.samples,
        native.signals,
        acquired.peaks,
        native.metadata,
    )
    with pytest.raises(OrdifileError) as direct:
        merge_acquired_result(with_peaks, acquired)
    assert direct.value.code == "LOGICAL_SOURCE_DIRECT_RESULT_PRESENT"
    mismatched_sample = acquired.samples[0]
    mismatched = DatasetBundle(
        acquired.sources,
        (
            type(mismatched_sample)(
                mismatched_sample.sample_id,
                mismatched_sample.source,
                instrument=InstrumentMetadata(None, "Different Vendor"),
            ),
        ),
        peaks=acquired.peaks,
        metadata=acquired.metadata,
    )
    with pytest.raises(OrdifileError) as vendor:
        merge_acquired_result(native, mismatched)
    assert vendor.value.code == "LOGICAL_SOURCE_VENDOR_MISMATCH"
