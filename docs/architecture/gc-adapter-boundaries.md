# GC adapter boundaries

- Status: Accepted; Agilent v181 and YoungIn YL-Clarity 9.0.1.19 decoded records,
  one Shimadzu LabSolutions 5.82 chromatogram profile, and one Shimadzu GCMSsolution
  QGD TIC profile are Experimental
- Date: 2026-08-16
- Evidence:
  - [`gc-fixture-search.md`](../research/gc-fixture-search.md)
  - [`youngin-chromass-format-investigation.md`](../research/youngin-chromass-format-investigation.md)
  - [`external-fixture-policy.md`](../research/external-fixture-policy.md)

## Context

Ordifile v0.1.0 supports only verified generic tabular exports. Subsequent research identified
a small BSEE Agilent ChemStation GC-FID `.ch` v181 file and has established official
product and lifecycle evidence for YOUNG IN Chromass, YL-Clarity, and Autochro. Neither
track authorizes a broad proprietary-format claim.

The boundary must prevent an instrument brand, a file extension, or a recovery artifact
from becoming a broad support claim.

## Accepted

1. `youngin_yl_clarity`, `youngin_autochro`, and `youngin_export` remain broad research
   categories. The runtime ID `youngin_yl_clarity_prm_raw` names only the exact observed
   YL-Clarity 9.0.1.19 structural profile and is not an umbrella vendor entry.
2. Runtime adapters are named for a verified byte format and version family. A future
   completed Clarity reader may use an ID such as `clarity_prm_<version-family>` only
   after a lawful, self-contained fixture proves its signature and version boundary.
3. A completed Clarity `.prm` may use the existing single-file `FormatAdapter` v1 only
   when a fixture proves that it is self-contained. General Clarity evidence does not
   establish byte-for-byte YL-Clarity compatibility.
4. Clarity `.raw` files are acquisition or recovery artifacts, not normal completed
   chromatograms. They are never a fallback extension for a `.prm` adapter, never
   merged automatically with completed results, and never exported as an ordinary
   successful run.
5. One verified acquisition maps to one `SampleRecord`. Each explicitly identified
   detector channel maps to one uninterpolated `SignalSeries`, preserving its native
   time axis, values, units, channel identity, and source order.
6. `FID` or `TCD` is assigned only when the source explicitly identifies the detector.
   Signal shape, channel order, ad hoc or partial filenames, and model marketing
   material are not detector evidence. An exact complete basename may be used only
   when an official vendor filename convention defines its detector/module/channel
   roles; renamed or partial files remain unsupported and are rejected. Unknown
   detector and unit semantics remain unknown.
7. Required sibling roles are exact, versioned, and fixture-backed. A missing, changed,
   aliased, or out-of-root required member fails the whole logical acquisition. Unknown
   siblings are not executed or interpreted.
8. A YoungIn or Clarity export that exactly matches Ordifile's documented generic
   schema may use the existing generic adapter, but that is not native Raw support. A
   different stable layout requires a separately tested format/profile adapter, such
   as `clarity_export_<profile-version>` or `autochro_export_<profile-version>`.
9. The first proprietary implementation is the exact BSEE Agilent ChemStation GC-FID
   `.ch` internal-v181 structural slice. Two public readers and an independent decoder
   agree on the 36,501 decoded values, while one reader exposes only 36,500 time labels.
   The adapter therefore retains every decoded record with ordinal x, unscaled integer
   y, unknown units, and explicit Experimental warnings. It does not expose retention
   time or apply candidate scaling. See
   [`agilent-chemstation-ch-v181-investigation.md`](../research/agilent-chemstation-ch-v181-investigation.md).
10. The owner-supplied intake authorizes local validation of 23 completed PRM files.
    Their exact producer marker, bounded typed properties, duplicate gzip blocks,
    record-count equations, finite binary32 payloads and stored FID/TCD labels support
    an Experimental structural adapter. Paired official export remains mandatory for
    Verified scientific semantics, not for deterministic raw-record conversion.
11. The Shimadzu runtime boundary is one LabSolutions 5.82 `GC-2014` file with a
    single `Ch1` mapping to `SFID1`, `uV`/`VF1`, and identity conversion/gain factors.
    A paired same-run ASCII chromatogram and an independent byte decoder validate the
    66,255-point signal and DLT-based time axis. This does not authorize legacy
    GCsolution, other LabSolutions versions, other detectors, multichannel files,
    `.QGD`, `.LCD`, or generic `.GCD` support. See
    [`shimadzu-gcsolution-gcd-investigation.md`](../research/shimadzu-gcsolution-gcd-investigation.md).
12. The separate QGD boundary is the exact `4.00` GCMSsolution compound-file profile
    in the CC0 Dryad fixture. It exposes only the 16,800-point TIC and verified minute
    axis; the TIC unit is unknown. Its MS1 index and blocks are validated structurally,
    and every scan intensity sum is required to equal the native TIC, but encoded mass
    is not called m/z and MS1 is not exported. See
    [`shimadzu-gcmssolution-qgd-investigation.md`](../research/shimadzu-gcmssolution-qgd-investigation.md).
13. The YoungIn runtime boundary is the exact observed YL-Clarity `9.0.1.19` PRM
    profile. Current blocks are exposed as `decoded_record_index` plus unscaled stored
    binary32 values. Stored FID/TCD labels may separate structural channels with an
    Experimental status, but detector verification, retention time, physical scaling,
    units and peaks remain unresolved or unsupported. See
    [`youngin-yl-clarity-prm-raw-format-notes.md`](../research/youngin-yl-clarity-prm-raw-format-notes.md).

## Deferred

- YoungIn PRM scientific-signal output and Verified promotion remain
  `BLOCKED_BY_PAIRED_EXPORT`; the narrow raw-record adapter is not blocked.
- Clarity `.raw` recovery inspection or salvage.
- Autochro generation mapping and native file readers.
- FID/TCD multi-channel support claims without a real paired fixture.
- A directory or compound-acquisition input API.
- Any proprietary **Verified** entry in `ordifile formats` or the README support table
  before its scientific semantics and same-run official export are validated.
- Shimadzu GCD profiles outside the exact LabSolutions 5.82 FID boundary, including
  the corroborating BID corpus, until each profile has its own fixture-backed gate.
- QGD MS1 scientific output, other QGD versions, width-4 recovery variants, SIM/MRM,
  compound identification, quantitation, and write support.

If evidence later proves that a logical acquisition is a directory or exact sibling
set, add an adapter API v2 with an immutable source-artifact kind, member inventory,
and canonical tree digest. The v1 single-file protocol and entry-point compatibility
remain unchanged through an internal wrapper. Directory grouping must use verified
container relationships or run identifiers, never basename or timestamp heuristics.

## Rejected

- One umbrella `youngin` or `youngin_*` runtime adapter.
- Treating `.prm` and `.raw` as interchangeable.
- Extension-only detection or automatic sibling grouping by basename, proximity, or
  acquisition time.
- Inferring FID/TCD from signal appearance or channel position.
- Calling arbitrary YL-Clarity or Autochro exports native Raw support.
- Implementing from marketing pages, screenshots, vendor executables, or protected
  program files without a lawful native fixture and independent verification.

## Implementation gate summary

The BSEE v181 adapter is limited to a standalone, version-specific decoded-record
stream. `SeriesKind.DECODED_RECORDS` and `SupportStatus.EXPERIMENTAL` keep it separate
from verified scientific signals. Verified promotion remains blocked by scientific
point-count, retention-time, scaling, unit, additional-run, and official-export
evidence. It must not claim peaks, TCD, all `.ch` generations, whole `.D` directories,
GC-MS, or write support.

The YoungIn raw-conversion track is Experimental GO after the 2026-08-17 local intake.
The 23 completed PRM files establish one exact producer/layout profile, 43 bounded
duplicate-validated raw blocks, stored FID/TCD labels and deterministic binary32
records. `SeriesKind.DECODED_RECORDS` keeps those values separate from scientific
signals. Retention time, detector verification, scaling, units and peaks remain
unsupported or unresolved, and paired official export is still required for Verified
promotion. The support matrix continues to separate YL-Clarity from Autochro,
completed PRM from recovery RAW, and the exact observed profile from broad YoungIn
claims.

The Shimadzu Experimental profile may expose `SeriesKind.SCIENTIFIC_SIGNAL` because
its paired same-run LabSolutions ASCII reference validates the sampled time and signal
values. Verified promotion remains blocked by the single in-scope real FID fixture and
the absence of broader independent in-profile validation.

The QGD Experimental profile may expose its TIC as `SeriesKind.SCIENTIFIC_SIGNAL`
because source RT/TIC arrays and all scan-level intensity sums agree. This does not
authorize treating its structurally decoded MS records as mass spectra or flattening
them into the chromatogram signal schema.
