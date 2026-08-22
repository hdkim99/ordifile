# Dependency and license review

- Research dates: 2026-08-15 through 2026-08-23
- Scope: minimal runtime/build/test dependencies, Python/OS policy, GUI candidates,
  release actions, GC reader candidates, and redistribution implications.
- Source details: exact titles, owners, source types, dates when available, URLs, and
  access date are consolidated in [`source-register.md`](source-register.md).

## Runtime decision

| Dependency | Source and current evidence | License | Use |
|---|---|---|---|
| [openpyxl 3.1.5](https://openpyxl.readthedocs.io/en/stable/) | Official docs; released 2024-06-28 | [MIT/Expat](https://foss.heptapod.net/openpyxl/openpyxl/-/blob/branch/default/LICENCE.rst) | Read XLSX with `read_only=True`; never evaluate formulas. |
| [defusedxml 0.7.1](https://pypi.org/project/defusedxml/) | Recommended by current openpyxl security docs | [PSF](https://github.com/tiran/defusedxml/blob/main/LICENSE) | Harden XML parsing; ZIP preflight remains separately required. |
| [et-xmlfile 2.0.0](https://pypi.org/project/et-xmlfile/) | Directly constrained by Ordifile and required by openpyxl; released 2024-10-25 | [MIT](https://foss.heptapod.net/openpyxl/et_xmlfile/-/blob/branch/default/LICENCE.rst) | Runtime dependency. |
| [XlsxWriter 3.2.9](https://pypi.org/project/xlsxwriter/) | Active pure-Python writer with constant-memory mode | [BSD-2-Clause](https://github.com/jmcnamara/XlsxWriter/blob/main/LICENSE.txt) | Deterministic, streaming-style XLSX output. |
| [olefile 0.47](https://pypi.org/project/olefile/) | Pure-Python universal wheel; imported under CPython 3.14 during review | [BSD/PIL-style](https://github.com/decalage2/olefile/blob/v0.47/LICENSE.txt) | Strict read-only CFB access for the exact Experimental Shimadzu profile; adapter-owned size, inventory, and stream limits still apply. |

The licenses above are compatible with distribution alongside Apache-2.0. Direct and
transitive runtime dependencies are recorded in `THIRD_PARTY_NOTICES.md`; none is copied
into this source repository. Standard-library
`dataclass`, `csv`, `argparse`, `pathlib`, and `hashlib` avoid unnecessary pandas,
NumPy, Pydantic, and Typer dependencies.

The Experimental Agilent Result XML adapter reuses the existing permissive
`defusedxml` dependency with adapter-owned byte, element, nesting, text and numeric
bounds. GC2ASM code is not copied or linked; its pinned CeCILL-2.1 XML fixture is an
external controlled-CI input only and is absent from distributions.

The Experimental Shimadzu result ASCII adapter adds no dependency: bounded ASCII,
decimal and hashing operations use the Python standard library. Its pinned primary
fixture is covered only by repository-level GPL >= 3 with no file-specific notice, so
the bytes remain a controlled external input. No GPL parser source, test expression,
constant table, dependency or derived code is copied into Ordifile. The separate
MIT-declared HPLC/RID file is documentation-only grammar evidence and does not expand
the GC runtime profile.

Development tools selected after inspecting their current package metadata are
Hatchling 1.31.0 (MIT, exact isolated-build pin), build 1.5.0 (MIT; 1.5.1 was yanked at
the research date), pytest
(MIT), pytest-cov (MIT), Ruff (MIT), mypy (MIT), and pip-audit (Apache-2.0).
The exact `types-olefile 0.47.0.20260508` Apache-2.0 stub is development-only and
must not appear in wheel runtime metadata.

## Python and operating systems

The [Python version status page](https://devguide.python.org/versions/) showed 3.11–3.14
as CPython-supported releases, Python 3.10 approaching October 2026 end-of-life, and
3.15 as a prerelease. The project therefore sets a validation target and package gate of
`requires-python = ">=3.11,<3.15"`. This does not become a Ordifile support claim until
the runtime dependency install and repository checks pass in CI for each version.

Linux, Windows, and macOS remain package support targets. Current continuous CI runs
the required quality and package job on Python 3.14 and the full test suite without
coverage on Python 3.11–3.13, all on the shared DGX self-hosted Linux ARM64 runner. This
is a Python compatibility matrix, not a current cross-platform matrix. The v0.1.0
release record separately preserves the historical Ubuntu, Windows, and macOS
validation that preceded the DGX-only CI policy.

## GUI comparison and decision

| Candidate | OS and UI evidence | Drag-and-drop / accessibility | License and bundling | Decision risk |
|---|---|---|---|---|
| [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/) | Windows, macOS, Linux; tables, progress and logs; official [deployment guide](https://doc.qt.io/qtforpython-6/deployment/index.html) | Native DnD and documented [Qt accessibility](https://doc.qt.io/qt-6/accessible.html) | [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html) documents LGPL-3.0/GPL-3.0/commercial options; Essentials wheels remain tens of MB and require redistribution review | Selected for the optional Experimental Python-package GUI; standalone redistribution still requires its own LGPL gate. |
| [tkinter](https://docs.python.org/3/library/tkinter.html) + [tkinterdnd2](https://pypi.org/project/tkinterdnd2/) | Tk is cross-platform; add-on classified pre-alpha | DnD requires the add-on/native components; accessibility evidence unresolved | Tcl/Tk plus MIT add-on; PyInstaller hook required | Smaller potential package, but higher DnD/accessibility risk. |
| [wxPython](https://pypi.org/project/wxPython/) | Windows, macOS, Linux native widgets | Native DnD; accessibility evidence unresolved | wxWindows Library License; Linux may require build/system GTK | Packaging complexity remains high. |
| [Toga](https://toga.beeware.org/en/stable/) | Cross-platform native abstraction, beta | Required production file/folder DnD not verified in stable docs | BSD-3-Clause; backend-specific prerequisites | Evidence gap blocks selection. |

The core and CLI are now stable enough for an optional Experimental GUI.
`PySide6-Essentials` is selected only for the `gui` extra, with `shiboken6` as its exact
required companion distribution. Neither dependency is installed by the default
Ordifile package. The selection rationale is recorded in
[`gui-framework-decision.md`](../architecture/gui-framework-decision.md); standalone
redistribution is now an unsigned, non-publishable prototype under Issue #6. The
separate decision and legal gates are recorded in
[`standalone-packaging-decision.md`](../architecture/standalone-packaging-decision.md).

## Standalone prototype tooling

Windows uses direct `Nuitka==4.1.3 --zig` with official Zig 0.16.0 x86-64 bytes as
run-scoped build tooling. Zig's top-level license is MIT, but its Windows GNU ABI uses
MinGW-w64/libc build inputs with their own license inventory. macOS retains Qt's
`pyside6-deploy` frontend with standalone mode and the same exact Nuitka pin. Neither
compiler toolchain is distributed in the candidate. Windows forces the exact release's
built-in MIT-licensed `pefile` dependency scanner instead of downloading the default
legacy dependency tool. Nuitka's exact Runtime Library
Exception applies to qualifying generated target code; it does not weaken the compiler
license. Before any public Windows distribution, the exact linked Zig/MinGW/libc/compiler
runtime provenance, notices and source obligations must be resolved. PyInstaller 6.22.2
onedir remains a documented fallback and is not installed by the primary build lock.
The exact standalone build environment also pins `ordered-set==4.1.0` (MIT) and
`zstandard==0.25.0` (BSD-3-Clause). They are build-only environment dependencies, not
Ordifile wheel runtime dependencies or separately distributed prototype components.

Windows and macOS candidates are native onedir/`.app` ZIPs. Onefile, MSI, DMG, signing,
notarization and release publication are excluded. The candidate is explicitly
non-publishable until exact Qt/PySide/shiboken corresponding source and third-party
notices, replacement/relinking and applicable installation information, publisher
identity, platform signing and clean-machine tests all pass. Detailed primary-source
evidence is in [`standalone-packaging-evidence.md`](standalone-packaging-evidence.md).

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

GC fixture research used external readers only as research oracles. Entab 0.3.3 is MIT
but does not accept v181; rainbow 1.4.0 is LGPL-3.0 and produced a v181 time/signal
length mismatch; ChromStream 0.2.0 and GPL-licensed chromConverter use
chemplexity-derived axis/scaling assumptions that are not a vendor export
cross-check. None is a production or development dependency, and no reader code was
copied. The pinned commits, observed behavior, license boundary, and current
independent-implementation decision are in
[`agilent-chemstation-ch-v181-investigation.md`](agilent-chemstation-ch-v181-investigation.md).
No reader is a runtime or development dependency. The Ordifile implementation was
written from independently recorded byte facts and normalized output summaries, not
by copying or translating reader source.

For Shimadzu GCD research, the GPL >= 3 `chromConverter` reader is likewise a
comparison-only source. Its code is not copied, translated, imported, or bundled.
OpenChrom's separately licensed GCD converter is also excluded. The only new runtime
dependency is permissive `olefile`, which supplies general CFB container access rather
than Shimadzu interpretation. Ordifile independently validates the exact LabSolutions
5.82 stream inventory, metadata relationships, point-count equations, time axis, and
signal semantics described in
[`shimadzu-gcsolution-gcd-investigation.md`](shimadzu-gcsolution-gcd-investigation.md).
The LabSolutions result ASCII reader is independently implemented from the pinned
fixture's observable schema, official Peak Table semantics and same-file/paired-file
invariants. It does not import or execute chromConverter.

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
- Unresolved: the unsigned standalone prototype is implemented, but public signed
  distribution remains blocked by explicit source/relinking/install-information,
  publisher identity, signing and notarization gates; future adapter dependencies
  require their own source and license review.
- Risk and impact: dependency versions and vulnerability status can change. Package
  constraints, CI installation, `pip-audit`, source review, and
  `THIRD_PARTY_NOTICES.md` must be updated together before a release.
