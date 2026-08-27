# YoungIn YL-Clarity PRM scientific-family equivalence

- Date: 2026-08-25
- Individually validated profiles: YL-Clarity `9.0.1.19` and `9.1.0.76`
- Structural family: `COMPATIBLE_NOT_IDENTICAL`
- Common time and numeric-response semantics: `GO`
- Shared physical-unit rule: `NO_GO`; units remain profile-specific
- Stored/vendor PRM peaks, Area and Height: `NO_GO`; selectable Ordifile-derived
  `calculated_area` is a separate Experimental capability

This privacy-safe record explains why Ordifile shares one time/numeric-response core without
claiming that every YL-Clarity release was individually validated. Native PRMs, official
curves, filenames, local paths and measured arrays remain local-only.

## Structural corpus

| Validated producer | PRMs | Current channels | Finite records | Observed history | Stored-label layouts |
|---|---:|---:|---:|---|---|
| `9.0.1.19` | 25 | 47 | 615,940 | 1–4 | FID+TCD: 22; TCD-only: 3 |
| `9.1.0.76` | 5 | 10 | 138,000 | 1 | FID+TCD: 5 |
| Total | 30 | 57 | 753,940 | — | — |

All 57 current channels use the same bounded `RAWData6 -> metadata -> PRMData -> DetName`
grammar, byte-identical duplicate gzip payloads, finite little-endian binary32 ordering,
`RAWSize == DSize == record_count`, `DStep=1`, `MinTicks=600`, and current-revision source
order. History cardinality, channel layout and absolute record counts differ, so the files are
compatible rather than byte-identical.

## Completed 9.1 counterfactual replay

Before a 9.0 full curve was available, a local research-only probe changed only the typed,
equal-length producer field of the five validated 9.1 sources in temporary copies. The masked
structural replay reproduced 10/10 channel identities and 138,000/138,000 time and response
values. This established a version-independent candidate but did not by itself change the
production gate. Originals were unchanged and derived bytes were deleted.

## Decisive 9.0 full-curve evidence

A bounded owner corpus supplies twelve distinct exact `9.0.1.19` FID+TCD PRMs and twelve
same-run full-range curve exports. Per-channel record counts vary, giving 158,110 FID points
and 158,110 TCD points.

Pairing uses unique full-series content equality in source channel order, not filenames.
For all 316,220 time points:

```text
t[i] = 0 + i * DStep / MinTicks
DStep = 1
MinTicks = 600
x unit = min
```

Every five-decimal time lexeme matches the candidate. For all 316,220 response points, the
official four-decimal value matches the stored binary32 value within the precision-derived
absolute bound `0.00005001`; the transformation is identity. Point-count equality proves that
the supplied curves are full resolution and that no point loss is present. The exports do not
carry Time Step, Global Filter or Bunching metadata, so those UI states are recorded as absent
from export metadata rather than guessed.

Both 9.0 curve blocks explicitly use `Voltage [mV]`. Full-series source-order matching assigns
the first block to the stored-label FID stream and the second to TCD. The validated 9.0 units
are therefore FID mV and TCD mV.

## Shared and profile-specific semantics

| Capability | 9.0 evidence | 9.1 evidence | Production decision |
|---|---:|---:|---|
| Zero-origin minute time | 316,220/316,220 | 138,000/138,000 | Shared core |
| Identity numeric response | 316,220/316,220 | 138,000/138,000 | Shared core |
| Stored FID label | mV | pA | Profile-specific unit |
| Stored TCD label | mV | mV | Profile-specific unit |
| Direct peaks/Area/Height | no stored grammar | no stored grammar | Unsupported |

The shared scientific evidence is 454,220 time points and 454,220 response points. Producer
version is provenance and unit evidence, not the formula source of truth.

## Compatibility-first production boundary

The runtime first proves structural safety, then evaluates a typed scientific fingerprint.
Exact `9.0.1.19` and `9.1.0.76` are individually validated and receive their evidence-backed
unit mappings. A strictly framed, otherwise unknown YL-Clarity 9.x file may produce an
Experimental scientific signal only when every family invariant matches. Its retention-time
unit is the validated family minute unit; its physical response unit remains unresolved.

If the structural reader is safe but the scientific fingerprint is incomplete, the file is
downgraded to ordered decoded records. Corrupt payload framing, duplicate mismatch, size
mismatch, invalid history or channel structure still fail closed. YL-Clarity 8.x and 10.x are
outside the current family boundary. This runtime compatibility is not a claim that all 9.x
versions were individually validated.

## Peak and Result boundary

No raw-signal integration, baseline reconstruction or automatic peak detection was used.
PRM-derived peaks, Area and Height remain unsupported. The separate exact Result CSV adapter
continues to preserve explicit RT/Area/Height rows with independent provenance.

## Interoperability and privacy

The implementation is independently written from owner-controlled bytes and paired official
exports. It includes no vendor source, executable, DLL or SDK and changes no license,
authentication or access-control mechanism. Owner files and generated workbooks remain absent
from Git, Actions artifacts, wheels and sdists. Public records contain aggregate counts,
precision rules and status only.
