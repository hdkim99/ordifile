# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

import labconvert
from labconvert.cli.main import main


def test_package_version() -> None:
    assert labconvert.__version__ == "0.1.0"


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--help"])

    assert error.value.code == 0
    assert "Batch-convert" in capsys.readouterr().out
