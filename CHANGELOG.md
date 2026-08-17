# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
