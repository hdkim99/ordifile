# Shimadzu LabSolutions result ASCII 5.82

Status: **Experimental** (development source tree; published availability is shown by
the PyPI badge)

Ordifile reads one exact standalone LabSolutions result-export profile. The adapter
does not require a `.GCD` file and does not read the chromatogram section as a raw
signal. This is not a claim of general LabSolutions, GCsolution, Shimadzu, ASCII-report,
instrument or detector compatibility.

## Exact capability

| Capability | Status |
|---|---|
| Text container | Bounded 7-bit ASCII with CRLF line endings, no BOM or NUL |
| Producer/profile | Exact LabSolutions 5.82 `Data File`, GC-2014 |
| Configuration | Exactly one detector `SFID1` and one channel `Ch1` |
| Section shape | Exact nine-section order for the observed export profile |
| Canonical rows | `Peak Table(Ch1)` source rows, source order preserved |
| Peak number | Source `Peak#`, required sequential `1..N` |
| Retention time | `R.Time`, unit min |
| Peak boundaries | `I.Time` / `F.Time`, unit min |
| Area / height | Source numeric values, physical units unresolved |
| Compound | Not emitted for the exact fixture's blank `ID#` / `Name` rows |
| Raw chromatogram signal | Not read or required |
| Other versions, instruments, detectors, channels or section sets | Not supported |

Canonical peak rows use manufacturer `Shimadzu`, detector `FID`, and channel `Ch1`.
Metadata separately records the source detector label `SFID1`, the exact producer,
instrument and profile boundary, and that the detector mapping is source-explicit.
Sample names, operators, original paths and other free-form run metadata are not
exported. The public sample and source identities are derived from the full source
SHA-256.

The source `Peak#` and canonical `observation_order` are both retained: `peak_number`
is the vendor row number, while `observation_order` independently preserves the source
row order. Ordifile performs no peak detection, integration, compound identification,
calibration or raw/result pairing.

## Workbook output

- `Peaks` retains every canonical row with manufacturer, source peak number,
  observation order, RT, area, height, start/end boundaries and explicit RT unit.
- Area and height unit cells remain blank because the exact evidence does not establish
  physical units. Ordifile never substitutes a guessed `unknown` unit string.
- The existing compound `Peak_Matrix` remains unchanged and has no rows for the exact
  fixture because no compound identity is present.
- Conditional `Peak_Order_Matrix` rows retain source-order `peak_N_rt` / `peak_N_area`
  pairs with sample, public source, manufacturer, detector, channel and units.
- `Samples`, `Metadata`, and `Import_Log` use the core-owned full-SHA-256 source alias.

Rows or pairs are never silently dropped. Invalid files are isolated from other batch
inputs and receive structured failures.

## Detection and rejection

The `.txt` suffix is required but insufficient. Detection also checks a bounded
newline-independent LabSolutions family marker before the exact ASCII envelope,
sections and producer/profile are parsed. An identified LabSolutions family document
outside the supported boundary is rejected rather than falling through to the generic
semicolon-TXT adapter, even when its line endings or required sections are malformed.

Parsing verifies the exact fixed fields and 21-column peak-table schema, a positive
bounded declared count, sequential source peak numbers, exact-lossless decimal-to-float
conversion, finite values, strictly increasing RT, `I.Time <= R.Time <= F.Time`, and
nonnegative area and height. The exact profile also requires a zero-row Compound
Results section and the observed chromatogram header/time grid as an internal
same-document structural check; every peak and integration boundary must fit that
chromatogram range, but chromatogram intensities are not exported.

Wrong line endings, BOM/NUL/control bytes, truncation, append data, oversized fields,
unknown or duplicate sections, count mismatches, non-finite or lossy numeric values,
unsupported profile fields and source mutation are rejected. The observed 40 ms
sampling interval is an external golden fact, not a runtime detector/profile constant;
other bounded positive declared intervals are preserved as structural metadata.

## Evidence and limitations

The exact controlled external fixture is 971,258 bytes with SHA-256 recorded in the
manifest. It contains 83 source peaks, but 83 is a golden fixture count rather than a
runtime constant. Full exact source-lexeme digests for RT, start, end, area and height
are asserted in the maintainer-only external test. The same workflow compares the
entire paired same-run GCD chromatogram without making that pairing a runtime
dependency or treating it as independent vendor conformance certification.

The ASCII fixture remains outside Git, distributions, logs, workbooks and Actions
artifacts because it carries repository-level GPL terms without a file-specific notice
and contains privacy-bearing source metadata. No GPL reader code, tests or source
expressions are copied or used as a dependency. See the
[investigation](../research/shimadzu-labsolutions-result-ascii-investigation.md) and
[implementation notes](../research/shimadzu-labsolutions-result-ascii-format-notes.md).

Verified promotion requires additional independent GC-FID result exports, profile
variation and a documented vendor export comparison. Shimadzu and LabSolutions are
trademarks or product names of their respective owner. Ordifile is independent and is
not affiliated with or endorsed by Shimadzu.
