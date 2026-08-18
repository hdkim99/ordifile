# Third-party notices

Ordifile is licensed under the Apache License 2.0. It does not bundle proprietary
vendor software, SDKs, DLLs, executables, or instrument files.

The following packages are declared dependencies. They are installed separately by the
Python package manager and are not copied into this source repository. Versions below
are the versions reviewed for the current dependency baseline; the package metadata
constrains the accepted versions.

## Runtime dependencies

| Package | Reviewed version | License | Copyright / owner | Source |
|---|---:|---|---|---|
| openpyxl | 3.1.5 | MIT/Expat | openpyxl project contributors | [Project](https://openpyxl.readthedocs.io/) · [License](https://foss.heptapod.net/openpyxl/openpyxl/-/blob/3.1.5/LICENCE.rst) |
| defusedxml | 0.7.1 | PSF License | Christian Heimes and contributors | [Project](https://pypi.org/project/defusedxml/) · [License](https://github.com/tiran/defusedxml/blob/v0.7.1/LICENSE) |
| et-xmlfile | 2.0.0 | MIT | et-xmlfile contributors | [Project](https://pypi.org/project/et-xmlfile/) · [License](https://foss.heptapod.net/openpyxl/et_xmlfile/-/blob/2.0.0/LICENCE.rst) |
| olefile | 0.47 | BSD/PIL-style | Philippe Lagadec and contributors; based in part on PIL OleFileIO by Secret Labs AB and Fredrik Lundh | [Project](https://pypi.org/project/olefile/) · [License](https://github.com/decalage2/olefile/blob/v0.47/LICENSE.txt) |
| XlsxWriter | 3.2.9 | BSD-2-Clause | John McNamara | [Project](https://github.com/jmcnamara/XlsxWriter) · [License](https://github.com/jmcnamara/XlsxWriter/blob/RELEASE_3.2.9/LICENSE.txt) |

## Optional desktop interface dependency

The `gui` extra installs the following distributions separately. They are not included
in the Ordifile wheel and are not required by the CLI or conversion API.

| Package | Reviewed version | License | Copyright / owner | Source |
|---|---:|---|---|---|
| PySide6-Essentials | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only, with commercial licensing available | The Qt Company and Qt contributors | [Project](https://pypi.org/project/PySide6-Essentials/6.11.2/) · [Open-source obligations](https://www.qt.io/development/open-source-lgpl-obligations) |
| shiboken6 | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only, with commercial licensing available | The Qt Company and Qt contributors | [Project](https://pypi.org/project/shiboken6/6.11.2/) · [Open-source obligations](https://www.qt.io/development/open-source-lgpl-obligations) |

Ordifile intends to use the LGPLv3 licensing option for the optional desktop
dependency. `PySide6-Essentials` and its required `shiboken6` distribution are
installed separately; the Ordifile wheel and source distribution do not contain Qt
binaries. This separation does not by itself satisfy every LGPLv3 obligation. Any
future distribution that redistributes Qt binaries, including a standalone bundle,
must complete a separate
LGPL and third-party-license gate covering notices, license text,
corresponding-source availability, applicable installation information, and user
replacement/relinking rights.

## Standalone prototype build boundary

The maintainer-only unsigned prototype uses Qt's `pyside6-deploy` frontend and
`Nuitka==4.1.3`. Nuitka is an AGPL-3.0 build tool and is not shipped in the generated
bundle. Nuitka's exact Runtime Library Exception permits qualifying generated target
code to be conveyed under the program's own terms; it does not relicense Nuitka or
remove the compiler's AGPL obligations.

Prototype bundles dynamically include Qt/PySide6/shiboken6 components under the
LGPL-3.0 option. Ordifile does not copy or modify their source code; native deployment
tooling may rewrite loader metadata in copied bundle binaries, so final modification
and source obligations remain a public-distribution gate. The artifact carries the
full LGPL text, component notice,
Python and Ordifile licenses, installed permissive dependency license files, the exact
Nuitka Runtime Library Exception and this notice. That inventory does not authorize a
public binary release. Exact corresponding-source delivery, Qt third-party notices,
tested replacement/relinking and installation information, publisher identity,
Windows signing, and macOS signing/notarization remain required public-release gates.

## Build, test, quality, and documentation tools

These tools are used to develop, verify, or document the project; they are not runtime imports.

| Package | Reviewed version | License | Source |
|---|---:|---|---|
| Hatchling | 1.31.0 | MIT | [Project and license](https://github.com/pypa/hatch) |
| build | 1.5.0 | MIT | [Project and license](https://github.com/pypa/build) |
| pytest | 9.1.1 | MIT | [Project and license](https://github.com/pytest-dev/pytest) |
| pytest-cov | 7.1.0 | MIT | [Project and license](https://github.com/pytest-dev/pytest-cov) |
| Ruff | 0.16.x | MIT | [Project and license](https://github.com/astral-sh/ruff) |
| mypy | 2.3.x | MIT | [Project and license](https://github.com/python/mypy) |
| pip-audit | 2.10.1 | Apache-2.0 | [Project and license](https://github.com/pypa/pip-audit) |
| types-olefile | 0.47.0.20260508 | Apache-2.0 | [Project](https://pypi.org/project/types-olefile/) · [License](https://github.com/python/typeshed/blob/main/LICENSE) |
| Matplotlib | 3.11.1 | PSF-based | [Project](https://matplotlib.org/) · [License](https://matplotlib.org/stable/project/license.html) |
| Nuitka | 4.1.3 | AGPL-3.0 build tool; generated target covered by the exact Nuitka Runtime Library Exception | [Project](https://pypi.org/project/Nuitka/4.1.3/) · [License and exception](https://github.com/Nuitka/Nuitka/tree/4.1.3) |

Python itself is distributed under the Python Software Foundation License. GitHub
Actions used by this repository retain their own licenses and are not included in the
Ordifile distribution.

## External research fixtures (not distributed)

The following privacy-bearing fixtures are used only as controlled external or local
validation inputs. Their licenses govern those external bytes, not the Apache-2.0
Ordifile source or release distributions.

- The pinned Agilent ChemStation Result XML fixture is hosted by the IFPEN
  [GC2ASM repository](https://github.com/ifpen/GC2ASM/tree/161b940846bd606e33e0100b4c0614aef328bd01)
  under its [CeCILL-2.1 repository boundary](https://github.com/ifpen/GC2ASM/blob/161b940846bd606e33e0100b4c0614aef328bd01/LICENCE.txt).
- The pinned Shimadzu LabSolutions result ASCII fixture is hosted by the
  [chromConverter repository](https://github.com/ethanbass/chromConverter/tree/9137b85f341ceb4f2bc71cc171650af75449ac96)
  under its [repository-level GPL >= 3 boundary](https://github.com/ethanbass/chromConverter/blob/9137b85f341ceb4f2bc71cc171650af75449ac96/LICENSE.md);
  no file-specific notice was found.
- Owner-provided YoungIn YL-Clarity fixtures remain private, local-only, and without
  redistribution authorization.

None of these fixture bytes, upstream parser code, generated workbooks, or external
fixture caches is committed, bundled, installed as a runtime dependency, or included
in Ordifile wheels and source distributions.

No code from the researched EPL-2.0, GPL-3.0, or LGPL-3.0 chromatography projects has
been copied into Ordifile. ChromStream/chemplexity (MIT), chromConverter (GPL >= 3),
rainbow (LGPL-3.0), and Entab (MIT) were used only as documented research/output
oracles for independent Experimental adapters; none is bundled, imported, or installed
by Ordifile.

The Experimental Shimadzu GCD and QGD readers use only `olefile` for strict, read-only access
to the Microsoft Compound File Binary container. No Shimadzu vendor component,
chromConverter GPL code, or proprietary OpenChrom converter is bundled, translated,
imported, or installed.
