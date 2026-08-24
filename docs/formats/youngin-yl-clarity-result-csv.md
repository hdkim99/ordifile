# YoungIn YL-Clarity Result Table CSV profile

- Status: Experimental
- Adapter: `youngin_yl_clarity_result_csv`
- Evidence: two owner-generated local-only Result exports
- Runtime dependency on YL-Clarity: none

This adapter reads one exact Result Table text grammar attributed to YL-Clarity by
owner-controlled export provenance. The bytes themselves contain neither an OEM
producer name nor a software-version marker, so this is not a claim of general
YL-Clarity, Clarity, CSV, detector, or software-version compatibility.

## Exact capability

| Capability | Status |
|---|---|
| Container | CP949-compatible text, BOM-free, CRLF, tab delimiter, `.csv` observed |
| Result header | Exact repeated nine-column unit-bearing header |
| Observed variants | Signal 1 TCD with peaks; or Signal 1 FID no-peaks then Signal 2 TCD with peaks |
| Retention time | Explicit `Reten. time [min]`, unit min |
| Area | Explicit `Area [mV.s]`, unit mV.s |
| Height | Explicit `Height [mV]`, unit mV |
| Signal identity | `Signal No.` and `Signal Name` retained as channel identity |
| Detector | Unresolved; `Signal Name` is not automatically asserted as detector identity |
| Start/end | Not present |
| Compound | Not present in any peak row; no compound identity is inferred |
| Raw sibling | Not required |

Two actual exports contain six finite source peak rows in total: two in one TCD
section, and four in a second run's TCD section. The latter run also contains one
explicit empty FID section. The exact local pairing evidence maps both exports to two
distinct owner PRM sources, but pairing is not a runtime requirement.

Five later owner-controlled files use a different composite Result-plus-full-curve grammar
and contain 21 additional research-only TCD rows. Their displayed Total semantics differ
from this profile's exact validation equation. They are therefore not accepted by this
adapter and do not change its two-export/six-row production evidence count. Their curve
sections independently validate the exact 9.1 PRM scientific-signal profile.

## Canonical output

Each numeric source row becomes one source-order `PeakRecord`. `Peak No.` is retained
as `peak_number`; section-local row order is retained independently as
`observation_order`. RT, area and height map to `Peaks` with the units printed by the
source. `Peak_Order_Matrix` groups the two populated channels independently. The empty
FID section is retained in metadata but does not invent a peak or matrix row.

`Area [%]`, `Height [%]` and `W05 [min]` are validated. They are not substituted for
canonical Area/Height, and W05 is not treated as an integration start/end boundary.
Signal `Total` rows are exact response checks, not peaks. The appended empty compound
table does not identify any peak, so YoungIn rows add no compound columns to
`Peak_Matrix`.

## Detection and rejection

The suffix is insufficient. Detection requires the exact first header family and a
complete bounded parse of the repeated section grammar, strict finite decimal fields,
sequential signal and peak numbers, explicit no-peak or populated sections, exact
totals, the observed private-trailer shape and the empty compound-table terminator.
Recognized but malformed family documents fail under this adapter rather than falling
through to the generic CSV adapter. Ordinary UTF-8 comma CSV continues to use
`generic_csv` and regains ordinary relative provenance after validation.

BOM/NUL, wrong line endings, wrong delimiter, unknown or reordered columns, unsupported
signal combinations, missing or mismatched totals, non-finite/lossy numbers,
truncation, append data and resource-limit violations are structured failures. Source
rows are never silently dropped.

## Privacy, evidence and limitations

The actual exports contain privacy-bearing run metadata after the scientific table.
Only the scientific and structural allowlist above is emitted. API, CLI, issues,
progress, `Samples`, `Metadata` and `Import_Log` use the core-owned full-SHA-256 source
alias. Private source bytes, basenames, trailer values and generated workbooks remain
outside Git, distributions and Actions artifacts. Public tests use independently
invented synthetic values.

The exact source identities, sizes, section counts and scientific sequence digests are
recorded in the tracked, sanitized [evidence manifest](../research/youngin-result-csv-external-fixture-manifest.json)
for the local-only source bytes.
See the [implementation notes](../research/youngin-yl-clarity-result-csv-format-notes.md).
Verified promotion requires independent exports, additional signal/detector cases and
profile variation. YL-Clarity and related vendor names are used only for compatibility
identification. Ordifile is independent and is not affiliated with or endorsed by the
vendor.
