# Cross-vendor proprietary adapter hard-gate audit

- Status: Complete; no new family relaxation justified
- Date: 2026-08-25
- Scope: existing Agilent, Shimadzu, YoungIn and LECO proprietary adapters
- Policy: [`cross-vendor-compatibility-policy.md`](../architecture/cross-vendor-compatibility-policy.md)

## Decision summary

YoungIn PRM is the reference compatibility-family implementation. The other adapters have
useful partial capabilities, but no actual lawful variant currently proves that an exact
version/profile gate can be removed without weakening structure, scientific meaning, unit
attribution or deterministic ownership.

| Adapter | Version/build role | Available capability | Actual evidence | Decision |
|---|---|---|---|---|
| Agilent ChemStation CH v181 | Internal `181` is a byte-layout discriminator; producer text is provenance/safeguard | decoded structural records; time, scaling and unit unresolved | one v181 source; v179 research evidence is scientifically inconsistent | `KEEP_EXACT` |
| Agilent ChemStation Result XML | `C.01.10 [201]` is provenance/safeguard; exact XML schema, signal, unit and quantitation paths establish the implemented slice | peaks, RT min, Area pA\*s, Height pA, explicit boundaries | one 36-row source | `NEEDS_MORE_EVIDENCE`; operationally `KEEP_EXACT` |
| Shimadzu LabSolutions GCD | File schema `5.01` is structural; software `5.82` is provenance/safeguard; channel, factors, unit and signal framing are scientific gates | 66,255-point RT min and FID uV signal | one FID source plus same-run curve | `NEEDS_MORE_EVIDENCE`; operationally `KEEP_EXACT` |
| Shimadzu GCMSsolution QGD | File Property `4.00` is a profile/schema marker; array and scan equations are the scientific fingerprint | 16,800-point RT/TIC; physical TIC unit unresolved; MS1 unavailable | one fully validated source from a ten-file lawful corpus | `PARTIAL_CAPABILITY`; gate `KEEP_EXACT` |
| Shimadzu LabSolutions Result ASCII | `5.82` is provenance/safeguard; exact section, instrument, channel and peak-table grammar establish the slice | peaks and RT/start/end min; numeric Area/Height with unresolved physical units | one 83-row source | `PARTIAL_CAPABILITY`; gate `KEEP_EXACT` |
| YoungIn YL-Clarity PRM | Framed 9.x producer is family ownership/safeguard; exact versions resolve provenance and units; the formula is fingerprint-driven | structural records; compatible scientific RT/numeric signal; profile-specific or unresolved units | 30 PRMs, 57 channels, 753,940 records; 454,220 time and 454,220 response comparisons | `RELAXED_FAMILY` |
| YoungIn YL-Clarity Result CSV | No embedded version gate; exact encoding, section, numeric, Total and trailer grammar is the evidence boundary | peaks, RT min, Area mV.s, Height mV | two exports and six rows; different composite exports are research-only | `KEEP_EXACT` |
| LECO ChromaTOF GCxGC Result text | Version `4.72.0.0` is external provenance; exact rare header/column/text grammar owns the file | peaks, RT1/RT2 s, profile-specific Area/Height AU | one 100-row CC0 source | `KEEP_EXACT` |

## Capability matrix

`TIME` and `SIGNAL` below mean chromatogram time/signal output, not a Result peak's RT.
`UNIT` is the signal-response unit. Exact-profile values remain `PROFILE_SPECIFIC` even
when their scientific meaning is fully validated.

| Adapter | STRUCTURAL RECORDS | TIME | SIGNAL | UNIT | PEAKS | AREA | HEIGHT | RT2 | CHANNEL | DETECTOR |
|---|---|---|---|---|---|---|---|---|---|---|
| Agilent CH v181 | `GO` | `UNRESOLVED` | `UNAVAILABLE` | `UNRESOLVED` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` |
| Agilent Result XML | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` |
| Shimadzu GCD | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` |
| Shimadzu QGD | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `UNRESOLVED` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` |
| Shimadzu Result ASCII | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` |
| YoungIn PRM | `GO` | fingerprint `GO`; otherwise `UNAVAILABLE` | fingerprint `GO`; otherwise `UNAVAILABLE` | exact `PROFILE_SPECIFIC`; compatible `UNRESOLVED` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `GO` | exact `PROFILE_SPECIFIC`; compatible `UNRESOLVED` |
| YoungIn Result CSV | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `UNRESOLVED` |
| LECO GCxGC Result | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `UNAVAILABLE` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `PROFILE_SPECIFIC` | `UNAVAILABLE` | `UNAVAILABLE` |

## Hard-gate inventory

Eight logical version/build/producer gate groups were reviewed:

1. Agilent CH internal version `181`;
2. Agilent CH producer marker;
3. Agilent Result XML revision;
4. Shimadzu GCD file schema `5.01`;
5. Shimadzu GCD software version `5.82`;
6. Shimadzu QGD File Property `4.00`;
7. Shimadzu Result ASCII software version `5.82`; and
8. YoungIn framed 9.x producer plus exact-profile unit attribution.

The CH internal version, GCD file schema and QGD File Property are current structural
discriminators. The Agilent XML, GCD and Shimadzu Result software revisions are likely
provenance/safeguard fields rather than formula inputs, but no same-grammar variant proves
safe relaxation. The Agilent CH producer marker is also conservative but remains a useful
ownership safeguard. YoungIn is the only gate already relaxed from exact-version formula
selection to an evidence-backed family fingerprint.

The YoungIn Result and LECO bytes contain no software-version marker; their documented
versions are evidence provenance, while their exact grammars are the runtime gates.

## Variation evidence

- Agilent v179 evidence does not reproduce one unambiguous v181 scientific time/signal
  interpretation and cannot justify a CH family.
- Agilent's published Result XML schema is broader than the single-signal `Percent/Area`
  slice. A different revision with full RT/Area/Height/unit equality is still required.
- A lawful Shimadzu GCD corpus contains 320 real sources across other software revisions,
  but its BID/BID1 detector layout and streams differ from the implemented FID profile.
  Removing only the `5.82` check would not make those files compatible.
- Nine additional lawful QGD files are the highest-value bounded follow-up before relaxing
  the fixed scan-count/time-envelope profile. This audit does not attempt MS1 decoding.
- Other Shimadzu Result exports use BID or multichannel layouts rather than the exact
  nine-section FID grammar.
- YoungIn composite Result exports differ in grammar and displayed Total semantics from
  the standalone exact Result adapter.
- Other known ChromaTOF tables use different 1D/multi-run layouts and do not prove the
  exact GCxGC grammar is a cross-version family.

## Product impact

No actual scientifically compatible variant was proven to be rejected solely because of
a version string, so this audit relaxes zero additional adapter families. The justified
exact gates remain seven adapters; YoungIn PRM remains the one compatible family.

The audit did identify one user-facing correctness defect shared by the exact adapters:
recognized unsupported or malformed family inputs retained ownership but their probes
defaulted to routable. Preflight could therefore show `Ready` before conversion failed.
The focused correction preserves exact ownership and generic fallback behavior while
marking those matches non-routable with their original structured error code. Only an
explicit allowlist of semantically precise version/schema/detector/signal/unit/encoding and
related capability codes is presented as unsupported format. Overloaded `PROFILE_UNSUPPORTED`
codes, corruption, conflicts, truncation and invalid values remain malformed input.

This correction changes no scientific formula, unit, canonical value, sheet, parser
grammar or ownership boundary. Adapter patch versions change only so reviewed route
snapshots cannot silently reuse the old probe behavior; the Ordifile public package version
remains `0.5.0`.

## Remaining evidence gates

- Agilent Result XML: one actual different revision with the same bounded scientific slice.
- Shimadzu GCD: an actual alternative FID profile with a deterministic stream/science
  fingerprint, not the existing BID variation alone.
- Shimadzu QGD: bounded validation of acquisition-envelope variation across the remaining
  lawful sources.
- Shimadzu Result ASCII: one actual different software revision with the same FID grammar.
- YoungIn Result and LECO: actual grammar variants with complete row/unit validation.

Until those fixtures exist, retaining the exact gates is a data-integrity decision rather
than an all-or-nothing adapter architecture.
