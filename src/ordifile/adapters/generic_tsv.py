# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generic tab-delimited export adapter."""

from typing import ClassVar

from ordifile.adapters._delimited import DelimitedAdapter
from ordifile.adapters.base import AdapterDescriptor


class GenericTsvAdapter(DelimitedAdapter):
    """Read an explicit-schema tab-delimited UTF-8 table."""

    adapter_id: ClassVar[str] = "generic_tsv"
    delimiter: ClassVar[str] = "\t"
    preferred_extensions: ClassVar[tuple[str, ...]] = (".tsv", ".txt")
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        "0.1.0",
        "Generic TSV table",
        preferred_extensions,
        True,
        True,
        True,
        True,
    )
