# GC adapter boundaries

- Status: Accepted research boundary; no proprietary adapter implemented
- Date: 2026-08-16
- Evidence:
  - [`gc-fixture-search.md`](../research/gc-fixture-search.md)
  - [`youngin-chromass-format-investigation.md`](../research/youngin-chromass-format-investigation.md)
  - [`external-fixture-policy.md`](../research/external-fixture-policy.md)

## Context

Ordifile v0.1.0 supports only verified generic tabular exports. Research has identified
a small BSEE Agilent ChemStation GC-FID `.ch` v181 file and has established official
product and lifecycle evidence for YOUNG IN Chromass, YL-Clarity, and Autochro. Neither
track authorizes a proprietary parser in this release branch.

The boundary must prevent an instrument brand, a file extension, or a recovery artifact
from becoming a broad support claim.

## Accepted

1. `youngin_yl_clarity`, `youngin_autochro`, and `youngin_export` are research and
   fixture-tracking categories, not runtime adapter IDs or public support entries.
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
   Signal shape, channel order, filename, or model marketing material is not detector
   evidence. Unknown detector and unit semantics remain unknown.
7. Required sibling roles are exact, versioned, and fixture-backed. A missing, changed,
   aliased, or out-of-root required member fails the whole logical acquisition. Unknown
   siblings are not executed or interpreted.
8. A YoungIn or Clarity export that exactly matches Ordifile's documented generic
   schema may use the existing generic adapter, but that is not native Raw support. A
   different stable layout requires a separately tested format/profile adapter, such
   as `clarity_export_<profile-version>` or `autochro_export_<profile-version>`.
9. The first proprietary implementation candidate remains the BSEE Agilent ChemStation
   GC-FID `.ch` internal v181 slice. Implementation still requires bounded detection,
   independently justified field semantics, resolved or explicitly unknown units,
   provenance and license review, exact real-fixture tests, corrupt-input tests, and
   cross-platform verification.
10. YOUNG IN Chromass is reconsidered for first-adapter priority as soon as a complete
    lawful fixture, exact CDS version, completed-versus-recovery classification,
    FID/TCD channel semantics, paired unbunched official export, reproducible test
    permission, and lawful implementation route are all available.

## Deferred

- Every YOUNG IN Chromass native adapter and branded export-profile adapter; status is
  `BLOCKED_BY_FIXTURE`.
- Clarity `.raw` recovery inspection or salvage.
- Autochro generation mapping and native file readers.
- FID/TCD multi-channel support claims without a real paired fixture.
- A directory or compound-acquisition input API.
- Any proprietary entry in `ordifile formats` or the README support table.

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

The BSEE v181 candidate must stay signal-only and version-specific unless further
fixtures prove more. It must not claim peaks, TCD, all `.ch` generations, whole `.D`
directories, GC-MS, or write support.

The YoungIn track must stay documentation-only until the fixture request is fulfilled.
A future support matrix must separate ChroZen from YL6500, YL-Clarity from each
Autochro generation, completed data from recovery data, and FID from TCD and
multi-channel claims.
