# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate invented bytes for the exact LECO GCxGC Result text grammar."""

from __future__ import annotations

HEADERS = (
    "Name",
    "1st Dimension Time (s)",
    "2nd Dimension Time (s)",
    "Area",
    "Height",
    "Spectra",
    "wb1",
    "wb2",
    "Retention Index",
)

DEFAULT_PEAKS = (
    ("Synthetic Alpha", "120", "0.450", "100000", "5000", "43:999 58:250", "8", "0.120", "850.0"),
    ("Synthetic Beta", "180", "0.875", "250000", "12000", "57:999 71:400", "12", "0.180", "920.5"),
    (
        "Synthetic Gamma",
        "240",
        "1.250",
        "400000",
        "18000",
        "69:999 83:300",
        "16",
        "0.240",
        "1001.0",
    ),
)


def synthetic_gcgc_result_bytes(
    *, peaks: tuple[tuple[str, str, str, str, str, str, str, str, str], ...] = DEFAULT_PEAKS
) -> bytes:
    """Return deterministic public-safe CRLF/tab bytes."""
    rows = (HEADERS, *peaks)
    return ("\r\n".join("\t".join(row) for row in rows) + "\r\n").encode("ascii")
