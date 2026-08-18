# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "ci"))
import run_in_venv as isolated  # noqa: E402


def _record_digest(content: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
    return digest.decode("ascii")


def _write_entrypoint_probe_wheel(path: Path) -> None:
    dist_info = "ordifile_entrypoint_probe-1.0.dist-info"
    contents = {
        "ordifile_entrypoint_probe.py": (
            b"import sys\n"
            b"def main():\n"
            b"    if sys.argv[1:] == ['--version']:\n"
            b"        print('ordifile probe 1.0')\n"
            b"        return 0\n"
            b"    return 2\n"
        ),
        f"{dist_info}/METADATA": (
            b"Metadata-Version: 2.4\nName: ordifile-entrypoint-probe\nVersion: 1.0\n"
        ),
        f"{dist_info}/WHEEL": (
            b"Wheel-Version: 1.0\n"
            b"Generator: ordifile-test\n"
            b"Root-Is-Purelib: true\n"
            b"Tag: py3-none-any\n"
        ),
        f"{dist_info}/entry_points.txt": (
            b"[console_scripts]\nordifile = ordifile_entrypoint_probe:main\n"
        ),
    }
    record_name = f"{dist_info}/RECORD"
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for name, content in contents.items():
        writer.writerow((name, f"sha256={_record_digest(content)}", str(len(content))))
    writer.writerow((record_name, "", ""))
    contents[record_name] = output.getvalue().encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in contents.items():
            archive.writestr(name, content)


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


def test_installed_entrypoint_resolution_uses_active_venv_not_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    environment = runner_temp / "ordifile-entrypoint-test"
    wheel = tmp_path / "ordifile_entrypoint_probe-1.0-py3-none-any.whl"
    output = tmp_path / "entrypoint-result.json"
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    _write_entrypoint_probe_wheel(wheel)

    isolated.create_environment(environment, runner_temp)
    assert (
        isolated.run_in_environment(
            environment,
            runner_temp,
            executable="python",
            arguments=("-m", "pip", "install", "--no-deps", "--no-cache-dir", str(wheel)),
        )
        == 0
    )
    monkeypatch.setenv("PATH", str(empty_path))
    probe = f"""
import json
import os
import shutil
import subprocess
import sysconfig
from pathlib import Path

scripts = Path(sysconfig.get_path("scripts"))
executable = scripts / ("ordifile.exe" if os.name == "nt" else "ordifile")
completed = subprocess.run(
    [executable, "--version"], check=False, capture_output=True, text=True
)
Path({str(output)!r}).write_text(
    json.dumps(
        {{
            "scripts": str(scripts),
            "entrypoint_exists": executable.is_file(),
            "path_lookup": shutil.which("ordifile"),
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
        }}
    ),
    encoding="utf-8",
)
raise SystemExit(0 if executable.is_file() and completed.returncode == 0 else 1)
"""
    assert (
        isolated.run_in_environment(
            environment,
            runner_temp,
            executable="python",
            arguments=("-c", probe),
        )
        == 0
    )

    result = json.loads(output.read_text(encoding="utf-8"))
    expected_scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    assert Path(result["scripts"]).resolve() == expected_scripts.resolve()
    assert result["entrypoint_exists"] is True
    assert result["path_lookup"] is None
    assert result["returncode"] == 0
    assert result["stdout"] == "ordifile probe 1.0"
    assert isolated.remove_environment(environment, runner_temp)


@pytest.mark.skipif(os.name == "nt", reason="POSIX decoy executable setup")
def test_missing_venv_entrypoint_never_falls_back_to_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    environment = runner_temp / "ordifile-missing-entrypoint"
    decoy_path = tmp_path / "decoy-path"
    decoy_path.mkdir()
    decoy = decoy_path / "ordifile"
    decoy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    decoy.chmod(0o755)

    isolated.create_environment(environment, runner_temp)
    monkeypatch.setenv("PATH", str(decoy_path))
    probe = """
import os
import shutil
import sysconfig
from pathlib import Path

scripts = Path(sysconfig.get_path("scripts"))
executable = scripts / ("ordifile.exe" if os.name == "nt" else "ordifile")
path_candidate = shutil.which("ordifile")
raise SystemExit(0 if path_candidate is not None and not executable.is_file() else 1)
"""
    assert (
        isolated.run_in_environment(
            environment,
            runner_temp,
            executable="python",
            arguments=("-c", probe),
        )
        == 0
    )
    assert isolated.remove_environment(environment, runner_temp)


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


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GITHUB_RUN_ID", "../1"),
        ("GITHUB_RUN_ATTEMPT", "one"),
        ("GITHUB_JOB", "../../outside"),
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
