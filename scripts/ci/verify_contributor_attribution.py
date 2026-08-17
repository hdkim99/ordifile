# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Reject automated-tool identities in new repository attribution."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Never

ATTRIBUTION_LABELS = (
    "author",
    "authored-by",
    "co-authored-by",
    "committer",
    "contributed-by",
    "contributor",
    "signed-off-by",
)
PROHIBITED_TOOL_NAMES = frozenset(
    {
        "ai agent",
        "anthropic",
        "automated coding assistant",
        "chatgpt",
        "claude",
        "claude code",
        "codex",
        "copilot",
        "cursor",
        "gemini",
        "github copilot",
        "google gemini",
        "microsoft copilot",
        "openai",
    }
)
PROHIBITED_COMPOSITE_TOKENS = frozenset(
    {"anthropic", "chatgpt", "claude", "codex", "copilot", "cursor", "gemini", "openai"}
)
KNOWN_AUTOMATED_EMAILS = frozenset({"noreply@anthropic.com"})
AUTOMATION_SUFFIXES = (" ai", " agent", " assistant", " bot", " [bot]")
MAX_TRACKED_FILES = 20_000
MAX_TRACKED_TEXT_BYTES = 4 * 1024 * 1024
MAX_TOTAL_TRACKED_TEXT_BYTES = 64 * 1024 * 1024
TRAILER_PATTERN = re.compile(
    rf"^[ \t]*(?P<label>{'|'.join(re.escape(value) for value in ATTRIBUTION_LABELS)})"
    r"[ \t]*:[ \t]*(?P<identity>[^\r\n]+)$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AttributionFinding:
    """Privacy-safe description of a prohibited attribution."""

    location: str
    category: str


class AttributionVerificationError(RuntimeError):
    """The requested repository inspection could not be completed safely."""


def _is_prohibited_identity(value: str) -> bool:
    matched = re.fullmatch(r"(?P<name>.*?)\s*<(?P<email>[^<>]+)>\s*", value.strip())
    if matched is None:
        name = value.strip()
        email = ""
    else:
        name = matched.group("name").strip()
        email = matched.group("email").strip()
    normalized_name = " ".join(name.casefold().split())
    normalized_email = email.casefold()
    if normalized_email in KNOWN_AUTOMATED_EMAILS:
        return True
    if normalized_name in PROHIBITED_TOOL_NAMES:
        return True
    name_tokens = normalized_name.split()
    if len(name_tokens) >= 2 and all(token in PROHIBITED_COMPOSITE_TOKENS for token in name_tokens):
        return True
    return any(
        normalized_name == f"{tool}{suffix}"
        for tool in PROHIBITED_TOOL_NAMES
        for suffix in AUTOMATION_SUFFIXES
    )


def scan_identity(value: str, *, location: str, category: str) -> tuple[AttributionFinding, ...]:
    """Return a finding when an author-like identity names an automated tool."""
    if _is_prohibited_identity(value):
        return (AttributionFinding(location=location, category=category),)
    return ()


def scan_message(value: str, *, location: str) -> tuple[AttributionFinding, ...]:
    """Inspect attribution trailers without treating ordinary technical prose as credit."""
    findings: list[AttributionFinding] = []
    for line_number, line in enumerate(value.splitlines(), start=1):
        matched = TRAILER_PATTERN.fullmatch(line)
        if matched is None:
            continue
        if _is_prohibited_identity(matched.group("identity")):
            findings.append(
                AttributionFinding(
                    location=f"{location}:line-{line_number}",
                    category="attribution trailer",
                )
            )
    return tuple(findings)


def _run_git(arguments: Sequence[str], *, workspace: Path) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise AttributionVerificationError("Git metadata inspection failed")
    return completed.stdout


def _commit_findings(commit: str, *, workspace: Path) -> tuple[AttributionFinding, ...]:
    metadata = _run_git(
        ["show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", commit],
        workspace=workspace,
    )
    values = metadata.split("\x00", maxsplit=4)
    if len(values) != 5:
        raise AttributionVerificationError("Git commit metadata was malformed")
    author_name, author_email, committer_name, committer_email, message = values
    location = f"commit-{commit[:12]}"
    findings = [
        *scan_identity(
            f"{author_name} <{author_email}>", location=location, category="commit author"
        ),
        *scan_identity(
            f"{committer_name} <{committer_email}>",
            location=location,
            category="commit committer",
        ),
        *scan_message(message, location=location),
    ]
    return tuple(findings)


def _commit_range(event: Mapping[str, object]) -> tuple[str, str] | None:
    event_name = event.get("event_name")
    if event_name == "pull_request":
        pull_request = event.get("pull_request")
        if not isinstance(pull_request, Mapping):
            raise AttributionVerificationError("pull request metadata was malformed")
        base = pull_request.get("base")
        head = pull_request.get("head")
        if not isinstance(base, Mapping) or not isinstance(head, Mapping):
            raise AttributionVerificationError("pull request commit range was malformed")
        base_sha = base.get("sha")
        head_sha = head.get("sha")
    elif event_name == "push":
        base_sha = event.get("before")
        head_sha = event.get("after")
    else:
        return None
    if not isinstance(base_sha, str) or not isinstance(head_sha, str):
        raise AttributionVerificationError("event commit range was malformed")
    if len(head_sha) != 40:
        raise AttributionVerificationError("event head commit was malformed")
    if base_sha == "0" * 40:
        return None
    if len(base_sha) != 40:
        raise AttributionVerificationError("event base commit was malformed")
    return base_sha, head_sha


def _event_findings(event: Mapping[str, object]) -> tuple[AttributionFinding, ...]:
    findings: list[AttributionFinding] = []
    pull_request = event.get("pull_request")
    if isinstance(pull_request, Mapping):
        title = pull_request.get("title")
        body = pull_request.get("body")
        if isinstance(title, str):
            findings.extend(scan_message(title, location="pull-request-title"))
        if isinstance(body, str):
            findings.extend(scan_message(body, location="pull-request-body"))
    return tuple(findings)


def _tracked_file_findings(workspace: Path) -> tuple[AttributionFinding, ...]:
    names = _run_git(["ls-files", "-z"], workspace=workspace).split("\x00")
    tracked_names = tuple(name for name in names if name)
    if len(tracked_names) > MAX_TRACKED_FILES:
        raise AttributionVerificationError("The tracked-file count exceeds the inspection limit")
    findings: list[AttributionFinding] = []
    total_bytes = 0
    for name in tracked_names:
        path = workspace / name
        try:
            if path.is_symlink():
                data = str(path.readlink()).encode("utf-8")
            else:
                size = path.stat().st_size
                if size > MAX_TRACKED_TEXT_BYTES:
                    raise AttributionVerificationError(
                        "A tracked file exceeds the attribution inspection limit"
                    )
                data = path.read_bytes()
        except OSError as error:
            raise AttributionVerificationError("A tracked file could not be inspected") from error
        if b"\x00" in data:
            continue
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_TRACKED_TEXT_BYTES:
            raise AttributionVerificationError(
                "Tracked text exceeds the attribution inspection limit"
            )
        text = data.decode("utf-8", errors="replace")
        path_token = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
        findings.extend(scan_message(text, location=f"tracked-file-{path_token}"))
    return tuple(findings)


def verify_repository(
    *,
    workspace: Path,
    event: Mapping[str, object] | None = None,
    message: str | None = None,
) -> tuple[AttributionFinding, ...]:
    """Inspect new commits, mutable tracked files, and optional event/message metadata."""
    findings = list(_tracked_file_findings(workspace))
    if message is not None:
        findings.extend(scan_message(message, location="proposed-commit-message"))
    if event is None:
        findings.extend(_commit_findings("HEAD", workspace=workspace))
        return tuple(findings)
    findings.extend(_event_findings(event))
    commit_range = _commit_range(event)
    if commit_range is None:
        findings.extend(_commit_findings("HEAD", workspace=workspace))
        return tuple(findings)
    base, head = commit_range
    commits = _run_git(["rev-list", "--reverse", f"{base}..{head}"], workspace=workspace)
    for commit in commits.splitlines():
        findings.extend(_commit_findings(commit, workspace=workspace))
    return tuple(findings)


def _load_event(path: Path | None) -> Mapping[str, object] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AttributionVerificationError("GitHub event metadata could not be read") from error
    if not isinstance(value, Mapping):
        raise AttributionVerificationError("GitHub event metadata must be an object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--event", type=Path)
    parser.add_argument("--event-name")
    parser.add_argument("--message-file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        workspace = arguments.workspace.resolve(strict=True)
        event = _load_event(arguments.event)
        if event is not None and arguments.event_name is not None:
            event = {**event, "event_name": arguments.event_name}
        message = (
            arguments.message_file.read_text(encoding="utf-8")
            if arguments.message_file is not None
            else None
        )
        findings = verify_repository(workspace=workspace, event=event, message=message)
    except AttributionVerificationError as error:
        print(f"contributor attribution check failed: {error}")
        return 1
    except (OSError, UnicodeError):
        print("contributor attribution check failed: local input could not be inspected")
        return 1
    if findings:
        print(f"contributor attribution check failed: {len(findings)} prohibited attribution(s)")
        for finding in findings:
            print(f"- {finding.category} at {finding.location}")
        return 1
    print("contributor attribution check: PASS")
    return 0


def _entry_point() -> Never:
    raise SystemExit(main())


if __name__ == "__main__":
    _entry_point()
