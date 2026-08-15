# Naming review

- Research date: 2026-08-15
- Scope: PyPI normalized project names, GitHub repositories, active software and
  services using `LabConvert` or close variants.
- Source details: exact titles, owners, source types, dates when available, URLs, and
  access date are consolidated in [`source-register.md`](source-register.md).

## Evidence

| Source | Owner | Type | Verified fact | Project impact |
|---|---|---|---|---|
| [PyPI: labconvert](https://pypi.org/project/labconvert/) | Python Software Foundation | Package registry | The PyPI JSON project endpoint returned 404 on the research date. | The distribution name was unregistered when checked. |
| [lab-converter 0.1.4](https://pypi.org/project/lab-converter/) | PyPI project owner | Package registry | A differently normalized package converts CIELAB colors. | It is adjacent in search results but does not reserve `labconvert`. |
| [Names and normalization](https://packaging.python.org/en/latest/specifications/name-normalization/) | Python Packaging Authority | Specification | Runs of `.`, `_`, and `-` normalize to `-`; `lab-converter` and `labconvert` remain distinct. | Keep the import and CLI name `labconvert`. |
| [TiagoGOliveira/labconvert](https://github.com/TiagoGOliveira/labconvert) | Repository owner | Source repository | A small same-name repository already exists. | GitHub uniqueness is owner-scoped; search ambiguity remains. |
| [Lab Test PDF to Table Converter](https://labtestconverter.com/) | Lab Test Converter | Active service | The service uses `LabConvert` for medical-lab PDF-to-table conversion. | Material brand/search ambiguity exists in a related data-to-Excel context. |
| [LabConvert Brazil](https://www.labconvert.com.br/) | LabConvert Brazil | Active service | An unrelated checkout service uses the name. | Additional brand collision, but a different market. |

## Decision

Keep the requested product, repository, import package, and CLI names. Do not claim
that the name is legally clear. Before a formal release or trademark application,
the owner should obtain jurisdiction-specific trademark clearance. If a package
registry collision appears later, use a distinct distribution name such as
`labconvert-cli` while keeping `import labconvert` and the `labconvert` executable.

## Uncertainty and risk

This is a technical collision search, not legal advice or a trademark clearance.
WIPO, EUIPO, and USPTO registration results were not conclusively established.
