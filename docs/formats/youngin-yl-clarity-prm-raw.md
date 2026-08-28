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
processing tables. Ordifile binds the current detector table by source channel order. The full
processing-table shape and sequence must remain inside the bounded fingerprint; otherwise
calculated Area fails closed while Signals remain available.

For each stored marker cluster Ordifile resolves peak groups from the lower convex hull of the
stored signal, gives each group one straight baseline between its own baseline contacts, and
separates fused peaks inside a group at the stored-response minimum between neighbouring
stored apexes. A group boundary created by a baseline contact walks back from the stored valley
through response excursions no larger than the stored `Threshold` value. RT is the
stored-response maximum inside the stored partition. Area is
`sum over k in [start, end) of (response[k] - baseline(k + 0.5)) * dt_seconds`.
That is a controlled-corpus-derived left-edge/midpoint summation, not the general trapezoidal
rule. It is an independently developed Ordifile calculation designed to reproduce displayed
Result Area as closely as the validated evidence supports; it is not an implementation or
replication of the proprietary Clarity/YL-Clarity integration algorithm. A partition that does
not contain its own retention index is a structured failure.

Four owner archives covering both validated producer versions, both detectors and both
composite-export layouts hold 347 official rows. Channels whose processing table carries a
manually added timed event fail closed, which removes 42 of those rows; their scientific
Signals are preserved. Those stored opcodes (`11`, `12`, `32`) are read from owner-controlled
interventions rather than from any published specification, and the meaning of `12` is
unresolved, so none of them is acted on. Of the remaining 305 rows, RT matches 305/305 and
Area matches 304/305 at each export's own displayed precision. One archive also exists as a
vendor Excel export publishing twelve significant digits: against it, its 241 rows match on RT,
Start time and End time exactly, and on Area to a maximum relative difference of `4.025e-13`
(`4.025e-11 %`). Calculated Height is not published. GUI, CLI and API callers opt in.
Every calculated row is labelled
`ordifile_marker_derived` and `ordifile_derived_experimental`; the
calculated value is written to `calculated_area`, source-explicit `area` remains empty, and
`height` remains empty. See the
[derived-Area investigation](../research/youngin-yl-clarity-prm-derived-area-investigation.md).

This calculation follows the marker partitions stored in the PRM. If a researcher manually
adjusted peak start/end ranges or integration results in YL-Clarity, the PRM-derived calculation
must not be treated as that reviewed Result. Export the YL-Clarity Result Table as CSV and convert
that export with Ordifile to preserve the explicit vendor RT/Area/Height rows instead.

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
