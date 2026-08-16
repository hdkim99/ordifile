# Third-party notices

Ordifile is licensed under the Apache License 2.0. It does not bundle proprietary
vendor software, SDKs, DLLs, executables, or instrument files.

The following packages are declared dependencies. They are installed separately by the
Python package manager and are not copied into this source repository. Versions below
are the versions reviewed for the initial release; the package metadata constrains the
accepted versions.

## Runtime dependencies

| Package | Reviewed version | License | Copyright / owner | Source |
|---|---:|---|---|---|
| openpyxl | 3.1.5 | MIT/Expat | openpyxl project contributors | [Project](https://openpyxl.readthedocs.io/) · [License](https://foss.heptapod.net/openpyxl/openpyxl/-/blob/3.1.5/LICENCE.rst) |
| defusedxml | 0.7.1 | PSF License | Christian Heimes and contributors | [Project](https://pypi.org/project/defusedxml/) · [License](https://github.com/tiran/defusedxml/blob/v0.7.1/LICENSE) |
| et-xmlfile | 2.0.0 | MIT | et-xmlfile contributors | [Project](https://pypi.org/project/et-xmlfile/) · [License](https://foss.heptapod.net/openpyxl/et_xmlfile/-/blob/2.0.0/LICENCE.rst) |
| XlsxWriter | 3.2.9 | BSD-2-Clause | John McNamara | [Project](https://github.com/jmcnamara/XlsxWriter) · [License](https://github.com/jmcnamara/XlsxWriter/blob/RELEASE_3.2.9/LICENSE.txt) |

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
| Matplotlib | 3.11.1 | PSF-based | [Project](https://matplotlib.org/) · [License](https://matplotlib.org/stable/project/license.html) |

Python itself is distributed under the Python Software Foundation License. GitHub
Actions used by this repository retain their own licenses and are not included in the
Ordifile distribution.

No code from the researched EPL-2.0, GPL-3.0, or LGPL-3.0 chromatography projects has
been copied into Ordifile.
