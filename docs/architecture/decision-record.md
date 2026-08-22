# Architecture decision record: v0.1 vertical slice

- Status: Accepted for implementation
- Date: 2026-08-15
- Evidence: [`docs/research/`](../research/)

## Context

Ordifile must batch-convert verified scientific instrument exports to one ordered
Excel workbook without modifying inputs, losing data silently, or implying unsupported
vendor compatibility. External adapters must remain possible without coupling a parser
to the workbook layout.

## Decisions

1. v0.1 verifies only generic CSV, TSV, semicolon-delimited TXT, and XLSX tabular
   exports backed by synthetic fixtures. No proprietary format is advertised.
2. Core data uses frozen standard-library dataclasses and enums. Adapters implement a
   typed protocol and return canonical bundles; exporters never parse source formats.
3. Built-in adapters are explicit. External adapters use the
   `ordifile.adapters` entry-point group, an API version, and collision rejection.
   Installed third-party adapters are trusted executable Python code.
4. The batch pipeline is discovery → bounded detection → parse → validate → sort →
   size planning → atomic export. Every file produces a structured result; ordinary
   adapter failures do not discard successful files.
5. Discovery preserves explicit input order, naturally sorts directory members,
   rejects symlinks by default, keeps same-basename files distinct, and records duplicate
   path or hard-link identities rather than deduplicating by content hash. Reliable
   filesystem identities use constant-time lookup; `samefile` is only a fallback when that
   identity is unavailable.
6. Automatic sort uses `acquired_at` only when every successful sample has a reliable,
   comparable timestamp; otherwise `sequence` when complete; otherwise natural filename.
   Ties use natural filename, normalized relative path, then input order. The chosen
   mode and fallback reason are exported.
7. XLSX input accepts only the non-macro `.xlsx` workbook content type. A bounded,
   defusedxml-based transitional-namespace package and worksheet-coordinate audit runs
   before openpyxl. Declared worksheet dimensions are never trusted as allocation or
   termination bounds; actual cells, explicit coordinates, relationships, types, formula
   lexemes, numeric lexemes, and documented practical resource limits are checked first.
   Openpyxl remains read-only and formula-preserving after that audit. XLSX output uses
   XlsxWriter in constant-memory mode.
8. User strings are written as literal strings with formula and URL auto-conversion
   disabled. This prevents formula execution without mutating source strings. Safety
   policy and counts are recorded.
9. Excel limits are checked before writing. Row-heavy sheets split deterministically.
   When a workbook plan is impractical, the user can request CSV sidecars. Their relative
   paths, row counts, and SHA-256 hashes are recorded in the workbook Manifest. Without
   that explicit option, export fails before writing rather than truncating data.
10. Workbooks and sidecars are written inside a private sibling transaction directory and
    each final name is published with an atomic no-replace rename. Existing output is never
    replaced without `overwrite=True`; inputs can never be outputs. A workbook plus multiple
    sidecars cannot be one filesystem-wide transaction. If a later name collides, Ordifile
    reports `OUTPUT_TRANSACTION_INCOMPLETE` and deliberately preserves earlier publications:
    deleting them by path could delete a concurrently exchanged foreign file.
    POSIX output parents that allow group/world entry replacement without the sticky bit are
    rejected before planning or writing private transaction data.
    Processes with the same operating-system user identity remain trusted because they
    already hold equivalent access to that user's local output and temporary files.
11. Python 3.11–3.14 and Linux, Windows, and macOS are portability targets. The v0.1.0
    release was validated on Ubuntu, Windows, and macOS with Python 3.11 and 3.14.
    Ongoing self-hosted coverage is documented separately and includes only OS/Python
    combinations backed by registered runners and passing clean-install, test, build,
    and CLI smoke jobs.
12. CLI exit codes are 0 success/warnings, 1 fatal or zero-success, 2 usage/configuration,
    3 valid workbook with file failures, and 130 interruption.
13. After the stable CLI and v0.3.1 release, the first Experimental desktop slice uses
    optional `PySide6-Essentials` and the same public API as the CLI. The default
    installation remains Qt-free. Standalone bundling and its LGPL/packaging gates are
    deferred to Issue #6; the detailed framework decision is recorded in
    [`gui-framework-decision.md`](gui-framework-decision.md).
14. Discovery records a streaming SHA-256 before parsing and repeats it after parsing.
    A changed file is rejected from scientific output. Files at or above 256 MiB receive
    a size warning; files above 2 GiB are still hashed but are not detected or parsed.
15. Portable output safety conservatively treats NFC-normalized, case-folded path aliases,
    hard links, and symbolic links as possible input collisions. The current Excel-compatible
    output-path limit is 218 Unicode code points, including the filename.
16. Excel numeric precision is explicit: integers with more than 15 significant digits are
    written as literal strings and counted in the Manifest. Non-finite and inexact float
    lexemes remain explicit and their original text is preserved in Metadata. Canonical
    integers are bounded to 1,000 decimal digits and source integer lexemes to 4,096 characters
    before integer construction.
17. `MetadataEntry.source` is a relative logical locator such as a sheet and row, never a
    machine path. Validation rejects absolute/drive paths and control characters before export.
    Long-cell CSV sidecars escape spreadsheet-formula prefixes, and the workbook records the
    sidecar hash, row count, and escape count.
18. Empty values and whitespace-only values are distinct. Mapped text preserves leading and
    trailing whitespace exactly; numeric and timestamp parsers may use a trimmed copy only when
    they preserve the source lexeme and record a warning. Unknown headers and values retain their
    original text.
19. Every behavior-affecting conversion option is captured in an immutable, privacy-safe batch
    snapshot and written to the Manifest. Discovery records intentionally excluded prior
    Ordifile outputs and sidecars rather than reparsing them on a same-folder rerun. Extension
    filters are normalized and bounded before discovery or hashing.
20. Canonical bundles returned by external adapters are runtime-validated field by field before
    export. An accidental plugin contract violation fails only that file. Workbook planning has a
    structured export-error boundary as defense in depth.
21. Workbook-bound text that XlsxWriter/openpyxl cannot round-trip unambiguously is rejected
    before any final artifact is created. Worksheet names are sanitized deterministically and
    case-insensitive collisions receive stable suffixes; scientific cell text is never silently
    stripped or substituted.
22. Filesystem source identity remains raw internally. XLSX audit display uses reversible
    `~uXXXXXX;` encoding for unsafe code points and doubles literal `~` to keep decoding
    unambiguous. The Manifest records the policy and count; input bytes, paths, and hashes are not
    changed.
23. CLI presentation treats filenames, progress labels, plugin descriptors, and issue text as
    untrusted display data. Terminal controls and bidirectional-format characters become visible,
    unambiguous single-line escapes; normal Unicode and Windows path separators remain readable.
24. Public API and exporter configuration values are runtime-validated before discovery or output
    mutation. In particular, only exact booleans can authorize overwrite or include behavior.
25. External canonical values require exact built-in container and primitive types. Datetimes are
    exception-safely serialized once and rebound to hook-free built-in values; non-orderable UTC
    edge values are preserved but marked unreliable. Plugin issue text cannot expose absolute
    machine paths.
26. OOXML numeric/index lexemes use bounded ASCII grammar, and each documented field has an
    explicit accepted cell-type set. Incompatible typed cells retain raw lexeme/type provenance
    instead of being converted through decoded Python display values. Formula literals account
    for their exported `=` prefix, and audited inline/shared rich text is reconstructed for
    mapping rather than trusting a potentially lossy decoded value.
27. Release publishing builds wheel and sdist once, verifies identical bytes through every
    downstream job, and uses GitHub OIDC Trusted Publishing without long-lived package tokens.
    External scientific fixtures remain outside the repository and default CI; the maintainer
    fetch tool requires a pinned manifest, explicit license acknowledgement, streaming bounds,
    digest verification, and safe extraction.
28. Proprietary GC research follows the format/version boundaries in
    [`gc-adapter-boundaries.md`](gc-adapter-boundaries.md). YOUNG IN Chromass umbrella names are
    research categories rather than runtime adapters, completed Clarity `.prm` and recovery
    `.raw` are distinct lifecycles, and no proprietary format appears in the support list before
    a lawful fixture and passing adapter tests exist.
29. All Actions jobs use one shared Linux DGX self-hosted runner selected by the `dgx-spark`
    label. CI uses one Python version and no operating-system matrix. Public-fork
    workflows require maintainer approval and receive read-only repository permission,
    no publishing secrets, no OIDC permission, and no release environment. Release
    publishing remains restricted to tag-only jobs with scoped OIDC Trusted Publishing.
30. Adapter descriptors distinguish Verified, Experimental, and external
    fixture-declared evidence levels. Signal series distinguish scientific signals from
    structural decoded records. The built-in Agilent ChemStation `.CH` internal-v181
    adapter is Experimental: it exposes every decoded record by ordinal and raw integer,
    but no retention time, physical scaling, physical unit, peak table, `.D` grouping,
    or other `.CH` version.
31. The Experimental Shimadzu adapter is limited to a LabSolutions 5.82, GC-2014,
    single-`Ch1`, `SFID1`, `uV`, identity-factor profile. It exposes a scientific
    signal because the native GCD stream and same-run LabSolutions ASCII reference
    agree on all 66,255 points and the DLT-based time axis. `olefile` provides bounded,
    read-only CFB access; Ordifile owns the profile validation and does not copy or
    depend on the GPL reference parser. Other versions, detectors, factors, channels,
    peak tables, `.QGD`, and `.LCD` remain unsupported.
32. The separate Experimental Shimadzu GCMSsolution `.QGD` adapter is limited to the
    exact `4.00` compound-file profile established by the CC0 Dryad fixture. It exposes
    the 16,800-point TIC with source milliseconds converted to minutes and preserves
    unsigned TIC integers with no claimed physical unit. MS1 blocks are walked only to
    validate offsets, scan/RT identity, record lengths, and the exact per-scan TIC sum;
    spectra are not exported until an independent m/z oracle and a bounded canonical
    mass-spectrum workbook model exist. The GPL readers remain comparison-only.
33. The Experimental YoungIn adapter is limited to one owner-observed YL-Clarity
    `9.0.1.19` completed-PRM profile. It exposes only the current, duplicate-validated
    little-endian binary32 blocks as `SeriesKind.DECODED_RECORDS`. The stored `FID` and
    `TCD` values are Experimental native channel labels, not Verified detector
    identities; `SignalSeries.detector`, time coordinates, physical scaling and units
    remain unset. Twenty-three local-only files establish bounded one/two-block parsing,
    source order and deterministic extraction. Same-run official export evidence is a
    Verified promotion gate rather than a structural-converter implementation gate.
34. Public source identity is adapter-declared but core-owned. `RELATIVE_PATH` remains
    the default for generic inputs; privacy-sensitive adapters may declare
    `SHA256_ALIAS`, which the core renders as `source-<full SHA-256>` or, before a hash
    is available, `source-input-<input order>`. Adapter-provided aliases are ignored.
    Detection failures, canonical records, issues, progress, API/CLI output, sort keys,
    `Samples` and `Import_Log` all use the same public reference. The policy is
    manufacturer-neutral and may be reused by future result adapters. If an adapter
    reports integrity from its bounded read, core requires its size/SHA-256 to equal
    discovery provenance before rebinding; the independent post-parse hash remains a
    second gate, and either mismatch excludes the parsed bundle.
35. Proprietary result consolidation is result-first and manufacturer-neutral.
    Evidence-backed Agilent, Shimadzu and YoungIn result adapters map RT/area rows to the
    common `PeakRecord`, `Peaks` and compound `Peak_Matrix`; raw signals are an
    optional independent capability, and a standalone result export never requires a
    raw source merely for pairing. The three vendor adapters remain separate exact-
    format readers, while their canonical peak rows, batch isolation, ordering,
    provenance and Excel output obey the same contract. No vendor result parser,
    canonical result field or source-order matrix is implemented before an actual
    result fixture establishes field boundaries and semantics. The 23 YoungIn PRM
    files still have no proven embedded peak table, but two owner-generated Result
    Table exports independently establish the standalone YoungIn RT/area path.
36. The first manufacturer-neutral result implementation is limited to the exact
    Agilent ChemStation Result XML `C.01.10 [201]`, single `FID1/A`, Percent/Area
    profile. Canonical rows come only from `ResultsGroup/Peak`; duplicate integration
    rows must agree exactly for RT, area and height and supply bounded start/end times.
    `PeakRecord` additively retains observation order, boundaries, area unit and height
    unit. `Peaks` adds manufacturer without reordering legacy columns. A conditional
    `Peak_Order_Matrix` uses seven fixed identity columns followed by atomic source-order
    RT/area pairs, at most 8,188 pairs per Excel segment; compound `Peak_Matrix` remains
    unchanged. Result XML uses `SHA256_ALIAS`, exports only allowlisted scientific
    metadata, requires no raw sibling, and makes no broader Agilent claim.
37. The separate Experimental Shimadzu result adapter is limited to one exact
    LabSolutions 5.82, GC-2014, single-`SFID1` / `Ch1` ASCII export profile. It maps
    Peak Table rows to the same manufacturer-neutral `PeakRecord`, `Peaks` and
    source-order matrix contract without a raw sibling. Source `Peak#` and independent
    source observation order are both preserved; RT/start/end are minutes, while area
    and height units remain unset. Shared `.txt` discovery keeps a provisional SHA
    alias until a generic adapter completes parse, validation and integrity checks.
    Identified unsupported LabSolutions profiles fail safely instead of falling
    through to the generic semicolon reader. The primary GPL-hosted fixture remains a
    controlled external oracle only; no reader or test expressions are copied.
38. YoungIn peak-result evidence is generated through an ordinary licensed
    YL-Clarity vendor export rather than inferred from structural PRM records. A
    maintainer-only Windows bridge may stage one SHA-addressed temporary PRM at a time,
    invoke the documented positional-open / `export_results` /
    `prm_close_discard` sequence, and record a local sanitized pairing manifest.
    The bridge never becomes a runtime or CI dependency, never saves or reintegrates a
    source, and never bundles vendor software. Exact Result implementation required
    actual explicit RT and area headers rather than command documentation alone. Two
    owner-generated local exports satisfied that gate on 2026-08-18; the bridge remains
    optional maintainer tooling rather than a runtime dependency.
39. The separate Experimental YoungIn Result adapter is limited to one owner-provenance
    CP949-compatible, tab-delimited Result Table grammar observed in two exports. The
    bytes contain no producer or version marker, so attribution is external provenance
    and broader YL-Clarity/Clarity support is not claimed. Exact repeated headers,
    signal sections, no-peak and Total rows, numeric fields, private-trailer shape and
    the empty compound-table terminator are required. Six source peaks map to the common
    result model with explicit min, mV.s and mV units. Signal number/name form channel
    identity; detector, compound and integration boundaries remain unset. Actual bytes
    remain local-only and all public fixtures are independently synthetic.
40. Wave-1 multi-vendor Result research treats `manufacturer + software/version
    boundary + exact export profile` as the support unit. Thermo Chromeleon,
    PerkinElmer SimplicityChrom/TotalChrom/Chromera, SCION CompassCDS, LECO
    ChromaTOF/Sync and current Bruker GC-MS profiles remain research-only until one
    exact lawful fixture supplies explicit finite RT and area and passes bounded
    detection, full-row canonical/workbook comparison, privacy and license gates. A
    lawful ChromaTOF 4.72 GCxGC fixture proves RT1/RT2/area/height semantics. Decision
    41 preserves RT2 additively, and the exact-profile Experimental adapter maps the
    selected non-human CC0 result without dropping or hiding either coordinate.
    Multiple-run report exports still require a separate architecture decision. The
    exact boundaries and current evidence states are recorded in
    [`result-export-profile-boundaries.md`](result-export-profile-boundaries.md) and
    [`multivendor-result-wave1.md`](../research/multivendor-result-wave1.md).
41. Two-dimensional retention is represented by appending optional
    `secondary_retention_time` and `secondary_retention_time_unit` fields to
    `PeakRecord`; the existing retention fields remain the primary coordinate.
    One-dimensional-only `Peaks` and `Peak_Order_Matrix` contracts remain unchanged.
    Two-dimensional batches append the secondary fields to `Peaks` and place only 2D
    streams in conditional `Peak_Order_Matrix_2D` rows with atomic RT1/RT2/area
    triples. Metadata, compound names, detector/channel fields, duplicate peak rows,
    and concatenated strings are not retention-coordinate carriers. The complete
    rationale and migration boundary are in
    [`secondary-retention-coordinate.md`](secondary-retention-coordinate.md).
42. Unsupported clean peak tables use an explicit, user-confirmed mapping layer over
    the existing audited CSV, TSV, semicolon-TXT, and XLSX readers. Mapping is a frozen,
    bounded, data-only JSON contract with exact label-plus-position column selectors,
    mandatory RT/Area roles, explicit units, and explicit ignored columns. It does not
    mutate global aliases, add a runtime adapter, change adapter API v1, infer scientific
    meaning, or verify a vendor. Mapped inputs use SHA-derived public source identities;
    the mapping path, filename, ignored values, and unselected header labels do not enter
    workbook provenance. Explicitly mapped canonical values and optional user-supplied
    manufacturer/software do enter the local workbook. Existing exact-profile adapters
    retain automatic ownership and emit a fixed per-file warning when a supplied mapping
    is therefore not applied. A selected mapped XLSX worksheet is recorded only as the
    fixed `USER_SELECTED` option marker, not as its potentially identifying title. Details are in
    [`../formats/explicit-peak-table-mapping.md`](../formats/explicit-peak-table-mapping.md).
43. Reusable mapping profiles extend that same mapping contract without changing
    `PeakRecord`, workbook scientific sheets, generic readers, or adapter API v1. Automatic
    exact-profile detection runs before Mapping Set routing. Generic candidates are selected
    only by exact container plus ordered local header/title structure; filename, vendor guess,
    and row values never participate. Zero or multiple matches fail the file without generic
    fallback. Local profile/set JSON may contain private selectors and labels, while workbook
    provenance contains only opaque IDs and a separate public-safe structural fingerprint.
44. Mapping schema-drift diagnostics explain a failed exact profile match without changing
    routing. Comparison is bounded, same-container, occurrence-aware, and limited to exact
    labels/positions plus existing worksheet policy; previewed row or measurement values are
    never used for matching, ranking, diagnostics, or output, and no fuzzy scientific
    remapping is performed. Public results contain only opaque IDs, fixed
    categories/roles and counts. Raw headers and local labels remain in the existing local
    preview. Repair reuses the explicit mapping dialog and adds a new user-confirmed profile;
    the parent profile is never mutated or silently replaced. Exact adapters and exact
    profile matching remain authoritative and fail closed.
45. Conversion preflight is a route-only orchestration layer, not a second parser or exporter.
    `plan_conversion()` shares the exact adapter/Mapping routing helper, hashes bounded
    read-only discovery, and records only `ROUTABLE`/failure/duplicate/excluded dispositions;
    it does not create canonical rows, effective scientific sort, workbook sheets, sidecars,
    or filesystem artifacts. Its public-safe entries omit paths, filenames, headers, worksheet
    titles, profile labels, and measurement rows. The same-process, non-serializable immutable
    plan keeps private local bindings and `convert_plan()` repeats discovery/routing before
    calling the unchanged conversion pipeline. Source/config/output differences fail closed;
    the exporter remains the authoritative live output and late-collision gate. The public
    plan-summary hash is deterministic equality/audit evidence for its privacy-safe projection,
    not the private binding identity, a signature, an authentication proof, a future-write
    guarantee, or a workbook digest.
    Mapping-profile inspection is header-only, while an exact-adapter ownership probe may
    decode and validate bounded numeric source syntax. Neither path constructs or retains
    canonical rows. Executable plans reject overwrite authorization and require a new target;
    direct conversion retains the existing explicit-overwrite contract.
46. Researcher workbook usability is improved in the existing typed sheets rather than by
    duplicating them in a new Overview or Run Summary. `Manifest` remains the first audit tab,
    while `Samples` is the active sheet when the workbook opens. Static presentation rules add
    bounded schema-based widths, a literal header style, frozen identity columns, and filters
    only on useful identity/table ranges. Scientific numeric cells retain `General`; no value,
    unit, dimension, or processing provenance is inferred or reformatted. A shared frozen
    count-only result summary supplies Manifest, CLI, and desktop completion messages. It
    excludes identifiers and scientific values. Revalidated-plan conversions add only the plan
    schema and public summary SHA-256 to Manifest; direct conversions record `DIRECT`, and no
    plan JSON or private binding is embedded.
47. Repeated laboratory settings use one bounded, strict UTF-8 `ConversionRecipe` rather than
    a serialized plan, project database, or external Mapping Set path. Schema v1 stores only
    stable conversion behavior and optionally embeds one explicit Mapping or one Mapping Set;
    runtime inputs, output, overwrite authorization, source identities, and scientific rows are
    excluded. Recipe conversion uses the same implementation as `plan_conversion()` through
    the typed `plan_recipe()` boundary and is
    executed only through `convert_plan()`, so exact-adapter ownership, exact Mapping matching,
    drift diagnostics, ambiguity handling, and freshness checks remain authoritative. A stored
    adapter is considered only after exact-profile ownership finds no owner. CLI Recipe use
    rejects separate behavior flags instead of merging hidden precedence. The private exact
    semantic SHA-256 is used only for local equality. Recipe-specific Plan and Manifest
    provenance uses Recipe schema plus a public-safe fingerprint that excludes exact headers,
    worksheet titles, local labels, and user-provided mapping text. Existing scientific and
    public-safe Mapping Set provenance keeps its workbook contract; a Recipe-embedded single
    Mapping does not repeat its private semantic digest. A saved Recipe is never changed
    automatically after local settings or Mapping repair.

## Public boundaries

- `ordifile.api`: `inspect_file`, `inspect_inputs`, `preview_peak_table`,
  `list_formats`, `get_format_report`, `plan_conversion`, `plan_recipe`, `convert_plan`,
  `convert_recipe`, `convert`
- `ordifile.core.models`: canonical immutable values, structured issues,
  `ProgressEvent`, `BatchOutcome`, and immutable `ConversionOptions`
- `ordifile.core.peak_mapping`: strict data-only mapping, local preview value, and
  deterministic mapping identity
- `ordifile.core.recipe`: strict local Conversion Recipe model, serialization, and separate
  private semantic/public fingerprint identities
- `ordifile.adapters.base`: `FormatAdapter` protocol and descriptors
- `ordifile.exporters.base`: exporter protocol
- `ordifile.cli`: presentation and exit-code mapping only

## Data flow

```text
CLI / optional desktop GUI
  -> public API
  -> route-only preflight (optional; no canonical rows or artifacts)
  -> reviewed plan revalidation (when executing a plan)
  -> discover and hash read-only inputs
  -> probe adapters (no match / unique match / ambiguity)
  -> parse and validate each file independently
  -> choose and record batch sort
  -> preflight workbook limits and segments
  -> write a sibling temporary workbook
  -> close the temporary workbook and atomically place the output
  -> return success, partial success, or structured failure
```

## Rejected alternatives

- pandas/Pydantic/Typer: unnecessary v0.1 dependency surface.
- Parsing vendor formats directly into worksheets: prevents safe reuse and testing.
- Retention-time compound matching by default: scientifically unsupported.
- Implicit aggregation of duplicate compounds: data loss and reinterpretation.
- XLSX byte-for-byte golden tests: unstable container metadata; reopen and assert cells.
- Trusting worksheet `<dimension>` or formula caches: producers may record incorrect bounds,
  and cached formula results may be stale.
- Accepting duplicate or unordered OOXML cell coordinates with first/last-write-wins behavior:
  conflict resolution would silently discard one source value.
- Treating the Agilent v181 candidate transform as a verified chromatogram: rejected.
  The exact BSEE fixture supports a bounded Experimental decoded-record stream, while
  retention time, physical scaling, signal unit, and the last record's scientific role
  remain unresolved.
- Treating one LabSolutions 5.82 FID fixture as universal GCsolution, LabSolutions,
  Shimadzu, or `.GCD` support: rejected. Detection requires the exact linked
  producer/channel/unit/factor profile and structured rejection of every other profile.
- Flattening QGD MS1 records into the existing two-dimensional signal model: rejected.
  It would lose scan boundaries and materialize about 9.5 million rows before writing.
  The first QGD adapter is TIC-only and makes MS1 non-export explicit.
- Umbrella YoungIn adapters or treating `.prm` and `.raw` as interchangeable: the
  fixture-backed Experimental adapter is limited to one exact observed PRM profile;
  brand and suffix alone are not byte-format or lifecycle boundaries.
- GUI before the shared core and CLI were stable: rejected for the v0.1 vertical
  slice. The later optional desktop layer now reuses that verified public workflow.

## Known risks

- XLSX is a ZIP/XML container; archive bombs and corrupt XML need bounded preflight.
- External adapters execute code at import time and must be treated as trusted plugins.
- Naive and timezone-aware timestamps cannot be mixed into a trustworthy acquired sort.
- No formal trademark clearance has been performed for the product or vendor compatibility
  wording; registry and web searches are evidence, not legal clearance.
