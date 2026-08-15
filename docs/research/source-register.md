# Source register

- Research and access dates: 2026-08-15 through 2026-08-16
- Search scope: names, package registries, chromatography conversion software, GC
  exports, format standards, licenses, Python support, Excel limits, GUI distribution,
  vendor trademark guidance, OOXML worksheet coordinates and cell semantics, Excel
  numeric/date behavior, XML/OOXML string escaping, Python package release security,
  and redistributable or external GC raw fixtures.

The table records opened sources rather than search-result snippets. “Current” means
the page did not expose a stable publication date; the common access date above applies.
Verified facts are used only for the listed claim. Project inferences, unresolved
questions, redistribution risks, and implementation impact are separated in the four
topic reviews beside this register.

| Title | Publisher / owner | Type | Date available | Claim supported |
|---|---|---|---|---|
| [Names and normalization](https://packaging.python.org/en/latest/specifications/name-normalization/) | PyPA | Specification | Updated 2026-08-11 | Python project-name normalization. |
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
| [actions/checkout](https://github.com/actions/checkout) | GitHub | Repository and tag reference | Existing CI v5 and release workflow v7.0.1 reviewed through 2026-08-16 | Existing CI pin and release pin `3d3c42e5aac5ba805825da76410c181273ba90b1` are immutable commits. |
| [actions/setup-python](https://github.com/actions/setup-python) | GitHub | Repository, LICENSE, and tag reference | Existing CI v6 and release workflow v7.0.0 reviewed through 2026-08-16 | Cross-platform Python CI; release pin `5fda3b95a4ea91299a34e894583c3862153e4b97`. |
| [Codex configuration reference](https://developers.openai.com/codex/config-reference/) | OpenAI | Official documentation | Accessed 2026-08-15 | Current `web_search`, agent enablement, concurrency, and per-agent configuration keys used in `.codex/`. |
| [Qt for Python](https://doc.qt.io/qtforpython-6/) | Qt Company | Official documentation | Qt 6 | GUI functionality, deployment, accessibility. |
| [Likelihood of confusion](https://www.uspto.gov/trademarks/search/likelihood-confusion) | USPTO | Government guidance | Current | Trademark confusion is use/context dependent. |
| [Shimadzu Trademarks](https://www.shimadzu.com/about/trademarks/index.html) | Shimadzu | Vendor policy | Current | Vendor names and marks remain their owners' property. |
| [Thermo Fisher Trademark Information](https://www.thermofisher.com/io/en/home/global/trademark-information.html) | Thermo Fisher Scientific | Vendor policy | Updated 2025-09 | Trademark ownership and use cautions. |
| [Trusted Publishers](https://docs.pypi.org/trusted-publishers/) | Python Package Index | Official documentation | Accessed 2026-08-16 | OIDC publishing model, pending-publisher fields, and account boundary. |
| [Publishing package distribution releases using GitHub Actions CI/CD workflows](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/) | Python Packaging Authority | Official guide | Accessed 2026-08-16 | Trusted Publishing workflow, environment protection, and build/publish separation. |
| [Creating new Trusted Publisher projects](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) | Python Package Index | Official documentation | Accessed 2026-08-16 | Pending publishers do not reserve a project name and must exactly match owner, repository, workflow, and environment. |
| [Using artifact attestations to establish provenance for builds](https://docs.github.com/en/actions/security-guides/using-artifact-attestations-to-establish-provenance-for-builds) | GitHub | Official documentation | Accessed 2026-08-16 | GitHub build-provenance permissions and attestation verification. |
| [actions/attest v4.2.2 usage](https://github.com/actions/attest/blob/1e69f48acb82d1966a394da916b4c1698aa569d6/README.md#usage) | GitHub | Pinned official action documentation | Accessed 2026-08-16 | The exact pinned action requires `id-token: write`, `attestations: write`, and `artifact-metadata: write` for artifact attestations. |
| [Managing environments for deployment](https://docs.github.com/en/actions/deployment/targeting-different-environments/managing-environments-for-deployment) | GitHub | Official documentation | Accessed 2026-08-16 | Environment reviewers and deployment branch/tag rules. |
| [Side Wall Core Trim Extract GC Data Files](https://www.bsee.gov/stats-facts/ocs-regions/alaska/arctic-drilling/arctic-exploration-burger-j-well-data-2015/side-wall-core-trim-extract-gc-data) | Bureau of Safety and Environmental Enforcement | Government dataset page | Accessed 2026-08-16 | Stable source of the inspected Agilent ChemStation GC-FID v181 channel file. |
| [Privacy, copyright, and disclaimer](https://www.bsee.gov/bsee.gov/privacy-disclaimer) | Bureau of Safety and Environmental Enforcement | Government terms | Accessed 2026-08-16 | BSEE public-information copying and source-acknowledgement guidance. |
| [IODP Expedition 384 gas safety report](https://zenodo.org/records/15122350) | International Ocean Discovery Program / Zenodo | Dataset record | Published 2025-01-21; accessed 2026-08-16 | CC BY 4.0 GC-FID/TCD raw and method archive, file metadata, and checksums. |
| [Data to Support the Development of Rapid GC-MS Methods for Seized Drug Analysis](https://doi.org/10.18434/mds2-2862) | National Institute of Standards and Technology | Government dataset record | Modified 2022-12-13; accessed 2026-08-16 | Native Agilent GC-MS `.D` fallback corpus and provider SHA-256. |
| [NIST/NIJ Characterized Authentic Drug Sample Project Raw & Processed Data](https://doi.org/10.18434/mds2-3628) | National Institute of Standards and Technology | Government dataset record | Version 1.1.0, 2025-03-20; accessed 2026-08-16 | Large GC-FID TXT and GC-MS mzXML external corpus; not proprietary raw evidence. |
| [Copyright, fair use and licensing statements for NIST publications and data](https://www.nist.gov/open/copyright-fair-use-and-licensing-statements-srd-data-software-and-technical-series-publications) | National Institute of Standards and Technology | Government license guidance | Accessed 2026-08-16 | NIST data attribution and change-notice boundary. |
| [ChromStream](https://github.com/MyonicS/ChromStream) | ChromStream maintainers | Repository and LICENSE | Release 0.2.0, accessed 2026-08-16 | Independent v181 signal-read result and unresolved upstream-notice provenance. |
| [chemplexity/chromatography](https://github.com/chemplexity/chromatography) | chemplexity | Repository and LICENSE | Accessed 2026-08-16 | MIT reference implementation and documented `.ch` generation scope. |
| [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/) | Creative Commons | License | Current; accessed 2026-08-16 | Sharing and adaptation permission plus attribution, link, and change-marking requirements. |
| [Creative Commons CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/) | Creative Commons | Public-domain dedication | Current; accessed 2026-08-16 | Reuse permission and limits concerning other rights. |
| [YOUNGIN Chromass company history](https://kor.youngincm.com/page/?M2_IDX=7532&SCL_CODE=io7tjkrj) | YOUNGIN Chromass | Official company history | Accessed 2026-08-16; events dated by year | Corporate lineage, 2019 name change, and product chronology. |
| [YOUNGIN Scientific greeting](https://www.youngin.com/ko/about/greeting.asp) | YOUNGIN Scientific | Official corporate page | Accessed 2026-08-16 | YOUNGIN Chromass is a separately listed affiliate, not an automatic manufacturer alias. |
| [New OEM cooperation](https://www.dataapex.com/news/26748/new-oem-cooperation) | DataApex | Official announcement | 2008-04-14 | Young Lin Instruments sold a Clarity OEM product named YL-Clarity. |
| [YL-Clarity Software, SNSW-202112-02](https://file.younglin.com/Service_Note/23_YCM_Service_Note_SNSW-202112-02.pdf) | YOUNGIN Chromass | Official service note | 2021-12-16 | YL-Clarity 8.1/8.5/8.6.1 mappings for ChroZen and YL6500 detector configurations. |
| [YL-Clarity Chromatography Data System](https://eng.youngincm.com/goods/read.php?M2_IDX=18459&SC_SC2_IDX=1082&SP_CODE=19113EE3) | YOUNGIN Chromass | Official product page | Accessed 2026-08-16 | Current CDS control, detector-signal, export, and post-run claims. |
| [YOUNGIN Lab. Highlight, issue 78](https://www.youngin.com/upload/file/vol.78.pdf) | YOUNGIN Scientific | Official group newsletter | Published 2017-12; accessed 2026-08-16 | `AUTOCHRO-II` instrument control, contemporary Windows support, multiple-channel and auxiliary-signal acquisition, and ASCII/CDF interoperability. |
| [LC practical-analysis workshop registration](https://kor.youngincm.com/form/add.php?M2_IDX=39745) | YOUNGIN Chromass | Indexed official training form | Publication date not shown; accessed 2026-08-16 | Search index lists YL-Clarity, Autochro-2, and Autochro-3000 as separate choices. Direct access is currently login-gated; the source does not prove native-format compatibility. |
| [ChroZen GC](https://kor.youngincm.com/goods/read.php?M2_IDX=18351&SC_BOOKMARK=N&SC_SC1_IDX=351&SP_CODE=1911IA7H) | YOUNGIN Chromass | Official product page | Accessed 2026-08-16 | Current GC brand and detector configurations. |
| [YL6500 GC discontinuation notice](https://eng.youngincm.com/board/read.php?B_IDX=88384&M2_IDX=7443) | YOUNGIN Chromass | Official notice | Posted 2023-11-02 | YL6500 discontinuation and ChroZen GC replacement. |
| [ChroZen GC/MS](https://kor.youngincm.com/goods/read.php?M2_IDX=18353&SC_SC2_IDX=896&SP_CODE=1912SQGW) | YOUNGIN Chromass | Official product page | Accessed 2026-08-16 | Single-quadrupole scope and stated YL-Clarity integration. |
| [ChroZen TQ GC/MS System](https://kor.youngincm.com/goods/read.php?M2_IDX=18353&SC_ALL=N&SC_SC2_IDX=1732&SP_CODE=2003BTSG) | YOUNGIN Chromass | Official product page | Documented 2020-03; accessed 2026-08-16 | Tandem-MS scope; the page does not establish a CDS or native format. |
| [Clarity list of terms](https://www.dataapex.com/documentation/Content/Help/100-list-of-terms/100.000-list-of-terms/100-list-of-terms.htm) | DataApex | Official documentation | Accessed 2026-08-16 | General Clarity `.prm`, `.raw`, method, sequence, calibration, project, and report-layout meanings. |
| [Recovering data after crash or freeze](https://www.dataapex.com/documentation/Content/user-guide/troubleshooting/13-recovering-data-after-crash-freeze.htm) | DataApex | Official documentation | Accessed 2026-08-16 | General Clarity `RUN.RAW` and `LAST.RAW` recovery semantics and incompleteness risk. |
| [Export Chromatogram](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.010-file/030.010-export-chromatogram.htm) | DataApex | Official documentation | Accessed 2026-08-16 | General Clarity CDF, TXT, CHR, and ASC export behavior and AIA scope limits. |
| [Export Data](https://www.dataapex.com/documentation/Content/Help/020-instrument/020.050-setting/020.050-export-data.htm) | DataApex | Official documentation | Accessed 2026-08-16 | All-versus-displayed export range and time-step bunching. |
| [Clarity End User License Agreement](https://www.dataapex.com/downloads/26027/view) | DataApex | Official software license | 2024-01-12 | Proprietary licensing, redistribution, modification, and reverse-engineering boundary. |

## Gaps

No authoritative complete Agilent `.ch` structure or formal `Ordifile` trademark
clearance was established. A BSEE v181 `.CH` file has a redistribution basis and was
independently read, but its signal-unit field and the byte-level specification remain
unresolved. ASTM E1947's paid text was not accessed or used as implementation evidence.
No publicly redistributable YoungIn completed chromatogram, Autochro native fixture,
paired official export, public native reader, or reader SDK was found. These gaps block
proprietary support claims but do not block the generic export vertical slice or its
v0.1.0 release.
