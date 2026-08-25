# Cross-vendor compatibility and partial-capability policy

- Status: Accepted
- Date: 2026-08-25
- Evidence: [`cross-vendor-adapter-hard-gate-audit.md`](../research/cross-vendor-adapter-hard-gate-audit.md)

## Purpose

Ordifile separates a source's producer/version provenance from the byte structure and
scientific rules that justify canonical output. A version string is not automatically a
scientific formula, but it remains a required safeguard when no evidence-backed family
classifier exists.

This policy does not make proprietary adapters permissive. It prevents both unnecessary
whole-file rejection and unsupported scientific inference.

## Capability states

The following capabilities are evaluated independently when an adapter's evidence and
canonical contract permit it:

- `STRUCTURAL_RECORDS`
- `SCIENTIFIC_TIME_AXIS`
- `SCIENTIFIC_SIGNAL`
- `SIGNAL_UNIT`
- `RESULT_PEAKS`
- `RESULT_AREA`
- `RESULT_HEIGHT`
- `SECONDARY_RETENTION`
- `CHANNEL_IDENTITY`
- `DETECTOR_IDENTITY`

Each capability is described as one of:

- `GO`: evidence-backed canonical output is emitted;
- `PROFILE_SPECIFIC`: valid only within the named evidence boundary;
- `UNRESOLVED`: a value is preserved but its physical meaning or unit is not asserted;
- `UNAVAILABLE`: no value is emitted; or
- `REJECTED`: an invariant required for that output failed.

The existing canonical model already represents these states: decoded-record and
scientific-signal series are distinct, units are optional, peaks and secondary retention
are optional, and structured metadata and issues record evidence boundaries. A new global
supported/unsupported flag or capability model is not justified yet.

## Version and producer fields

A version, build or producer field can serve one or more roles:

- **A — structural discriminator:** selects or proves a byte layout;
- **B — provenance:** records the producer/evidence cohort without defining a formula;
- **C — unit-resolution hint:** resolves a physical unit only for an evidenced profile; or
- **D — unsupported-profile safeguard:** prevents unvalidated data from inheriting known
  semantics.

Removing a category B or C interpretation does not remove category D. A profile gate is
relaxed only when an actual lawful variant proves a deterministic family fingerprint,
the same emitted scientific semantics, controlled ownership, and a real user benefit.

## Routing outcomes

Adapters with an evidence-backed family classifier may use these outcomes:

1. A known validated profile emits its validated capabilities.
2. An unknown but structurally and scientifically compatible profile emits only the
   family capabilities whose meaning is established. Profile-specific units remain
   unresolved.
3. A structurally safe but science-incomplete profile emits structural records only.
4. An incompatible or corrupt profile is rejected.

Adapters without such evidence remain exact-profile only. YoungIn PRM is currently the
only proprietary adapter with an accepted compatibility-family classifier.

A family owner that recognizes an unsupported or malformed profile remains the owner but
must report `matched=True`, `routable=False`, and its structured failure code. It must not
fall through to a generic table adapter or appear `Ready` in Preflight.

## Partial output

- Valid structural records are not suppressed because time semantics are unresolved.
- Valid time and numeric signal are not suppressed because a physical response unit is
  unresolved.
- Explicit numeric Result Area or Height is not suppressed because its physical unit is
  unresolved.
- Missing peak support does not suppress a valid chromatogram.
- An optional unsupported channel may be isolated only when the source grammar proves
  that the remaining channel is independently complete.

No adapter may fill an unresolved capability by interpolation, unit inference from a
detector name, numerical integration, peak detection, RT alignment, or vendor-result
imitation.

## Presentation and ownership

Preflight distinguishes routable exact/family/partial inputs from recognized unsupported
or malformed inputs using the existing route and issue model. Metadata and workbook rows
preserve profile/version provenance and native or unresolved units without normalization.
No new GUI control or workbook sheet is required.

Any future family relaxation must add positive exact and compatible cases, rejected and
corrupt cases, unknown-version behavior, adapter collision tests, generic fallback tests,
and workbook/Preflight regression. Extension-only or common `RT`/`Area` headers are never
sufficient ownership evidence.
