# Source register

- Research date and access date: 2026-08-15
- Search scope: names, package registries, chromatography conversion software, GC
  exports, format standards, licenses, Python support, Excel limits, GUI distribution,
  vendor trademark guidance, OOXML worksheet coordinates and cell semantics, Excel
  numeric/date behavior, and XML/OOXML string escaping.

The table records opened sources rather than search-result snippets. “Current” means
the page did not expose a stable publication date; the common access date above applies.
Verified facts are used only for the listed claim. Project inferences, unresolved
questions, redistribution risks, and implementation impact are separated in the four
topic reviews beside this register.

| Title | Publisher / owner | Type | Date available | Claim supported |
|---|---|---|---|---|
| [Names and normalization](https://packaging.python.org/en/latest/specifications/name-normalization/) | PyPA | Specification | Updated 2026-08-11 | Python project-name normalization. |
| [PyPI: labconvert](https://pypi.org/project/labconvert/) | Python Software Foundation | Registry | Accessed 2026-08-15 | The PyPI JSON project endpoint returned 404. |
| [OpenChrom](https://github.com/OpenChrom/openchrom) | OpenChrom | Repository and LICENSE | Active 2026-08 | Actual license and project scope. |
| [OpenChrom paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC2920884/) | BMC Bioinformatics | Peer-reviewed paper | 2010 | Historical platform scope; current license comes from the repository. |
| [chromConverter](https://github.com/ethanbass/chromConverter) | ethanbass | Repository and LICENSE | Release 2026-05-31 | Parser/converter scope and GPL-3.0. |
| [Entab](https://github.com/bovee/entab) | bovee | Repository and LICENSE | Active 2026 | Parser scope and MIT license. |
| [Entab on PyPI](https://pypi.org/project/entab/) | Python Software Foundation | Registry | Release 2024-06-28 | Published wheel/platform limits. |
| [rainbow](https://github.com/evanyeyeye/rainbow) | evanyeyeye | Repository and LICENSE | Active 2026-08 | Signal parser scope and LGPL-3.0. |
| [ThermoRawFileParser](https://github.com/CompOmics/ThermoRawFileParser) | CompOmics | Repository and LICENSE | Active 2026 | MS focus, Apache-2.0 core, vendor reader boundary. |
| [ProteoWizard](https://github.com/ProteoWizard/pwiz) | ProteoWizard | Repository and LICENSE | Active 2026 | MS conversion scope and license boundary. |
| [HUPO-PSI mzML](https://github.com/HUPO-PSI/mzML) | HUPO-PSI | Standard repository | Active 2026 | mzML is an MS format, not generic GC-FID. |
| [Export Chromatogram Signal as CSV](https://community.agilent.com/knowledge/chromatography-software-portal/kmp/chromatography-software-articles/kp331.export-chromatogram-signal-as-csv-with-openlab-cds-version-2-4-or-higher) | Agilent | Vendor documentation | Modified 2024-01-11 | Signal CSV export. |
| [Peak Area and Retention Time in Excel](https://community.agilent.com/knowledge/chromatography-software-portal/kmp/chromatography-software-articles/kp908.reporting-peak-area-and-retention-time-of-sequence-in-excel-format-with-openlab-cds) | Agilent | Vendor documentation | Modified 2025-11-14 | Processed peak report semantics. |
| [Export AIA Files](https://community.agilent.com/knowledge/chromatography-software-portal/kmp/chromatography-software-articles/kp1566.how-to-export-aia-files-in-openlab-cds) | Agilent | Vendor documentation | Modified 2025-10-03 | AIA export behavior. |
| [netCDF File Format Specifications](https://docs.unidata.ucar.edu/netcdf-c/current/file_format_specifications.html) | NSF Unidata | Specification | Current | Public byte-level netCDF structure. |
| [netCDF copyright](https://docs.unidata.ucar.edu/netcdf-c/current/copyright.html) | NSF Unidata | License | Current | BSD-3-Clause terms. |
| [openpyxl documentation](https://openpyxl.readthedocs.io/en/stable/) | openpyxl maintainers | Official documentation | 3.1.5 | XLSX read features and XML warning. |
| [ECMA-376 Office Open XML file formats](https://ecma-international.org/publications-and-standards/standards/ecma-376/) | Ecma International | Standard and schemas | Part 1, 5th edition, 2016-12 | SpreadsheetML schema, worksheet dimension, cell types, formulas, and workbook properties. |
| [SheetDimension Class](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.sheetdimension?view=openxml-3.0.1) | Microsoft | ISO/IEC 29500 API reference | Accessed 2026-08-15 | Worksheet dimension is an optional used-range declaration. |
| [Optimised Modes](https://openpyxl.readthedocs.io/en/3.1/optimized.html) | openpyxl maintainers | Official documentation | 3.1.4 docs, accessed 2026-08-15 | Producers can record incorrect dimensions; `reset_dimensions()` clears cached bounds. |
| [Working with sheets](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-sheets) | Microsoft | Official OOXML guidance | Updated 2025-01-21 | Worksheet row, cell-reference, and value structure. |
| [ST_CellRef implementation note](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/044c2ba4-098b-4b15-b960-3f7f972665df) | Microsoft | Official implementation note | Updated 2022-08-16 | Excel cell references range from A1 through XFD1048576. |
| [Cell Class](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.cell?view=openxml-3.0.1) | Microsoft | ISO/IEC 29500 API reference | Accessed 2026-08-15 | Cell coordinate, style, type, formula, value, and inline-string fields. |
| [Working with the shared string table](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-the-shared-string-table) | Microsoft | Official OOXML guidance | Updated 2025-01-14 | Shared-string indexing and rich-text ordering. |
| [Cell Value implementation note](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/053027c9-6036-4155-a16a-ba3a10e4ecc0) | Microsoft | Official implementation note | Updated 2022-08-16 | Typed cell-value and cached-formula-result semantics. |
| [Working with formulas](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-formulas) | Microsoft | Official OOXML guidance | Updated 2025-01-14 | Formula text and last-calculated cached values are distinct. |
| [Dates and Times](https://openpyxl.readthedocs.io/en/3.1/datetime.html) | openpyxl maintainers | Official documentation | 3.1.4 docs, accessed 2026-08-15 | Excel 1900/1904 epochs, timezone limits, and date precision. |
| [Floating-point arithmetic may give inaccurate results in Excel](https://learn.microsoft.com/en-us/office/troubleshoot/excel/floating-point-arithmetic-inaccurate-result) | Microsoft | Official product guidance | Updated 2026-03-30 | IEEE-754 behavior and 15-significant-digit precision. |
| [Office XML file extension reference](https://learn.microsoft.com/en-us/office/compatibility/xml-file-name-extension-reference-for-office) | Microsoft | Official product reference | Updated 2026-04-26 | `.xlsx`, `.xlsm`, `.xltx`, and `.xltm` are distinct file types. |
| [XML 1.0 Fifth Edition](https://www.w3.org/TR/REC-xml/) | W3C | Standard | 2008-11-26 | Legal XML characters and disallowed control characters. |
| [ST_Xstring implementation note](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/bd0aa042-434a-4ca7-b25f-4e1fd25a954d) | Microsoft | Official implementation note | Updated 2022-08-16 | OOXML `_xHHHH_` escaping and literal escape-prefix handling. |
| [openpyxl LICENSE](https://foss.heptapod.net/openpyxl/openpyxl/-/blob/branch/default/LICENCE.rst) | openpyxl maintainers | License file | Current branch | MIT/Expat terms. |
| [defusedxml LICENSE](https://github.com/tiran/defusedxml/blob/main/LICENSE) | defusedxml maintainers | License file | Current branch | PSF terms. |
| [et-xmlfile LICENSE](https://foss.heptapod.net/openpyxl/et_xmlfile/-/blob/branch/default/LICENCE.rst) | et-xmlfile maintainers | License file | Current branch | MIT terms. |
| [XlsxWriter](https://github.com/jmcnamara/XlsxWriter) | John McNamara | Repository and LICENSE | Active 2026 | Writer behavior and BSD-2-Clause. |
| [XlsxWriter 3.2.9](https://pypi.org/project/XlsxWriter/3.2.9/) | John McNamara / Python Software Foundation | Source distribution | Released 2025-09-16 | Numeric and OOXML control-string serialization inspected in the source distribution. |
| [Hatch LICENSE](https://github.com/pypa/hatch/blob/master/LICENSE.txt) | PyPA | License file | Current branch | MIT build-backend terms. |
| [build LICENSE](https://github.com/pypa/build/blob/main/LICENSE) | PyPA | License file | Current branch | MIT frontend terms. |
| [pytest LICENSE](https://github.com/pytest-dev/pytest/blob/main/LICENSE) | pytest-dev | License file | Current branch | MIT test-runner terms. |
| [pytest-cov LICENSE](https://github.com/pytest-dev/pytest-cov/blob/master/LICENSE) | pytest-dev | License file | Current branch | MIT coverage-plugin terms. |
| [Ruff LICENSE](https://github.com/astral-sh/ruff/blob/main/LICENSE) | Astral | License file | Current branch | MIT linter/formatter terms. |
| [mypy LICENSE](https://github.com/python/mypy/blob/master/LICENSE) | mypy maintainers | License file | Current branch | MIT type-checker terms. |
| [pip-audit LICENSE](https://github.com/pypa/pip-audit/blob/main/LICENSE) | PyPA | License file | Current branch | Apache-2.0 audit-tool terms. |
| [Excel specifications and limits](https://support.microsoft.com/en-us/office/excel-specifications-and-limits-1672b34d-7043-467e-8e27-269d656771c3) | Microsoft | Official documentation | Current | Worksheet and cell limits. |
| [CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection) | OWASP | Security guidance | Current | Spreadsheet formula-injection risk. |
| [Status of Python versions](https://devguide.python.org/versions/) | Python core developers | Official status | Updated 2026-05-27 | Supported and prerelease versions. |
| [actions/checkout](https://github.com/actions/checkout) | GitHub | Repository and tag reference | v5 tag resolved 2026-08-15 | CI pins reviewed tag commit `fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09`. |
| [actions/setup-python](https://github.com/actions/setup-python) | GitHub | Repository, LICENSE, and tag reference | v6 tag resolved 2026-08-15 | Cross-platform Python CI; pinned commit `ece7cb06caefa5fff74198d8649806c4678c61a1`. |
| [Codex configuration reference](https://developers.openai.com/codex/config-reference/) | OpenAI | Official documentation | Accessed 2026-08-15 | Current `web_search`, agent enablement, concurrency, and per-agent configuration keys used in `.codex/`. |
| [Qt for Python](https://doc.qt.io/qtforpython-6/) | Qt Company | Official documentation | Qt 6 | GUI functionality, deployment, accessibility. |
| [Likelihood of confusion](https://www.uspto.gov/trademarks/search/likelihood-confusion) | USPTO | Government guidance | Current | Trademark confusion is use/context dependent. |
| [Shimadzu Trademarks](https://www.shimadzu.com/about/trademarks/index.html) | Shimadzu | Vendor policy | Current | Vendor names and marks remain their owners' property. |
| [Thermo Fisher Trademark Information](https://www.thermofisher.com/io/en/home/global/trademark-information.html) | Thermo Fisher Scientific | Vendor policy | Updated 2025-09 | Trademark ownership and use cautions. |

## Gaps

No authoritative complete Agilent `.ch` structure, redistributable proprietary fixture,
or formal `LabConvert` trademark clearance was established. ASTM E1947's paid text was
not accessed or used as implementation evidence. These gaps block proprietary support
claims but do not block the generic export vertical slice.
