# YoungIn YL-Clarity PRM raw-record format notes

- Date: 2026-08-24
- Status: `STRUCTURAL_GO`; 9.0 `DIRECT_SIGNAL_NO_GO`; 9.1 `DIRECT_SIGNAL_GO`;
  `DIRECT_PEAKS_NO_GO`
- Scope: exact observed YL-Clarity `9.0.1.19` and `9.1.0.76` completed-PRM profiles
- Fixture policy: 28 unique owner-supplied files, local-only and not redistributable

These notes record independently observed file facts. They are not a vendor binary
specification. No vendor executable, DLL, proprietary OpenChrom converter, GPL source,
or protected source code was copied, translated, bundled, or used as a runtime
dependency.

## Aggregate fixture facts

The ignored source archive is 3,083,937 bytes with SHA-256
`4af61e1aa8abef3694a4c24a28203b0a1d382a11b6442c3e9b43653487f97fe5`.
Its safe intake contains 23 distinct PRM files. Public records use only aggregate
counts, hashes and privacy-safe aliases; original member names and embedded metadata
values remain local.

| Observation | Result |
|---|---:|
| PRM files | 23 |
| Current structural blocks | 43 |
| Dual stored-label profile | 20 files, `FID` then `TCD` |
| Single stored-label profile | 3 files, `TCD` |
| Total finite binary32 records | 563,240 |
| Record-count distribution | 11,970 x 2; 11,980 x 1; 13,180 x 32; 13,190 x 6; 13,210 x 2 |

The decoded values are deterministic. The canonical batch-digest scheme and aggregate
digest are public reference facts, and the local external test asserts that full
digest. Native bytes, original per-file names and per-file source hashes remain local
and are not placed in Git or release artifacts.

The owner archive and both paired Result exports were re-opened locally on 2026-08-24.
All 23 PRM files, 43 current blocks, 563,240 records, record-count distributions and
stored-label layouts reproduced the tracked reference. Original files were read-only and
no private basename, path, metadata value or measured value was added to public output.

## Expanded 9.1 paired evidence

A second owner archive passed bounded ZIP validation: ten regular members, five PRM and
five CP949-compatible tab-delimited composite CSV exports, with no duplicate bytes,
traversal, links, encryption, nested archives or executable members. Its five PRMs are
distinct from the earlier 23 and carry the exact `YL-Clarity 9.1.0.76 FULL` producer
prefix. They add ten current blocks and 138,000 finite records. The combined inventory is
28 PRMs, 53 current blocks and 701,240 records; the original 23-file structural digest is
unchanged.

Each new CSV contains a Result section and full-range FID/TCD time-response curves. Content
comparison, not filenames, gives five unique confirmed pairs. All ten curves contain 13,800
points. Across 138,000 points, the time text is exactly the five-decimal representation of
`i * DStep / MinTicks` with zero origin, `DStep=1`, `MinTicks=600` and explicit minute unit.
The signal relation is identity: every four-decimal exported value is within the
precision-derived half-unit bound of the corresponding stored binary32 value. Explicit
headers identify FID as pA and TCD as mV for all five distinct source/export pairs.

The same composite files contain 21 TCD peak rows and five explicit no-peak FID sections.
They strengthen paired Result evidence but do not match the standalone exact Result CSV
grammar: their composite prefix and displayed Total semantics differ. The production Result
adapter therefore remains unchanged at two exports and six canonical peaks. The 21 rows are
research evidence only and do not change the controlled 225-peak production baseline.

No repeatable bounded stored peak result was found in the five PRMs. Exact RT, Area and
Height text or little-endian float32/float64 values did not occur as a consistent result
record, and candidate method neighborhoods remained byte-stable while result values and
counts changed. Direct PRM Peak/Area/Height stays NO_GO; numerical integration and automatic
peak detection were not used.

## Structural grammar

Every file in the initial 9.0 corpus starts with the same four bytes, `5a a5 00 08`. The
value is an observed signature only; it is not interpreted as software version 8. Those
files contain a bounded UTF-16LE producer prefix for YL-Clarity `9.0.1.19`; the adjacent
license/serial suffix is sensitive and is never parsed or exposed. The separate 9.1
profile requires the first length-framed `Info` value to carry its exact `9.1.0.76 FULL`
producer prefix. Every later framed YL-Clarity `Info` value must identify the same exact
profile; unrelated framed values and unframed byte occurrences do not select a profile.

In the 9.0 corpus, the active raw blocks occur only after the greatest and last
`ChromVersion1` entry. The observed revision sequences are `[1]`, `[1, 2]`, or
`[1, 2, 3]`, and the revision, method and log-data counts agree. DataApex documentation
describes the most recent stored method as current and historical versions as read-only.
Earlier revision intervals contain no separate raw snapshot in those files, so the
adapter exposes one current/global raw set and records the revision boundary as
Experimental metadata. The exact 9.1 scientific profile requires the independently
observed single current revision.

Each of the 43 active 9.0 blocks has this source order:

```text
RAWData6 -> RAWSize -> PRMData -> DetName
```

`RAWData6` and `PRMData` are typed, little-endian-length-prefixed gzip blobs. Within
each block their compressed bytes are identical. `RAWSize` and the second structural
size candidate both equal the decompressed length divided by four. In 9.0 the observed
step and tick candidates remain structural values and are not converted into time.

All observed 9.0 blocks store `DStep=1` and `MinTicks=600`. The evidence-guided candidate
interval `DStep / MinTicks = 1/600 min` is consistent, at the Result export's precision,
with all six RT values in the two paired Result Tables and places all six peaks within the
corresponding record ranges. This is supporting evidence for a candidate interval only.
Result rows do not establish time origin or compare every stored record to an official
curve, so the 9.0 candidate is not emitted as retention time. For 9.1, the separate
full-curve oracle validates the same interval, a zero origin and minutes across every
point in five distinct source/export pairs.

The subsequent [cross-version research probe](youngin-yl-clarity-prm-cross-version-equivalence.md)
replayed all five 9.1 sources after masking only the typed producer field and reproduced
all 138,000 scientific time and signal points. Across all 28 PRMs, raw framing, binary32
ordering, size equations and `DStep=1` / `MinTicks=600` placement overlap, while history
and channel-layout envelopes differ. This is a version-independent structural and formula
candidate only. No same-run 9.0 full-range curve was found, so 9.0 remains structural-only
and the exact production version gate remains unchanged.

The gzip payload is an array of little-endian IEEE-754 binary32 values. All observed
records in both exact profiles are finite. Reinterpreting the same bytes as big-endian
produces non-finite and implausibly large values and is rejected by the evidence.

`DetName` is a bounded UTF-16LE field exactly associated with each active block. Only
the stored labels `FID` and `TCD` occur. In 9.0 the adapter uses these only as
Experimental native channel labels and leaves `SignalSeries.detector` unset. For the
separate 9.1 profile, the five paired full curves independently validate FID pA and TCD
mV channel identity and units at export precision.

## Independent references

- DataApex documents `.PRM` as the completed Clarity chromatogram and documents
  `.CDF`, `.CHR`, `.TXT` and `.ASC` export routes, including `prm_export`.
- DataApex documents chromatogram history and the read-only role of older methods.
- YOUNGIN documents YL-Clarity as a Clarity OEM and documents FID/TCD configurations.
- OpenChrom lists a DataApex FID PRM converter, but the converter is proprietary,
  installed separately through the GUI, absent from the open-source core, and not a
  lawful implementation dependency. OpenChrom 1.5 and later removed the prior public
  command-line import path.
- chromConverter has no native PRM parser; its old GPL bridge depended on OpenChrom
  1.4 or earlier and is comparison-only.

The current OpenChrom converter could not be run in a privacy-safe automated local
mode. This is recorded as `Unavailable`, not as negative parser evidence.

Official DataApex documentation separates `export_results` from `prm_export`. The five
9.1 full-range composite curves now provide a same-run time/signal oracle for that exact
profile. A future 9.0 oracle, if pursued, should use the same PRM and include a
detector-specific AIA/CDF plus a full-range text or multidetector export with X axis
enabled and Time Step zero or below the sampling interval. Global Filter/Bunching state
must be recorded; text export is compared at its declared precision rather than treated
as a bit-exact raw oracle.

## Peak-result audit and vendor-export bridge

The 23 local PRM files were also audited specifically for an integrated peak/result
table before any result parser or canonical-model change was considered. The current
revision contains 43 `RAWData6` blocks and 43 byte-identical `PRMData` duplicates, but
no separate deterministic result blob or populated table carrying retention time plus
area. Searches for structured peak-result fields tying retention time, area, height,
width, component/compound identity and result-channel references together did not
establish a result-record grammar. The separately validated `DetName` field labels raw
blocks; it is not a peak-result row. Observed `PeakWidth` configuration and `ATime` /
`BTime` event fields belong to method/event state and are not evidence of integrated
peaks. No populated calibration linkage or same-run result companion was present.

DataApex documents separate export paths. `prm_export` creates CDF/CHR/TXT/ASC
chromatogram curves and remains a possible future signal/time-axis oracle for the exact
9.0 profile. The GUI **Export Data**
Result Table path and command-line `export_results` path export active-chromatogram
results; the GUI can write result tables to TXT/CSV or XLS/XLSX. DataApex's Result Table
documentation identifies peak rows and retention-time ordering and explains that the
visible fields and units depend on active signal, calibration and table settings. The
PRM bytes themselves establish neither a Result Table nor deterministic RT/area
extraction. Two separately owner-generated YL-Clarity Result Table exports now
establish the standalone Result path while raw-record conversion remains an
independent capability.
The local bridge stages a temporary SHA-addressed PRM copy, never passes the original
source to the vendor, invokes positional PRM open, `export_results` and
`prm_close_discard`, validates explicit RT+Area headers, and records a sanitized local
pairing manifest. No `PeakRecord` field was introduced from PRM marker names alone.
The actual export bytes remain local-only; the exact Result adapter and full
source-to-workbook comparison use their content without requiring the vendor
application at runtime.

The implemented result path is manufacturer-neutral: standalone Agilent, Shimadzu and
YoungIn result adapters map evidence-backed rows into the existing `PeakRecord`,
`Peaks`, conditional `Peak_Order_Matrix` and compound-only `Peak_Matrix` contract.
Raw-signal extraction remains optional and separate.

## Capability decision

| Capability | Status |
|---|---|
| Exact observed profile detection | Experimental, fixture-backed |
| Deterministic raw binary32 extraction | Experimental GO |
| Stored channel-label separation | Experimental |
| Maintainer FID/TCD fixture grouping | Local external oracle only; not runtime output |
| Independently verified detector identity | 9.0 unverified; 9.1 FID/TCD full-curve validated |
| Retention-time axis | 9.0 NO_GO; 9.1 GO in minutes |
| Physical/display scaling | 9.0 NO_GO; 9.1 identity transformation GO |
| Physical unit | 9.0 unknown; 9.1 FID pA and TCD mV |
| Peak table in PRM raw | NO_GO; no repeatable stored result grammar established |
| Standalone Result Table CSV | Experimental GO for the exact owner-validated profile |
| Batch PRM to one workbook | Experimental GO |
| Experimental scientific chromatogram | GO for exact 9.1 profile; 9.0 remains blocked |
| Vendor Result export bridge | Local-only ready; actual Result exports received |

## Remaining promotion inputs

- a same-run YL-Clarity/Clarity Result Table exported through GUI **Export Data** or
  `export_results` as CSV, TXT, XLS or XLSX, as the primary RT/area oracle (two paired
  Result exports are already available);
- a 9.0-specific same-run full curve only if direct scientific signals are later pursued
  for that separate producer profile;
- independent PRM runs with different lengths and detector configurations;
- exact agreement for point count, full value sequence and channel identity;
- retention-time origin and interval confirmation;
- physical/display scaling and unit confirmation;
- cross-fixture malformed and regression coverage.

## Sources

- [DataApex: YL-Clarity OEM announcement](https://www.dataapex.com/news/26748/new-oem-cooperation)
- [DataApex: Clarity terms and PRM lifecycle](https://www.dataapex.com/documentation/Content/Help/100-list-of-terms/100.000-list-of-terms/100-list-of-terms.htm)
- [DataApex: chromatogram history](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.010-file/030.010-open-chromatogram.htm)
- [DataApex: chromatogram export](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.010-file/030.010-export-chromatogram.htm)
- [DataApex: Export Data](https://www.dataapex.com/documentation/Content/Help/020-instrument/020.050-setting/020.050-export-data.htm)
- [DataApex: Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-result-table.htm)
- [DataApex: `prm_export`](https://www.dataapex.com/documentation/Content/Help/110-technical-specifications/110.020-command-line-parameters/110.020-command-line-parameters.htm)
- [DataApex: AIA import fields](https://www.clarityguide.dataapex.com/documentation/Content/Help/030-chromatogram/030.010-file/030.010-import-aia.htm)
- [YOUNGIN: YL-Clarity configuration guidance](https://file.younglin.com/Service_Note/23_YCM_Service_Note_SNSW-202112-02.pdf)
- [OpenChrom format catalogue](https://www.openchrom.net/)
- [OpenChrom converter installer](https://converter.openchrom.net/)
