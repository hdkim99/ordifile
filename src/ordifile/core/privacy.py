# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Platform-neutral privacy checks for external diagnostic and provenance text."""

from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath

ABSOLUTE_PATH_PLACEHOLDER = "[absolute-path-omitted]"

_HTTP_URL = re.compile(r"(?<![A-Za-z0-9+.-])https?://[^\s<>\"']+", re.IGNORECASE)
_AUTHORITY_URI = re.compile(
    r"(?<![A-Za-z0-9+.-])(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://", re.IGNORECASE
)
_FILE_URI = re.compile(r"(?<![A-Za-z0-9+.-])file:", re.IGNORECASE)
_WINDOWS_DRIVE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:(?:[\\/][^\s<>\"']+|[^\s<>\"']+)")
_WINDOWS_UNC = re.compile(r"(?<![\\])\\\\[^\\\s<>\"']+\\[^\s<>\"']+")
_WINDOWS_ROOT = re.compile(r"(?<![\\A-Za-z0-9])\\(?!\\)[^\s<>\"']+")
_POSIX_ABSOLUTE = re.compile(r"(?<![:/A-Za-z0-9_])/(?:[^\s<>\"']+)")
_URI_REFERENCE = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*:")


def contains_machine_local_path(value: str) -> bool:
    """Detect embedded platform paths and non-network local URI schemes."""
    for pattern in (_WINDOWS_DRIVE, _WINDOWS_UNC, _WINDOWS_ROOT):
        for match in pattern.finditer(value):
            windows_path = PureWindowsPath(match.group(0))
            if windows_path.is_absolute() or windows_path.drive or windows_path.root:
                return True
    if _FILE_URI.search(value) is not None:
        return True
    for match in _AUTHORITY_URI.finditer(value):
        if match.group("scheme").casefold() not in {"http", "https"}:
            return True
    http_spans = tuple(match.span() for match in _HTTP_URL.finditer(value))
    for match in _POSIX_ABSOLUTE.finditer(value):
        if any(start <= match.start() < end for start, end in http_spans):
            continue
        if PurePosixPath(match.group(0)).is_absolute():
            return True
    return False


def contains_uri_reference(value: str) -> bool:
    """Detect a URI scheme anywhere in source-controlled provenance text."""
    return _URI_REFERENCE.search(value) is not None


def scrub_machine_local_paths(value: str) -> str:
    """Omit the entire value when a path could otherwise leak a whitespace tail."""
    return ABSOLUTE_PATH_PLACEHOLDER if contains_machine_local_path(value) else value
