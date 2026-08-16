# Examples

`basic/` contains three small, fully synthetic GC peak-table exports. Their names demonstrate
natural filename sorting (`sample_1`, `sample_2`, `sample_10`).

`unicode/` contains one small, fully synthetic peak-table export whose filename uses a
non-ASCII (Korean) name, demonstrating that normal Unicode input filenames are preserved
through to the `Samples` sheet.

From the repository root after installation:

```console
ordifile convert examples/basic --sort filename --output Ordifile_Result.xlsx
ordifile convert examples/unicode --sort filename --output Ordifile_Result.xlsx
```

The command creates one workbook and does not modify the example inputs.
