# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "ci"))
import clean_workspace as cleanup  # noqa: E402


def _workspace(path: Path) -> Path:
    path.mkdir()
    (path / ".git").mkdir()
    return path


def test_cleanup_removes_exact_generated_allowlist_and_is_idempotent(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    generated_directories = (
        ".ci-venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        "fixture-cache",
        "htmlcov",
        "release-artifact",
        "release-download",
        ".github/.tmp",
        ".research-downloads/external",
        "src/ordifile.egg-info",
        "src/ordifile/__pycache__",
    )
    for relative in generated_directories:
        directory = workspace / relative
        directory.mkdir(parents=True)
        (directory / "generated.bin").write_bytes(b"generated")
    generated_files = (
        ".coverage",
        ".coverage.worker-1",
        "Ordifile_Result.xlsx",
        "Ordifile_Result_Peaks_001.csv",
        "src/ordifile/generated.pyc",
    )
    for relative in generated_files:
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"generated")
    preserved = (
        ".github/workflows/ci.yml",
        ".research-downloads/keep.txt",
        "src/ordifile/module.py",
        "research-results.xlsx",
        "Ordifile_Result.notes.txt",
    )
    for relative in preserved:
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("preserve\n", encoding="utf-8")

    removed = cleanup.clean_workspace(workspace, phase="pre")

    assert removed
    assert all(not (workspace / relative).exists() for relative in generated_directories)
    assert all(not (workspace / relative).exists() for relative in generated_files)
    assert all((workspace / relative).is_file() for relative in preserved)
    assert cleanup.clean_workspace(workspace, phase="post") == ()


def test_cleanup_unlinks_allowlisted_symlink_without_touching_outside(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside\n", encoding="utf-8")
    try:
        (workspace / ".ci-venv").symlink_to(outside, target_is_directory=True)
        (workspace / ".research-downloads").mkdir()
        (workspace / ".research-downloads" / "external").symlink_to(
            outside,
            target_is_directory=True,
        )
    except OSError:
        pytest.skip("symlink creation is unavailable")

    cleanup.clean_workspace(workspace, phase="post")

    assert sentinel.read_text(encoding="utf-8") == "outside\n"
    assert not (workspace / ".ci-venv").exists()
    assert not (workspace / ".research-downloads" / "external").exists()


@pytest.mark.parametrize("parent", [".github", ".research-downloads"])
def test_cleanup_rejects_allowlisted_target_beneath_symlink_parent(
    tmp_path: Path,
    parent: str,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    outside = tmp_path / "outside"
    target_name = ".tmp" if parent == ".github" else "external"
    outside_target = outside / target_name
    outside_target.mkdir(parents=True)
    sentinel = outside_target / "sentinel.txt"
    sentinel.write_text("outside\n", encoding="utf-8")
    try:
        (workspace / parent).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(cleanup.WorkspaceCleanupError, match="symlink parent"):
        cleanup.clean_workspace(workspace, phase="post")

    assert sentinel.read_text(encoding="utf-8") == "outside\n"
    assert (workspace / parent).is_symlink()


def test_cleanup_rejects_broad_nonrepository_and_symlink_roots(tmp_path: Path) -> None:
    with pytest.raises(cleanup.WorkspaceCleanupError, match="root"):
        cleanup.clean_workspace(Path(Path.cwd().anchor), phase="pre")
    with pytest.raises(cleanup.WorkspaceCleanupError, match="root"):
        cleanup.clean_workspace(Path.home(), phase="pre")

    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    with pytest.raises(cleanup.WorkspaceCleanupError, match=".git"):
        cleanup.clean_workspace(ordinary, phase="pre")

    workspace = _workspace(tmp_path / "workspace")
    alias = tmp_path / "workspace-link"
    try:
        alias.symlink_to(workspace, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(cleanup.WorkspaceCleanupError, match="symlink"):
        cleanup.clean_workspace(alias, phase="pre")


def test_cleanup_rejects_invalid_phase_before_deleting(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    generated = workspace / "dist"
    generated.mkdir()

    with pytest.raises(cleanup.WorkspaceCleanupError, match="phase"):
        cleanup.clean_workspace(workspace, phase="invalid")

    assert generated.is_dir()
