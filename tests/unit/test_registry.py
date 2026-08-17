from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from ordifile.adapters.base import (
    AdapterDescriptor,
    DetectionResult,
    ParseOptions,
    SourceIdentityPolicy,
    SupportStatus,
)
from ordifile.adapters.registry import (
    ENTRY_POINT_GROUP,
    AdapterRegistry,
    create_registry,
    load_external_adapters,
)
from ordifile.api import get_format_report, list_formats
from ordifile.core.errors import OrdifileError
from ordifile.core.models import DatasetBundle, SeriesKind


class ExternalAdapter:
    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "external_test"
    adapter_version: ClassVar[str] = "1"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id, "1", "External", (".ext",), False, False, False, True
    )

    def probe(self, path: Path) -> DetectionResult:
        return DetectionResult(False, 0, path.name)

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        raise NotImplementedError


class FakeEntryPoint:
    def __init__(self, name: str, loaded: Any) -> None:
        self.name = name
        self._loaded = loaded

    def load(self) -> Any:
        if isinstance(self._loaded, Exception):
            raise self._loaded
        return self._loaded


def test_builtin_descriptors_have_explicit_evidence_status_and_stable_ids() -> None:
    assert ENTRY_POINT_GROUP == "ordifile.adapters"
    descriptors = create_registry(include_external=False).descriptors()
    assert {item.adapter_id for item in descriptors} == {
        "agilent_chemstation_ch_v181",
        "generic_csv",
        "generic_semicolon",
        "generic_tsv",
        "generic_xlsx",
        "shimadzu_gcsolution_gcd",
        "shimadzu_gcmssolution_qgd",
        "youngin_yl_clarity_prm_raw",
    }
    assert all(item.tested_fixture for item in descriptors)
    statuses = {item.adapter_id: item.support_status for item in descriptors}
    assert statuses["agilent_chemstation_ch_v181"] is SupportStatus.EXPERIMENTAL
    assert statuses["shimadzu_gcsolution_gcd"] is SupportStatus.EXPERIMENTAL
    assert statuses["shimadzu_gcmssolution_qgd"] is SupportStatus.EXPERIMENTAL
    assert statuses["youngin_yl_clarity_prm_raw"] is SupportStatus.EXPERIMENTAL
    assert all(
        status is SupportStatus.VERIFIED
        for adapter_id, status in statuses.items()
        if adapter_id.startswith("generic_")
    )
    series_kinds = {item.adapter_id: item.series_kinds for item in descriptors}
    assert series_kinds["agilent_chemstation_ch_v181"] == (SeriesKind.DECODED_RECORDS,)
    assert series_kinds["shimadzu_gcsolution_gcd"] == (SeriesKind.SCIENTIFIC_SIGNAL,)
    assert series_kinds["shimadzu_gcmssolution_qgd"] == (SeriesKind.SCIENTIFIC_SIGNAL,)
    assert series_kinds["youngin_yl_clarity_prm_raw"] == (SeriesKind.DECODED_RECORDS,)
    assert all(
        kinds == (SeriesKind.SCIENTIFIC_SIGNAL,)
        for adapter_id, kinds in series_kinds.items()
        if adapter_id.startswith("generic_")
    )
    identity_policies = {item.adapter_id: item.source_identity_policy for item in descriptors}
    assert identity_policies["youngin_yl_clarity_prm_raw"] is SourceIdentityPolicy.SHA256_ALIAS
    assert all(
        policy is SourceIdentityPolicy.RELATIVE_PATH
        for adapter_id, policy in identity_policies.items()
        if adapter_id != "youngin_yl_clarity_prm_raw"
    )


def test_collision_and_api_incompatibility_are_rejected() -> None:
    registry = AdapterRegistry()
    registry.register(ExternalAdapter())
    with pytest.raises(OrdifileError, match="already registered"):
        registry.register(ExternalAdapter())
    ExternalAdapter.api_version = "wrong"
    try:
        with pytest.raises(OrdifileError, match="API version"):
            AdapterRegistry().register(ExternalAdapter())
    finally:
        ExternalAdapter.api_version = "1"


def test_external_entry_point_loads_and_failure_is_recorded() -> None:
    registry = AdapterRegistry()
    points = [FakeEntryPoint("good", ExternalAdapter), FakeEntryPoint("bad", RuntimeError("no"))]
    load_external_adapters(registry, entry_points=points)  # type: ignore[arg-type]
    assert registry.get("external_test").adapter_id == "external_test"
    assert "bad: RuntimeError" in registry.load_errors
    assert "no" not in registry.load_errors[0]


@pytest.mark.parametrize(
    ("adapter_id", "adapter_version", "display_name", "extensions", "expected_code"),
    (
        ("bad\x01", "1", "External", (".ext",), "ADAPTER_INVALID"),
        ("external_test", "1\x01", "External", (".ext",), "ADAPTER_VERSION_INVALID"),
        (
            "external_test",
            "1",
            "External_x000D_",
            (".ext",),
            "ADAPTER_DESCRIPTOR_INVALID",
        ),
        (
            "external_test",
            "1",
            "External",
            (".ext", ".bad\x01"),
            "ADAPTER_DESCRIPTOR_INVALID",
        ),
    ),
)
def test_registry_rejects_unsafe_adapter_descriptor_fields(
    adapter_id: str,
    adapter_version: str,
    display_name: str,
    extensions: tuple[str, ...],
    expected_code: str,
) -> None:
    class InvalidAdapter(ExternalAdapter):
        pass

    InvalidAdapter.adapter_id = adapter_id
    InvalidAdapter.adapter_version = adapter_version
    InvalidAdapter.descriptor = AdapterDescriptor(
        adapter_id,
        adapter_version,
        display_name,
        extensions,
        False,
        False,
        False,
        True,
    )

    with pytest.raises(OrdifileError) as caught:
        AdapterRegistry().register(InvalidAdapter())
    assert caught.value.code == expected_code


def test_invalid_external_descriptor_load_is_isolated_from_builtins() -> None:
    class InvalidAdapter(ExternalAdapter):
        adapter_id = "bad\x01"
        descriptor = AdapterDescriptor(adapter_id, "1", "Bad", (".bad",), False, False, False, True)

    registry = create_registry(include_external=False)
    load_external_adapters(
        registry,
        entry_points=[FakeEntryPoint("unsafe_x000D_name", InvalidAdapter)],  # type: ignore[list-item]
    )

    assert registry.get("generic_csv").adapter_id == "generic_csv"
    assert registry.load_errors == ("unsafe~u00005F;x000D_name: OrdifileError",)


def test_registry_rejects_invalid_support_status() -> None:
    class InvalidStatusAdapter(ExternalAdapter):
        descriptor = AdapterDescriptor(
            "external_test", "1", "External", (".ext",), False, False, False, True
        )

    object.__setattr__(InvalidStatusAdapter.descriptor, "support_status", "verified")
    with pytest.raises(OrdifileError) as caught:
        AdapterRegistry().register(InvalidStatusAdapter())
    assert caught.value.code == "ADAPTER_DESCRIPTOR_INVALID"


def test_registry_rejects_non_enum_source_identity_policy() -> None:
    class InvalidPolicyAdapter(ExternalAdapter):
        adapter_id = "invalid_policy"
        adapter_version = "1"
        descriptor = AdapterDescriptor(
            adapter_id,
            adapter_version,
            "Invalid policy",
            (".invalid-policy",),
            False,
            False,
            False,
            True,
        )

    object.__setattr__(
        InvalidPolicyAdapter.descriptor,
        "source_identity_policy",
        "sha256_alias",
    )
    with pytest.raises(OrdifileError) as caught:
        AdapterRegistry().register(InvalidPolicyAdapter())
    assert caught.value.code == "ADAPTER_DESCRIPTOR_INVALID"


def test_registry_rejects_invalid_or_duplicate_series_kind_declarations() -> None:
    for value in (
        "scientific_signal",
        (),
        ("scientific_signal",),
        (SeriesKind.SCIENTIFIC_SIGNAL, SeriesKind.SCIENTIFIC_SIGNAL),
    ):
        descriptor = AdapterDescriptor(
            "external_test", "1", "External", (".ext",), False, False, True, True
        )
        object.__setattr__(descriptor, "series_kinds", value)

        class InvalidSeriesAdapter(ExternalAdapter):
            pass

        InvalidSeriesAdapter.descriptor = descriptor
        with pytest.raises(OrdifileError) as caught:
            AdapterRegistry().register(InvalidSeriesAdapter())
        assert caught.value.code == "ADAPTER_DESCRIPTOR_INVALID"


def test_public_format_list_excludes_unverified_installed_descriptor() -> None:
    class UnverifiedAdapter(ExternalAdapter):
        adapter_id = "unverified_test"
        descriptor = AdapterDescriptor(
            adapter_id, "1", "Unverified", (".unverified",), False, False, False, False
        )

    registry = AdapterRegistry()
    registry.register(ExternalAdapter())
    registry.register(UnverifiedAdapter())

    assert {item.adapter_id for item in list_formats(registry=registry)} == {"external_test"}
    assert {item.adapter_id for item in get_format_report(registry=registry).descriptors} == {
        "external_test",
        "unverified_test",
    }
