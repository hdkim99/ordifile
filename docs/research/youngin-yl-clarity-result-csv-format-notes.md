# YoungIn YL-Clarity Result Table CSV independent implementation notes

- Date: 2026-08-18
- Adapter: `youngin_yl_clarity_result_csv`
- Boundary: Experimental standalone Result-only conversion
- Actual evidence: two owner-generated local-only exports, six total peak rows

## Evidence boundary

The user generated both exports through the normally used YL-Clarity application. A
bounded local analysis paired each export to a distinct owner PRM by source identity.
The export bytes do not contain `YL-Clarity`, `Clarity`, `DataApex`, `YoungIn` or a
software-version marker. Runtime detection therefore uses only the exact observed
content grammar; the OEM/product attribution remains external provenance.

Official DataApex documentation independently defines Result Table retention time,
area, height, half-height width, `Signal Name`, no-peak states and signal totals. The
actual unit-bearing header, rather than documentation alone, is the source of the
canonical min, mV.s and mV units. No vendor implementation code or proprietary reader
was copied, translated, bundled or added as a dependency.

## Exact structural gate

- bounded stable read and SHA-256;
- BOM-free CP949-compatible bytes, exact CRLF envelope and tab fields;
- repeated exact nine-column Result Table header;
- sequential unique signal sections and contiguous source `Peak No.` values;
- observed one-section TCD or empty-FID-plus-populated-TCD variants only;
- exact-lossless finite nonnegative RT, Area, Height, Area%, Height% and W05 decimals;
- section totals that equal the exact Area and Height sum;
- explicit no-peak row shape;
- one bounded privacy-bearing metadata block per signal, validated by structure only;
- the observed final report header and empty compound-table terminator; and
- no trailing or silently ignored rows.

An exact family header claims malformed documents at lower confidence so they cannot
fall through to the generic CSV adapter. The parser exposes no private trailer value.

## Canonical mapping

| Source | Canonical |
|---|---|
| `Peak No.` | `PeakRecord.peak_number` |
| source section row position | `PeakRecord.observation_order` |
| `Reten. time [min]` | retention time, min |
| `Area [mV.s]` | area, mV.s |
| `Height [mV]` | height, mV |
| `Signal No.` + `Signal Name` | channel `Signal N: label` |
| detector | unset |
| compound/start/end | unset |

The signal label is recorded in namespaced metadata but is not promoted to detector
identity without separate evidence. The raw PRM adapter follows the same conservative
detector rule. Percentages, W05 and Total values are validated with explicit
not-exported status metadata; they are not silently reinterpreted.

## External golden facts

The external manifest records two source SHA-256 identities, sizes, section layouts,
paired raw SHA identities and full RT/Area/Height lexeme digests without exposing a
basename or scientific value. The local external test checks every source row against
the canonical bundle and reopened workbook. The combined actual regression requires:

- Agilent Result XML: 36 peaks;
- Shimadzu Result ASCII: 83 peaks;
- YoungIn Result Table exports: 6 peaks;
- one workbook: 125 peaks and four populated `Peak_Order_Matrix` streams.

Actual exports, vendor software and validation workbooks are never committed or
uploaded. Redistribution rights for the exports are not asserted.

## References

- [DataApex Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-result-table.htm)
- [DataApex All Signals Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-all-signals-results.htm)
- [DataApex Export Data](https://www.dataapex.com/documentation/Content/Help/020-instrument/020.050-setting/020.050-export-data.htm)
- [DataApex / Young Lin OEM announcement](https://www.dataapex.com/news/26748/new-oem-cooperation)
