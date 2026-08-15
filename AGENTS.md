# AGENTS.md

## Product goal

Ordifile batch-converts scientific instrument files and merges verified data into
one ordered Excel workbook. The priority is usability, correctness, transparent
behavior, and GitHub adoption. This is not a paper-oriented research project.

## Communication

- Progress reports to the repository owner must be in Korean honorific language.
- Code, APIs, CLI output keys, commit titles, and the primary README use English.
- Maintain `README.ko.md` for Korean users.
- Do not expose personal names, personal email addresses, machine paths, or secrets.

## Required workflow

- For proprietary formats, external libraries, licenses, standards, and
  version-sensitive claims, use `evidence_researcher` before implementation.
- Use subagents for independent research, architecture, and verification.
- Serialize overlapping write work.
- The primary agent owns commits, pushes, and integration.
- Follow the decisions in `docs/architecture/decision-record.md` and the evidence in
  `docs/research/`.

## Engineering rules

- Input files are read-only.
- Never silently discard, truncate, interpolate, or alter data.
- Never claim format support without a fixture and passing tests.
- Keep core, CLI, GUI, and format adapters separated.
- Add tests for every bug fix and public behavior change.
- Use deterministic ordering and output where technically possible.
- A bad input file must produce a structured failure, not corrupt unrelated output.
- Do not add dependencies without reason and license review.
- Do not bundle proprietary vendor software.
- Use synthetic or redistributable fixtures only.

## Required checks

Run the repository-defined commands for formatting, linting, type checking, unit and
integration tests, package build, CLI smoke tests, and dependency and license review.

## Definition of done

A change is complete only when behavior matches the requirement, tests cover success
and failure paths, documentation reflects actual behavior, no unsupported claims are
introduced, relevant checks pass, and the diff has been independently reviewed.
