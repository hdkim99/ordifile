# Contributing to Ordifile

Thank you for helping make scientific instrument conversion clearer and safer.

## Before opening an issue

- Search existing issues first.
- Do not attach proprietary instrument files, personal data, credentials, or files you
  are not authorized to redistribute to a public issue.
- Do not attach private conversion plans, Conversion Recipe JSON, detailed dry-run logs, plan
  or Recipe screenshots, mapping configuration, or generated workbooks; share reviewed
  fixed-code/count summaries only.
- Use synthetic data whenever possible. If a real fixture is essential, first confirm
  redistribution rights and discuss a safe transfer path with the maintainers.
- A requested format is not considered supported until a redistributable fixture and
  passing tests establish its exact capabilities.

## Development setup

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the required checks:

```bash
ruff format --check .
ruff check .
mypy
pytest
python -m build
ordifile --help
pip-audit
```

## Pull requests

- Keep changes focused and explain user-visible behavior.
- Add tests for public behavior and failure paths.
- Preserve input files as read-only.
- Do not silently truncate, aggregate, interpolate, rename, or reinterpret scientific
  data.
- Update the English and Korean documentation when behavior changes.
- Do not add a production dependency without documenting its purpose, maintenance
  status, actual license, transitive dependencies, and distribution impact.
- Use English for code, APIs, CLI text, commit titles, issues, and pull requests.
- AI-assisted contributions are permitted, but automated tools must not be listed as
  commit authors or co-authors; attribution belongs to the human contributors.
- Public-fork jobs are deliberately skipped and never run on the shared DGX self-hosted
  runner. Review workflow, dependency, script, binary, symlink, network, credential,
  and hidden-control-character changes before reproducing an external contribution on
  a same-repository branch. Pull-request jobs receive read-only repository access and
  no publishing secrets, OIDC permission, or release environment.

## Scientific behavior changes

A pull request that changes measured-field parsing, unit preservation, source identity,
retention coordinates, ordering, mapping, aggregation, or workbook semantics must state:

- the exact data definition and transformation, including units and assumptions;
- a primary format specification, public dataset DOI, or other authoritative evidence;
- whether existing exported values or row relationships change and why;
- a hand-checkable, synthetic, or legally usable regression with success and failure
  paths; and
- how the behavior is preserved through CLI, GUI/preflight, canonical models, and export.

Passing `pytest` alone does not establish scientific correctness. Public-data-derived
fixtures must identify source, license, checksum, and reduction method. Never change an
expected value without explaining whether the previous implementation, test, definition,
fixture, or numerical precision was wrong.

## Adapter contributions

Read [Adding an adapter](docs/formats/adding-an-adapter.md). A new adapter requires
bounded detection, typed parsing, structured issues, synthetic or redistributable
fixtures, tests, license evidence, and an accurate support-matrix update.

## License

Unless explicitly stated otherwise, contributions intentionally submitted for inclusion
are accepted under the Apache License 2.0, consistent with the repository license.
