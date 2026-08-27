# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest

from ordifile import (
    ColumnSelector,
    ConversionRecipe,
    PeakTableFormat,
    PeakTableMapping,
    PeakTableMappingProfile,
    PeakTableMappingSet,
)
from ordifile.api import plan_conversion
from ordifile.core.models import BatchOutcome
from ordifile.desktop.models import (
    DesktopBatchReport,
    DesktopRequest,
    InputSelectionModel,
    RequestValidationError,
    validate_request,
)


def test_input_selection_preserves_order_and_ignores_lexical_duplicates(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    model = InputSelectionModel()

    result = model.add((first, second, first))

    assert result.added == (first, second)
    assert result.duplicates == (first,)
    assert model.paths == (first, second)


def test_input_selection_normalizes_relative_and_absolute_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    model = InputSelectionModel()

    result = model.add((Path("sample.csv"), tmp_path / "sample.csv"))

    assert result.added == (Path("sample.csv"),)
    assert result.duplicates == (tmp_path / "sample.csv",)


def test_input_selection_remove_and_clear_preserve_remaining_order(tmp_path: Path) -> None:
    paths = tuple(tmp_path / f"input-{index}.csv" for index in range(3))
    model = InputSelectionModel()
    model.add(paths)

    model.remove((paths[1],))
    assert model.paths == (paths[0], paths[2])

    model.clear()
    assert len(model.paths) == 0


@pytest.mark.parametrize(
    ("desktop_request", "code"),
    [
        (DesktopRequest((), Path("result.xlsx")), "NO_INPUTS"),
        (DesktopRequest((Path("input.csv"),), Path("result.csv")), "OUTPUT_EXTENSION_INVALID"),
        (
            DesktopRequest((Path("input.csv"),), Path("missing/result.xlsx")),
            "OUTPUT_DIRECTORY_MISSING",
        ),
        (
            DesktopRequest((Path("input.csv"),), Path("result.xlsx"), "unsupported"),
            "SORT_MODE_INVALID",
        ),
    ],
)
def test_request_validation_rejects_invalid_local_options(
    desktop_request: DesktopRequest, code: str
) -> None:
    with pytest.raises(RequestValidationError) as caught:
        validate_request(desktop_request)

    assert caught.value.code == code


def test_request_validation_accepts_every_public_sort_mode(tmp_path: Path) -> None:
    for sort in ("auto", "acquired_at", "sequence", "filename", "input_order"):
        validate_request(DesktopRequest((tmp_path / "input.csv",), tmp_path / "result.xlsx", sort))


def test_request_validation_rejects_non_boolean_experimental_area(tmp_path: Path) -> None:
    request = DesktopRequest(
        (tmp_path / "input.csv",),
        tmp_path / "result.xlsx",
        experimental_derived_area="yes",  # type: ignore[arg-type]
    )

    with pytest.raises(RequestValidationError) as caught:
        validate_request(request)

    assert caught.value.code == "OPTION_TYPE_INVALID"


def test_request_validation_rejects_directory_output(tmp_path: Path) -> None:
    with pytest.raises(RequestValidationError) as caught:
        validate_request(DesktopRequest((tmp_path / "input.csv",), tmp_path))

    assert caught.value.code == "OUTPUT_EXTENSION_INVALID"


def test_desktop_request_preserves_optional_frozen_peak_mapping(tmp_path: Path) -> None:
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
    )

    request = DesktopRequest(
        (tmp_path / "input.csv",),
        tmp_path / "result.xlsx",
        peak_table_mapping=mapping,
    )

    assert request.peak_table_mapping is mapping


def test_desktop_request_preserves_optional_frozen_mapping_set(tmp_path: Path) -> None:
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
    )
    mapping_set = PeakTableMappingSet((PeakTableMappingProfile(mapping, "Daily CSV"),))

    request = DesktopRequest(
        (tmp_path / "input.csv",),
        tmp_path / "result.xlsx",
        peak_table_mapping_set=mapping_set,
    )

    assert request.peak_table_mapping is None
    assert request.peak_table_mapping_set is mapping_set


def test_desktop_request_preserves_optional_frozen_conversion_recipe(tmp_path: Path) -> None:
    recipe = ConversionRecipe()

    request = DesktopRequest(
        (tmp_path / "input.csv",),
        tmp_path / "result.xlsx",
        recipe=recipe,
    )

    assert request.recipe is recipe


def test_request_validation_rejects_recipe_with_separate_behavior_settings(
    tmp_path: Path,
) -> None:
    recipe = ConversionRecipe()

    with pytest.raises(RequestValidationError) as caught:
        validate_request(
            DesktopRequest(
                (tmp_path / "input.csv",),
                tmp_path / "result.xlsx",
                sort="filename",
                recipe=recipe,
            )
        )

    assert caught.value.code == "CONVERSION_RECIPE_OPTION_CONFLICT"


def test_request_validation_rejects_simultaneous_single_mapping_and_set(
    tmp_path: Path,
) -> None:
    mapping = PeakTableMapping(
        ColumnSelector("RT", 1),
        ColumnSelector("Area", 2),
        "min",
        PeakTableFormat.CSV,
    )
    mapping_set = PeakTableMappingSet((PeakTableMappingProfile(mapping, "Daily CSV"),))

    with pytest.raises(RequestValidationError) as caught:
        validate_request(
            DesktopRequest(
                (tmp_path / "input.csv",),
                tmp_path / "result.xlsx",
                peak_table_mapping=mapping,
                peak_table_mapping_set=mapping_set,
            )
        )

    assert caught.value.code == "PEAK_MAPPING_MODE_CONFLICT"


def test_desktop_report_preserves_the_same_immutable_conversion_plan(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text("sample_id,area\na,1\n", encoding="utf-8")
    plan = plan_conversion(source, tmp_path / "result.xlsx")

    report = DesktopBatchReport(BatchOutcome.SUCCESS, plan=plan)

    assert report.plan is plan
