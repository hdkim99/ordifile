# YoungIn YL-Clarity PRM scientific family

- Status: Experimental
- Adapter: `youngin_yl_clarity_prm_raw`
- Individually validated producers: YL-Clarity `9.0.1.19` and `9.1.0.76`
- Compatible producer boundary: strictly framed YL-Clarity `9.x` files that pass the
  complete structural and scientific-family fingerprint
- Runtime dependency on YL-Clarity, Clarity, vendor DLLs or executables: none
- Exact 9.0/9.1 marker-derived Peak RT and Area: selectable Experimental, explicitly
  Ordifile-derived in `calculated_area`
- Stored/vendor Result table and Height from PRM: unsupported

PRM contains stored chromatographic data. Ordifile separates producer provenance from
scientific capability: a version identifies the evidence cohort and known physical units,
while bounded file structure determines whether records, retention time and numeric response
can be exposed safely.

## Scientific-family fingerprint

Every accepted file first passes the structural safety reader: observed start and footer
framing, sequential history and current-revision selection, one or two source-ordered channel
blocks, byte-identical `RAWData6` and `PRMData` gzip payloads, bounded decompression, nonempty
finite little-endian binary32 records, `RAWSize == DSize == record_count`, allowlisted stored
labels (`TCD` or `FID` then `TCD`), and exact section boundaries.

Scientific conversion additionally requires the validated family fingerprint:

- `DStep=1` and `MinTicks=600` in every current channel;
- equal record counts for a two-channel file;
- zero-origin time `t[i] = i * DStep / MinTicks` in minutes;
- identity preservation of each stored binary32 numeric response.

The formula implementation is shared and does not branch on the producer version. Known
profiles that violate their validated exact envelope fail closed. A compatible 9.x file that
passes structural safety but not the scientific fingerprint is preserved as
`SeriesKind.DECODED_RECORDS` with record ordinal and no time or physical-response claim.
Malformed payloads, size mismatches, conflicting producer fields or invalid channel framing
are rejected rather than downgraded.

## Individually validated profiles

### YL-Clarity 9.0.1.19

Twelve content-confirmed same-run FID+TCD pairs validate 316,220 time points and 316,220
response points. Each official curve is CP949 tab text with a five-decimal minute axis and
four-decimal response. Every time lexeme matches `format(i / 600, ".5f")`; every response
matches its stored binary32 value within the bound derived from the export precision. Both
official channel headers declare voltage in mV, including the stream whose stored label is
FID. The production units are therefore FID mV and TCD mV, not a global FID-to-pA rule.

The broader 9.0 structural corpus contains 25 files, 47 current channels and 615,940 records,
including TCD-only and FID+TCD files with one to four history entries. The same current-
revision rule and scientific-family fingerprint are applied to every file.

### YL-Clarity 9.1.0.76

Five content-confirmed same-run FID+TCD pairs validate 138,000 time points and 138,000
response points using the same time and identity-response semantics. Their explicit official
headers declare FID pA and TCD mV. This exact profile retains its stricter single-history,
source-ordered FID/TCD and equal-count envelope.

Across both validated profiles, the common scientific core is backed by 454,220 time points
and 454,220 response points. Physical response units remain profile-specific.

## Compatible, unvalidated 9.x producers

A well-framed YL-Clarity 9.x producer outside the two individually validated versions is not
accepted by version string alone. It must pass all structural safety and scientific-family
invariants. If it does, Ordifile emits `SCIENTIFIC_SIGNAL` with retention time in minutes and
the unmodified numeric response, records `family_compatible_experimental` provenance, and
leaves the physical response unit unresolved. Stored FID/TCD labels remain source channel
identity; they do not determine physical units.

This is runtime compatibility, not evidence that every YL-Clarity release was individually
validated. YL-Clarity 8.x, 10.x, malformed producer fields and incompatible structures remain
unsupported. A future generation needs its own lawful evidence before its physical units or
exact-profile status can be added.

## Workbook and user workflow

Scientific streams use the existing `Signals_FID` and `Signals_TCD` workbook contract with
explicit `x_label`, `x_unit`, `y_label` and `y_unit` columns. A compatible profile with an
unresolved response unit keeps the numeric rows and leaves `y_unit` blank; Metadata and
Import_Log record the fixed compatibility warning. Structural-only files use existing
`Signals_Records_*` sheets. The GUI exposes a dedicated unchecked option without hiding it in
advanced controls; CLI/API callers must request it explicitly. When an exact validated profile also contains the bounded
marker/integration fingerprint, Ordifile writes experimental derived rows to the existing `Peaks` and
`Peak_Order_Matrix` sheets. The source-explicit `area` field remains empty; the independent
estimate is written to `calculated_area`. Each row carries its data origin, method identifier
and evidence profile.

The desktop route is **Add → Output → Preflight → Convert**. Exact adapter ownership means no
Mapping or Recipe is required. Preflight keeps validated profiles on the `Exact adapter` route,
labels fingerprint-compatible scientific inputs as `Compatible family — scientific signal`,
and labels science-incomplete inputs as `Compatible family — structural only`. The latter two
remain routable, with the unresolved scientific boundary available in the row tooltip and
details. CLI users request the same rows explicitly:

```console
ordifile convert run.prm --include-signals --output Ordifile_Result.xlsx

# Explicitly request the independent experimental Area calculation.
ordifile convert run.prm --experimental-derived-area --output Ordifile_Result.xlsx
```

Neither route calls YL-Clarity or Clarity, loads a vendor DLL, or creates a temporary CSV.

## Derived-Area boundary

PRM does not expose a repeatable bounded stored Result table. Exact validated profiles may
instead expose stored start/apex/valley/end marker partitions and numbered current-history
processing tables. Ordifile binds the current detector table by source channel order and applies
only the bounded exclusion rule observed in the same paired corpus. The full optional-event
shape and sequence must remain inside that bounded fingerprint; otherwise calculated Area fails
closed while Signals remain available. The later non-fixed-format evidence includes processing
events that add or terminate official peaks without a one-to-one marker window; Ordifile does
not reconstruct those rows. It uses the raw maximum inside each retained partition for RT.
Original single-peak 9.0 Legacy clusters use adjacent envelope contacts with a straight
base-to-base baseline; multi-peak 9.0 clusters and 9.1 use the shared cluster lower envelope.
All variants use a deterministic trapezoidal Area calculation.

Across 27 local-only same-run pairs, 340 safely emitted rows align with official displayed RT and
order at export precision; 7 rows governed by an unimplemented processing-event shape are
omitted. Area is not vendor-equivalent: 264/340 rows are within 1%, 288/340 within 5%, and
integration-sensitive peaks include larger differences. Area matches 112/340 rows after
two-decimal rounding and 2/340 after numerical rounding to four decimals. The 18 safely emitted
rows from the new 25-row non-fixed oracle present official Area at three decimals; the earlier
fixed-format oracles present four. GUI, CLI and API
callers opt in. The result describes the same paired corpus used to select the rules; no
untouched holdout has established generalization. Official Area coverage is 9.0 FID 243, 9.0 TCD 83,
9.1 TCD 21, and 9.1 FID 0 (not tested).
Every calculated row is labelled
`ordifile_marker_derived` and `ordifile_derived_experimental`; the
estimate is written to `calculated_area`, source-explicit `area` remains empty, and Height
remains unavailable. See the
[derived-Area investigation](../research/youngin-yl-clarity-prm-derived-area-investigation.md).

The separate exact Result CSV adapter remains the path for explicit vendor RT/Area/Height rows.

## Privacy and interoperability

Owner archives, PRMs and exports remain outside Git, wheels, sdists and Actions artifacts.
Runtime identities are SHA-256 aliases; private filenames, paths, serial suffixes, operator or
sample fields, and measured arrays are not public output. Producer parsing decodes only the
bounded numeric version before `FULL, SN:` and never decodes or stores the suffix.

The parser is an independent file-format interoperability implementation based on
owner-controlled bytes and paired official exports. It bundles no vendor source, DLL,
executable or SDK and changes no license, authentication or access-control mechanism. See the
[format research notes](../research/youngin-yl-clarity-prm-raw-format-notes.md), the
[cross-version evidence](../research/youngin-yl-clarity-prm-cross-version-equivalence.md), the
[sanitized 9.0 manifest](../research/youngin-yl-clarity-prm-9-0-scientific-external-fixture-manifest.json),
and the
[sanitized 9.1 manifest](../research/youngin-yl-clarity-prm-scientific-external-fixture-manifest.json).
