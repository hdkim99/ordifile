from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from labconvert.core.models import (
    DatasetBundle,
    FileResult,
    FileStatus,
    SampleRecord,
    SortMode,
    SourceFile,
)
from labconvert.core.sorting import sort_file_results


def _result(
    name: str,
    order: int,
    *,
    acquired: datetime | None = None,
    reliable: bool = False,
    sequence: int | None = None,
) -> FileResult:
    source = SourceFile(Path(name), name, name, 1, "a" * 64, None, order)
    sample = SampleRecord(name.removesuffix(".csv"), source, acquired, reliable, sequence)
    bundle = DatasetBundle((source,), (sample,))
    return FileResult(source, FileStatus.SUCCESS, "test", "1", bundle)


def _names(items: tuple[FileResult, ...]) -> list[str]:
    return [item.source.name for item in items]


def _outcome(name: str, order: int, status: FileStatus) -> FileResult:
    source = SourceFile(Path(name), name, name, 1, "a" * 64, None, order)
    return FileResult(source, status)


def test_auto_prefers_complete_reliable_acquisition_time_with_ties() -> None:
    same = datetime(2026, 1, 1, tzinfo=UTC)
    files = (
        _result("sample_10.csv", 0, acquired=same, reliable=True),
        _result("sample_2.csv", 1, acquired=same, reliable=True),
        _result("sample_1.csv", 2, acquired=datetime(2025, 1, 1, tzinfo=UTC), reliable=True),
    )
    ordered, decision = sort_file_results(files)
    assert decision.effective is SortMode.ACQUIRED_AT
    assert _names(ordered) == ["sample_1.csv", "sample_2.csv", "sample_10.csv"]


def test_auto_uses_sequence_then_filename_fallback() -> None:
    sequenced = (_result("b.csv", 0, sequence=2), _result("a.csv", 1, sequence=1))
    ordered, decision = sort_file_results(sequenced)
    assert decision.effective is SortMode.SEQUENCE
    assert _names(ordered) == ["a.csv", "b.csv"]

    natural = (
        _result("sample_10.csv", 0),
        _result("sample_1.csv", 1),
        _result("sample_2.csv", 2),
    )
    ordered, decision = sort_file_results(natural)
    assert decision.effective is SortMode.FILENAME
    assert "fallback" in decision.reason
    assert _names(ordered) == ["sample_1.csv", "sample_2.csv", "sample_10.csv"]


def test_requested_partial_sort_keeps_mode_and_records_fallback() -> None:
    files = (
        _result("missing.csv", 0),
        _result("available.csv", 1, sequence=3),
    )
    ordered, decision = sort_file_results(files, SortMode.SEQUENCE)
    assert decision.effective is SortMode.SEQUENCE
    assert _names(ordered) == ["available.csv", "missing.csv"]
    assert ordered[1].sort_key == "fallback:missing.csv"


def test_input_order_is_preserved() -> None:
    files = (_result("z.csv", 0), _result("a.csv", 1))
    ordered, decision = sort_file_results(files, "input_order")
    assert decision.effective is SortMode.INPUT_ORDER
    assert _names(ordered) == ["z.csv", "a.csv"]


def test_filename_and_input_order_include_every_file_status() -> None:
    files = (
        _result("sample_10.csv", 0),
        _outcome("sample_2.csv", 1, FileStatus.FAILED),
        _outcome("sample_1.csv", 2, FileStatus.DUPLICATE),
        _outcome("sample_3.csv", 3, FileStatus.SKIPPED),
    )
    by_filename, _ = sort_file_results(files, SortMode.FILENAME)
    assert _names(by_filename) == [
        "sample_1.csv",
        "sample_2.csv",
        "sample_3.csv",
        "sample_10.csv",
    ]
    assert [item.sort_key for item in by_filename] == _names(by_filename)

    by_input, _ = sort_file_results(tuple(reversed(files)), SortMode.INPUT_ORDER)
    assert _names(by_input) == [
        "sample_10.csv",
        "sample_2.csv",
        "sample_1.csv",
        "sample_3.csv",
    ]
    assert [item.sort_key for item in by_input] == ["0", "1", "2", "3"]


def test_requested_scientific_sort_places_all_unavailable_outcomes_in_filename_fallback() -> None:
    files = (
        _outcome("missing_10.csv", 0, FileStatus.FAILED),
        _result("available.csv", 1, sequence=2),
        _outcome("missing_2.csv", 2, FileStatus.SKIPPED),
    )

    ordered, decision = sort_file_results(files, SortMode.SEQUENCE)

    assert decision.effective is SortMode.SEQUENCE
    assert "missing values" in decision.reason
    assert _names(ordered) == ["available.csv", "missing_2.csv", "missing_10.csv"]
    assert [item.sort_key for item in ordered] == [
        "2",
        "fallback:missing_2.csv",
        "fallback:missing_10.csv",
    ]

    acquired_files = (
        _outcome("missing_10.csv", 0, FileStatus.DUPLICATE),
        _result(
            "available.csv",
            1,
            acquired=datetime(2026, 1, 1, tzinfo=UTC),
            reliable=True,
        ),
        _outcome("missing_2.csv", 2, FileStatus.FAILED),
    )
    acquired_order, acquired_decision = sort_file_results(acquired_files, SortMode.ACQUIRED_AT)
    assert acquired_decision.effective is SortMode.ACQUIRED_AT
    assert _names(acquired_order) == ["available.csv", "missing_2.csv", "missing_10.csv"]
    assert [item.sort_key for item in acquired_order[1:]] == [
        "fallback:missing_2.csv",
        "fallback:missing_10.csv",
    ]


def test_all_failed_auto_uses_actual_natural_filename_order() -> None:
    files = (
        _outcome("sample_10.csv", 0, FileStatus.FAILED),
        _outcome("sample_1.csv", 1, FileStatus.FAILED),
        _outcome("sample_2.csv", 2, FileStatus.FAILED),
    )

    ordered, decision = sort_file_results(files)

    assert decision.effective is SortMode.FILENAME
    assert _names(ordered) == ["sample_1.csv", "sample_2.csv", "sample_10.csv"]
    assert [item.sort_key for item in ordered] == _names(ordered)


def test_unreliable_acquired_value_uses_fallback_sort_key_and_datetimes_compare_exactly() -> None:
    unreliable = _result(
        "unreliable.csv",
        0,
        acquired=datetime(2026, 1, 1),
        reliable=False,
    )
    fallback, _ = sort_file_results((unreliable,), SortMode.ACQUIRED_AT)
    assert fallback[0].sort_key == "fallback:unreliable.csv"

    later = _result(
        "a.csv",
        1,
        acquired=datetime(2500, 1, 1, 0, 0, 0, 2, tzinfo=UTC),
        reliable=True,
    )
    earlier = _result(
        "z.csv",
        2,
        acquired=datetime(2500, 1, 1, 0, 0, 0, 1, tzinfo=UTC),
        reliable=True,
    )
    exact, _ = sort_file_results((later, earlier), SortMode.ACQUIRED_AT)
    assert _names(exact) == ["z.csv", "a.csv"]
