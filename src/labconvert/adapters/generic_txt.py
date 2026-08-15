# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generic semicolon-delimited text export adapter."""

from typing import ClassVar

from labconvert.adapters._delimited import DelimitedAdapter
from labconvert.adapters.base import AdapterDescriptor


class GenericSemicolonAdapter(DelimitedAdapter):
    """Read an explicit-schema semicolon-delimited UTF-8 table."""

    adapter_id: ClassVar[str] = "generic_semicolon"
    delimiter: ClassVar[str] = ";"
    preferred_extensions: ClassVar[tuple[str, ...]] = (".txt",)
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        "0.1.0",
        "Generic semicolon-delimited table",
        preferred_extensions,
        True,
        True,
        True,
        True,
    )
