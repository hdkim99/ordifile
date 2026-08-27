# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ordifile import (
    ColumnSelector,
    ConversionPlanEntryStatus,
    ConversionPlanReadiness,
    ConversionPlanRoute,
    ConversionRecipe,
    PeakMappingDriftCategory,
    PeakMappingDriftDiagnostic,
    PeakTableFormat,
    PeakTableImportSettings,
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
)
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


def _drift_diagnostic(
    profile_id: str = "profile-11111111111111111111111111111111",
) -> PeakMappingDriftDiagnostic:
    return PeakMappingDriftDiagnostic(
        profile_id=profile_id,
        profile_structural_fingerprint="b" * 64,
        source_format=PeakTableFormat.CSV,
        categories=(PeakMappingDriftCategory.HEADER_CHANGED_UNRESOLVED,),
        expected_column_count=2,
        observed_column_count=2,
        exact_position_matches=1,
        changed_column_count=1,
        added_column_count=0,
        removed_column_count=0,
        moved_column_count=0,
        total_difference_count=1,
        unresolved_required_roles=("area",),
        unresolved_optional_roles=(),
    )


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

    assert calls == {
        "inputs": inputs,
        "sort": "filename",
        "peak_table_mapping": None,
        "peak_table_mapping_set": None,
        "progress": events.append,
    }
    assert report.outcome is BatchOutcome.SUCCESS
    assert report.files[0].format_name == "Generic CSV (Verified)"
    assert report.files[0].status is DesktopInputStatus.SUCCESS


def test_preflight_selection_preserves_public_plan_and_projects_public_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "private-canary.csv"
    source.write_text(
        "Private RT Header,Private Area Header,Private Note Header\n"
        "1,2,Private Measurement Canary\n",
        encoding="utf-8",
    )
    output = tmp_path / "result.xlsx"
    profile = PeakTableMappingProfile(
        PeakTableMapping(
            ColumnSelector("Private RT Header", 1),
            ColumnSelector("Private Area Header", 2),
            "Private RT Unit",
            PeakTableFormat.CSV,
            manufacturer="Private Manufacturer",
            software="Private Software",
            ignored_columns=(ColumnSelector("Private Note Header", 3),),
        ),
        "Private Profile Label",
    )
    xlsx_profile = PeakTableMappingProfile(
        PeakTableMapping(
            ColumnSelector("Private XLSX RT", 1),
            ColumnSelector("Private XLSX Area", 2),
            "s",
            PeakTableFormat.XLSX,
        ),
        "Private XLSX Profile Label",
        worksheet_title="Private Worksheet Title",
    )
    mapping_set = PeakTableMappingSet((profile, xlsx_profile))
    plan = public_api.plan_conversion(source, output, peak_table_mapping_set=mapping_set)
    calls: list[tuple[object, object, object]] = []

    def preflight(inputs: object, destination: object, **kwargs: object) -> object:
        calls.append((inputs, destination, kwargs.get("sort")))
        return plan

    monkeypatch.setattr(public_api, "plan_conversion", preflight)
    report = services.preflight_selection(
        DesktopRequest((source,), output, "filename", peak_table_mapping_set=mapping_set)
    )

    assert calls == [((source,), output, "filename")]
    assert report.plan is plan
    assert report.success_count == 1
    assert report.files[0].plan_status is ConversionPlanEntryStatus.ROUTABLE
    assert report.files[0].plan_route is ConversionPlanRoute.USER_MAPPING_PROFILE
    assert report.files[0].source.startswith("source-")
    assert source.name not in repr(report)
    public_report = repr(report)
    for canary in (
        "Private RT Header",
        "Private Area Header",
        "Private Note Header",
        "Private Measurement Canary",
        "Private RT Unit",
        "Private Manufacturer",
        "Private Software",
        "Private Profile Label",
        "Private XLSX RT",
        "Private XLSX Area",
        "Private XLSX Profile Label",
        "Private Worksheet Title",
    ):
        assert canary not in public_report


def test_convert_preflight_plan_passes_the_exact_plan_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    output = tmp_path / "result.xlsx"
    plan = public_api.plan_conversion(source, output)
    received: list[object] = []

    def convert(candidate: object, **_kwargs: object) -> BatchResult:
        received.append(candidate)
        return _batch(FileStatus.SUCCESS, output=output)

    monkeypatch.setattr(public_api, "convert_plan", convert)

    report = services.convert_preflight_plan(plan)

    assert received == [plan]
    assert received[0] is plan
    assert report.outcome is BatchOutcome.SUCCESS


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
        "include_signals": True,
        "experimental_derived_area": False,
        "on_error": "continue",
        "overwrite": False,
        "sheet": None,
        "peak_table_mapping": None,
        "peak_table_mapping_set": None,
        "progress": None,
    }
    assert report.output_path == output
    assert report.outcome is BatchOutcome.SUCCESS
    assert report.summary is not None
    assert report.summary.total_sources == 1
    assert report.summary.peak_records == 0


def test_convert_selection_calls_public_recipe_conversion_with_frozen_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = ConversionRecipe(sort=SortMode.FILENAME, display_label="Daily conversion")
    output = tmp_path / "result.xlsx"
    request = DesktopRequest((tmp_path / "input.csv",), output, recipe=recipe)
    calls: list[tuple[object, object, dict[str, object]]] = []

    def convert(inputs: object, destination: object, **kwargs: object) -> BatchResult:
        calls.append((inputs, destination, kwargs))
        return _batch(FileStatus.SUCCESS, output=output)

    monkeypatch.setattr(public_api, "convert_recipe", convert)

    report = services.convert_selection(request)

    assert calls == [
        (
            request.inputs,
            output,
            {
                "recipe": recipe,
                "experimental_derived_area": False,
                "progress": None,
            },
        )
    ]
    assert report.outcome is BatchOutcome.SUCCESS


def test_desktop_services_forward_one_frozen_mapping_to_preview_and_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
    )
    calls: list[PeakTableMapping | None] = []
    output = tmp_path / "result.xlsx"

    def inspect(*_args: object, **kwargs: object) -> BatchResult:
        value = kwargs.get("peak_table_mapping")
        assert value is None or isinstance(value, PeakTableMapping)
        calls.append(value)
        return _batch(FileStatus.SUCCESS)

    def convert(*_args: object, **kwargs: object) -> BatchResult:
        value = kwargs.get("peak_table_mapping")
        assert value is None or isinstance(value, PeakTableMapping)
        calls.append(value)
        return _batch(FileStatus.SUCCESS, output=output)

    monkeypatch.setattr(public_api, "inspect_inputs", inspect)
    monkeypatch.setattr(public_api, "convert", convert)

    services.inspect_selection((tmp_path / "input.csv",), sort="auto", peak_table_mapping=mapping)
    services.convert_selection(
        DesktopRequest((tmp_path / "input.csv",), output, peak_table_mapping=mapping)
    )

    assert calls == [mapping, mapping]


def test_desktop_services_forward_one_frozen_mapping_set_to_preview_and_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
    )
    mapping_set = PeakTableMappingSet((PeakTableMappingProfile(mapping, "Daily CSV"),))
    calls: list[tuple[object, object]] = []
    output = tmp_path / "result.xlsx"

    def inspect(*_args: object, **kwargs: object) -> BatchResult:
        calls.append((kwargs.get("peak_table_mapping"), kwargs.get("peak_table_mapping_set")))
        return _batch(FileStatus.SUCCESS)

    def convert(*_args: object, **kwargs: object) -> BatchResult:
        calls.append((kwargs.get("peak_table_mapping"), kwargs.get("peak_table_mapping_set")))
        return _batch(FileStatus.SUCCESS, output=output)

    monkeypatch.setattr(public_api, "inspect_inputs", inspect)
    monkeypatch.setattr(public_api, "convert", convert)

    services.inspect_selection(
        (tmp_path / "input.csv",),
        sort="auto",
        peak_table_mapping_set=mapping_set,
    )
    services.convert_selection(
        DesktopRequest(
            (tmp_path / "input.csv",),
            output,
            peak_table_mapping_set=mapping_set,
        )
    )

    assert calls == [(None, mapping_set), (None, mapping_set)]


def test_desktop_report_carries_only_public_mapping_route_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_id = "profile-11111111111111111111111111111111"
    source = _source("public.csv", 0)
    batch = BatchResult(
        (
            FileResult(
                source,
                FileStatus.SUCCESS,
                "generic_csv",
                "1",
                mapping_route="USER_MAPPING_PROFILE",
                mapping_profile_id=profile_id,
            ),
        ),
        SortDecision(SortMode.AUTO, SortMode.INPUT_ORDER, "test"),
    )
    monkeypatch.setattr(public_api, "inspect_inputs", lambda *_args, **_kwargs: batch)

    report = services.inspect_selection((tmp_path / "input.csv",), sort="auto")

    assert report.files[0].mapping_route == "USER_MAPPING_PROFILE"
    assert report.files[0].mapping_profile_id == profile_id


def test_desktop_report_carries_public_drift_diagnostics_without_raw_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "private-result.csv"
    source_path.write_text("Changed RT,Area\n1,2\n", encoding="utf-8")
    source = SourceFile(
        Path("source-" + "a" * 64),
        "source-" + "a" * 64,
        "source-" + "a" * 64,
        1,
        "a" * 64,
        None,
        0,
        public_id="source-" + "a" * 64,
    )
    diagnostic = _drift_diagnostic()
    batch = BatchResult(
        (
            FileResult(
                source,
                FileStatus.FAILED,
                issues=(
                    Issue(
                        "PEAK_MAPPING_PROFILE_NOT_MATCHED",
                        "No exact match.",
                        Severity.ERROR,
                    ),
                ),
                mapping_route="SCHEMA_DRIFT_CANDIDATE",
                mapping_diagnostics=(diagnostic,),
            ),
        ),
        SortDecision(SortMode.AUTO, SortMode.INPUT_ORDER, "test"),
    )
    monkeypatch.setattr(public_api, "inspect_inputs", lambda *_args, **_kwargs: batch)

    report = services.inspect_selection((source_path,), sort="auto")

    assert report.files[0].mapping_diagnostics == (diagnostic,)
    assert report.files[0].review_input_index == 0
    assert str(source_path) not in repr(report)
    assert source_path.name not in services.details_text(report)


def test_mapping_set_load_and_save_use_public_root_exports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
    )
    mapping_set = PeakTableMappingSet((PeakTableMappingProfile(mapping, "Daily CSV"),))
    path = tmp_path / "set.json"
    saved: list[tuple[PeakTableMappingSet, Path, bool]] = []
    monkeypatch.setattr(
        "ordifile.desktop.services.ordifile.load_peak_table_mapping_set",
        lambda value: mapping_set,
    )
    monkeypatch.setattr(
        "ordifile.desktop.services.ordifile.save_peak_table_mapping_set",
        lambda value, destination, *, overwrite: saved.append(
            (value, Path(destination), overwrite)
        ),
    )

    assert services.load_mapping_set(path) is mapping_set
    services.save_mapping_set(mapping_set, path, overwrite=True)

    assert saved == [(mapping_set, path, True)]


def test_recipe_load_and_save_use_public_root_exports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = ConversionRecipe(display_label="Daily conversion")
    path = tmp_path / "recipe.json"
    saved: list[tuple[ConversionRecipe, Path, bool]] = []
    monkeypatch.setattr(
        "ordifile.desktop.services.ordifile.load_conversion_recipe",
        lambda value: recipe,
    )
    monkeypatch.setattr(
        "ordifile.desktop.services.ordifile.save_conversion_recipe",
        lambda value, destination, *, overwrite: saved.append(
            (value, Path(destination), overwrite)
        ),
    )

    assert services.load_recipe(path) is recipe
    services.save_recipe(recipe, path, overwrite=True)

    assert saved == [(recipe, path, True)]


def test_preflight_selection_passes_only_the_frozen_recipe_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = ConversionRecipe(sort=SortMode.FILENAME, display_label="Daily conversion")
    request = DesktopRequest(
        (tmp_path / "input.csv",),
        tmp_path / "result.xlsx",
        recipe=recipe,
    )
    calls: list[dict[str, object]] = []
    plan: Any = SimpleNamespace(
        entries=(),
        readiness=ConversionPlanReadiness.BLOCKED,
        summary=SimpleNamespace(routable=0, failed=0, duplicates=0),
    )

    def preflight(*_args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return plan

    monkeypatch.setattr(public_api, "plan_recipe", preflight)

    report = services.preflight_selection(request)

    assert report.plan is plan
    assert calls == [
        {
            "recipe": recipe,
            "experimental_derived_area": False,
            "progress": None,
        }
    ]


def test_preview_peak_table_uses_public_bounded_preview_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.csv"
    expected = SimpleNamespace(
        source_format=PeakTableFormat.CSV,
        headers=("RT", "Area"),
        rows=(("1.2", "10"),),
        sheet=None,
        source_sha256="1" * 64,
        import_settings=PeakTableImportSettings(),
    )
    calls: list[tuple[object, ...]] = []

    def preview(*args: object, **kwargs: object) -> object:
        calls.append((*args, kwargs))
        return expected

    monkeypatch.setattr(public_api, "preview_peak_table", preview)

    report = services.preview_peak_table(source, PeakTableFormat.CSV)

    assert calls == [
        (
            source,
            PeakTableFormat.CSV,
            {"sheet": None, "import_settings": None},
        )
    ]
    assert report.preview is not None
    assert report.preview.headers == ("RT", "Area")
    assert report.preview.rows == (("1.2", "10"),)
    assert report.preview.source_sha256 == "1" * 64
    assert report.preview.import_settings == PeakTableImportSettings()


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


def test_safe_preview_text_visibly_escapes_controls_and_bidi() -> None:
    assert services.safe_preview_text("line\nbad\u202evalue") == ("line\\u000Abad\\u202Evalue")


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
