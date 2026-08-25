# YoungIn YL-Clarity PRM scientific family

- Status: Experimental
- Adapter: `youngin_yl_clarity_prm_raw`
- Individually validated producers: YL-Clarity `9.0.1.19` and `9.1.0.76`
- Compatible producer boundary: strictly framed YL-Clarity `9.x` files that pass the
  complete structural and scientific-family fingerprint
- Runtime dependency on YL-Clarity, Clarity, vendor DLLs or executables: none
- Peaks, Area and Height from PRM: unsupported

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

Ten content-confirmed same-run FID+TCD pairs validate 263,520 time points and 263,520
response points. Each official curve is CP949 tab text with a five-decimal minute axis and
four-decimal response. Every time lexeme matches `format(i / 600, ".5f")`; every response
matches its stored binary32 value within the bound derived from the export precision. Both
official channel headers declare voltage in mV, including the stream whose stored label is
FID. The production units are therefore FID mV and TCD mV, not a global FID-to-pA rule.

The broader 9.0 structural corpus remains 23 files, 43 current channels and 563,240 records,
including TCD-only and FID+TCD files with one to three history entries. The same current-
revision rule and scientific-family fingerprint are applied to every file.

### YL-Clarity 9.1.0.76

Five content-confirmed same-run FID+TCD pairs validate 138,000 time points and 138,000
response points using the same time and identity-response semantics. Their explicit official
headers declare FID pA and TCD mV. This exact profile retains its stricter single-history,
source-ordered FID/TCD and equal-count envelope.

Across both validated profiles, the common scientific core is backed by 401,520 time points
and 401,520 response points. Physical response units remain profile-specific.

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
`Signals_Records_*` sheets. No new workbook schema or YoungIn-specific GUI control is added.

The desktop route is **Add → Output → Preflight → Convert**. Exact adapter ownership means no
Mapping or Recipe is required. Preflight keeps validated profiles on the `Exact adapter` route,
labels fingerprint-compatible scientific inputs as `Compatible family — scientific signal`,
and labels science-incomplete inputs as `Compatible family — structural only`. The latter two
remain routable, with the unresolved scientific boundary available in the row tooltip and
details. CLI users request the same rows explicitly:

```console
ordifile convert run.prm --include-signals --output Ordifile_Result.xlsx
```

Neither route calls YL-Clarity or Clarity, loads a vendor DLL, or creates a temporary CSV.

## Peak-result boundary

PRM emits no `PeakRecord`, Area or Height. Paired Result evidence did not identify a repeatable
bounded stored result record, and a scientific curve is not a license to reconstruct vendor
integration. Ordifile performs no numerical integration, baseline reconstruction or automatic
peak detection. The separate exact Result CSV adapter remains the production path for explicit
RT/Area/Height rows.

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
