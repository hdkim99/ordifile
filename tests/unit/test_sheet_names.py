from __future__ import annotations

from labconvert.exporters.excel import sanitize_sheet_name


def test_sheet_names_remove_forbidden_characters_and_limit_length() -> None:
    used: set[str] = set()
    value = sanitize_sheet_name("a[]:*?/\\" + "x" * 40, used)
    assert len(value) <= 31
    assert not any(character in value for character in "[]:*?/\\")


def test_sheet_names_are_case_insensitively_unique_and_history_is_reserved() -> None:
    used: set[str] = set()
    assert sanitize_sheet_name("History", used) == "History_"
    first = sanitize_sheet_name("Signals_FID", used)
    second = sanitize_sheet_name("signals_fid", used)
    assert first == "Signals_FID"
    assert second.casefold() != first.casefold()


def test_control_noncharacter_and_normalization_collisions_are_sanitized() -> None:
    used: set[str] = set()
    first = sanitize_sheet_name("FID\x01?\ufdd0", used)
    second = sanitize_sheet_name("FID___", used)
    assert first == "FID___"
    assert second == "FID____2"
    assert all(ord(character) >= 32 for character in first)
    assert "\ufdd0" not in first

    composed = sanitize_sheet_name("Résumé", used)
    decomposed = sanitize_sheet_name("Re\u0301sume\u0301", used)
    assert composed == "Résumé"
    assert decomposed == "Résumé_2"
    assert sanitize_sheet_name("FID_x000D_signal", used) == "FID_signal"
