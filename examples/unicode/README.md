# Unicode filename example

This directory holds one tiny, fully synthetic CSV whose **filename** uses a
non-ASCII (Korean) name: `시료_신호.csv` ("sample_signal"). The contents are ordinary
generic-schema peak rows — no real person, institution, machine path, or vendor
raw data. Its only purpose is to demonstrate a documented generic-schema edge:
Ordifile preserves normal Unicode input filenames instead of mangling or stripping
them, so the name appears verbatim in the workbook's `Samples` sheet
(`source_file` column).

From the repository root after installation:

```console
ordifile convert examples/unicode --sort filename --output Ordifile_Result.xlsx
```

The command creates one workbook and does not modify the example input. The
generated `Samples` sheet lists `source_file` as `시료_신호.csv` and `status` as
`success`.

## Screenshot

![The Samples sheet of the workbook generated from the Unicode-named example file; the source_file column reads 시료_신호.csv](https://raw.githubusercontent.com/hdkim99/ordifile/main/docs/assets/unicode-example-samples.png)

The PNG is rendered from the **actual** workbook the command above produces
(`docs/assets/unicode-example-samples.png`). It is generated — not a hand-drawn
mock — with `render_screenshot.py`, which reads the workbook with the same
openpyxl reader the integration tests use and draws the real cell values:

```console
ordifile convert examples/unicode --sort filename --output /tmp/unicode_result.xlsx
python examples/unicode/render_screenshot.py /tmp/unicode_result.xlsx \
    docs/assets/unicode-example-samples.png --sheet Samples
```

`render_screenshot.py` is a documentation tool only. It needs an extra,
non-runtime dependency:

```console
python -m pip install matplotlib
```

Keep the README claim limited to the verified generic schema: this example shows
that a Unicode filename is carried through discovery, hashing, and export. It does
not claim support for proprietary raw formats or for control/bidirectional
characters (those are escaped, not shown here).
