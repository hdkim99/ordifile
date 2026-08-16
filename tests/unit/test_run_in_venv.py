# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "ci"))
import run_in_venv as isolated  # noqa: E402


def test_environment_lifecycle_runs_without_path_activation(tmp_path: Path) -> None:
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    environment = runner_temp / "ordifile-test"
    output = tmp_path / "child.txt"

    isolated.create_environment(environment, runner_temp)
    configuration = (environment / "pyvenv.cfg").read_text(encoding="utf-8")
    assert "include-system-site-packages = false" in configuration
    assert (
        isolated.run_in_environment(
            environment,
            runner_temp,
            executable="python",
            arguments=(
                "-c",
                f"from pathlib import Path; Path({str(output)!r}).write_text('child')",
            ),
        )
        == 0
    )
    assert output.read_text(encoding="utf-8") == "child"
    assert isolated.remove_environment(environment, runner_temp)
    assert not environment.exists()
    assert not isolated.remove_environment(environment, runner_temp)


def test_environment_rejects_outside_nested_broad_and_symlink_targets(tmp_path: Path) -> None:
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    outside = tmp_path / "ordifile-outside"
    nested = runner_temp / "nested" / "ordifile-test"

    for target in (outside, nested, runner_temp):
        with pytest.raises(isolated.EnvironmentError):
            isolated.create_environment(target, runner_temp)

    real = runner_temp / "ordifile-real"
    real.mkdir()
    alias = runner_temp / "ordifile-alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    assert isolated.remove_environment(alias, runner_temp)
    assert real.is_dir()


def test_github_environment_path_is_unique_per_attempt_and_job(tmp_path: Path) -> None:
    values: Mapping[str, str] = {
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_RUN_ID": "12345",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_JOB": "required",
    }

    environment, runner_temp = isolated.github_environment_paths(dict(values))

    assert runner_temp == tmp_path
    assert environment == tmp_path / "ordifile-12345-2-required"

    matrix_values = dict(values)
    matrix_values["ORDIFILE_CI_VENV_SUFFIX"] = "py-3.11"
    matrix_environment, _ = isolated.github_environment_paths(matrix_values)
    assert matrix_environment == tmp_path / "ordifile-12345-2-required-py-3.11"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GITHUB_RUN_ID", "../1"),
        ("GITHUB_RUN_ATTEMPT", "one"),
        ("GITHUB_JOB", "../../outside"),
        ("ORDIFILE_CI_VENV_SUFFIX", "../matrix"),
    ],
)
def test_github_environment_path_rejects_unbounded_or_path_like_values(
    tmp_path: Path,
    key: str,
    value: str,
) -> None:
    values = {
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_RUN_ID": "12345",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_JOB": "required",
    }
    values[key] = value

    with pytest.raises(isolated.EnvironmentError, match="GitHub"):
        isolated.github_environment_paths(values)
