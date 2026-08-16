# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A Unicode-filename synthetic example under `examples/unicode/` with a rendered
  screenshot of its generated workbook, showing that normal Unicode input
  filenames are preserved in the `Samples` sheet. (Issue #7)

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
