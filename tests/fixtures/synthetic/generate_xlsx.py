# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Regenerate the synthetic XLSX peak-table fixture."""

import argparse
import os
import re
import tempfile
import zipfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook  # type: ignore[import-untyped]

_ARCHIVE_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
_CORE_MODIFIED_TIMESTAMP = b"2026-08-15T11:15:08Z"
_CORE_MODIFIED = re.compile(rb"(<dcterms:modified\b[^>]*>)[^<]*(</dcterms:modified>)")


def _normalize_core_properties(content: bytes) -> bytes:
    """Fix the timestamp that openpyxl replaces with current UTC during save."""
    normalized, count = _CORE_MODIFIED.subn(
        rb"\g<1>" + _CORE_MODIFIED_TIMESTAMP + rb"\g<2>",
        content,
    )
    if count != 1:
        raise RuntimeError("docProps/core.xml must contain exactly one modified timestamp")
    return normalized


def _normalize_archive(path: Path) -> None:
    """Rewrite OOXML members with stable ordering and timestamps."""
    with zipfile.ZipFile(path, "r") as source:
        members = tuple(
            (
                info,
                _normalize_core_properties(source.read(info.filename))
                if info.filename == "docProps/core.xml"
                else source.read(info.filename),
            )
            for info in sorted(source.infolist(), key=lambda item: item.filename)
        )
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=".generic_peaks_",
        suffix=".xlsx.tmp",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary = Path(raw_temporary)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as target:
            for original, content in members:
                stable = zipfile.ZipInfo(original.filename, _ARCHIVE_TIMESTAMP)
                stable.compress_type = zipfile.ZIP_DEFLATED
                stable.create_system = original.create_system
                stable.external_attr = original.external_attr
                stable.internal_attr = original.internal_attr
                target.writestr(stable, content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def generate_fixture(output: Path) -> None:
    """Write one deterministic fixture to an explicit destination."""
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.properties.created = datetime(2026, 1, 1)
    workbook.properties.modified = datetime(2026, 1, 1)
    workbook.properties.creator = "LabConvert"
    workbook.properties.lastModifiedBy = "LabConvert"
    worksheet = workbook.active
    worksheet.title = "Peak Table"
    worksheet.append(
        [
            "sample_id",
            "acquired_at",
            "sequence",
            "instrument_type",
            "vendor",
            "channel",
            "detector",
            "runtime",
            "peak_number",
            "retention_time",
            "retention_time_unit",
            "area",
            "height",
            "compound",
            "compound_source",
            "time",
            "signal",
            "x_unit",
            "y_unit",
            "batch_note",
        ]
    )
    worksheet.append(
        [
            "synthetic_xlsx",
            "2026-01-01T04:00:00Z",
            4,
            "GC",
            "Synthetic Instrument",
            "FID-A",
            "FID",
            5,
            1,
            1.25,
            "min",
            1500,
            86,
            "methanol",
            "synthetic",
            0,
            0.4,
            "min",
            "mV",
            "fixture",
        ]
    )
    worksheet.append(
        [
            "synthetic_xlsx",
            "2026-01-01T04:00:00Z",
            4,
            "GC",
            "Synthetic Instrument",
            "FID-A",
            "FID",
            5,
            2,
            2.5,
            "min",
            2800,
            135,
            "ethanol",
            "synthetic",
            1,
            1.8,
            "min",
            "mV",
            "fixture",
        ]
    )
    workbook.save(output)
    _normalize_archive(output)


def main(argv: Sequence[str] | None = None) -> None:
    """Generate the committed fixture or an explicit temporary output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("generic_peaks.xlsx"),
        help="Destination XLSX path (defaults to the committed synthetic fixture).",
    )
    arguments = parser.parse_args(argv)
    generate_fixture(arguments.output)


if __name__ == "__main__":
    main()
