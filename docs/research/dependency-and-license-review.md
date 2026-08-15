# Dependency and license review

- Research dates: 2026-08-15 through 2026-08-16
- Scope: minimal runtime/build/test dependencies, Python/OS policy, GUI candidates,
  release actions, GC reader candidates, and redistribution implications.
- Source details: exact titles, owners, source types, dates when available, URLs, and
  access date are consolidated in [`source-register.md`](source-register.md).

## Runtime decision

| Dependency | Source and current evidence | License | Use |
|---|---|---|---|
| [openpyxl 3.1.5](https://openpyxl.readthedocs.io/en/stable/) | Official docs; released 2024-06-28 | [MIT/Expat](https://foss.heptapod.net/openpyxl/openpyxl/-/blob/branch/default/LICENCE.rst) | Read XLSX with `read_only=True`; never evaluate formulas. |
| [defusedxml 0.7.1](https://pypi.org/project/defusedxml/) | Recommended by current openpyxl security docs | [PSF](https://github.com/tiran/defusedxml/blob/main/LICENSE) | Harden XML parsing; ZIP preflight remains separately required. |
| [et-xmlfile 2.0.0](https://pypi.org/project/et-xmlfile/) | openpyxl direct dependency; released 2024-10-25 | [MIT](https://foss.heptapod.net/openpyxl/et_xmlfile/-/blob/branch/default/LICENCE.rst) | Transitive runtime dependency. |
| [XlsxWriter 3.2.9](https://pypi.org/project/xlsxwriter/) | Active pure-Python writer with constant-memory mode | [BSD-2-Clause](https://github.com/jmcnamara/XlsxWriter/blob/main/LICENSE.txt) | Deterministic, streaming-style XLSX output. |

The licenses above are compatible with distribution alongside Apache-2.0. Direct and
transitive runtime dependencies are recorded in `THIRD_PARTY_NOTICES.md`; none is copied
into this source repository. Standard-library
`dataclass`, `csv`, `argparse`, `pathlib`, and `hashlib` avoid unnecessary pandas,
NumPy, Pydantic, and Typer dependencies.

Development tools selected after inspecting their current package metadata are
Hatchling (MIT), build 1.5.0 (MIT; 1.5.1 was yanked at the research date), pytest
(MIT), pytest-cov (MIT), Ruff (MIT), mypy (MIT), and pip-audit (Apache-2.0).

## Python and operating systems

The [Python version status page](https://devguide.python.org/versions/) showed 3.11–3.14
as CPython-supported releases, Python 3.10 approaching October 2026 end-of-life, and
3.15 as a prerelease. The project therefore sets a validation target and package gate of
`requires-python = ">=3.11,<3.15"`. This does not become a Ordifile support claim until
the runtime dependency install and repository checks pass in CI for each version.

Linux, Windows, and macOS are support targets, not claims until package installation,
tests, build, and CLI smoke tests pass in GitHub Actions. Pull requests test 3.11 and
3.14 on each OS; a scheduled matrix covers all 3.11–3.14 combinations.

## GUI comparison and decision

| Candidate | OS and UI evidence | Drag-and-drop / accessibility | License and bundling | Decision risk |
|---|---|---|---|---|
| [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/) | Windows, macOS, Linux; tables, progress and logs; official [deployment guide](https://doc.qt.io/qtforpython-6/deployment/index.html) | Native DnD and documented [Qt accessibility](https://doc.qt.io/qt-6/accessible.html) | [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html) documents LGPL-3.0/GPL-3.0/commercial options; Essentials wheels remain tens of MB and require redistribution review | Provisional leader; require an installer prototype and LGPL checklist. |
| [tkinter](https://docs.python.org/3/library/tkinter.html) + [tkinterdnd2](https://pypi.org/project/tkinterdnd2/) | Tk is cross-platform; add-on classified pre-alpha | DnD requires the add-on/native components; accessibility evidence unresolved | Tcl/Tk plus MIT add-on; PyInstaller hook required | Smaller potential package, but higher DnD/accessibility risk. |
| [wxPython](https://pypi.org/project/wxPython/) | Windows, macOS, Linux native widgets | Native DnD; accessibility evidence unresolved | wxWindows Library License; Linux may require build/system GTK | Packaging complexity remains high. |
| [Toga](https://toga.beeware.org/en/stable/) | Cross-platform native abstraction, beta | Required production file/folder DnD not verified in stable docs | BSD-3-Clause; backend-specific prerequisites | Evidence gap blocks selection. |

GUI work is deferred until the core and CLI are stable. `PySide6-Essentials` is only a
provisional functional leader, not a production dependency or support claim.

## Excel constraints

Microsoft's [Excel specifications and limits](https://support.microsoft.com/en-us/office/excel-specifications-and-limits-1672b34d-7043-467e-8e27-269d656771c3)
establish 1,048,576 rows, 16,384 columns, and 32,767 characters per cell. Sheet count
is resource-bound. XlsxWriter documents a 31-character worksheet-name maximum,
forbidden characters, case-insensitive uniqueness, and restrictions on `History`.

Implementation impact:

- preflight every logical sheet; never truncate;
- reserve one row for headers;
- split row-heavy signal sheets deterministically;
- reject cells beyond the character limit unless a verified sidecar path exists;
- use literal string writes and disable automatic formula/URL conversion;
- preserve timezone values as ISO 8601 text and reject/record NaN and infinity safely.

For input XLSX, ECMA-376, Microsoft OOXML implementation notes, and openpyxl behavior
also require a narrower verified boundary than the Excel grid maxima alone. Ordifile
accepts only the transitional non-macro workbook content type and applies a bounded
package/worksheet audit before openpyxl. The practical row, cell, XML-depth, and raw
lexeme caps are project resource-safety policies documented in
`docs/formats/generic-tabular.md`; they are not claims about all valid XLSX files.

If deterministic numbered sheets are not practical, an explicit CSV-sidecar mode writes
the affected logical table beside the workbook and records its relative path, row count,
and SHA-256 in Manifest. The default remains a pre-write structured error; no automatic
offloading or truncation occurs.

## Excluded code and libraries

No OpenChrom (EPL-2.0), chromConverter (GPL-3.0), rainbow (LGPL-3.0), proprietary SDK,
DLL, executable, or fixture of unresolved provenance is copied or bundled.

GC fixture research used external readers only as independent oracles. Entab 0.3.3 is
MIT but has limited published wheels and a current CLI compatibility defect; rainbow
1.4.0 is LGPL-3.0 and produced a v181 time/signal length mismatch; ChromStream 0.2.0
read the selected v181 file but its adapted-code notice chain needs clarification.
None is a production or development dependency, and no reader code was copied. The
exact results and future clean-room recommendation are in
[`gc-fixture-search.md`](gc-fixture-search.md).

## Release workflow tooling

The release workflow uses official GitHub and PyPA actions pinned to immutable commits:

| Action | Reviewed release / commit | Purpose |
|---|---|---|
| `actions/checkout` | v7.0.1 / `3d3c42e5aac5ba805825da76410c181273ba90b1` | Read-only source checkout for validation and the single build. |
| `actions/setup-python` | v7.0.0 / `5fda3b95a4ea91299a34e894583c3862153e4b97` | Supported Python setup. |
| `actions/upload-artifact` | v7.0.1 / `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` | Store the one immutable workflow artifact. |
| `actions/download-artifact` | v8.0.1 / `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` | Reuse the same wheel, sdist, notes, and checksums. |
| `actions/attest` | v4.2.2 / `1e69f48acb82d1966a394da916b4c1698aa569d6` | GitHub artifact provenance for the reviewed distributions; this pinned release requires `id-token: write`, `attestations: write`, and `artifact-metadata: write`. |
| `pypa/gh-action-pypi-publish` | v1.14.2 / `dc37677b2e1c63e2034f94d8a5b11f265b73ba33` | Short-lived OIDC publication to TestPyPI and PyPI. |

Actions are workflow tooling and are not included in Ordifile distributions. The
publish action receives `id-token: write` only in the two tag-only publication jobs;
no package-index token or secret is configured. Release archives are built once,
hashed, tested outside the checkout, and byte-compared after both index publications.
The separate attestation job has only the read permission needed for the artifact subject
plus the three write permissions documented by the pinned `actions/attest` release.

## Verified facts, inference, and remaining risk

- Verified: the selected runtime licenses permit distribution with an Apache-2.0
  project when their notice conditions are retained; none requires a vendor runtime.
- Inference: the small pure-Python dependency set is sufficient for the verified
  vertical slice and lowers cross-platform packaging risk.
- Unresolved: a GUI bundling decision remains open, and future adapter dependencies
  require their own source and license review.
- Risk and impact: dependency versions and vulnerability status can change. Package
  constraints, CI installation, `pip-audit`, source review, and
  `THIRD_PARTY_NOTICES.md` must be updated together before a release.
