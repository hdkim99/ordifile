# Security policy

## Reporting a vulnerability

Please use the repository's private GitHub security advisory reporting flow. Do not open
a public issue for a vulnerability that could expose user data, execute spreadsheet
formulas, escape a path boundary, exhaust resources, or corrupt scientific results.

Include the affected version, a minimal reproduction using synthetic data, impact, and
any suggested mitigation. Do not include personal data, credentials, proprietary raw
files, vendor SDKs, or material you are not authorized to share.

If private vulnerability reporting is not enabled for the repository, open a public
issue containing only a non-sensitive request for a private reporting channel. Do not
include exploit details or affected data in that issue.

## Security boundaries

- Ordifile's normal conversion path operates offline and does not upload source data.
- Inputs are opened read-only. Output and sidecar paths are checked against inputs,
  aliases, hard links, and symbolic links before writing.
- Source files are hashed before parsing and checked again afterward. A changed input is
  excluded from scientific output.
- Installed third-party adapters are trusted executable Python code. Install adapters
  only from sources you trust.
- XLSX input is an archive/XML boundary. The built-in adapter applies ZIP, relationship,
  Content-Type, namespace, coordinate, type, lexeme, and resource checks before parsing.
- Spreadsheet strings are written as literal strings with formula and URL auto-detection
  disabled. Text that cannot be represented exactly by the verified writer/reader pair
  is rejected for that file.
- Filenames that require workbook-unsafe code points use a reversible display encoding
  in audit sheets. CLI presentation escapes terminal-control and bidirectional-format
  characters without changing the actual filesystem path.
- Public API and exporter overwrite flags require exact Boolean values before any output
  mutation. External adapter canonical values, descriptors, and issues are runtime
  validated; private absolute paths in plugin diagnostics are omitted or reject that
  plugin file.
- Size and integer limits are intentional denial-of-service boundaries. Limit breaches
  are reported; data is not silently truncated.
- Temporary output is finalized only after successful writing. A power loss cannot make
  a workbook and multiple sidecars one filesystem-wide transaction, so users should
  treat the Manifest as the authoritative artifact list.
- A passing dependency audit does not replace source review or data-integrity testing.
- GitHub Actions runs on a shared Linux DGX self-hosted runner. Public-fork and
  bot-authored pull-request jobs are deliberately skipped and never execute there.
  Maintainers review workflow, dependency, and executable changes before reproducing an
  outside or dependency contribution on an owner-authored same-repository branch;
  ordinary CI has read-only repository permission and receives no publishing
  secrets, OIDC permission, or release environment.

The exact v0.1 input and resource contract is documented in
[`docs/formats/generic-tabular.md`](docs/formats/generic-tabular.md).

## Supported versions

| Version | Supported |
|---|---|
| 0.5.x | Security fixes |
| Unreleased `main` branch | Best effort |
