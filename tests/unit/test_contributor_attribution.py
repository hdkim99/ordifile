# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "ci"))
import verify_contributor_attribution as attribution  # noqa: E402


@pytest.mark.parametrize(
    "identity",
    (
        "Claude",
        "Claude Code",
        "Anthropic",
        "Codex",
        "OpenAI",
        "ChatGPT",
        "GitHub Copilot",
        "Gemini",
        "Cursor",
        "AI agent",
        "automated coding assistant",
    ),
)
@pytest.mark.parametrize("label", ("Co-authored-by", "Co-Authored-By", "Signed-off-by"))
def test_ai_attribution_trailers_are_rejected(identity: str, label: str) -> None:
    findings = attribution.scan_message(
        f"A useful change\n\n{label}: {identity} <tool@example.invalid>\n",
        location="test-message",
    )

    assert len(findings) == 1
    assert findings[0].category == "attribution trailer"


def test_human_attribution_and_technical_ai_discussion_are_allowed() -> None:
    message = """Document contributor policy.

The project may discuss Claude, Codex, OpenAI, or Copilot as tools.
Co-authored-by: Human Contributor <human@example.invalid>
Signed-off-by: Human Contributor <human@example.invalid>
"""

    assert attribution.scan_message(message, location="test-message") == ()


def test_human_name_and_employer_domain_are_not_mistaken_for_tools() -> None:
    message = """Preserve real people.

Co-authored-by: Claude Dupont <human@example.invalid>
Signed-off-by: Human Contributor <human@openai.com>
"""

    assert attribution.scan_message(message, location="test-message") == ()


@pytest.mark.parametrize("label", ("Author", "Authored-by", "Committer", "Contributor"))
def test_other_author_like_ai_trailers_are_rejected(label: str) -> None:
    findings = attribution.scan_message(
        f"{label} : Codex <tool@example.invalid>", location="test-message"
    )

    assert len(findings) == 1
    assert findings[0].category == "attribution trailer"


@pytest.mark.parametrize(
    "identity", ("OpenAI Codex", "Codex OpenAI", "Anthropic Claude", "Google Gemini")
)
def test_composite_tool_identities_are_rejected(identity: str) -> None:
    findings = attribution.scan_identity(
        f"{identity} <tool@example.invalid>", location="test-commit", category="commit author"
    )

    assert len(findings) == 1


@pytest.mark.parametrize("category", ("commit author", "commit committer"))
def test_automated_tool_author_identity_is_rejected(category: str) -> None:
    findings = attribution.scan_identity(
        "Codex <tool@example.invalid>", location="test-commit", category=category
    )

    assert len(findings) == 1
    assert findings[0].category == category


def test_pull_request_body_attribution_is_rejected_without_echoing_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Human Maintainer"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "human@example.invalid"], cwd=repository, check=True
    )
    (repository / "README.md").write_text("safe\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "Initial"], cwd=repository, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "title": "Safe title",
                    "body": "Co-authored-by: Claude <private@example.invalid>",
                    "base": {"sha": head},
                    "head": {"sha": head},
                }
            }
        ),
        encoding="utf-8",
    )

    result = attribution.main(
        [
            "--workspace",
            str(repository),
            "--event",
            str(event),
            "--event-name",
            "pull_request",
        ]
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "pull-request-body" in output
    assert "Claude" not in output
    assert "private@example.invalid" not in output


def test_tracked_file_attribution_is_rejected_but_binary_is_ignored(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Human Maintainer"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "human@example.invalid"], cwd=repository, check=True
    )
    (repository / "NOTICE").write_text(
        "Co-authored-by: automated coding assistant <tool@example.invalid>\n",
        encoding="utf-8",
    )
    (repository / "binary.dat").write_bytes(b"\x00Co-authored-by: Claude <tool@example.invalid>\n")
    subprocess.run(["git", "add", "NOTICE", "binary.dat"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "Initial"], cwd=repository, check=True)

    findings = attribution.verify_repository(workspace=repository)

    assert len(findings) == 1
    assert findings[0].location.startswith("tracked-file-")
    assert findings[0].location.endswith(":line-1")
    assert "NOTICE" not in findings[0].location


def test_pull_request_commit_range_rejects_a_new_ai_coauthor(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Human Maintainer"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "human@example.invalid"], cwd=repository, check=True
    )
    (repository / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "Initial"], cwd=repository, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repository / "README.md").write_text("feature\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-qm",
            "Feature\n\nCo-authored-by: Claude <tool@example.invalid>",
        ],
        cwd=repository,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    event: dict[str, object] = {
        "event_name": "pull_request",
        "pull_request": {
            "title": "Safe title",
            "body": "Technical discussion of automated tools is allowed.",
            "base": {"sha": base},
            "head": {"sha": head},
        },
    }

    findings = attribution.verify_repository(workspace=repository, event=event)

    assert len(findings) == 1
    assert findings[0].category == "attribution trailer"
    assert findings[0].location.startswith(f"commit-{head[:12]}")


def test_cli_does_not_echo_a_private_unreadable_input_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    private_path = tmp_path / "private-person-name" / "missing-message"

    result = attribution.main(["--workspace", str(tmp_path), "--message-file", str(private_path)])

    output = capsys.readouterr().out
    assert result == 1
    assert "private-person-name" not in output
    assert "missing-message" not in output
    assert "local input could not be inspected" in output


@pytest.mark.parametrize(
    ("limit_name", "limit"),
    (
        ("MAX_TRACKED_FILES", 0),
        ("MAX_TRACKED_TEXT_BYTES", 1),
        ("MAX_TOTAL_TRACKED_TEXT_BYTES", 1),
    ),
)
def test_tracked_file_resource_limits_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit_name: str, limit: int
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Human Maintainer"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "human@example.invalid"], cwd=repository, check=True
    )
    (repository / "one.txt").write_text("safe\n", encoding="utf-8")
    (repository / "two.txt").write_text("safe\n", encoding="utf-8")
    subprocess.run(["git", "add", "one.txt", "two.txt"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "Initial"], cwd=repository, check=True)
    monkeypatch.setattr(attribution, limit_name, limit)

    with pytest.raises(attribution.AttributionVerificationError):
        attribution.verify_repository(workspace=repository)


def test_symlink_content_is_not_followed_and_control_filename_is_not_reported(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    private = tmp_path / "private-source"
    private.write_text(
        "Co-authored-by: Codex <tool@example.invalid>\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Human Maintainer"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "human@example.invalid"], cwd=repository, check=True
    )
    (repository / "safe-link").symlink_to(private)
    unsafe_name = "private\x1bname\nmetadata"
    (repository / unsafe_name).write_text(
        "Co-authored-by: Codex <tool@example.invalid>\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "safe-link", unsafe_name], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "Initial"], cwd=repository, check=True)

    findings = attribution.verify_repository(workspace=repository)

    assert len(findings) == 1
    assert findings[0].location.startswith("tracked-file-")
    assert "private" not in findings[0].location
    assert "\x1b" not in findings[0].location
    assert "\n" not in findings[0].location
