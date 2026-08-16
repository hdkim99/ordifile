# Shimadzu LabSolutions 5.82 `.GCD` investigation

- Status: **Experimental GO for one exact profile**
- Research date: 2026-08-16
- Runtime adapter boundary: LabSolutions 5.82, GC-2014, one `Ch1` stream,
  `SFID1`, `uV`, `CF=1`, `GF=1`
- Tracking issue: [#15](https://github.com/hdkim99/ordifile/issues/15)

This investigation does not establish general GCsolution, LabSolutions, Shimadzu,
or `.GCD` compatibility. It establishes one reproducible scientific-signal profile
from a real fixture, an independently inspected compound-file structure, and a paired
same-run LabSolutions ASCII chromatogram.

## Fixture and provenance

| Item | Evidence |
|---|---|
| Native file | `FS19_214.gcd`, 1,433,600 bytes, SHA-256 `d670806265f994507ac99fc676f17098bf9b9d1c362c98df1cb31154ac7a5180` |
| Source | `chromConverterExtraTests`, commit `f9cb88d90f6be00e3c0f16fa3e2bb7734a5da66b` |
| Native-file license | The source README assigns CC0 1.0 specifically to `FS19_214.gcd` |
| Privacy | Contains contributor and machine-local text; external, transient, and non-logged only |
| Paired reference | `ladder.txt`, 971,258 bytes, SHA-256 `46d1dcde188d7844c32abb89cda1f0d773cac480f6d6c93f2b6ca7149fdb9297` |
| Reference provenance | The ASCII header identifies the same GCD filename, sample, LabSolutions 5.82, 66,255 points, and 40 ms rate; native values match point by point after the ASCII rounding rule |
| Reference license | No separate file-level permission was established; it is not downloaded, copied, or redistributed by Ordifile |

The paired ASCII is strong same-run behavior evidence, not an official Shimadzu
conformance file. Only derived numeric summaries and cryptographic digests are kept
in Git. The native GCD is also external despite its file-specific CC0 declaration,
because its embedded personal and local-machine text must not enter source history or
public Actions output.

## Official product evidence

Shimadzu's current LabSolutions material describes LabSolutions LC/GC as the successor
environment for LCsolution and GCsolution. The inspected LabSolutions operator guide
uses `.gcd` as a GC data-file suffix, and Shimadzu material for related products also
identifies GCD as a LabSolutions data file. These sources establish product and file
lifecycle context; they are not a byte-level specification.

## Reference implementations

| Reader | Result | License boundary |
|---|---|---|
| Ordifile independent research decoder | Reads the exact CFB profile, the 66,255 little-endian float64 samples, and the metadata links listed below | Independently implemented from observed bytes and public container rules |
| `chromConverter` 0.9.1, commit `9137b85f...` | Its GCD reader informed behavior comparison. Its test computes a comparison but does not assert it, and its generated time vector omits the observed 20 ms delay | GPL >= 3; research-only oracle, no copy, translation, dependency, or vendoring |
| OpenChrom Shimadzu GCD converter | A separately distributed proprietary plug-in exists, but it was not a usable or redistributable oracle | Not copied, executed, bundled, or used as an implementation dependency |
| `olefile` 0.47 | Provides read-only CFB container access; it does not implement Shimadzu semantics | BSD/PIL-style permissive runtime dependency |

No second openly executable semantic GCD parser was found. Confidence instead comes
from agreement among the independent byte decoder, the native container invariants,
the paired LabSolutions ASCII values, and a larger independent corpus described below.

## Exact fixture result

| Field | Result | Status |
|---|---:|---|
| Producer software | LabSolutions 5.82 | Required exact profile field |
| Instrument model | GC-2014 | Required exact profile field |
| Signal mapping | one `Ch1` linked to `SFID1` | Required exact profile field |
| Signal unit / factor | selected `DUS=1`: `uV` / `VF1`; bounded alternatives `mV` / 1,000 and `V` / 1,000,000 | Required exact profile fields; selected output is `uV` |
| Conversion factors | `CF=1`, `GF=1` | Required exact profile field |
| Point count | 66,255 | Verified |
| Sampling interval | 40 ms | Verified in signal header, metadata link, and paired ASCII |
| First retention time | 0.0003333333333333333 min | Verified from `DLT=20 ms` |
| Last retention time | 44.169666666666664 min | Verified |
| Signal minimum | -395.7000058963895 uV | Verified |
| Signal maximum | 347432.1051771417 uV | Verified |
| Peak table | Not parsed | Unsupported |

The time axis is `t[i] = (DLT_ms + i * interval_ms) / 60000`. It is not the
`(i + 1) * interval` construction used by the inspected GPL reader. Every ASCII time
equals the native calculation rounded to five decimals; every ASCII intensity equals
the corresponding native value rounded to the nearest integer. The maximum native-to-
ASCII signal rounding error is below 0.5 uV.

## Independent-corpus corroboration

The Cambridge Apollo dataset at DOI `10.17863/CAM.108306` is licensed CC BY 4.0 and
contains 320 GCD files, 353 text exports, and 306 exact filename pairs. Its inspected
files reproduce the same container, signal-block, time-delay, interval, and unit/factor
relationships. They use BID/BID1 and LabSolutions 5.71 SP2 or 5.86, so they corroborate
the structural interpretation but do **not** expand this adapter's initial FID/5.82
support boundary.

## GO decision and remaining gates

Experimental support is justified because detection is bounded, the scientific signal
and retention-time axis have a same-run reference, malformed containers can be rejected,
and the unit and factors are explicit in the linked metadata. The adapter must reject
other software versions, detectors, units, factors, ambiguous channel links, multiple
populated channels, non-finite values, and inconsistent lengths.

Verified promotion still requires at least three independent in-scope FID GCD runs,
cross-fixture regression, and preferably an official Shimadzu export or documented
conformance path. GCsolution generations, BID/TCD/MS profiles, `.QGD`, `.LCD`, multiple
channels, peak tables, method interpretation, and write support remain unsupported.
