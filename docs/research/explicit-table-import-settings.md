# Explicit table-import settings evidence

Status: implementation evidence, reviewed 2026-08-23.

Ordifile's mapped structured-table intake uses explicit, bounded choices rather than automatic
encoding or scientific-role detection.

- Python's [`csv` documentation](https://docs.python.org/3/library/csv.html) defines explicit
  delimiters/dialects and recommends opening CSV files with `newline=""`. Ordifile keeps its
  existing comma, tab, and semicolon container choices and uses strict parsing.
- Python's [standard encoding table](https://docs.python.org/3/library/codecs.html#standard-encodings)
  provides `utf_8_sig`, `cp949`, and `cp1252`. Ordifile exposes only these reviewed choices for
  explicit mapped text and uses strict decoding without a fallback chain.
- openpyxl's [Workbook API](https://openpyxl.readthedocs.io/en/stable/api/openpyxl.workbook.workbook.html)
  supports exact worksheet-title lookup. The Ordifile desktop presents audited visible titles
  and requires a selection when more than one is available. The existing CLI/API may instead
  resolve exactly one mapping-compatible worksheet and fails when that result is ambiguous.
- Qt for Python's [QComboBox API](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QComboBox.html)
  supports separate user-facing text and machine data, used for readable encoding labels and
  stable typed values.

These sources support only the table-import mechanism. They do not establish chromatography
semantics or vendor compatibility. RT, Area, units, and vendor ownership remain explicit or
fixture-backed Ordifile decisions.
