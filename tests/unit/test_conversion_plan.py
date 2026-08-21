# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import ClassVar

import pytest

from ordifile.adapters.base import AdapterDescriptor, DetectionResult, ParseOptions
from ordifile.adapters.registry import create_registry
from ordifile.api import convert, convert_plan, plan_conversion
from ordifile.core import planning
from ordifile.core.errors import OrdifileError
from ordifile.core.models import DatasetBundle, ProgressEvent
from ordifile.core.peak_mapping import (
    ColumnSelector,
    PeakTableFormat,
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
)
from ordifile.core.planning import (
    ConversionPlanEntryStatus,
    ConversionPlanOutputDisposition,
    ConversionPlanProblem,
    ConversionPlanReadiness,
    ConversionPlanRoute,
)
from ordifile.exporters import excel


def _write_generic(path: Path, *, area: int = 1) -> None:
    path.write_text(f"sample_id,area\na,{area}\n", encoding="utf-8")


class _LateRegisteredAdapter:
    api_version: ClassVar[str] = "1"
    adapter_id: ClassVar[str] = "late_registered"
    adapter_version: ClassVar[str] = "1"
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        adapter_version,
        "Late registered",
        (".late",),
        False,
        False,
        False,
        True,
    )

    def probe(self, path: Path) -> DetectionResult:
        del path
        return DetectionResult(False, 0.0, "not used")

    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle:
        del path, options
        raise AssertionError("a stale plan must stop before parsing")


def _profile(
    *,
    profile_id: str = "profile-11111111111111111111111111111111",
    area_unit: str | None = None,
) -> PeakTableMappingProfile:
    return PeakTableMappingProfile(
        PeakTableMapping(
            ColumnSelector("RT", 1),
            ColumnSelector("Area", 2),
            "min",
            PeakTableFormat.CSV,
            area_unit=area_unit,
        ),
        "Local template",
        profile_id=profile_id,
    )


def test_plan_is_route_only_immutable_and_path_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "private-canary-source.csv"
    output = tmp_path / "private-canary-output.xlsx"
    _write_generic(source)

    def parse_must_not_run(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("preflight must not parse")

    monkeypatch.setattr("ordifile.adapters.generic_csv.GenericCsvAdapter.parse", parse_must_not_run)
    plan = plan_conversion(source, output)

    assert plan.schema_version == 1
    assert plan.readiness is ConversionPlanReadiness.READY
    assert plan.entries[0].status is ConversionPlanEntryStatus.ROUTABLE
    assert plan.entries[0].route is ConversionPlanRoute.GENERIC_INPUT
    assert plan.entries[0].source_id.startswith("source-")
    assert "private-canary" not in repr(plan)
    assert not output.exists()
    assert not list(tmp_path.glob(".ordifile_*"))
    with pytest.raises(AttributeError):
        plan._public_summary_sha256 = "0" * 64
    with pytest.raises(TypeError):
        pickle.dumps(plan)


def test_preflight_progress_failure_creates_no_artifact(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "result.xlsx"
    _write_generic(source)

    def fail_progress(_event: object) -> None:
        raise RuntimeError("private-canary-progress")

    with pytest.raises(RuntimeError, match="private-canary-progress"):
        plan_conversion(source, output, progress=fail_progress)
    assert not output.exists()
    assert not list(tmp_path.glob(".ordifile_*"))


def test_preflight_rejects_adapter_inventory_change_during_progress(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "result.xlsx"
    _write_generic(source)
    registry = create_registry()

    def mutate_registry(event: object) -> None:
        if getattr(event, "stage", None) == "planning_discovery":
            registry.register(_LateRegisteredAdapter())

    with pytest.raises(OrdifileError) as caught:
        plan_conversion(source, output, registry=registry, progress=mutate_registry)

    assert caught.value.code == "CONVERSION_PLAN_ADAPTER_CHANGED"
    assert not output.exists()
    assert not list(tmp_path.glob(".ordifile_*"))


def test_plan_hash_is_deterministic_and_tracks_public_options(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "result.xlsx"
    _write_generic(source)

    first = plan_conversion(source, output)
    second = plan_conversion(source, output)
    signals = plan_conversion(source, output, include_signals=True)

    assert first.public_summary_sha256 == second.public_summary_sha256
    assert first.public_summary_sha256 != signals.public_summary_sha256


def test_plan_routes_exact_mapping_drift_and_ambiguity_without_applying_candidates(
    tmp_path: Path,
) -> None:
    exact = tmp_path / "exact.csv"
    drifted = tmp_path / "drifted.csv"
    exact.write_text("RT,Area\n1,10\n", encoding="utf-8")
    drifted.write_text("RT,Peak Area\n1,10\n", encoding="utf-8")
    one_profile = PeakTableMappingSet((_profile(),))

    exact_plan = plan_conversion(exact, tmp_path / "exact.xlsx", peak_table_mapping_set=one_profile)
    drift_plan = plan_conversion(
        drifted, tmp_path / "drift.xlsx", peak_table_mapping_set=one_profile
    )

    assert exact_plan.entries[0].route is ConversionPlanRoute.USER_MAPPING_PROFILE
    assert exact_plan.entries[0].status is ConversionPlanEntryStatus.ROUTABLE
    assert drift_plan.entries[0].route is ConversionPlanRoute.UNROUTED
    assert drift_plan.entries[0].problem is ConversionPlanProblem.MAPPING_SCHEMA_DRIFT
    assert drift_plan.entries[0].status is ConversionPlanEntryStatus.FAILED
    assert drift_plan.entries[0].mapping_diagnostics

    ambiguous_set = PeakTableMappingSet(
        (
            _profile(),
            _profile(
                profile_id="profile-22222222222222222222222222222222",
                area_unit="mV.s",
            ),
        )
    )
    ambiguous = plan_conversion(
        exact,
        tmp_path / "ambiguous.xlsx",
        peak_table_mapping_set=ambiguous_set,
    )
    assert ambiguous.entries[0].problem is ConversionPlanProblem.MAPPING_PROFILE_AMBIGUOUS
    assert ambiguous.entries[0].route is ConversionPlanRoute.UNROUTED


def test_plan_classifies_unsupported_malformed_duplicate_and_output_conflict(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.csv"
    unsupported = tmp_path / "unknown.bin"
    empty = tmp_path / "empty.csv"
    output = tmp_path / "result.xlsx"
    _write_generic(source)
    unsupported.write_bytes(b"unsupported")
    empty.write_bytes(b"")
    output.write_bytes(b"foreign")

    unsupported_plan = plan_conversion(unsupported, tmp_path / "unsupported.xlsx")
    malformed_plan = plan_conversion(
        empty,
        tmp_path / "malformed.xlsx",
        peak_table_mapping_set=PeakTableMappingSet((_profile(),)),
    )
    duplicate_plan = plan_conversion((source, source), tmp_path / "duplicates.xlsx")
    conflict_plan = plan_conversion(source, output)

    assert unsupported_plan.entries[0].problem is ConversionPlanProblem.UNSUPPORTED_FORMAT
    assert malformed_plan.entries[0].problem is ConversionPlanProblem.MALFORMED_INPUT
    assert duplicate_plan.summary.duplicates == 1
    assert duplicate_plan.entries[1].status is ConversionPlanEntryStatus.DUPLICATE
    assert conflict_plan.output_disposition is ConversionPlanOutputDisposition.BLOCKED
    assert conflict_plan.output_issue_code == "OUTPUT_EXISTS"
    assert conflict_plan.readiness is ConversionPlanReadiness.BLOCKED
    assert output.read_bytes() == b"foreign"

    with pytest.raises(OrdifileError) as replace_plan:
        plan_conversion(source, output, overwrite=True)
    assert replace_plan.value.code == "CONVERSION_PLAN_OVERWRITE_UNSUPPORTED"
    assert output.read_bytes() == b"foreign"
    assert not list(tmp_path.glob(".ordifile_*"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory mode policy")
def test_plan_blocks_non_sticky_shared_writable_output_directory(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    _write_generic(source)
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)

    plan = plan_conversion(source, shared / "result.xlsx")

    assert plan.output_disposition is ConversionPlanOutputDisposition.BLOCKED
    assert plan.output_issue_code == "OUTPUT_DIRECTORY_UNSAFE"
    assert plan.readiness is ConversionPlanReadiness.BLOCKED
    assert not list(shared.glob(".ordifile_*"))


def test_equal_bytes_at_distinct_paths_are_not_reported_as_duplicate(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    _write_generic(first)
    second.write_bytes(first.read_bytes())

    plan = plan_conversion((first, second), tmp_path / "result.xlsx")

    assert plan.summary.duplicates == 0
    assert plan.summary.routable == 2
    assert plan.entries[0].source_id == plan.entries[1].source_id
    assert plan.entries[0].input_order != plan.entries[1].input_order


def test_continue_and_stop_readiness_preserve_current_failure_policy(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    unsupported = tmp_path / "unsupported.bin"
    _write_generic(source)
    unsupported.write_bytes(b"unsupported")

    continued = plan_conversion(
        (source, unsupported), tmp_path / "continue.xlsx", on_error="continue"
    )
    stopped = plan_conversion((source, unsupported), tmp_path / "stop.xlsx", on_error="stop")

    assert continued.readiness is ConversionPlanReadiness.READY_WITH_KNOWN_FAILURES
    assert continued.is_executable
    assert stopped.readiness is ConversionPlanReadiness.BLOCKED
    assert not stopped.is_executable


def test_convert_plan_revalidates_source_folder_and_output_state(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "result.xlsx"
    _write_generic(source)
    plan = plan_conversion(source, output)
    source.write_text("sample_id,area\na,2\n", encoding="utf-8")

    with pytest.raises(OrdifileError) as changed:
        convert_plan(plan)
    assert changed.value.code == "CONVERSION_PLAN_STALE"
    assert not output.exists()

    _write_generic(source)
    folder_plan = plan_conversion(tmp_path, output, extensions=("csv",))
    added = tmp_path / "added.csv"
    _write_generic(added)
    with pytest.raises(OrdifileError) as added_error:
        convert_plan(folder_plan)
    assert added_error.value.code == "CONVERSION_PLAN_STALE"
    assert not output.exists()

    added.unlink()
    deleted_plan = plan_conversion(tmp_path, output, extensions=("csv",))
    source.unlink()
    with pytest.raises(OrdifileError) as deleted_error:
        convert_plan(deleted_plan)
    assert deleted_error.value.code == "CONVERSION_PLAN_STALE"
    _write_generic(source)

    output_plan = plan_conversion(source, output)
    output.write_bytes(b"foreign")
    with pytest.raises(OrdifileError) as output_error:
        convert_plan(output_plan)
    assert output_error.value.code == "CONVERSION_PLAN_STALE"
    assert output.read_bytes() == b"foreign"


def test_unchanged_plan_executes_existing_converter(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "result.xlsx"
    _write_generic(source)
    plan = plan_conversion(source, output)

    result = convert_plan(plan)

    assert result.success_count == 1
    assert result.output_path == output
    assert output.is_file()


def test_convert_with_reviewed_plan_rejects_current_mapping_change(tmp_path: Path) -> None:
    source = tmp_path / "mapped.csv"
    output = tmp_path / "result.xlsx"
    source.write_text("RT,Area\n1,10\n", encoding="utf-8")
    original = _profile().mapping
    changed = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "s",
        PeakTableFormat.CSV,
    )
    plan = plan_conversion(source, output, peak_table_mapping=original)

    with pytest.raises(OrdifileError) as caught:
        convert(
            source,
            output,
            peak_table_mapping=changed,
            conversion_plan=plan,
        )

    assert caught.value.code == "CONVERSION_PLAN_STALE"
    assert not output.exists()


def test_convert_with_reviewed_plan_rejects_mapping_set_repair(tmp_path: Path) -> None:
    source = tmp_path / "mapped.csv"
    output = tmp_path / "result.xlsx"
    source.write_text("RT,Area\n1,10\n", encoding="utf-8")
    original = _profile()
    mapping_set = PeakTableMappingSet((original,))
    plan = plan_conversion(source, output, peak_table_mapping_set=mapping_set)
    repaired = PeakTableMappingProfile(
        PeakTableMapping(
            ColumnSelector("Time", 1),
            ColumnSelector("Value", 2),
            "min",
            PeakTableFormat.CSV,
        ),
        "Repaired template",
        profile_id="profile-22222222222222222222222222222222",
    )
    changed_set = PeakTableMappingSet(
        (*mapping_set.profiles, repaired),
        set_id=mapping_set.set_id,
    )

    with pytest.raises(OrdifileError) as caught:
        convert(
            source,
            output,
            peak_table_mapping_set=changed_set,
            conversion_plan=plan,
        )

    assert caught.value.code == "CONVERSION_PLAN_STALE"
    assert not output.exists()


def test_convert_plan_rejects_registry_mutation_after_revalidation(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "result.xlsx"
    _write_generic(source)
    registry = create_registry()
    plan = plan_conversion(source, output, registry=registry)

    def mutate_registry(event: ProgressEvent) -> None:
        if event.stage == "discovery":
            registry.register(_LateRegisteredAdapter())

    with pytest.raises(OrdifileError) as caught:
        convert_plan(plan, registry=registry, progress=mutate_registry)

    assert caught.value.code == "CONVERSION_PLAN_STALE"
    assert not output.exists()


def test_convert_plan_asserts_reviewed_route_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "result.xlsx"
    _write_generic(source)
    registry = create_registry()
    plan = plan_conversion(source, output, registry=registry)
    adapter_type = type(registry.get("generic_csv"))

    def change_probe(event: ProgressEvent) -> None:
        if event.stage == "discovery":
            monkeypatch.setattr(
                adapter_type,
                "probe",
                lambda _self, _path: DetectionResult(False, 0.0, "changed after review"),
            )

    with pytest.raises(OrdifileError) as caught:
        convert_plan(plan, registry=registry, progress=change_probe)

    assert caught.value.code == "CONVERSION_PLAN_STALE"
    assert not output.exists()


def test_convert_plan_asserts_reviewed_routing_failure_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "result.xlsx"
    source.write_text("unrecognized,columns\nx,y\n", encoding="utf-8")
    registry = create_registry()
    plan = plan_conversion(source, output, registry=registry, on_error="continue")
    assert plan.entries[0].status is ConversionPlanEntryStatus.FAILED
    adapter_type = type(registry.get("generic_csv"))

    def fail_parse(_self: object, _path: Path, _options: ParseOptions) -> DatasetBundle:
        raise AssertionError("stale failure must stop before parsing")

    def change_failure(event: ProgressEvent) -> None:
        if event.stage == "discovery":
            monkeypatch.setattr(
                adapter_type,
                "probe",
                lambda _self, _path: DetectionResult(True, 1.0, "changed after review"),
            )
            monkeypatch.setattr(
                adapter_type,
                "parse",
                fail_parse,
            )

    with pytest.raises(OrdifileError) as caught:
        convert_plan(plan, registry=registry, progress=change_failure)

    assert caught.value.code == "CONVERSION_PLAN_STALE"
    assert not output.exists()


def test_convert_plan_preserves_output_appearing_during_finalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "result.xlsx"
    canary = b"foreign"
    _write_generic(source)
    plan = plan_conversion(source, output)
    real_rename = excel._rename_no_replace

    def collide_rename(source_path: Path, destination_path: Path) -> None:
        if Path(destination_path) == output:
            output.write_bytes(canary)
        real_rename(Path(source_path), Path(destination_path))

    monkeypatch.setattr(excel, "_rename_no_replace", collide_rename)
    with pytest.raises(OrdifileError) as caught:
        convert_plan(plan)
    assert caught.value.code == "CONVERSION_PLAN_STALE"
    assert output.read_bytes() == canary


def test_relative_plan_bindings_do_not_follow_a_later_working_directory_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    planned_root = tmp_path / "planned"
    other_root = tmp_path / "other"
    planned_root.mkdir()
    other_root.mkdir()
    _write_generic(planned_root / "source.csv")
    _write_generic(other_root / "source.csv", area=999)
    monkeypatch.chdir(planned_root)
    plan = plan_conversion("source.csv", "result.xlsx")

    monkeypatch.chdir(other_root)
    result = convert_plan(plan)

    assert result.output_path == planned_root / "result.xlsx"
    assert (planned_root / "result.xlsx").is_file()
    assert not (other_root / "result.xlsx").exists()


def test_large_synthetic_plan_is_bounded_ordered_and_deterministic(tmp_path: Path) -> None:
    folder = tmp_path / "batch"
    folder.mkdir()
    for index in range(150):
        _write_generic(folder / f"run-{index:03d}.csv", area=index + 1)
    output = tmp_path / "result.xlsx"

    first = plan_conversion(folder, output)
    second = plan_conversion(folder, output)

    assert first.summary.total_inputs == 150
    assert first.summary.routable == 150
    assert tuple(entry.input_order for entry in first.entries) == tuple(range(150))
    assert first.public_summary_sha256 == second.public_summary_sha256


def test_plan_rejects_discovery_above_the_explicit_input_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "batch"
    folder.mkdir()
    _write_generic(folder / "one.csv")
    _write_generic(folder / "two.csv")
    monkeypatch.setattr(planning, "MAX_CONVERSION_PLAN_INPUTS", 1)

    with pytest.raises(OrdifileError) as caught:
        plan_conversion(folder, tmp_path / "result.xlsx")
    assert caught.value.code == "CONVERSION_PLAN_TOO_LARGE"

    monkeypatch.setattr(planning, "MAX_CONVERSION_PLAN_INPUTS", 10)
    monkeypatch.setattr(planning, "MAX_CONVERSION_PLAN_TOTAL_INPUT_BYTES", 1)
    with pytest.raises(OrdifileError) as aggregate:
        plan_conversion(folder, tmp_path / "result.xlsx")
    assert aggregate.value.code == "CONVERSION_PLAN_TOO_LARGE"
