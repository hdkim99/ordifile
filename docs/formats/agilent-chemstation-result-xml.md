# Agilent ChemStation Result XML `C.01.10 [201]`

Status: **Experimental** (development source tree; published availability is shown by
the PyPI badge)

Ordifile reads one exact standalone ChemStation result-report profile. The adapter does
not require a raw `.CH` file and does not parse a `.D` directory. This is not a claim of
general ChemStation, OpenLab, XML-report, detector, or Agilent compatibility.

## Exact capability

| Capability | Status |
|---|---|
| UTF-16LE `ChemStationResult` / `export.xsd` shape | Exact-profile gate |
| Acquisition and sample revision | Exact `Rev. C.01.10 [201]` producer text |
| Signal | One source `FID1` / `A`, min / pA profile |
| Quantitation mode | Exact `Percent` / `Area` profile |
| Canonical rows | `Results/ResultsGroup/Peak`, source order preserved |
| Retention time | Source `MeasRetTime`, unit min |
| Area / height | Source values, units pA\*s / pA |
| Integration boundaries | `IntegrationResults/TimeStart` / `TimeEnd` |
| Compound | Nonblank calibrated `Peak/Name` only |
| Duplicate validation | RT, area and height exact decimal strings agree by index |
| Raw chromatogram signal | Not read or required |
| Other revisions, signals, detectors or quantitation modes | Not supported |

The source labels `FID1` and `A` are retained separately in Metadata. Canonical peak
rows use detector `FID` and channel `FID1A`, matching Ordifile's existing Agilent
channel convention. The manufacturer is `Agilent`; no sample, operator, method path,
serial number, instrument identifier, or other free-form run metadata is exported.

`Peak/ExpRetTime`, `Amount`, and `CompoundID` are not reinterpreted as measured RT,
area, or identity. A missing or blank optional `Name` produces no compound value.
Ordifile performs no peak identification, calibration, integration, or raw/result
pairing.

## Workbook output

- `Peaks` retains every canonical row with manufacturer, observation order, measured
  RT, area, height, start/end boundaries, compound provenance and explicit units.
- The existing compound `Peak_Matrix` remains unchanged and includes only explicit
  compound names.
- Conditional `Peak_Order_Matrix` rows retain source-order `peak_N_rt` / `peak_N_area`
  pairs with sample, public source, manufacturer, detector, channel and units. A pair
  is never split across sheet segments; at most 8,188 pairs fit in one Excel segment.
- `Samples`, `Metadata`, and `Import_Log` use the core-owned full-SHA-256 source alias.

Rows or pairs are never silently dropped. Invalid files are isolated from other batch
inputs and receive structured failures.

## Detection and rejection

The `.xml` suffix is required but insufficient. Detection also checks the UTF-16LE BOM
and exact XML declaration, safe XML parsing without DTD/entities, bounded file size,
streaming-preflight element count and nesting depth before full-tree construction,
lowercase checksum shape, `export.xsd` basename, top-level and scalar row schemas,
exact revision, one signal and result group, scientific
units, an empty `CustomResults` section, nonempty bounded peak count, strictly
increasing finite RTs, integration boundaries, signal range, duplicate-table count,
and exact duplicate decimal strings.

Malformed, truncated, appended, oversized, deeply nested, unsafe, mixed-content,
non-finite, lossy-to-canonical-float, out-of-order, mismatched, multi-signal, or
unsupported-profile inputs are rejected. The parser's bounded-read size and SHA-256
must also match core discovery provenance before any canonical rows are exposed.

## Evidence and limitations

The exact external fixture is 98,084 bytes with SHA-256 recorded in the controlled-CI
manifest. It contains 36 source peaks, but 36 is a golden fixture count rather than a
runtime format constant; other positive counts are accepted only under every exact
profile and consistency gate. Full source RT, area, height, start and end lexeme
digests are asserted in the maintainer-only external test.

The fixture remains outside Git, packages, logs, workbooks and Actions artifacts
because it contains privacy-bearing run metadata. See the
[investigation](../research/agilent-chemstation-result-xml-investigation.md) and
[implementation notes](../research/agilent-chemstation-result-xml-format-notes.md).

Verified promotion requires additional independent runs and profile variation with
the same full-row agreement. Agilent and ChemStation are trademarks or product names
of their respective owner. Ordifile is independent and is not affiliated with or
endorsed by Agilent.
