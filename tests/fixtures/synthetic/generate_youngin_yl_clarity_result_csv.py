# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generate invented YL-Clarity-style Result Table exports for exact-profile tests."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

RESULT_HEADERS = (
    "Signal No.",
    "Signal Name",
    "Peak No.",
    "Reten. time [min]",
    "Area [mV.s]",
    "Height [mV]",
    "Area [%]",
    "Height [%]",
    "W05 [min]",
)

PeakValues = tuple[str, str, str, str, str, str]


def _metadata_block(signal_number: int) -> list[str]:
    rows = (
        ("Synthetic", "Profile", str(signal_number), "Local"),
        ("Table", "invented", "data", "only", "safe"),
        ("Source", "synthetic"),
        ("Run", "offline", "Signal", str(signal_number)),
        tuple(f"field-{index}" for index in range(34)),
        ("Method", "not", "vendor", "or", "private"),
        ("Instrument", "synthetic", "Detector", "unresolved", "Unit", "mV", "safe"),
        ("End", "block"),
    )
    return ["\t".join(row) for row in rows]


def _result_section(
    signal_number: int,
    signal_name: str,
    peaks: Sequence[PeakValues],
) -> list[str]:
    rows = ["\t".join(RESULT_HEADERS)]
    if not peaks:
        rows.append(
            "\t".join(
                (str(signal_number), signal_name, "No peak to report", *("" for _ in range(22)))
            )
        )
        rows.append("")
        return rows
    areas: list[Decimal] = []
    heights: list[Decimal] = []
    for peak_number, values in enumerate(peaks, start=1):
        retention, area, height, area_percent, height_percent, width_05 = values
        areas.append(Decimal(area))
        heights.append(Decimal(height))
        rows.append(
            "\t".join(
                (
                    str(signal_number),
                    signal_name,
                    str(peak_number),
                    retention,
                    area,
                    height,
                    area_percent,
                    height_percent,
                    width_05,
                )
            )
        )
    rows.append(
        "\t".join(
            (
                str(signal_number),
                signal_name,
                "",
                "Total",
                str(sum(areas)),
                str(sum(heights)),
                "100",
                "100",
                "",
            )
        )
    )
    rows.append("")
    return rows


def synthetic_result_csv_bytes(
    *,
    variant: str = "single_tcd",
    tcd_peaks: Sequence[PeakValues] = (
        ("1.25", "100.5", "10.25", "40", "25", "0.05"),
        ("2.5", "150.75", "30.75", "60", "75", "0.08"),
    ),
) -> bytes:
    """Return invented CP949/CRLF/tab bytes for one observed section variant."""
    sections: tuple[tuple[int, str, Sequence[PeakValues]], ...]
    if variant == "single_tcd":
        sections = ((1, "TCD", tcd_peaks),)
    elif variant == "empty_fid_then_tcd":
        sections = ((1, "FID", ()), (2, "TCD", tcd_peaks))
    else:
        raise ValueError("unsupported synthetic section variant")

    lines: list[str] = []
    for signal_number, signal_name, peaks in sections:
        lines.extend(_result_section(signal_number, signal_name, peaks))
    for signal_number, _signal_name, _peaks in sections:
        lines.extend(_metadata_block(signal_number))
        lines.extend(("", ""))
    lines.append("\t\tSynthetic report\tNo identities\tOffline\t\t\t\t\t\t")
    lines.append(
        "\t\t\t\t\tReten. Time [min]\tResponse\tAmount [N/A]\tAmount% [%]\tPeak Type\tCompound Name"
    )
    lines.append("")
    return ("\r\n".join(lines) + "\r\n").encode("cp949")
