from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from labconvert.adapters.base import AdapterDescriptor, DetectionResult, ParseOptions
from labconvert.adapters.registry import AdapterRegistry, create_registry, load_external_adapters
from labconvert.api import get_format_report, list_formats
from labconvert.core.errors import LabConvertError
from labconvert.core.models import DatasetBundle


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


def test_builtin_descriptors_are_verified_and_stable() -> None:
    descriptors = create_registry(include_external=False).descriptors()
    assert {item.adapter_id for item in descriptors} == {
        "generic_csv",
        "generic_semicolon",
        "generic_tsv",
        "generic_xlsx",
    }
    assert all(item.tested_fixture for item in descriptors)


def test_collision_and_api_incompatibility_are_rejected() -> None:
    registry = AdapterRegistry()
    registry.register(ExternalAdapter())
    with pytest.raises(LabConvertError, match="already registered"):
        registry.register(ExternalAdapter())
    ExternalAdapter.api_version = "wrong"
    try:
        with pytest.raises(LabConvertError, match="API version"):
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

    with pytest.raises(LabConvertError) as caught:
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
    assert registry.load_errors == ("unsafe~u00005F;x000D_name: LabConvertError",)


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
