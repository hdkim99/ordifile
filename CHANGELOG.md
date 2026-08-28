# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Shimadzu GCMSsolution `.QGD` files now emit the peak rows the document already stores in
  `GCMS Data Processing/MC Peak Table`: retention, start and end time, Area, Height, and the
  stored compound name. These are source-explicit values, not an Ordifile calculation.
  **These values have not been validated against a Shimadzu GCMSsolution export**, because no
  raw-plus-export pair is available for any file carrying a populated table. Their meanings
  were established only against each file's own TIC, and every parse that yields peaks raises
  `SHIMADZU_QGD_STORED_PEAK_TABLE_UNVALIDATED` while the `stored_peak_value_validation`
  metadata key reports `internal_only_no_vendor_export`. Compound names are read only up to
  their NUL terminator, because the bytes after it are uninitialised writer memory holding
  fragments of unrelated strings. Two f64 fields whose meaning was not established are
  deliberately not read. Evidence: five CC BY 4.0 University of Florida acquisitions, 295
  stored rows. See
  [the investigation](https://github.com/hdkim99/ordifile/blob/main/docs/research/shimadzu-gcmssolution-qgd-mc-peak-table-investigation.md).

### Changed

- The Shimadzu `.QGD` reader no longer pins one acquisition. The scan grid is read from the
  document and accepted when it is strictly increasing with a uniform interval, and the
  `Spectrum Index` stream is accepted in both observed encodings: a bare u32 offset array and
  a `01 00`-tagged u64 offset array. The two can never be confused, since a u32 array is a
  multiple of four bytes while the tagged u64 array is two modulo four. A second acquisition
  profile (9,100 scans at 300 ms, alongside the earlier 16,800 at 200 ms) now parses instead
  of failing closed. Non-uniform grids still fail closed.

- The exact validated Shimadzu LabSolutions 5.82 `.GCD` profile now emits the peak rows the
  document already stores: retention, start and end time, Area and Height, read from the
  single bounded `LSS Data Processing/PT-*` stream. These are source-explicit `area` and
  `height` values, not an Ordifile calculation - Ordifile does not integrate the signal here.
  The stored values keep every digit the vendor's own text export rounds away, so a `.gcd`
  file alone now yields a complete peak table at higher precision than its paired export.
  Area and Height units stay unresolved, matching the paired result-ASCII adapter, and stored
  negative peaks are preserved. Evidence: one same-run `.GCD`/result-ASCII pair (83 rows,
  every field exact) plus an owner-approved CC BY 4.0 corpus of 318 further documents across
  LabSolutions 5.71 SP2 and 5.86 (1,548 rows, every field exact), which shows the record
  layout is not specific to the 5.82 profile the adapter accepts. A document without that
  stream, or with a stream outside the bounded layout, keeps its scientific chromatogram and
  reports the peak table as absent or invalid.

- Explicit peak-table mapping accepts **UTF-16 with a byte-order mark** as a Table Options text
  encoding, and a header record of **0** to declare that a delimited source carries no header.
  With no header the first record stays data and column roles bind to one-based positional
  labels instead of header text. Declaring a headerless worksheet is refused, because no
  worksheet fixture establishes that behaviour. Both remain explicit researcher choices; no
  encoding, delimiter, header, or scientific role is detected. A headerless mapping is never
  selected automatically by reusable-profile routing: synthetic positional labels carry no
  source evidence, so the routing key would degenerate to container plus column count and could
  apply one vendor's column roles to an unrelated table of the same shape. The researcher names
  a headerless mapping for the conversion instead.

- An Experimental reader for Agilent ChemStation `.CH` **internal version 179**. That
  generation shares the v181 header family and stores an uncompressed little-endian binary64
  payload, so it yields a scientific signal rather than structural records: retention time is
  constructed from the run boundaries stored at offsets 282 and 286 and the point count, and
  the response uses the scale stored at 4732 with the unit lexeme at 4172. Only an observed
  unit lexeme is promoted to a physical unit; any other preserves the numeric response without
  one. The axis is validated against paired vendor report exports - the step is exactly
  20.000 ms, the stored maximum matches the decoded maximum, and official retention times land
  on decoded maxima. The scale agrees with those exports to within 0.5% but is not proven
  exact, which the metadata records; no peak, area or height is derived. Version 181 files are
  unaffected and continue to expose structural decoded records only.

### Fixed

- A UTF-16 source selected as UTF-8, CP949 or Western Windows (1252) now fails closed with
  `PEAK_MAPPING_TEXT_ENCODING_MISMATCH`. The single-unit encodings map every byte, so such a
  source previously decoded into text carrying NUL characters instead of raising.
- The bounded delimited preview reassembles decoded text into whole lines. A multi-unit
  encoding splits a line terminator across two byte-bounded reads, which previously made the
  CSV reader see a newline inside an unquoted field.

### Changed

- The optional YoungIn YL-Clarity PRM calculated Area now resolves peak groups from the lower
  convex hull of the stored signal, gives each group one straight baseline between its own
  baseline contacts, separates fused peaks at the stored-response minimum between neighbouring
  stored apexes, and sums the baseline-corrected response with a left-edge response and a
  centre-of-interval baseline. That summation is derived from the controlled corpus and is not
  the general trapezoidal rule. This independently developed calculation is intended to reproduce
  displayed Result Area as closely as the validated evidence supports; it is not an implementation
  or replication of the proprietary Clarity/YL-Clarity integration algorithm. No vendor source
  code, library, DLL, or executable is used by the implementation or at runtime. Four owner archives
  covering both validated producer versions, both detectors and both composite-export layouts
  hold 347 official rows; the new fail-closed rule below removes 42 of them. Of the remaining 305,
  retention time matches 305/305 and
  calculated Area matches 304/305 at each export's own displayed precision, replacing the
  previous lower-envelope calculation's 112/340. Against the one archive that also exists as a
  twelve-significant-digit vendor Excel export, its 241 rows match retention, start and end time
  exactly; the maximum relative Area difference is `4.025e-13`. Calculated Height is computed internally for
  verification only and is still not published. The method identifier is now
  `youngin-prm-marker-group-baseline-v4`.
- A YoungIn PRM channel whose stored processing table carries a manually added timed event
  (stored opcodes 11, 12 or 32) now fails closed for calculated Area and records the channel
  status `time_table_manual_event_unsupported`. The exact effects of these owner-observed timed
  events are not fully reproduced; opcode 12 remains unresolved. Those rows are therefore
  omitted rather than estimated, and the scientific Signals for those channels are unchanged.
  The opcode readings come from owner-controlled interventions, not from a published
  specification.

### Fixed

- A YoungIn PRM peak whose calculated partition no longer contained its own retention index
  could be emitted with `end_time` before `retention_time`. The calculation now fails closed
  for the affected channel instead.
- Resolving a stored marker cluster into peak groups is now iterative and charged against a
  deterministic sample budget. The previous recursive form raised `RecursionError`, which the
  adapter did not handle, on clusters with roughly a thousand baseline-separated peaks, and a
  bounded-but-quadratic marker stream could still stall a conversion for a long time.
- A YoungIn PRM peak whose calculated Area is not strictly positive now fails closed for the
  affected channel. The left-edge/midpoint summation can total below zero on a sloping baseline
  even when the response never falls below it, and every official Area in the controlled corpus
  is positive, so such a result is outside the evidence.

## [0.5.1] - 2026-08-25

### Added

- Direct scientific FID/TCD signal series for the exact validated YoungIn YL-Clarity
  `9.0.1.19` and `9.1.0.76` PRM profiles. Ten 9.0 and five 9.1 content-confirmed same-run
  curve pairs establish shared zero-origin `DStep/MinTicks` minute axes and identity numeric
  response over 401,520 points. Physical units remain profile-specific: 9.0 FID/TCD mV and
  9.1 FID pA/TCD mV. Strictly compatible unvalidated 9.x files may expose the shared values
  only after the complete fingerprint matches, and their response unit remains unresolved.
  No PRM-derived peaks, Area, Height, integration or peak detection is added.
- Explicit, bounded **Table Options** for mapped structured Result intake: UTF-8/UTF-8-BOM,
  CP949, or Windows-1252 text decoding; one-based header-record selection; and visible
  worksheet selection for multi-sheet XLSX. The approved structure is stored with the
  Mapping/Profile and reused by Mapping Sets and named Recipes without scientific inference.
- A bounded local desktop Recipe library using strict existing `ConversionRecipe` JSON,
  opaque storage identifiers, operating-system application configuration locations, atomic
  writes, serialized local mutations, and isolated handling of invalid members. Named Recipes
  can be saved, selected, renamed, duplicated, deleted, imported, and exported without storing
  scientific rows or runtime source/output paths.
- Researcher onboarding, a public-safe pilot kit and feedback workflow, and an Ordifile
  application icon shared by the Python-package GUI and private Windows/macOS standalone
  prototypes. No public standalone executable or application bundle is included.

### Changed

- Refactored YoungIn PRM scientific decoding around one bounded scientific-family
  fingerprint while preserving exact producer provenance and profile-specific unit evidence.
  Structurally safe 9.x files with an incomplete scientific fingerprint retain decoded-record
  output; malformed structures fail closed, and versions outside the implemented 9.x boundary
  remain unsupported.
- Generic mapped preview, profile routing, drift review, Preflight, and conversion now share
  the same explicit table-import settings. Existing default schema-version-1 Mapping JSON and
  semantic hashes remain unchanged; exact adapters retain ownership and invalid scientific
  rows are never silently removed.
- Simplified the desktop interface around the visible researcher workflow
  **Inputs → Output → Preflight → Convert**. Recipe selection and saving are name-based;
  JSON import/export, Mapping controls, Mapping Sets, and sort are progressively disclosed,
  while drift review and diagnostic details appear contextually. Existing Recipe schema,
  CLI/API behavior, exact-adapter precedence, Mapping exact matching, and Preflight freshness
  checks are unchanged.
- Completed the researcher-facing **Saved Setup** workflow: confirmed generic mappings are
  collected into an internal reusable Mapping Set, setups can be saved before or after
  conversion and reused after restart, and update, save-as-new, rename, duplicate, delete,
  import, and export remain explicit operations. Stale-revision and storage failures fail
  safely without preventing a direct conversion.

### Fixed

- Preflight no longer reports malformed or unsupported proprietary inputs as ready, and it
  distinguishes exact adapters, compatible scientific profiles, compatible structural-only
  profiles, mapping-required inputs, drift, unsupported profiles, and malformed inputs.
- Mixed-vendor routing preserves exact-adapter ownership and prevents generic Mapping from
  claiming proprietary inputs or silently rerouting them during conversion.
- `Peak_Matrix` keeps otherwise identical peak columns separate when their Area units differ.
  Ordifile does not normalize or convert the underlying values.

### Documentation

- Updated the English and Korean researcher workflow, format boundaries, workbook guidance,
  GUI screenshots, pilot checklist, and privacy-safe feedback path for the consolidated
  v0.5.1 capabilities.

## [0.5.0] - 2026-08-23

### Added

- Strict local `ConversionRecipe` JSON for repeated laboratory workflows. Recipes persist
  stable conversion behavior and optional embedded Mapping/Mapping Set configuration without
  source/output paths, overwrite authority, plans, or scientific rows. API, CLI, desktop,
  preflight revalidation, Manifest provenance, and installed-package smoke share the same typed
  contract; exact adapters and exact Mapping matching remain authoritative, and a stored adapter
  is considered only when no exact-profile adapter owns an input.
- Researcher-oriented workbook presentation without a duplicate summary sheet: `Samples`
  opens as the active tab, existing typed sheets gain deterministic frozen identity columns,
  bounded widths, header styling, and useful filters, while numeric scientific cells retain
  their original values and `General` display. A count-only post-conversion summary is shared
  by Manifest, CLI, and desktop completion messages, and revalidated preflight execution can
  be linked by its public plan-summary SHA-256.
- Deterministic route-only conversion preflight through an immutable same-process
  `ConversionPlan`, public `plan_conversion()` / `convert_plan()` APIs, CLI
  `convert --dry-run`, and the desktop background workflow. Reviewed plans revalidate
  source membership/content, adapter/configuration bindings, and output state before
  using the existing converter; dry-run constructs no canonical rows or output artifacts.
- Privacy-safe Mapping Schema Drift Diagnostics and an explicit desktop review flow that
  clones a repaired mapping as a new profile. Diagnostics never authorize fuzzy mapping,
  expose raw headers publicly, mutate the parent profile, or bypass exact adapters.
- Reusable Peak Table Mapping Profiles and bounded Mapping Set JSON for mixed-template
  generic batches. Exact vendor adapters retain priority; exact structural zero/multiple
  matches fail closed, while API, CLI, desktop, workbook provenance, and standalone smoke
  share the same user-supplied mapping contract.
- A strict, reproducible Explicit Peak Table Mapping workflow for user-selected RT and
  Area columns in the existing CSV, TSV, semicolon-TXT, and audited XLSX containers.
  The shared API, CLI, desktop UI, canonical `PeakRecord` path, ordered matrices, and
  workbook provenance distinguish user declarations from verified vendor support.
- A privacy-first Result fixture intake guide with exact requests for the currently
  blocked Thermo, PerkinElmer, SCION, LECO 1D, and Bruker profiles.
- An Experimental Result adapter for the exact externally evidenced LECO ChromaTOF
  4.72.0.0 GCxGC tab-delimited profile. It preserves explicit RT1/RT2 seconds,
  area/height arbitrary units, source order, compound-name evidence and row-aligned
  Spectra/width/retention-index lexemes without requiring raw files or claiming broad
  LECO, ChromaTOF, TXT, or mass-spectral support.
- A backward-compatible optional secondary retention coordinate in `PeakRecord`, plus
  conditional `Peaks` columns and `Peak_Order_Matrix_2D` atomic RT1/RT2/area triples.
  Existing construction call patterns, public conversion function signatures,
  one-dimensional `Peaks`, `Peak_Order_Matrix`, and the adapter API version remain
  compatible.

### Fixed

- Release publication now requires the exact built wheel to pass both the default Linux
  smoke and a macOS Python 3.14 GUI-extra install, window-creation, and clean-exit smoke
  before TestPyPI can receive the distributions.
- Isolated package builds now use the exact reviewed Hatchling 1.31.0 backend, and the
  release verifier rejects an unreviewed build-backend range.
- Continuous integration now runs the full test suite on Python 3.11–3.13 in addition
  to the required Python 3.14 quality and package job.
- macOS desktop tests now prepare a clean temporary Qt offscreen plugin location before
  creating `QApplication`, preventing repeated Python termination reports during test setup.
- Non-overwrite workbook and sidecar finalization now uses an atomic no-clobber publish
  so a foreign artifact appearing after preflight is never silently replaced.

### Documentation

- Updated the public installation instructions for the current PyPI CLI/API and optional
  desktop extra, and synchronized the quick-start output with the count-only conversion
  summary.

## [0.4.0] - 2026-08-18

### Added

- An optional Experimental offline desktop interface with file and folder selection,
  local drag and drop, detected-format preview, all five existing sort modes,
  background conversion, per-file outcomes, and an explicit output-open action. The
  interface calls the same public conversion API as the CLI and has no network,
  telemetry, cloud, or vendor-application dependency.
- A public `inspect_inputs()` batch-preview API and presentation-neutral
  `BatchOutcome` shared by the CLI and desktop interface. Preview intentionally
  re-reads and validates inputs during conversion rather than authorizing stale data.
- An Experimental standalone YoungIn YL-Clarity Result Table adapter for the exact
  owner-validated CP949-compatible, tab-delimited export grammar. It preserves six
  actual RT/area/height rows across two local-only exports, source-order signal
  streams and explicit min, mV.s and mV units without claiming detector identity,
  compound assignments, integration boundaries or a producer/version marker in bytes.
- Synthetic single- and multi-signal fixtures, malformed-family/generic-CSV collision
  coverage, a local-only full-sequence external regression, and a three-vendor actual
  Result workbook gate for 36 Agilent + 83 Shimadzu + 6 YoungIn peaks.
- A maintainer-only, privacy-safe Windows bridge for generating YL-Clarity Result
  Table exports from the 23 existing local PRM inputs through an ordinarily licensed
  vendor installation. It stages SHA-named temporary copies, records local source-to-
  export hashes, uses the documented positional-PRM / `export_results` /
  `prm_close_discard` sequence, and never makes YL-Clarity a runtime or CI dependency.

### Changed

- PySide6 Qt Widgets is available only through the optional `gui` extra; the default
  Ordifile installation and CLI do not install Qt. Standalone installers and Qt
  redistribution remain deferred to Issue #6.
- YoungIn Result status advanced from local bridge readiness to Experimental GO for
  the exact received Result Table grammar. Owner export/PRM pairing is external
  evidence; runtime conversion remains standalone and requires no PRM or vendor app.
- YoungIn Result work now actively generates same-run vendor exports instead of
  waiting indefinitely for an externally supplied companion. The generic Clarity
  automation route is documented, while exact YL-Clarity `9.0.1.19` OEM command
  compatibility remains gated by a one-file pilot on a licensed installation.

### Security

- Owner-generated YoungIn Result exports remain local-only and use SHA-derived public
  identities; independently synthetic fixtures cover the public parser behavior.
- The desktop interface performs no upload, telemetry, remote logging, browser, shell,
  or vendor-application execution. Qt is an exact optional dependency and no Qt binary
  is bundled in the Ordifile wheel or source distribution.

## [0.3.1] - 2026-08-18

### Fixed

- TestPyPI and PyPI installed-wheel verification no longer depends on `PATH`.
  Release verification resolves the `ordifile` entry point from the active isolated
  Python environment's scripts directory and executes that exact file.
- Added real temporary-venv regression coverage proving that installed entry-point
  verification succeeds with the venv scripts directory absent from `PATH`, and that
  an unrelated `ordifile` on `PATH` is never accepted for a missing venv entry point.

## [0.3.0] - 2026-08-17

### Release status

- An immutable annotated `v0.3.0` tag was created and its exact wheel and source
  distribution were published to TestPyPI. Their filenames, hashes and downloaded
  bytes matched the single DGX-built release artifact, and wheel installation
  succeeded.
- The workflow then stopped because its installed-CLI check searched the host `PATH`
  even though the isolated environment deliberately does not alter `PATH`. Version
  0.3.0 was never published to PyPI and no GitHub Release was created. The tag and
  TestPyPI files remain unchanged as an audit record; v0.3.1 carries the same reviewed
  feature set with the deterministic verification repair.

### Added

- An Experimental standalone Shimadzu LabSolutions result ASCII reader for the exact
  5.82, GC-2014, single `SFID1` / `Ch1` profile. It preserves source peak numbers,
  observation order, RT/start/end minutes, area and height while leaving area/height
  units unresolved and emitting no compound identity.
- A maintainer-only controlled-CI workflow that validates all 83 external result rows,
  canonical digests, workbook output, privacy exclusion, and the full paired same-run
  GCD chromatogram without committing or uploading either source file.
- An Experimental, standalone Agilent ChemStation Result XML reader for the exact
  `C.01.10 [201]`, single `FID1/A`, `Percent`/`Area` profile. It preserves canonical
  source-order RT, area, height, integration boundaries, calibrated compound names and
  explicit units while rejecting other revisions and report shapes.
- A conditional manufacturer-aware `Peak_Order_Matrix` with atomic source-order
  RT/area pairs, plus additive `PeakRecord` observation order, integration boundaries,
  area unit and height unit fields. The existing compound `Peak_Matrix` is unchanged.
- A maintainer-only controlled-CI integration workflow for the exact external
  Result XML fixture, with immutable size/SHA-256/license gates and no fixture or
  workbook artifact upload.
- An Experimental structural converter for one observed YoungIn YL-Clarity
  `9.0.1.19` `.PRM` profile. It preserves ordered native binary32 records and
  allowlisted stored channel labels across local-only real fixtures without claiming
  retention time, physical scaling, physical units, peaks, or Verified detector
  semantics.
- Synthetic bounded-parser, batch-isolation, deterministic-digest and workbook
  regression coverage for the YoungIn PRM raw-record boundary. Native owner files stay
  outside Git, Actions artifacts and release distributions.

### Changed

- Shared `.txt` discovery now keeps a provisional SHA-256 alias while the private
  Shimadzu result owner is unresolved, selectively redacts its probe reason, and
  restores ordinary relative-path provenance only after a generic TXT adapter parses
  and validates successfully. Ordered result streams may preserve a consistently
  unresolved area unit as `None`; mixed or blank unit states remain invalid.
- Implemented the first manufacturer-neutral result adapter under the result-first
  contract. Standalone Agilent Result XML RT/area rows map to common `PeakRecord`,
  `Peaks`, compound `Peak_Matrix` and conditional source-order `Peak_Order_Matrix`
  output independently of raw chromatogram support.
- Documented one manufacturer-neutral, result-first contract for future Agilent,
  Shimadzu and YoungIn result adapters: standalone verified RT/area exports map to the
  existing `PeakRecord`, `Peaks` and `Peak_Matrix` behavior, independently of optional
  raw chromatogram support.

### Security

- Added a core-owned SHA-256 public source identity policy for privacy-sensitive
  adapters so API, CLI, progress, sorting, issues and workbook audit sheets do not
  expose private source basenames. YoungIn runtime sample IDs are also content-derived;
  filename-based FID/TCD grouping is limited to the local maintainer oracle and is not
  exported. Probe reasons supplied by adapters are replaced with fixed non-identifying
  evidence whenever the effective source identity policy uses a SHA-256 alias. At the
  same boundary, structured adapter errors preserve only validated codes and ordinary
  adapter exceptions expose neither free-form messages nor class names.

## [0.2.1] - 2026-08-17

### Added

- A Unicode-filename synthetic example under `examples/unicode/` with a rendered
  screenshot of its generated workbook, showing that normal Unicode input
  filenames are preserved in the `Samples` sheet. (Issue #7)
- A reproducible Agilent ChemStation `.CH` internal-v181 evidence review that records
  exact byte observations and separates reader-derived interpretations.
- An independently implemented Experimental Agilent ChemStation `.CH` internal-v181 adapter that
  retains every decoded structural record by ordinal and raw integer, without claiming
  retention time, physical scaling, signal units, peaks, other versions, or `.D`
  directory support. The proprietary fixture remains external.
- An Experimental Shimadzu LabSolutions 5.82 `.GCD` reader for one exact GC-2014,
  single-channel `SFID1` profile, with paired-reference validation of its 66,255-point
  retention-time and `uV` signal series. The privacy-bearing native fixture remains
  external and is never uploaded as a CI artifact.
- An Experimental Shimadzu GCMSsolution `.QGD` TIC reader for one exact `4.00`
  compound-file profile. It preserves the native unsigned TIC integers and verified
  retention-time axis; MS1 is structurally validated but not exported.
- Maintainer-only external-fixture workflows for the exact Agilent, Shimadzu GCD, and
  Shimadzu QGD profiles, with reviewed source and license records, exact size and
  SHA-256 gates, no raw-fixture artifact upload, and mandatory cleanup.
- Capability-specific format documentation that distinguishes verified scientific
  signals, structural decoded records, unknown units, and unsupported variants.

### Security

- Added bounded proprietary-container and binary parsing, exact profile and stream
  validation, malformed-input isolation, full-array reference digests, and explicit
  rejection of unverified versions, detectors, scaling, units, and MS1 semantics.
- Kept privacy-bearing native fixtures outside Git and release distributions, and kept
  GPL/LGPL reference implementations outside Ordifile runtime code and dependencies.

### Fixed

- Isolated synthetic release-verifier test data from the ambient GitHub tag context so
  protected tag workflows validate the intended synthetic version without weakening
  the real tag/version gate.

## [0.2.0] - 2026-08-17

### Release status

- Not published to TestPyPI or PyPI. The protected tag workflow stopped during tests,
  before building or uploading an artifact, because a synthetic release-verifier test
  inherited the real tag version. No GitHub Release was created.
- The annotated `v0.2.0` tag remains unchanged as the audit record. The isolated test
  fix and the same reviewed feature set are assigned to v0.2.1.

## [0.1.0] - 2026-08-16

### Changed

- Renamed the project, repository metadata, Python package, CLI, and workbook branding
  to Ordifile before the first package or GitHub release.

### Added

- Evidence-backed architecture, naming, format-feasibility, dependency, and license
  decisions for the v0.1 vertical slice.
- Canonical instrument-data models, structured warnings and errors, format-adapter
  registry, and external adapter entry point.
- Read-only file and folder discovery with recursion, extension filters, streaming
  SHA-256, symlink rejection, duplicate identity detection, and per-file isolation.
- Verified generic CSV, TSV, semicolon-delimited TXT, and audited non-macro XLSX
  adapters backed by synthetic fixtures.
- Automatic, acquisition-time, sequence, natural-filename, and input-order sorting
  with exported fallback provenance.
- Ordered Excel export with `Manifest`, `Samples`, `Peak_Matrix`, `Peaks`, `Metadata`,
  `Import_Log`, and optional signal sheets.
- Excel limit planning, deterministic sheet splitting, optional hashed CSV sidecars,
  formula-safe literal output, overwrite protection, and temporary-file finalization.
- `formats`, `inspect`, and `convert` CLI commands with automation-friendly exit codes
  and presentation-neutral progress events.
- Cross-platform GitHub Actions, strict typing, linting, formatting, packaging,
  vulnerability auditing, and branch-coverage gates.
- English and Korean user documentation, security and contribution policies, issue
  templates, and an adapter contribution guide.
- A build-once, Trusted Publishing release workflow with clean-wheel smoke tests on
  Ubuntu, Windows, and macOS, exact TestPyPI/PyPI artifact verification, checksums,
  and build provenance.
- Reproducible CLI demo, workbook, and social-preview assets generated only from
  synthetic example data.
- Evidence-backed GC raw-fixture research, an external-fixture policy, and bounded
  maintainer tooling for checksum-verified acquisition without enabling network access
  in the product or default CI.

### Security

- Added bounded OOXML package, namespace, relationship, worksheet-coordinate, raw
  numeric, date, formula, and resource audits before XLSX parsing.
- Added runtime validation for external adapter bundles and exact workbook-text
  representability checks so one malformed input cannot corrupt unrelated output.
- Added bounded integer parsing, input mutation detection, portable path collision
  checks, and explicit preservation of raw lexemes that cannot be interpreted safely.
- Added exact public-option validation, reversible workbook source-name display,
  terminal-safe CLI rendering, private-path omission for plugin diagnostics, and
  file-level enforcement of mandatory Excel cell limits.
- Added ASCII OOXML numeric/index grammar, field-specific XLSX cell-type checks, exact
  ISO-date provenance, and hook-free timestamp normalization before sorting/export.
- Added exact inline/shared rich-text reconstruction, formula literal length accounting,
  and bounded pre-discovery extension-filter normalization.
