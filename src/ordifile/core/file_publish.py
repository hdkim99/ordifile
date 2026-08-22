# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Cross-platform atomic publication helpers for local output files."""

from __future__ import annotations

import ctypes
import errno
import os
import platform
from pathlib import Path


def _raise_rename_error(result: int, source: Path, destination: Path) -> None:
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(error_number, os.strerror(error_number), destination)
    raise OSError(
        error_number,
        os.strerror(error_number),
        f"{source!s} -> {destination!s}",
    )


def rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically consume ``source`` without replacing ``destination``."""
    if os.name == "nt":  # pragma: no cover - exercised by Windows CI
        os.rename(source, destination)
        return

    library = ctypes.CDLL(None, use_errno=True)
    encoded_source = os.fsencode(source)
    encoded_destination = os.fsencode(destination)
    current_platform = platform.system()
    if current_platform == "Darwin":  # pragma: no branch - platform-specific
        rename_exclusive = library.renamex_np
        rename_exclusive.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename_exclusive.restype = ctypes.c_int
        _raise_rename_error(
            rename_exclusive(encoded_source, encoded_destination, 0x00000004),
            source,
            destination,
        )
        return
    if current_platform == "Linux":  # pragma: no cover - exercised by Linux CI
        try:
            rename_exclusive = library.renameat2
        except AttributeError as error:
            raise OSError(
                errno.ENOTSUP,
                "Atomic no-replace publication is unavailable on this platform.",
            ) from error
        rename_exclusive.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_exclusive.restype = ctypes.c_int
        _raise_rename_error(
            rename_exclusive(-100, encoded_source, -100, encoded_destination, 1),
            source,
            destination,
        )
        return
    raise OSError(
        errno.ENOTSUP,
        "Atomic no-replace publication is unavailable on this platform.",
    )
