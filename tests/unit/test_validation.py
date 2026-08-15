from __future__ import annotations

from datetime import datetime
from pathlib import Path

from labconvert.core.models import (
    DatasetBundle,
    MetadataEntry,
    PeakRecord,
    SampleRecord,
    SignalSeries,
    SourceFile,
)
from labconvert.core.validation import validate_bundle


def _source() -> SourceFile:
    return SourceFile(Path("a.csv"), "a.csv", "a.csv", 1, "a" * 64, None, 0)


def test_requires_exactly_one_source_and_sample() -> None:
    issues = validate_bundle(DatasetBundle((), ()))
    assert {item.code for item in issues} == {"SOURCE_COUNT_INVALID", "SAMPLE_COUNT_INVALID"}


def test_signal_length_and_sample_reference_are_validated() -> None:
    source = _source()
    sample = SampleRecord("sample", source)
    signal = SignalSeries("other", source.name, None, None, (1.0, 2.0), (3.0,))
    issues = validate_bundle(DatasetBundle((source,), (sample,), (signal,)))
    assert {item.code for item in issues} == {"SIGNAL_SAMPLE_MISMATCH", "SIGNAL_LENGTH_MISMATCH"}


def test_valid_bundle_has_no_issues() -> None:
    source = _source()
    sample = SampleRecord("sample", source)
    assert validate_bundle(DatasetBundle((source,), (sample,))) == ()


def test_reliable_acquisition_requires_aware_timestamp_and_metadata_sample_matches() -> None:
    source = _source()
    sample = SampleRecord(
        "sample",
        source,
        acquired_at=datetime(2026, 1, 1),
        acquired_at_reliable=True,
    )
    metadata = MetadataEntry("other", source.name, "test", "key", "value")
    issues = validate_bundle(DatasetBundle((source,), (sample,), metadata=(metadata,)))
    assert {item.code for item in issues} == {
        "ACQUIRED_AT_RELIABILITY_INVALID",
        "METADATA_SAMPLE_MISMATCH",
    }


def test_metadata_source_rejects_machine_paths_and_control_characters() -> None:
    source = _source()
    sample = SampleRecord("sample", source)
    for unsafe_source in (
        "/private/adapter/secret.dat",
        "C:\\Users\\person\\secret.dat",
        "\\\\server\\private share\\secret.dat",
        "file:///Users/example/My%20Project/secret.dat",
        "file://C:/Users/example/Secret%20Project/secret.dat",
        "https://example.test/instrument/source",
        "table:row:2\nsecret",
    ):
        metadata = MetadataEntry(
            "sample",
            source.name,
            "test",
            "key",
            "value",
            source=unsafe_source,
        )
        issues = validate_bundle(DatasetBundle((source,), (sample,), metadata=(metadata,)))
        assert {item.code for item in issues} == {"METADATA_SOURCE_UNSAFE"}


def test_metadata_source_accepts_relative_logical_locator() -> None:
    source = _source()
    sample = SampleRecord("sample", source)
    metadata = MetadataEntry(
        "sample",
        source.name,
        "test",
        "key",
        "value",
        source="table:row:2:column:3",
    )
    assert validate_bundle(DatasetBundle((source,), (sample,), metadata=(metadata,))) == ()


def test_metadata_source_accepts_sheet_cell_logical_locator() -> None:
    source = _source()
    sample = SampleRecord("sample", source)
    metadata = MetadataEntry(
        "sample",
        source.name,
        "test",
        "key",
        "value",
        source="sheet:1:cell:D2",
    )
    assert validate_bundle(DatasetBundle((source,), (sample,), metadata=(metadata,))) == ()


def test_external_oversized_integers_are_errors_across_canonical_records() -> None:
    source = _source()
    oversized = 10**1_000
    sample = SampleRecord("sample", source, sequence=oversized, runtime=oversized)
    peak = PeakRecord(
        "sample",
        source.name,
        peak_number=oversized,
        retention_time=oversized,
        area=oversized,
        height=oversized,
    )
    signal = SignalSeries(
        "sample",
        source.name,
        None,
        None,
        (oversized,),
        (oversized,),
    )
    metadata = MetadataEntry("sample", source.name, "test", "key", oversized)

    issues = validate_bundle(DatasetBundle((source,), (sample,), (signal,), (peak,), (metadata,)))

    integer_issues = [item for item in issues if item.code == "INTEGER_LIMIT_EXCEEDED"]
    assert len(integer_issues) == 9
    assert all(item.severity.value == "error" for item in integer_issues)


def test_metadata_value_rejects_arbitrary_objects_without_stringifying_them() -> None:
    class ExplodingText:
        def __str__(self) -> str:
            raise AssertionError("validation must not stringify arbitrary metadata")

    source = _source()
    sample = SampleRecord("sample", source)
    metadata = MetadataEntry("sample", source.name, "test", "key", ExplodingText())
    issues = validate_bundle(DatasetBundle((source,), (sample,), metadata=(metadata,)))
    assert {item.code for item in issues} == {"METADATA_VALUE_TYPE_INVALID"}


def test_workbook_bound_canonical_text_is_rejected_per_bundle() -> None:
    source = _source()
    sample = SampleRecord("bad_x000D_", source)
    metadata = MetadataEntry("bad_x000D_", source.name, "test", "key", "bad\x01")
    issues = validate_bundle(DatasetBundle((source,), (sample,), metadata=(metadata,)))
    assert {item.code for item in issues} == {"WORKBOOK_TEXT_UNREPRESENTABLE"}
