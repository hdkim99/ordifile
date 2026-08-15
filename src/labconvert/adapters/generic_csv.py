# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

"""Generic comma-delimited export adapter."""

from typing import ClassVar

from labconvert.adapters._delimited import DelimitedAdapter
from labconvert.adapters.base import AdapterDescriptor


class GenericCsvAdapter(DelimitedAdapter):
    """Read an explicit-schema comma-delimited UTF-8 table."""

    adapter_id: ClassVar[str] = "generic_csv"
    delimiter: ClassVar[str] = ","
    preferred_extensions: ClassVar[tuple[str, ...]] = (".csv",)
    descriptor: ClassVar[AdapterDescriptor] = AdapterDescriptor(
        adapter_id,
        "0.1.0",
        "Generic CSV table",
        preferred_extensions,
        True,
        True,
        True,
        True,
    )
