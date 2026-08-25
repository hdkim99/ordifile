# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import subprocess
import sys
import zipfile
from importlib.util import find_spec
from pathlib import Path

import pytest

import ordifile
from ordifile.cli.main import main

PROJECT_ROOT = Path(__file__).parents[2]


def test_package_version() -> None:
    assert ordifile.__version__ == "0.5.1"
    assert find_spec("labconvert") is None


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--help"])

    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "usage: ordifile" in output
    assert "Batch-convert" in output


def test_built_wheel_contains_only_ordifile_package_and_entry_points(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--outdir",
            str(tmp_path),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    wheels = tuple(tmp_path.glob("ordifile-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        members = tuple(archive.namelist())
        assert any(name.startswith("ordifile/") for name in members)
        assert "ordifile/desktop/assets/ordifile-icon-512.png" in members
        assert not any(name.startswith("labconvert/") for name in members)
        entry_point_name = next(
            name for name in members if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = archive.read(entry_point_name).decode("utf-8")
        metadata_name = next(name for name in members if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")

    assert entry_points.splitlines() == [
        "[console_scripts]",
        "ordifile = ordifile.cli.main:main",
        "ordifile-gui = ordifile.desktop.app:main",
    ]
    assert "labconvert" not in entry_points.casefold()
    assert "Name: ordifile\n" in metadata
    assert "Project-URL: Documentation, https://github.com/hdkim99/ordifile#readme" in metadata
    assert "Project-URL: Issues, https://github.com/hdkim99/ordifile/issues" in metadata
    assert "Project-URL: Repository, https://github.com/hdkim99/ordifile" in metadata
    assert "Requires-Dist: olefile<0.48,>=0.47" in metadata
    assert "Provides-Extra: gui" in metadata
    assert "Requires-Dist: pyside6-essentials==6.11.2; extra == 'gui'" in metadata
    assert "Requires-Dist: pyside6-essentials==6.11.2\n" not in metadata
    assert "Requires-Dist: types-olefile==0.47.0.20260508; extra == 'dev'" in metadata
    assert "Requires-Dist: types-olefile==0.47.0.20260508\n" not in metadata
