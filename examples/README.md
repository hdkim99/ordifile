# Examples

`basic/` contains three small, fully synthetic GC peak-table exports. Their names demonstrate
natural filename sorting (`sample_1`, `sample_2`, `sample_10`).

From the repository root after installation:

```console
labconvert convert examples/basic --sort filename --output LabConvert_Result.xlsx
```

The command creates one workbook and does not modify the example inputs.
