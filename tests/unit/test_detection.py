from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from ordifile.adapters.base import AdapterDescriptor, DetectionResult, ParseOptions
from ordifile.adapters.registry import AdapterRegistry, create_registry
from ordifile.core.detection import detect_adapter
from ordifile.core.errors import AdapterAmbiguityError, DetectionError
from ordifile.core.models import DatasetBundle


class ClaimingAdapter:
    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str]
    adapter_version: ClassVar[str] = "1"
    descriptor: ClassVar[AdapterDescriptor]

    def __init__(self, adapter_id: str, confidence: float) -> None:
        object.__setattr__(self, "adapter_id", adapter_id)
        object.__setattr__(
            self,
            "descriptor",
            AdapterDescriptor(adapter_id, "1", adapter_id, (".dat",), False, False, False, True),
        )
        self.confidence = confidence

    def probe(self, path: Path) -> DetectionResult:
        return DetectionResult(True, self.confidence, f"claimed {path.name}")

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        raise NotImplementedError


def test_content_detection_ignores_misleading_extension(tmp_path: Path) -> None:
    path = tmp_path / "table.bin"
    path.write_text("sample_id\tarea\na\t1\n", encoding="utf-8")
    outcome = detect_adapter(path, create_registry(include_external=False))
    assert outcome.adapter.adapter_id == "generic_tsv"


def test_unsupported_empty_and_binary_inputs_are_structured(tmp_path: Path) -> None:
    registry = create_registry(include_external=False)
    for name, content in (("empty.csv", b""), ("binary.csv", b"\x00\x01")):
        path = tmp_path / name
        path.write_bytes(content)
        with pytest.raises(DetectionError, match="No adapter matched"):
            detect_adapter(path, registry)


def test_similarly_confident_claims_are_ambiguous(tmp_path: Path) -> None:
    path = tmp_path / "data.dat"
    path.write_bytes(b"data")
    registry = AdapterRegistry()
    first = ClaimingAdapter("first", 0.90)
    registry.register(first)
    second = ClaimingAdapter("second", 0.88)
    registry.register(second)
    with pytest.raises(AdapterAmbiguityError) as caught:
        detect_adapter(path, registry)
    assert caught.value.code == "FORMAT_AMBIGUOUS"
    assert "first (confidence=0.90; reason=claimed data.dat)" in caught.value.message
    assert "second (confidence=0.88; reason=claimed data.dat)" in caught.value.message
    assert "confidence=0.900000" in caught.value.details["claim_1"]
    assert "reason=claimed data.dat" in caught.value.details["claim_1"]


def test_forced_adapter_records_probe_failure(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("not,a,schema\n1,2,3\n", encoding="utf-8")
    with pytest.raises(DetectionError) as caught:
        detect_adapter(path, create_registry(include_external=False), forced_adapter="generic_csv")
    assert "generic_csv" in caught.value.message
