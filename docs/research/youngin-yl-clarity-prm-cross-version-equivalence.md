# YoungIn YL-Clarity PRM cross-version scientific-equivalence research

- Date: 2026-08-24
- Scope: exact observed YL-Clarity `9.0.1.19` and `9.1.0.76` completed-PRM profiles
- Research status: `VERSION_INDEPENDENT_CANDIDATE_YES`
- Product status: 9.0 `STRUCTURAL_ONLY`; 9.1 `DIRECT_SCIENTIFIC_SIGNAL_GO`
- Common scientific semantics: `NO_GO` pending a 9.0 same-run full-range curve oracle

This privacy-safe comparison does not change the production adapter, public API, CLI, GUI,
workbook contract or exact producer gates. It does not claim support for other versions.

## Method and safety boundary

Every source first passed the production structural reader under its exact producer profile.
The research probe then created a short-lived private copy and changed only the length-framed
UTF-16LE producer prefix to the other known, equal-length prefix. It did not use global byte
replacement, patch parser constants, add an `ignore_version` runtime option, or allow an unknown
producer to become known. Derived bytes stayed in an operating-system temporary directory and
were deleted after parsing. Original hashes matched before and after every replay.

A masked replay is a counterfactual structural-decoder result. It cannot establish time origin,
time unit, detector identity, response scaling, response unit, peaks, Area or Height.

## Aggregate corpus

| Exact profile | PRMs | Current channels | Finite records | History counts | Stored-label layouts |
|---|---:|---:|---:|---|---|
| `9.0.1.19` | 23 | 43 | 563,240 | 1: 5; 2: 7; 3: 11 | FID+TCD: 20; TCD-only: 3 |
| `9.1.0.76` | 5 | 10 | 138,000 | 1: 5 | FID+TCD: 5 |
| Total | 28 | 53 | 701,240 | — | — |

There are no duplicate PRM bytes across the cohorts. Source-level names, paths, hashes,
payload digests and measured arrays remain local. The existing separately approved paired-
provenance hashes are not expanded into a new public per-file matrix.

## Structural comparison

| Component | Classification | Evidence boundary |
|---|---|---|
| Raw-block framing | `IDENTICAL` | The same bounded `RAWData6 -> metadata -> PRMData -> DetName` reader accepts all 53 current channels. |
| History/revision framing | `COMPATIBLE` | Both use the same history grammar and latest-revision selection; 9.0 has one to three histories while validated 9.1 requires one. |
| Channel framing | `COMPATIBLE` | Source-ordered FID+TCD occurs in both; TCD-only occurs only in the 9.0 corpus. |
| `DStep` placement/value | `IDENTICAL` structurally | All 53 channels store `1`; scientific time meaning remains unverified for 9.0. |
| `MinTicks` placement/value | `IDENTICAL` structurally | All 53 channels store `600`; scientific time meaning remains unverified for 9.0. |
| `DSize` | `IDENTICAL` relationship | `DSize == record_count` for 53/53 channels. |
| `RAWSize` | `IDENTICAL` relationship | `RAWSize == record_count` for 53/53 channels. |
| Record count | `COMPATIBLE` | Count is payload-derived and bounded in both; observed absolute distributions differ. |
| Binary32 storage/order | `IDENTICAL` structurally | Both use finite, source-ordered little-endian binary32 under the same duplicate-payload checks. |
| Stored FID/TCD labels | `COMPATIBLE` | The shared FID+TCD placement is identical; physical detector/unit meaning remains profile-specific evidence. |
| Current revision | `COMPATIBLE` | The same current-boundary rule applies; only 9.0 supplies multi-history observations. |

The normalized current-curve probe finds two 9.0 groups (FID+TCD and TCD-only) and one
9.1 group (FID+TCD). The 9.1 group is present in the 9.0 cohort. This establishes a shared
structural-decoder family candidate, not common scientific semantics.

## Version-masked 9.1 replay

The five validated 9.1 sources were decoded through the production scientific route and a
9.0-masked structural replay. The research calculation used the already validated 9.1 formula
and label-to-unit mapping without consulting the masked version.

| Comparison | Result |
|---|---:|
| PRMs | 5/5 |
| Streams | 10/10 |
| Points | 138,000/138,000 |
| Retention-time values identical | 138,000/138,000 |
| Signal values identical | 138,000/138,000 |
| Channel identities identical | 10/10 |
| Candidate units identical | 10/10 |
| Originals modified | 0 |

Reverse masking invokes the stricter production 9.1 envelope: 5/23 9.0 sources fit its
single-history, FID+TCD, equal-count layout; 18/23 are rejected with the exact unsupported-
profile error. This documents envelope differences and is not scientific negative evidence.

## 9.0 research-only candidate

The probe applied these 9.1-validated relationships offline to all 23 exact 9.0 sources:

```text
t_candidate[i] = 0 + i * DStep / MinTicks
y_candidate[i] = stored little-endian binary32 response
```

All 23 files, 43 channels and 563,240 records produced finite, non-empty candidate ranges.
The two confirmed 9.0 Result Tables provide six peak RT rows. All 6/6 are within the candidate
range and compatible with the nearest `1/600 min` grid point at their three-decimal source
precision. This strengthens the interval candidate. Peak RT is an integrated-result coordinate,
however, so it does not prove zero origin, the sampled time array, response identity or units.

Candidate FID `pA` and TCD `mV` labels remain research hypotheses only. The probe generated no
production `SCIENTIFIC_SIGNAL`, workbook scientific sheet, peak, Area or Height for 9.0.

## Existing curve-oracle search and decision

Approved local evidence locations and archives were deduplicated and inspected by bounded
content signature. The only five full-range curve objects are the already validated 9.1
composite exports. The 9.0 archive contains no curve member; no standalone curve, CDF container
or provenance-confirmed 9.0 curve was found. Result Tables are not full-curve oracles.

- `VERSION_INDEPENDENT_CANDIDATE = YES`
- `9.0.1.19 DIRECT_TIME_AXIS = NO_GO`
- `9.0.1.19 DIRECT_SIGNAL = NO_GO`
- `COMMON_SCIENTIFIC_SEMANTICS = NO_GO`
- production exact-version dispatch remains unchanged
- unknown versions remain fail closed

## Decisive remaining evidence

The next decision requires a same-run full-resolution `9.0.1.19` curve. Prefer a FID+TCD
source whose structure overlaps the 9.1 envelope. The export must include all data, the X axis,
explicit detector and units, Time Step zero or below the sampling interval, and the actual
Global Filter/Bunching state. Pairing must be content/provenance based rather than filename-only.
Every PRM and official curve time/signal point must be compared at declared export precision.
Given the preceding 23-file structural comparison, one complete independent 9.0 curve is the
decisive remaining oracle defined for this research cycle.

Until those N/N comparisons pass, Ordifile must not transfer the 9.1 formula or units into 9.0.
Raw-signal integration, peak detection, Area/Height reconstruction and Result CSV imitation
remain outside this work.

## Interoperability and privacy

The probe is an independent interoperability aid based on owner-controlled file bytes and
existing Ordifile parsing. It includes no vendor source, executable, DLL, SDK, authentication,
license or access-control change. Owner files and derived copies are absent from Git, CI
artifacts, wheels and source distributions.

DataApex's [Export Data](https://www.dataapex.com/documentation/Content/Help/020-instrument/020.050-setting/020.050-export-data.htm)
and [Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-result-table.htm)
help distinguish sampled chromatogram export settings from integrated Result Table peak values.
