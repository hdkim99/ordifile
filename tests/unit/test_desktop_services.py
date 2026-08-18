# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ordifile import api as public_api
from ordifile.core.models import (
    BatchOutcome,
    BatchResult,
    FileResult,
    FileStatus,
    Issue,
    Severity,
    SortDecision,
    SortMode,
    SourceFile,
)
from ordifile.desktop import services
from ordifile.desktop.models import DesktopInputStatus, DesktopRequest


def _source(name: str, order: int) -> SourceFile:
    return SourceFile(Path(name), name, name, 1, "a" * 64, None, order)


def _batch(
    *statuses: FileStatus,
    output: Path | None = None,
    with_issues: bool = False,
) -> BatchResult:
    files = []
    for order, status in enumerate(statuses):
        issues = (
            (Issue("BAD_INPUT", "Input could not be parsed.", Severity.ERROR),)
            if with_issues and status is FileStatus.FAILED
            else ()
        )
        files.append(
            FileResult(
                _source(f"public-{order}.csv", order),
                status,
                "generic_csv" if status is not FileStatus.FAILED else None,
                "1",
                issues=issues,
            )
        )
    return BatchResult(
        tuple(files), SortDecision(SortMode.AUTO, SortMode.INPUT_ORDER, "test"), output
    )


@pytest.fixture(autouse=True)
def _formats(monkeypatch: pytest.MonkeyPatch) -> None:
    descriptor = SimpleNamespace(
        adapter_id="generic_csv",
        display_name="Generic CSV",
        support_status=SimpleNamespace(value="verified"),
    )
    monkeypatch.setattr(public_api, "list_formats", lambda: (descriptor,))


def test_inspect_selection_uses_public_batch_api_and_forwards_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, Any] = {}
    events: list[object] = []

    def inspect(inputs: object, **kwargs: object) -> BatchResult:
        calls["inputs"] = inputs
        calls.update(kwargs)
        return _batch(FileStatus.SUCCESS)

    monkeypatch.setattr(public_api, "inspect_inputs", inspect)
    inputs = (tmp_path / "data",)

    report = services.inspect_selection(inputs, sort="filename", progress=events.append)

    assert calls == {"inputs": inputs, "sort": "filename", "progress": events.append}
    assert report.outcome is BatchOutcome.SUCCESS
    assert report.files[0].format_name == "Generic CSV (Verified)"
    assert report.files[0].status is DesktopInputStatus.SUCCESS


def test_convert_selection_calls_only_public_convert_with_safe_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, Any] = {}
    output = tmp_path / "result.xlsx"

    def convert(inputs: object, destination: object, **kwargs: object) -> BatchResult:
        calls["inputs"] = inputs
        calls["output"] = destination
        calls.update(kwargs)
        return _batch(FileStatus.SUCCESS, output=output)

    monkeypatch.setattr(public_api, "convert", convert)
    request = DesktopRequest((tmp_path / "input.csv",), output, "sequence")

    report = services.convert_selection(request)

    assert calls == {
        "inputs": request.inputs,
        "output": output,
        "sort": "sequence",
        "on_error": "continue",
        "overwrite": False,
        "progress": None,
    }
    assert report.output_path == output
    assert report.outcome is BatchOutcome.SUCCESS


def test_convert_selection_distinguishes_partial_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result.xlsx"
    monkeypatch.setattr(
        public_api,
        "convert",
        lambda *_args, **_kwargs: _batch(
            FileStatus.SUCCESS,
            FileStatus.FAILED,
            output=output,
            with_issues=True,
        ),
    )

    report = services.convert_selection(
        DesktopRequest((tmp_path / "good.csv", tmp_path / "bad.bin"), output)
    )

    assert report.outcome is BatchOutcome.PARTIAL_SUCCESS
    assert report.success_count == 1
    assert report.failure_count == 1
    assert report.files[1].message == "[BAD_INPUT] Input could not be parsed."


def test_convert_selection_distinguishes_all_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result.xlsx"
    monkeypatch.setattr(
        public_api,
        "convert",
        lambda *_args, **_kwargs: _batch(FileStatus.FAILED, output=output, with_issues=True),
    )

    report = services.convert_selection(DesktopRequest((tmp_path / "bad.bin",), output))

    assert report.outcome is BatchOutcome.FAILED
    assert report.failure_count == 1
    assert not report.is_fatal_error


def test_structured_public_error_is_returned_without_traceback_or_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PublicError(Exception):
        code = "OUTPUT_EXISTS"
        message = "Output already exists."
        details = {"path": "private-path"}

    def fail(*_args: object, **_kwargs: object) -> BatchResult:
        raise PublicError

    monkeypatch.setattr(public_api, "convert", fail)

    report = services.convert_selection(
        DesktopRequest((tmp_path / "input.csv",), tmp_path / "result.xlsx")
    )

    assert report.error_code == "OUTPUT_EXISTS"
    assert report.error_message == "Output already exists."
    assert "private-path" not in services.details_text(report)
    assert "Traceback" not in services.details_text(report)


def test_unexpected_exception_does_not_expose_exception_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object, **_kwargs: object) -> BatchResult:
        raise RuntimeError("private scientific filename")

    monkeypatch.setattr(public_api, "inspect_inputs", fail)

    report = services.inspect_selection((tmp_path,), sort="auto")

    assert report.error_code == "UNEXPECTED_ERROR"
    assert "private scientific filename" not in (report.error_message or "")
    assert report.error_message == "Unexpected internal error; no files were changed."


@pytest.mark.parametrize(
    "error",
    [KeyboardInterrupt("private"), SystemExit("private"), MemoryError("private")],
)
def test_nonordinary_termination_is_a_fixed_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    def fail(*_args: object, **_kwargs: object) -> BatchResult:
        raise error

    monkeypatch.setattr(public_api, "convert", fail)

    report = services.convert_selection(
        DesktopRequest((tmp_path / "input.csv",), tmp_path / "result.xlsx")
    )

    assert report.error_code == "OPERATION_INTERRUPTED"
    assert "private" not in (report.error_message or "")
    assert "Traceback" not in services.details_text(report)


def test_safe_display_name_removes_controls_and_bidi(tmp_path: Path) -> None:
    rendered = services.safe_display_name(tmp_path / "line\nbad\u202ename.csv")

    assert "\n" not in rendered
    assert "\u202e" not in rendered
    assert rendered == "line bad name.csv"


def test_diagnostic_text_is_single_line_per_file_and_control_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = _batch(FileStatus.FAILED, with_issues=True)
    malicious = Issue("BAD\nCODE", "hidden\u202ename\nmessage", Severity.ERROR)
    batch = BatchResult(
        (FileResult(batch.files[0].source, FileStatus.FAILED, issues=(malicious,)),),
        batch.sort,
    )
    monkeypatch.setattr(public_api, "inspect_inputs", lambda *_a, **_k: batch)

    report = services.inspect_selection((Path("unused"),), sort="auto")
    rendered = services.details_text(report)

    assert "\u202e" not in rendered
    assert rendered.count("\n") == 0
