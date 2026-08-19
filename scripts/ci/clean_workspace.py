# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Remove only allowlisted CI artifacts from a checked-out Ordifile workspace."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import Never

TOP_LEVEL_DIRECTORIES = frozenset(
    {
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        "htmlcov",
        "release-artifact",
        "release-download",
        "standalone-candidate",
        "standalone-smoke-kit",
    }
)
RELATIVE_DIRECTORIES = (Path(".github/.tmp"),)
RECURSIVE_DIRECTORY_SUFFIXES = (".egg-info",)
RECURSIVE_DIRECTORY_NAMES = frozenset({"__pycache__"})
TOP_LEVEL_FILES = frozenset(
    {
        ".coverage",
        "Ordifile_Result.xlsx",
        "standalone-smoke-report.json",
    }
)
GENERATED_FILE_SUFFIXES = (".pyc", ".pyo")


class WorkspaceCleanupError(RuntimeError):
    """The requested cleanup root or target was unsafe."""


def _validated_workspace(value: Path) -> Path:
    absolute = Path(os.path.abspath(value))
    if absolute.is_symlink():
        raise WorkspaceCleanupError("workspace must not be a symlink")
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as error:
        raise WorkspaceCleanupError("workspace must be an existing directory") from error
    if not resolved.is_dir():
        raise WorkspaceCleanupError("workspace must be an existing directory")
    filesystem_root = Path(resolved.anchor)
    if resolved == filesystem_root or resolved == Path.home().resolve():
        raise WorkspaceCleanupError("refusing to clean a filesystem or home root")
    marker = resolved / ".git"
    if not marker.exists() or marker.is_symlink():
        raise WorkspaceCleanupError("workspace must contain a non-symlink .git marker")
    return resolved


def _remove_target(workspace: Path, target: Path) -> bool:
    absolute = Path(os.path.abspath(target))
    if absolute == workspace or not absolute.is_relative_to(workspace):
        raise WorkspaceCleanupError("cleanup target escapes the workspace")
    if not os.path.lexists(target):
        return False
    relative_parent = absolute.parent.relative_to(workspace)
    current = workspace
    for part in relative_parent.parts:
        current /= part
        if current.is_symlink():
            raise WorkspaceCleanupError("cleanup target has a symlink parent")
    try:
        resolved_parent = absolute.parent.resolve(strict=True)
    except OSError as error:
        raise WorkspaceCleanupError("cleanup target parent cannot be resolved safely") from error
    if resolved_parent != workspace and not resolved_parent.is_relative_to(workspace):
        raise WorkspaceCleanupError("cleanup target parent escapes the workspace")
    if target.is_symlink():
        target.unlink()
        return True
    if target.is_dir():
        shutil.rmtree(target)
        return True
    target.unlink()
    return True


def _recursive_targets(workspace: Path) -> tuple[Path, ...]:
    targets: list[Path] = []
    for current, directories, files in os.walk(workspace, topdown=True, followlinks=False):
        current_path = Path(current)
        if current_path == workspace:
            directories[:] = [
                name for name in directories if name != ".git" and name not in TOP_LEVEL_DIRECTORIES
            ]
        else:
            directories[:] = [name for name in directories if name != ".git"]
        for name in tuple(directories):
            if name in RECURSIVE_DIRECTORY_NAMES or name.endswith(RECURSIVE_DIRECTORY_SUFFIXES):
                targets.append(current_path / name)
                directories.remove(name)
        targets.extend(
            current_path / name for name in files if name.endswith(GENERATED_FILE_SUFFIXES)
        )
    return tuple(targets)


def _top_level_file_targets(workspace: Path) -> tuple[Path, ...]:
    targets: list[Path] = []
    for candidate in workspace.iterdir():
        name = candidate.name
        if name in TOP_LEVEL_FILES or name.startswith(".coverage."):
            targets.append(candidate)
            continue
        if name.startswith("Ordifile_Result") and candidate.suffix.casefold() in {
            ".csv",
            ".parquet",
            ".xlsx",
        }:
            targets.append(candidate)
    return tuple(targets)


def clean_workspace(workspace: Path, *, phase: str) -> tuple[Path, ...]:
    """Clean allowlisted artifacts and return their workspace-relative paths."""
    if phase not in {"pre", "post"}:
        raise WorkspaceCleanupError("phase must be 'pre' or 'post'")
    root = _validated_workspace(workspace)
    candidates = [root / name for name in sorted(TOP_LEVEL_DIRECTORIES)]
    candidates.extend(root / relative for relative in RELATIVE_DIRECTORIES)
    candidates.extend(sorted(_top_level_file_targets(root)))
    candidates.extend(sorted(_recursive_targets(root)))
    removed: list[Path] = []
    seen: set[Path] = set()
    for target in candidates:
        if target in seen:
            continue
        seen.add(target)
        if _remove_target(root, target):
            removed.append(target.relative_to(root))
    return tuple(removed)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--phase", choices=("pre", "post"), required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        removed = clean_workspace(arguments.workspace, phase=arguments.phase)
    except WorkspaceCleanupError as error:
        print(f"workspace cleanup failed: {error}")
        return 1
    print(f"workspace cleanup ({arguments.phase}): removed {len(removed)} allowlisted artifacts")
    return 0


def _entry_point() -> Never:
    raise SystemExit(main())


if __name__ == "__main__":
    _entry_point()
