# Workbook interpretation guide

An Ordifile workbook is an auditable conversion result, not a new scientific analysis.
Measured RT, Area, Height, secondary RT, units, and observation order retain their
canonical meaning. Display formatting does not round the stored numeric values.

## Recommended review order

| Step | Sheet | What to confirm |
|---:|---|---|
| 1 | `Samples` | Source count, stream count, status, order, detector/channel when explicit, dimension, peak count, and units |
| 2 | `Import_Log` | Every success, warning, duplicate, and failure; adapter or mapping route; bounded status codes |
| 3 | `Peaks` | Every canonical row and its RT1, optional RT2, Area, Height, units, stream identity, and observation order |
| 4 | `Peak_Matrix` | Comparison view keyed only by explicit compound identity; blanks are not inferred matches |
| 5 | `Peak_Order_Matrix` | 1D stream view grouped by observed peak order |
| 6 | `Peak_Order_Matrix_2D` | Conditional 2D stream view preserving RT1/RT2/Area triples |
| 7 | `Metadata` | Preserved metadata and raw lexemes that were not promoted to scientific fields |
| 8 | Optional signal sheets | Only signal or structural record series explicitly requested and actually parsed |
| 9 | `Manifest` | Effective options, sorting decision, limits, sidecars, and public-safe provenance |

`Manifest` remains the first worksheet for compatibility, while `Samples` is the active
researcher entry sheet. A 2D matrix is present only when a converted stream has an
explicit secondary retention coordinate.

Some non-Excel spreadsheet applications ignore the XLSX active-tab setting and open the
first worksheet (`Manifest`). In that case, select `Samples` manually before following
the review order above; the workbook data and sheet order are unchanged.

## Canonical rows and derived views

`Peaks` is the row-level source for reviewing converted scientific values. Matrices are
derived layouts for comparison and do not create compounds, align RT, combine streams,
or normalize values. `Peak_Matrix` contains only explicit compound identities. Order
matrices preserve observations by stream and order; an empty matrix cell is not a zero
measurement.

When otherwise identical `Peak_Matrix` compound/detector/channel columns contain different
Area units, Ordifile separates them and adds an `area_unit` qualifier to each affected
header. A missing unit uses an `area_unit_status=unresolved` qualifier; it is never merged
with a resolved unit.

RT1 and RT2 units are independent. Area and Height units are also independent. Values in
`pA*s`, `mV.s`, `AU`, or an unresolved unit must not be treated as directly comparable
without a separate, scientifically justified workflow outside Ordifile. A blank or
`Unresolved` unit means the input did not provide a verified unit; it is not an inferred
default.

## Warnings, duplicates, and partial results

Use `Import_Log` as the detailed source for per-file outcomes. A warning remains visible,
a duplicate is counted separately, and a failure is not silently omitted. When the
current `continue` policy allows partial conversion, the workbook contains successful
records plus an audit row for each failed input. The concise CLI/GUI summary should agree
with `Samples`, `Import_Log`, and the `Manifest` counts.

Long cell content or large sheet limits follow the deterministic workbook/sidecar policy
recorded in `Manifest`. Ordifile does not silently truncate scientific data. If an input
cannot be represented within the documented policy, conversion reports a structured
failure instead of changing the value.

## Privacy and reproducibility

Public-safe source references and hashes support local comparison without adding source
absolute paths. The workbook does not contain the full Conversion Recipe or its local
path. When Recipe provenance is present, it is limited to a schema version and a
privacy-safe fingerprint. Keep the workbook local when sample identifiers or laboratory
metadata are private.

For reproducibility, record the Ordifile version, effective Mapping/Recipe files in your
local laboratory records, runtime inputs and output choice, reviewed preflight summary,
and the generated workbook hash. Do not publish local configuration solely because the
workbook uses a public-safe fingerprint.
