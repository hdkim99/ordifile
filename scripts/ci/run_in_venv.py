# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Create, use, and remove a runner-temporary virtual environment safely."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import venv
from pathlib import Path
from typing import Never


class EnvironmentError(RuntimeError):
    """The requested temporary environment operation was unsafe."""


_GITHUB_JOB_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,100}")
_GITHUB_SUFFIX_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,40}")


def github_environment_paths(environment: dict[str, str] | None = None) -> tuple[Path, Path]:
    """Derive the unique environment path from bounded GitHub runner variables."""
    values = os.environ if environment is None else environment
    try:
        runner_temp = Path(values["RUNNER_TEMP"])
        run_id = values["GITHUB_RUN_ID"]
        run_attempt = values["GITHUB_RUN_ATTEMPT"]
        job = values["GITHUB_JOB"]
    except KeyError as error:
        raise EnvironmentError("required GitHub runner environment is unavailable") from error
    if not run_id.isascii() or not run_id.isdecimal() or len(run_id) > 20:
        raise EnvironmentError("GitHub run ID is invalid")
    if not run_attempt.isascii() or not run_attempt.isdecimal() or len(run_attempt) > 10:
        raise EnvironmentError("GitHub run attempt is invalid")
    if _GITHUB_JOB_PATTERN.fullmatch(job) is None:
        raise EnvironmentError("GitHub job ID is invalid")
    suffix = values.get("ORDIFILE_CI_VENV_SUFFIX")
    if suffix is not None and _GITHUB_SUFFIX_PATTERN.fullmatch(suffix) is None:
        raise EnvironmentError("GitHub environment suffix is invalid")
    name = f"ordifile-{run_id}-{run_attempt}-{job}"
    if suffix is not None:
        name = f"{name}-{suffix}"
    return runner_temp / name, runner_temp


def _validated_paths(environment: Path, runner_temp: Path) -> tuple[Path, Path]:
    temp_absolute = Path(os.path.abspath(runner_temp))
    environment_absolute = Path(os.path.abspath(environment))
    try:
        temp_resolved = temp_absolute.resolve(strict=True)
    except OSError as error:
        raise EnvironmentError("runner temporary directory must exist") from error
    if (
        not temp_resolved.is_dir()
        or temp_absolute.is_symlink()
        or temp_resolved == Path(temp_resolved.anchor)
        or temp_resolved == Path.home().resolve()
    ):
        raise EnvironmentError("runner temporary directory is unsafe")
    try:
        relative = environment_absolute.relative_to(temp_absolute)
    except ValueError as error:
        raise EnvironmentError(
            "environment must be inside the runner temporary directory"
        ) from error
    if len(relative.parts) != 1 or not relative.name.startswith("ordifile-"):
        raise EnvironmentError("environment must be a direct Ordifile runner-temporary child")
    if environment_absolute.parent.resolve(strict=True) != temp_resolved:
        raise EnvironmentError("environment parent escapes the runner temporary directory")
    return environment_absolute, temp_resolved


def create_environment(environment: Path, runner_temp: Path) -> Path:
    """Create a fresh virtual environment and return its lexical root."""
    target, _ = _validated_paths(environment, runner_temp)
    if os.path.lexists(target):
        raise EnvironmentError("environment already exists")
    venv.EnvBuilder(with_pip=True, clear=False, symlinks=os.name != "nt").create(target)
    return target


def _environment_executable(environment: Path, name: str) -> Path:
    if name not in {"python", "ordifile"}:
        raise EnvironmentError("executable must be 'python' or 'ordifile'")
    directory = environment / ("Scripts" if os.name == "nt" else "bin")
    suffix = ".exe" if os.name == "nt" else ""
    executable = directory / f"{name}{suffix}"
    if not executable.is_file():
        raise EnvironmentError(f"environment executable is unavailable: {name}")
    return executable


def run_in_environment(
    environment: Path,
    runner_temp: Path,
    *,
    executable: str,
    arguments: tuple[str, ...],
) -> int:
    """Run one environment executable without activating or changing process PATH."""
    target, _ = _validated_paths(environment, runner_temp)
    if target.is_symlink() or not (target / "pyvenv.cfg").is_file():
        raise EnvironmentError("environment is missing or invalid")
    command = _environment_executable(target, executable)
    return subprocess.run([str(command), *arguments], check=False).returncode


def remove_environment(environment: Path, runner_temp: Path) -> bool:
    """Remove only a direct Ordifile child of the configured runner temp root."""
    target, _ = _validated_paths(environment, runner_temp)
    if not os.path.lexists(target):
        return False
    if target.is_symlink():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    else:
        raise EnvironmentError("environment target is not a directory")
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for operation in ("create", "remove"):
        command = subparsers.add_parser(operation)
        command.add_argument("--venv", type=Path)
        command.add_argument("--runner-temp", type=Path)
        command.add_argument("--github-runner", action="store_true")
    run = subparsers.add_parser("run")
    run.add_argument("--venv", type=Path)
    run.add_argument("--runner-temp", type=Path)
    run.add_argument("--github-runner", action="store_true")
    run.add_argument("--executable", choices=("python", "ordifile"), default="python")
    run.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def _requested_paths(arguments: argparse.Namespace) -> tuple[Path, Path]:
    if arguments.github_runner:
        if arguments.venv is not None or arguments.runner_temp is not None:
            raise EnvironmentError("GitHub runner mode cannot be combined with explicit paths")
        return github_environment_paths()
    if arguments.venv is None or arguments.runner_temp is None:
        raise EnvironmentError("explicit environment and runner temporary paths are required")
    return arguments.venv, arguments.runner_temp


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        environment, runner_temp = _requested_paths(arguments)
        if arguments.operation == "create":
            create_environment(environment, runner_temp)
            return 0
        if arguments.operation == "remove":
            remove_environment(environment, runner_temp)
            return 0
        command_arguments = tuple(arguments.arguments)
        if command_arguments[:1] == ("--",):
            command_arguments = command_arguments[1:]
        return run_in_environment(
            environment,
            runner_temp,
            executable=arguments.executable,
            arguments=command_arguments,
        )
    except EnvironmentError as error:
        print(f"isolated environment operation failed: {error}")
        return 1


def _entry_point() -> Never:
    raise SystemExit(main())


if __name__ == "__main__":
    _entry_point()
