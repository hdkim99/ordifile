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
10. Workbooks are written to a sibling temporary file and atomically finalized. Existing
    output is never replaced without `overwrite=True`; inputs can never be outputs. A
    best-effort rollback covers ordinary process exceptions and interruptions, but a power
    failure cannot make a workbook plus multiple sidecars one filesystem-wide transaction.
11. Python 3.11–3.14 and Linux, Windows, and macOS are portability targets. The v0.1.0
    release was validated on Ubuntu, Windows, and macOS with Python 3.11 and 3.14.
    Ongoing self-hosted coverage is documented separately and includes only OS/Python
    combinations backed by registered runners and passing clean-install, test, build,
    and CLI smoke jobs.
12. CLI exit codes are 0 success/warnings, 1 fatal or zero-success, 2 usage/configuration,
    3 valid workbook with file failures, and 130 interruption.
13. GUI work and `PySide6-Essentials` adoption are deferred until a stable CLI plus an
    LGPL/packaging/size prototype exists.
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

## Public boundaries

- `ordifile.api`: `inspect_file`, `list_formats`, `get_format_report`, `convert`
- `ordifile.core.models`: canonical immutable values, structured issues,
  `ProgressEvent`, and immutable `ConversionOptions`
- `ordifile.adapters.base`: `FormatAdapter` protocol and descriptors
- `ordifile.exporters.base`: exporter protocol
- `ordifile.cli`: presentation and exit-code mapping only

## Data flow

```text
CLI / future GUI
  -> public API
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
- Umbrella YoungIn adapters or treating `.prm` and `.raw` as interchangeable: brand and suffix
  are not verified byte-format or lifecycle boundaries.
- GUI in the first vertical slice: delays verification of the shared core workflow.

## Known risks

- XLSX is a ZIP/XML container; archive bombs and corrupt XML need bounded preflight.
- External adapters execute code at import time and must be treated as trusted plugins.
- Naive and timezone-aware timestamps cannot be mixed into a trustworthy acquired sort.
- No formal trademark clearance has been performed for the product or vendor compatibility
  wording; registry and web searches are evidence, not legal clearance.
