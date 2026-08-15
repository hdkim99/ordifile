from __future__ import annotations

import os
from pathlib import Path

import pytest

from ordifile.core import discovery
from ordifile.core.discovery import discover_files, natural_key


def test_natural_key_orders_numeric_runs() -> None:
    values = ["sample_10.csv", "sample_2.csv", "sample_1.csv"]
    assert sorted(values, key=natural_key) == ["sample_1.csv", "sample_2.csv", "sample_10.csv"]


def test_discovers_single_multiple_and_unicode_paths(tmp_path: Path) -> None:
    korean = tmp_path / "한글 sample 2.csv"
    first = tmp_path / "sample_1.csv"
    korean.write_text("sample_id,area\na,1\n", encoding="utf-8")
    first.write_text("sample_id,area\nb,2\n", encoding="utf-8")
    records = discover_files((korean, first))
    assert [item.source.name for item in records] == [korean.name, first.name]
    assert all(item.source.sha256 and len(item.source.sha256) == 64 for item in records)


def test_folder_is_natural_sorted_and_recursive_is_explicit(tmp_path: Path) -> None:
    for name in ("sample_10.csv", "sample_1.csv", "sample_2.csv"):
        (tmp_path / name).write_text("sample_id,area\na,1\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "sample_3.csv").write_text("sample_id,area\na,1\n", encoding="utf-8")
    flat = discover_files((tmp_path,))
    assert [item.source.name for item in flat] == ["sample_1.csv", "sample_2.csv", "sample_10.csv"]
    recursive = discover_files((tmp_path,), recursive=True)
    assert "nested/sample_3.csv" in [item.source.relative_path for item in recursive]


def test_extension_filter_and_duplicate_resolved_path(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    (tmp_path / "ignored.bin").write_bytes(b"x")
    records = discover_files((source, tmp_path), extensions={"csv"})
    assert len(records) == 2
    assert records[1].source.duplicate_of == 0
    assert records[1].issues[0].code == "DUPLICATE_INPUT"


def test_rejects_symlink_without_following_it(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    link = tmp_path / "linked.csv"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlinks unavailable")
    record = discover_files((link,))[0]
    assert record.source.sha256 is None
    assert record.issues[0].code == "SYMLINK_REJECTED"


def test_missing_input_is_structured(tmp_path: Path) -> None:
    record = discover_files((tmp_path / "missing.csv",))[0]
    assert record.issues[0].code == "INPUT_NOT_FOUND"


def test_same_basename_from_different_inputs_gets_private_deterministic_paths(
    tmp_path: Path,
) -> None:
    first = tmp_path / "one" / "sample.csv"
    second = tmp_path / "two" / "sample.csv"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("sample_id,area\na,1\n", encoding="utf-8")
    second.write_text("sample_id,area\nb,2\n", encoding="utf-8")
    records = discover_files((first, second))
    assert [item.source.relative_path for item in records] == [
        "input_001/sample.csv",
        "input_002/sample.csv",
    ]
    assert all(str(tmp_path) not in item.source.relative_path for item in records)


def test_size_warning_and_limit_keep_streaming_sha256(tmp_path: Path) -> None:
    source = tmp_path / "large.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    warning = discover_files((source,), warn_file_bytes=1, max_file_bytes=10_000)[0]
    assert warning.issues[0].code == "INPUT_SIZE_WARNING"
    assert warning.source.sha256 is not None
    limited = discover_files((source,), warn_file_bytes=1, max_file_bytes=2)[0]
    assert limited.issues[0].code == "INPUT_SIZE_LIMIT"
    assert limited.source.sha256 == warning.source.sha256

    exact_threshold = discover_files(
        (source,), warn_file_bytes=source.stat().st_size, max_file_bytes=10_000
    )[0]
    assert exact_threshold.issues[0].code == "INPUT_SIZE_WARNING"


def test_hardlink_is_duplicate_by_file_identity_not_content_hash(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    hardlink = tmp_path / "different-name.csv"
    copied = tmp_path / "copied.csv"
    content = "sample_id,area\na,1\n"
    source.write_text(content, encoding="utf-8")
    try:
        os.link(source, hardlink)
    except OSError:
        pytest.skip("hardlinks unavailable")
    copied.write_text(content, encoding="utf-8")

    records = discover_files((source, hardlink, copied))

    assert records[1].source.duplicate_of == 0
    assert records[1].issues[0].code == "DUPLICATE_INPUT"
    assert records[2].source.duplicate_of is None
    assert records[2].source.sha256 == records[0].source.sha256


def test_nonzero_inode_is_fast_path_and_zero_inode_falls_back_to_samefile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    hardlink = tmp_path / "hardlink.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    try:
        os.link(source, hardlink)
    except OSError:
        pytest.skip("hardlinks unavailable")

    def samefile_must_not_run(_first: object, _second: object) -> bool:
        raise AssertionError("reliable nonzero inode should be the fast path")

    monkeypatch.setattr(os.path, "samefile", samefile_must_not_run)
    fast = discover_files((source, hardlink))
    assert fast[1].source.duplicate_of == 0

    monkeypatch.undo()
    monkeypatch.setattr(discovery, "_reliable_file_id", lambda _path: None)
    fallback = discover_files((source, hardlink))
    assert fallback[1].source.duplicate_of == 0


def test_unique_reliable_file_ids_never_call_samefile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs: list[Path] = []
    for index in range(100):
        source = tmp_path / f"sample_{index}.csv"
        source.write_text("sample_id,area\na,1\n", encoding="utf-8")
        inputs.append(source)

    calls = 0

    def count_samefile(_first: object, _second: object) -> bool:
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr(os.path, "samefile", count_samefile)
    records = discover_files(inputs)
    assert len(records) == 100
    assert all(record.source.duplicate_of is None for record in records)
    assert calls == 0


@pytest.mark.parametrize("recursive", [False, True])
def test_directory_iteration_failures_are_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recursive: bool
) -> None:
    def denied(_root: Path, _recursive: bool) -> object:
        raise PermissionError("private path must not leak")

    monkeypatch.setattr(discovery, "_directory_members", denied)
    record = discover_files((tmp_path,), recursive=recursive)[0]
    assert record.issues[0].code == "INPUT_DISCOVERY_FAILED"
    assert "private path" not in record.issues[0].message
    assert str(tmp_path) not in record.issues[0].message


def test_resolve_failure_is_structured_after_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    real_resolve = Path.resolve

    def fail_source_resolve(path: Path, strict: bool = False) -> Path:
        if path == source and strict:
            raise OSError("private resolve detail")
        return real_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_source_resolve)
    record = discover_files((source,))[0]
    assert record.issues[0].code == "INPUT_RESOLVE_FAILED"
    assert record.source.sha256 is not None
    assert "private resolve detail" not in record.issues[0].message
