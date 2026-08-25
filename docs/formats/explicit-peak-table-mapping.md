# Explicit peak-table mapping

Explicit peak-table mapping is a local, user-confirmed import mode for structured result
tables whose vendor/software profile does not have a built-in Ordifile adapter. It
does not detect or verify a vendor format.

The initial contract reuses only Ordifile's existing audited generic containers:

- comma-delimited `.csv`;
- tab-delimited `.tsv`, or `.txt` when the mapping declares TSV;
- semicolon-delimited `.txt`;
- Transitional, non-macro `.xlsx`, with a desktop-selected visible worksheet when more than
  one is available.

The desktop **Table Options** section lets the researcher explicitly choose the text encoding,
one-based header record, and visible XLSX worksheet before mapping scientific columns. Text
encodings are limited to UTF-8/UTF-8-BOM, Korean Windows (CP949), and Western Windows (1252).
There is no encoding fallback chain. Delimiters remain fixed by the declared container: comma
for CSV, tab for TSV, and semicolon for semicolon-TXT. The selected worksheet title is used
locally but is represented in conversion results and the Manifest only by the fixed
`USER_SELECTED` marker.

The CLI/API keep the existing direct-mapping behavior: an exact `--sheet`/`sheet=` selection
is accepted, and without one the audited generic XLSX reader may proceed only when the mapping
matches exactly one allowed worksheet. Zero or multiple compatible worksheets fail closed.

For delimited text, the header setting selects a bounded logical CSV record, so a quoted
multi-line preamble field remains one record. For XLSX it selects a bounded worksheet row.
Ordifile never guesses a header, encoding, delimiter, or scientific role. Legacy `.xls`, PDF,
arbitrary encodings or delimiters, formulas as scientific values, automatic footer removal,
locale-decimal guessing, and multiple runs in one table are outside this contract.

## Workflow

1. Select a structured result file.
2. If the preview is not the peak table, open **Table Options** and explicitly select the
   encoding, header record/row, or worksheet.
3. Select the exact source columns for retention time and area.
4. Declare the retention-time unit and confirm the area-unit state.
5. Optionally map height, compound, peak number, detector, channel, sample, run,
   acquisition time, integration boundaries, or a secondary retention coordinate.
6. Explicitly ignore every source column that is not mapped.
7. In the desktop, save the current **Saved setup** by name; confirmed mappings are captured
   automatically. CLI/API users may still save Mapping/Profile or Recipe JSON explicitly.
8. Convert through Preflight and the ordinary `PeakRecord` and Excel exporter pipeline.

The CLI form is:

```console
ordifile convert run001.csv run002.csv --peak-mapping peak-map.json -o results.xlsx
```

For a mixed batch containing several previously approved table templates, save those
mappings as profiles in one local Mapping Set and route the batch in one command:

```console
ordifile convert input/ --recursive --peak-mapping-set lab-mappings.json -o results.xlsx
```

The practical progression is: known exact format → automatic adapter; one unknown
table → map once; repeated same-template tables → reuse the same mapping; mixed generic
templates → use a Mapping Set. Exact-profile adapters always retain ownership before a
Mapping Set is considered.

For a neutral synthetic table with headers `Peak No.`, `Retention Time`, `Area`,
`Height`, and `Compound`, a minimal mapping can be saved as:

```json
{
  "schema_version": 1,
  "source_format": "csv",
  "retention_time_column": {"label": "Retention Time", "index": 2},
  "area_column": {"label": "Area", "index": 3},
  "retention_time_unit": "min",
  "area_unit": null,
  "height_column": {"label": "Height", "index": 4},
  "height_unit": null,
  "compound_name_column": {"label": "Compound", "index": 5},
  "peak_index_column": {"label": "Peak No.", "index": 1}
}
```

Missing optional properties mean “not mapped.” Default table-import settings are omitted,
so existing schema-version-1 JSON and semantic hashes remain unchanged. A non-default mapping
adds a strict `import_settings` object such as
`{"text_encoding":"cp949","header_row":6}`. Current Ordifile loads both forms; older Ordifile
versions can reject the extended form because unknown fields remain fail-closed. The serializer writes a normalized form
with every optional property present, including exact mapped and ignored header selectors,
units, and optional user-supplied manufacturer/software. It stores no source data rows or
source paths. Its path-independent semantic SHA-256 is stored in conversion provenance.
This semantic digest applies only to direct single-mapping mode. A Recipe-embedded single
Mapping keeps that exact digest local and uses the Recipe public fingerprint for public
provenance. Mapping Set provenance uses the separate public-safe structural fingerprint
described below.

The desktop interface provides the same mapping model. Preview and conversion receive
the same immutable mapping value; the UI does not contain a second CSV or XLSX parser.
The preview is bounded to 1,024 columns, ten rows through the public API (five in the
desktop dialog), 11,264 cells including headers, and 1,000,000 rendered characters. Text
preview also bounds each physical line to 256 KiB and the read prefix to 2 MiB. Unsafe
control and directional-format characters are rejected in headers and visibly escaped in
local preview values.

## Reusable profiles and Mapping Sets

A `PeakTableMappingProfile` combines one existing schema-version-1 mapping with a local
opaque profile ID, a local display label, and an XLSX worksheet policy. A
`PeakTableMappingSet` is a bounded ordered collection of at most 32 profiles. The set
uses its own schema version 1; existing single-mapping JSON remains loadable unchanged.
Both documents are strict, non-executable UTF-8 JSON.

Profile selection is exact structural routing, not scientific inference. For text it
uses the approved encoding/header setting and compares the declared container and every
decoded header label at its one-based position.
CSV, TSV, and semicolon-TXT remain distinct. For XLSX a profile either names one exact
local worksheet or requires one unambiguous visible worksheet, then compares the ordered
headers. Filename, directory, vendor name, display label, file hash, row count, and all
measurement or sample values are excluded from selection. Case folding, aliases, fuzzy
matching, and first-profile precedence are not used.

Exactly one match applies the already approved mapping. Zero matches produces
`PEAK_MAPPING_PROFILE_NOT_MATCHED`; multiple matches produce
`PEAK_MAPPING_PROFILE_AMBIGUOUS`; an ambiguous single-visible-sheet workbook produces
`PEAK_MAPPING_WORKSHEET_AMBIGUOUS`. The file fails without generic fallback, while other
batch files remain independently processable under `--on-error continue`. The selected
mapping is validated again against the actual header before any `PeakRecord` is created.

Each profile also has a public-safe structural fingerprint. It summarizes schema versions,
container, column count, ordered canonical roles or `IGNORED`, unit-presence states, and
worksheet-policy type. It contains no raw or hashed header labels, row values, filename,
path, worksheet title, display label, manufacturer, software, or free-text unit. This
fingerprint is an audit summary only: it cannot reproduce the mapping, is not the private
exact-match key, and does not verify a vendor.

## Schema drift diagnostics and confirmed repair

Saved profiles continue to apply only when the local container, ordered decoded headers,
duplicate-header occurrences, positions, and worksheet policy match exactly. A diagnostic
does not relax that rule. When exact matching fails, Ordifile may compare the observed local
structure with at most three same-container profiles and report fixed structural categories
such as changed, added, removed, reordered, duplicate, missing required/optional role, or
worksheet identity changes. Scientific values, row counts, filenames, paths, vendor strings,
display labels, units, aliases, fuzzy similarity, and semantic synonym dictionaries do not
participate.

The default CLI/API result contains only opaque profile IDs, public-safe fingerprints, fixed
categories, fixed canonical role names, and bounded counts. Raw expected/observed headers,
worksheet titles, and local labels are not written to terminal output, `Import_Log`, workbook
provenance, progress, or public evidence. The desktop may join an opaque profile ID with the
already loaded local Mapping Set and show the bounded local preview; that local screen and its
screenshots remain privacy-bearing.

A single diagnostic candidate is still not selected or applied. The file remains failed with
`PEAK_MAPPING_PROFILE_NOT_MATCHED`; `SCHEMA_DRIFT_CANDIDATE` only explains that a local review
is possible. Ambiguous exact profiles and ambiguous worksheets remain fail-closed. Exact
vendor/profile adapters are probed before any diagnostic and retain ownership.

Desktop repair reuses **Map Peak Columns**. Only selectors whose label and one-based position
survive exactly are prefilled. Changed, moved, removed, or duplicate-ambiguous fields remain
unmapped, so RT, Area, units, and optional roles require explicit user review. Accepting the
dialog creates a new opaque profile and adds it to a new immutable Mapping Set value; the old
profile and Mapping Set identity are preserved. Cancel creates nothing. Existing profiles are
not silently replaced, and conversion is rerun through ordinary exact matching after the new
profile is approved.

## Mixed-batch conversion preflight

`ordifile convert ... --dry-run` and `ordifile.api.plan_conversion()` apply the same
exact-adapter-first and exact-Mapping-Profile routing decisions without constructing canonical
scientific rows or creating output artifacts. Exact-adapter ownership probes may decode and
validate bounded numeric source syntax; Mapping Profile matching remains header-only. A
profile route is reported only for one exact structural match. Drift candidates remain failed
diagnostics, and zero/multiple matches never become an automatic mapping. The preflight
summary contains fixed categories, opaque profile IDs, public-safe structural fingerprints,
and whole-source SHA-256 identities; it contains no raw headers, worksheet titles, display
labels, mapping paths, or measurement rows.

The same-process `ConversionPlan` can be passed to `convert_plan()`. Execution immediately
re-discovers and re-routes the frozen input roots and compares private configuration/output
bindings. Any source-list, content, mapping, adapter, or output-state difference rejects the
plan as stale. GUI mapping repair therefore invalidates the displayed plan and requires a new
preflight. The plan does not cache a `DatasetBundle` or authorize later overwrite, and it is
not a persisted job file. Sort results, parsed validity, scientific row counts, sheet
segmentation, and optional sidecars are deferred to the existing parse/export pipeline.

## Reusable laboratory Conversion Recipes

A strict local `ConversionRecipe` connects repeated workflow settings to the same preflight
path. It can embed one explicit Mapping or one Mapping Set together with stable discovery,
sorting, signal, worksheet, failure, and sidecar choices. It never stores scientific inputs,
source/output paths, overwrite authorization, `ConversionPlan` state, or canonical rows.

Recipe JSON is privacy-bearing local configuration because embedded mappings may contain
exact headers, worksheet titles, units, local labels, and user-provided provenance. The exact
Recipe semantic SHA-256 remains local and is used only for configuration equality.
Recipe-specific public plan and workbook provenance contains only schema version and a
public-safe fingerprint that omits those private values. Existing scientific provenance and
public-safe Mapping Set provenance keeps its established workbook contract; the direct
single-Mapping semantic digest is not repeated for a Recipe-embedded Mapping. Neither Recipe
identity establishes vendor compatibility or predicts workbook contents.

Loading a Recipe does not apply mappings directly. Runtime inputs and output are combined with
the immutable Recipe, the existing conversion preflight performs exact-adapter-first routing,
through `plan_recipe()`, and `convert_plan()` repeats freshness checks before parsing. A stored
adapter is considered only when no exact-profile adapter owns the input. Template
drift remains diagnostic
only; a repaired Mapping Profile changes a new in-memory Recipe only after explicit user action,
and the previously saved Recipe file is never updated automatically.

In the desktop interface, a Recipe is presented as a named **Saved setup**, not as a JSON
file. The first confirmed generic mapping remains a simple embedded Mapping. Confirming a
second distinct table structure automatically promotes the existing and new mappings into one
internal Mapping Set; later distinct structures append deterministically. Reconfirming the
same structure and semantics is a no-op, while different semantics for the same structure
require explicit replacement confirmation. Users never need **Add Current** for this ordinary
flow.

**Save current setup…** stores reviewed settings under a local name, and a successful
conversion offers the non-blocking **Save this setup for reuse…** action. A modified selected
setup can be explicitly updated or saved as a new setup; nothing is silently autosaved.
**Manage…** provides rename, duplicate, delete, and optional JSON import/export. The index-free
library uses the operating system's application configuration location and opaque storage IDs;
a display label is never used as a filename. One invalid stored Recipe is isolated so other
valid setups and direct conversion remain available. JSON remains the portable CLI/API format,
not a requirement for ordinary desktop use.

## Mapping semantics

`retention_time_column`, `area_column`, `retention_time_unit`, and `source_format` are
required. A column selector contains its exact decoded label and one-based position,
so duplicate labels can be disambiguated without fuzzy matching. Every header position
must appear exactly once as a mapped role or in `ignored_columns`.

Each nonblank data row becomes one `PeakRecord`. Retention time and area must be explicit,
finite decimal values that round-trip exactly through the canonical float. Invalid mapped
data fails that file; it is never skipped, downgraded to Metadata, or replaced by another
field. Source row order becomes contiguous `observation_order` within each detector/channel
stream. Peak number remains separate from observation order.

One-dimensional mappings populate `Peaks` and `Peak_Order_Matrix`. A mapping with an
explicit secondary retention column and independent unit also populates
`Peak_Order_Matrix_2D`. Explicit compounds can populate the existing `Peak_Matrix`;
retention-time matching and compound inference are never performed.

Units are copied from the mapping and are not converted. An absent area or height unit is
canonical `None`, not a guessed `Unknown` unit. Height is never substituted for area, raw
signals are not integrated, and values are not normalized, interpolated, rounded, summed,
or deduplicated.

## Provenance and privacy

The local GUI preview displays the source basename, selected worksheet name, headers, and
up to five decoded, visibly escaped preview rows; the public local preview API permits a
bounded one-to-ten-row request.
Treat the preview, its screenshots, and the mapping JSON as
privacy-bearing local data: exact header labels and optional manufacturer/software are part
of the JSON. They are not public evidence artifacts.

Profile and Mapping Set JSON are also privacy-bearing local configuration. They contain
embedded mapping selectors and may contain a local display label or exact worksheet title.
Do not attach them to public issues. Workbooks record only opaque profile/set IDs, schema
versions, and public-safe fingerprints; they do not record the Mapping Set path, filename,
display label, exact headers, worksheet title, or complete JSON.

Mapped inputs always use `source-<full SHA-256>` public identities. If no sample column is
mapped, that source alias is also the deterministic sample identity. Direct single-mapping
workbooks record mapping mode `USER_SUPPLIED`, schema version, semantic mapping SHA-256,
canonical roles, unit provenance, converted row count, ignored-column count, and
manufacturer/software verification status. Mapping Set workbooks replace that private
semantic digest with the opaque profile/set IDs and public-safe fingerprint described above.
Both modes contain every explicitly mapped canonical value and optional
user-supplied manufacturer/software; mapping a sensitive sample, run, compound, peak-name,
detector, channel, or acquisition field therefore writes that value to the local workbook.
Ordifile does not record the source path/basename, mapping path/filename, complete JSON,
unselected header labels, or ignored cell values in workbook provenance.

Manufacturer and software strings in a mapping are user-supplied provenance. They do not
establish compatibility, do not change adapter detection, and do not add an entry to the
vendor support matrix. Vendor and software names are factual compatibility identification
only; Ordifile is not affiliated with or endorsed by those vendors.

Exact-profile adapters retain automatic ownership. If a mapping is supplied for a batch
that also contains an exact-profile input, Ordifile parses that file with its exact adapter
and records the fixed `PEAK_MAPPING_NOT_APPLIED_EXACT_PROFILE` warning for that file. The
mapping remains applicable to matching generic inputs in the same batch.

Mapping JSON is bounded, strict UTF-8 data. Duplicate or unknown keys, unsupported schema
versions, non-standard JSON numbers, duplicate selectors, expressions, regular-expression
programs, imports, commands, templates, and external file references are rejected. Mapping
files are processed locally and are never uploaded by Ordifile.

## Exact-profile promotion

A successful user mapping is not evidence for built-in vendor support. Promotion to an
Experimental exact-profile adapter still requires a lawful vendor-generated fixture,
privacy and license review, bounded detection anchors, full source-to-canonical RT/area
comparison, generic-collision tests, and an independent implementation review. See the
[result fixture intake guide](../contributing/result-fixture-intake.md).
