# Agilent ChemStation Result XML independent implementation notes

- Date: 2026-08-17
- Adapter: `agilent_chemstation_result_xml`
- Boundary: Experimental standalone result-only conversion
- Exact profile: `Rev. C.01.10 [201]`, one source `FID1` / `A`, `Percent` / `Area`
- External fixture: 98,084 bytes; SHA-256
  `4c876bb5712b2d943b5ad32ce5854698018e0b82f2dfc10cc0971ffab9a7056f`

The implementation was derived from the pinned XML fixture's observable structure and
the official Agilent XML Connectivity Guide. GC2ASM code was not copied, translated,
vendored, imported, or added as a dependency. The pinned CeCILL-2.1 fixture is used
unchanged only during controlled external integration.

## Exact structural gate

- UTF-16LE BOM and exact XML declaration;
- root `ChemStationResult`, lowercase 32-hex checksum shape and schema basename
  `export.xsd`;
- exact top-level section order;
- equal Acquisition and SampleInformation version text:
  `Rev. C.01.10 [201] Copyright © Agilent Technologies`;
- exactly one `Signal` with source Detector `FID1`, SignalId `A`, Description
  `FID1 A, `, XUnits `min`, and YUnits `pA`;
- Results QuantCalc `Percent`, QuantBase `Area`, and exactly one ResultsGroup;
- an empty `CustomResults` section;
- positive bounded variable peak count, equal to the IntegrationResults count;
- exact scalar Signal, IntegrationResults and Peak child-field layouts, with optional
  Peak/Name;
- bounded file bytes, peak count, text and numeric lexemes, plus streaming element and
  depth preflight before full-tree construction.

DTD, entity, mixed-content text, other schema/revision/signal/detector/channel/unit/
quantitation shapes, duplicates, count mismatches, non-finite values, invalid ranges
and partial files are rejected. Exact source decimals that cannot round-trip through
the canonical float model are rejected rather than rounded. The adapter's initial
bounded-read size and SHA-256 must match discovery provenance, including a
change-then-restore race.

## Canonical source and cross-check

`Results/ResultsGroup/Peak` is the single canonical peak row source.
`Chromatograms/Signal/IntegrationResults` is not emitted as a second row family. It is
used to require exact string equality by source index for:

- `Peak/MeasRetTime == IntegrationResults/RetTime`;
- `Peak/Area == IntegrationResults/Area`;
- `Peak/Height == IntegrationResults/Height`.

Integration `TimeStart` and `TimeEnd` supply the explicit boundaries, and every row
must satisfy `TimeStart <= MeasRetTime <= TimeEnd`. Measured RTs are finite and strictly
increasing, are within the Signal Start/End range, and every Peak/SignalDesc equals the
validated Signal Description.

`Peak/Name` is mapped only when nonblank to existing `compound`, with
`compound_source = canonical:agilent_chemstation_result_xml.results_peak_name`.
`ExpRetTime`, `Amount`, and `CompoundID` are deliberately not used as measured RT,
area, peak number, or identity.

## External golden facts

The external fixture contains 36 canonical rows. The following SHA-256 values use
UTF-8 encoding of exact source lexemes joined by LF with no trailing LF:

| Sequence | SHA-256 |
|---|---|
| measured RT | `25104dd542e674f3e0d07d9c3dbfe8b019bc9b9b4b59bcc406b87300a00e9b9d` |
| area | `db71fe58cf8646509cbd8dd2e34c0f8e566a7e4cf2043b3e49799a68115e9932` |
| height | `db939beb34b30313defecc864c511c666baa4da837914625f3ca51209fcf9c49` |
| integration start | `cbd1a2091518a1f1f92557c94f3a24764483a5c3e547c13963572c50e9fb62bb` |
| integration end | `8b68a48e59bbd33800198a1eae31eb79d6eda0209f64326cc9114d437588f976` |

The test compares all 36 source rows to canonical Peaks and the reopened workbook;
sample/operator/path values and native XML bytes are never logged or uploaded.

## Manufacturer-neutral output

`PeakRecord` additively retains observation order, start/end, area unit and height
unit. `Peaks` derives manufacturer from SampleRecord. The conditional
`Peak_Order_Matrix` fixed identity is sample, public source, manufacturer, detector,
channel, RT unit and area unit, followed by atomic source-order RT/area pairs. Its
column planner permits 8,188 pairs per Excel segment. Existing compound
`Peak_Matrix` behavior is unchanged.

The adapter opts into `SHA256_ALIAS`; sample ID and every public source reference are
content-hash derived. Only allowlisted scientific/profile metadata leaves the adapter.
