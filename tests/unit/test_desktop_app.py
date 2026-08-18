# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from ordifile.desktop import app


def test_missing_gui_extra_returns_bounded_helpful_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(_argv: object = None) -> object:
        raise ModuleNotFoundError(name="PySide6")

    monkeypatch.setattr(app, "create_application", missing)

    assert app.main([]) == app.MISSING_GUI_EXIT
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "pip install 'ordifile[gui]'" in captured.err
    assert "Traceback" not in captured.err


def test_bootstrap_does_not_hide_unrelated_missing_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(_argv: object = None) -> object:
        raise ModuleNotFoundError(name="unrelated_dependency")

    monkeypatch.setattr(app, "create_application", missing)

    with pytest.raises(ModuleNotFoundError) as caught:
        app.main([])

    assert caught.value.name == "unrelated_dependency"
