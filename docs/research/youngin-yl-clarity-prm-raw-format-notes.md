# YoungIn YL-Clarity PRM format notes

- Date: 2026-08-25
- Status: `STRUCTURAL_GO`; `DIRECT_TIME_GO`; `DIRECT_NUMERIC_SIGNAL_GO`;
  `DIRECT_PEAKS_NO_GO`
- Individually validated producers: YL-Clarity `9.0.1.19` and `9.1.0.76`
- Fixture policy: owner-supplied local-only files; native and export bytes are not
  redistributable

These notes record independently observed file facts for scientific data interoperability.
They are not a vendor binary specification. No vendor source, executable, DLL, SDK, protected
code, license state, authentication or access-control mechanism was copied or changed.

## Aggregate structural corpus

| Producer | PRMs | Current channels | Finite records | Histories | Layouts |
|---|---:|---:|---:|---|---|
| `9.0.1.19` | 25 | 47 | 615,940 | 1: 5; 2: 8; 3: 11; 4: 1 | FID+TCD: 22; TCD-only: 3 |
| `9.1.0.76` | 5 | 10 | 138,000 | 1: 5 | FID+TCD: 5 |
| Total | 30 | 57 | 753,940 | — | — |

There are no duplicate PRM bytes across those cohorts. The earlier 23-file canonical payload
digest remains unchanged. Original member names, per-file paths, producer serial suffixes and
measured arrays stay local.

## Bounded structural grammar

Every accepted file has the observed start and end-relative footer framing, a bounded
length-framed UTF-16LE YL-Clarity producer, sequential `ChromVersion1` history, consistent
detector counts, and one current raw set after the latest history marker. Each current channel
uses this exact source order:

```text
RAWData6 -> RAWSize/DStep/DSize/MinTicks -> PRMData -> DetName
```

The `RAWData6` and `PRMData` compressed bytes must be identical. Each is one complete bounded
gzip member with no trailing member or data. The decompressed payload is nonempty finite
little-endian IEEE-754 binary32. `RAWSize` and `DSize` must equal the payload-derived record
count. Stored labels are exactly `TCD` or source-ordered `FID`, `TCD`; framing and terminal
branches are validated independently of filenames.

The parser decodes only the bounded numeric producer version before `FULL, SN:`. It never
decodes, stores, logs or fingerprints the serial/license suffix. Conflicting later framed
YL-Clarity values fail closed; unrelated framed values and unframed byte occurrences do not
select a producer.

## Typed scientific-family fingerprint

Structural safety and scientific compatibility are separate. A structurally safe file matches
the current scientific fingerprint only when every current channel has `DStep=1` and
`MinTicks=600`, and two-channel files have equal record counts. The validated shared equations
are:

```text
t[i] = i * DStep / MinTicks
time origin = 0
time unit = min
y[i] = stored binary32 value
```

If these scientific invariants are incomplete, ordered raw records remain available without
time or physical-response meaning. Duplicate mismatch, size corruption, non-finite response,
invalid history or channel framing is a hard failure rather than a downgrade.

## 9.0 scientific oracle

The local corpus contains twelve exact `9.0.1.19` FID+TCD PRMs and twelve CP949/tab
full-curve exports. Every intake passed CRC, member/path, compression, duplicate and
source-integrity checks. Point counts and history cardinalities vary, preventing a
single-length coincidence from serving as the pairing rule.

Unique full-series content pairing confirms twelve PRM/export pairs. Across 158,110 FID and
158,110 TCD points:

- time is 316,220/316,220 at the export's five-decimal minute precision;
- numeric response is 316,220/316,220 at the four-decimal precision-derived bound;
- point count and source order are identical;
- the transformation is identity;
- both official channel headers are `Voltage [mV]`.

Therefore exact 9.0 FID and TCD units are both mV. Stored `DetName=FID` is not a global pA rule.
The exports prove full resolution by point-count equality; Time Step, Global Filter and
Bunching UI states are not present in the exported metadata and are not guessed.

## 9.1 scientific oracle

Five exact `9.1.0.76` FID+TCD PRMs have five same-run full-curve exports. All 138,000 time
points and all 138,000 response points match the same shared formulas. Their explicit headers
identify FID pA and TCD mV. The exact 9.1 profile additionally requires one history,
source-ordered FID/TCD, and equal point counts.

The combined shared-core evidence is 454,220 time points and 454,220 numeric-response points.
Physical units remain profile-specific.

## Compatibility boundary

The exact profiles `9.0.1.19` and `9.1.0.76` are individually validated. A strictly framed
unknown YL-Clarity 9.x producer is only an Experimental compatibility candidate. It is routable
scientifically when the entire structural and scientific fingerprint matches, but its physical
response unit remains unresolved in the absence of an exact profile or trusted in-file unit
field. If only structural safety matches, it produces decoded records. 8.x, 10.x and malformed
producer framing are outside the current boundary.

This does not claim universal or future-version support. New lawful evidence can add an exact
unit/provenance policy without copying the scientific formula into another adapter.

## Peak-result and calculated-Area boundary

Paired Result evidence has not identified a repeatable bounded PRM record containing explicit
RT, Area and Height. Method/event fields are not treated as integrated results. Exact validated
9.0/9.1 marker profiles may produce independent Ordifile peak RT and `calculated_area` values
from stored partitions and signal after the visible GUI selection or explicit CLI/API opt-in.
Source-explicit `area` remains
empty, Height is unavailable, and vendor equivalence is not claimed. The standalone YoungIn
Result CSV adapter remains the explicit source RT/Area/Height path.

## Runtime and public artifacts

The direct parser uses the existing `DatasetBundle` and `SignalSeries` contract. It does not
call YL-Clarity or Clarity, load vendor libraries, or create temporary CSV files. Owner PRMs,
curve exports and derived workbooks remain outside Git, Actions artifacts, wheels and sdists.
Only aggregate hashes, counts, units, precision rules and statuses are public.

## References

- [DataApex: YL-Clarity OEM announcement](https://www.dataapex.com/news/26748/new-oem-cooperation)
- [DataApex: chromatogram export](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.010-file/030.010-export-chromatogram.htm)
- [DataApex: command-line `prm_export`](https://www.dataapex.com/documentation/Content/Help/110-technical-specifications/110.020-command-line-parameters/110.020-command-line-parameters.htm)
- [DataApex: Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-result-table.htm)
- [YOUNGIN: YL-Clarity configuration guidance](https://file.younglin.com/Service_Note/23_YCM_Service_Note_SNSW-202112-02.pdf)
