# YOUNG IN Chromass GC format investigation

- Research and access dates: 2026-08-16; local fixture intake 2026-08-17
- Status: `BLOCKED_BY_PAIRED_EXPORT_AND_FORMAT_EVIDENCE`; no Ordifile support claim
- Canonical project identifier: `youngin_chromass`
- Canonical display: YOUNG IN Chromass / 영인크로매스

## Purpose

This track evaluates YOUNG IN Chromass as a required priority candidate for
Ordifile's first proprietary GC adapter. It separates manufacturer, instrument, CDS,
native file, recovery file, and export evidence. It does not implement an adapter and
does not add YOUNG IN Chromass to the v0.1.0 support table.

## Terminology

- **Native completed chromatogram:** the normal finalized acquisition result selected
  by the CDS after a successful run.
- **Temporary acquisition file:** the file written while acquisition is in progress.
- **Recovery file:** data retained to recover after a crash or abnormal termination;
  it may be incomplete or reprocessed with a later method.
- **Processed result:** integration, peak, identification, or calculation results
  stored with or beside a chromatogram.
- **Exported chromatogram:** signal values emitted through a documented export path.
- **Peak-table export:** processed peak rows, not necessarily the raw signal.
- **Method, sequence, calibration, report:** distinct control or presentation records;
  none is assumed to be part of a chromatogram without evidence.

An extension is never enough to assign one of these meanings.

## Manufacturer and brand history

Project documentation uses **YOUNG IN Chromass** and **영인크로매스** as requested.
Current official English pages also render the legal/brand text as `YOUNGIN Chromass`;
that exact source spelling should be retained in provenance rather than silently
normalized.

Official company history describes this line as an analytical-instrument development
department of YOUNGIN Scientific in 1985, a dedicated analytical-instrument company in
1993, and a 2019 corporate-name change from Young Lin Instrument to YOUNGIN Chromass.
YOUNGIN Scientific currently lists YOUNGIN Chromass as a separate affiliated company,
not the same legal entity. `ChroZen` is a product brand, not a manufacturer name.

| Source text | Ordifile treatment |
|---|---|
| `YOUNG IN Chromass`, `YOUNGIN Chromass`, `영인크로매스` | Canonical vendor `youngin_chromass`, while preserving the exact source lexeme |
| `Young Lin Instrument(s)`, `YL Instruments`, `영린기기` | Historical alias only; do not imply current format compatibility |
| `YOUNGIN Scientific`, `영인과학` | Separate affiliate, distributor, or service organization unless a specific record proves another role |
| `ChroZen` | Product brand |
| `YL-Clarity` | Named OEM chromatography data system; not a file-format identity by itself |

## Current GC models

| Manufacturer display | Model | Sales status | Detectors or acquisition type | CDS evidence | Native format | Fixture | Adapter feasibility |
|---|---|---|---|---|---|---|---|
| YOUNG IN Chromass | ChroZen GC | Current; official history records development in 2019 | Official product material lists FID, TCD, micro-TCD, NPD, FPD, PFPD, PDD, micro-ECD, MS, PID, and VUV configurations | Current YL-Clarity page says it controls GC systems | Unresolved | None | High priority only after completed FID/TCD fixture |
| YOUNG IN Chromass | ChroZen GC/MS | Current single quadrupole; announced 2020-03-03 | EI, optional CI, Scan/SIM | Product page states integrated YL-Clarity control and analysis | Unresolved and likely different from GC-FID/TCD | None | Separate GC-MS investigation |
| YOUNG IN Chromass | ChroZen TQ GC/MS | Current triple quadrupole; documented by 2020-03 | Scan/SIM/MRM, EI and optional CI | Current page does not identify the CDS | Unresolved | None | Separate GC-MS/MS investigation; do not infer YL-Clarity |

GC/MS and tandem GC-MS/MS are not forced into a future FID/TCD adapter.

## Legacy GC models

| Manufacturer at the time | Model | Known period / status | Detectors | CDS evidence | Native format | Fixture | Feasibility |
|---|---|---|---|---|---|---|---|
| Young Lin Instrument historical line | YL6500 GC | Launched in 2011; discontinued effective 2023-11-01 with ChroZen GC named as replacement | Official service material covers FID, TCD, NPD, FPD, PDD, micro-ECD and configurations | Service note recommends YL-Clarity 8.6.1 for supported configurations; DataApex lists a Young Lin LAN driver | Unresolved | None | `BLOCKED_BY_FIXTURE` |
| Historical YL line | YL6900 GC/MSD | Launch recorded in 2015; current sale status unresolved | GC-MS | DataApex current control list marks its module `Testing` | Unresolved | None | Low until product/CDS status is clarified |
| Historical YL line | YL6100 | Legacy; current sale status unresolved | GC | DataApex control list marks the general Clarity module `Ready` | Unresolved | None | Low; not a support target without a fixture |

Other `YL` model names are not added based on naming similarity alone.

## Chromatography software inventory

| Software | Verified relationship and versions | OS / instrument evidence | Project and file evidence | Export / SDK | Decision |
|---|---|---|---|---|---|
| YL-Clarity | DataApex officially announced in 2008 that Young Lin Instruments would sell a Clarity OEM as `YL-Clarity`; a 2021 YOUNG IN Chromass note names 8.1, 8.5, and 8.6.1 | 2021 note maps versions to ChroZen and YL6500 detector configurations; generic Clarity OS claims cannot be copied to every OEM build | General Clarity structure is documented below; YL binary identity remains unverified | Current product page describes export and post-run features; DataApex control-module SDK is contractual, not a public `.prm` reader SDK | Required current-CDS research target; blocked by fixture |
| AUTOCHRO-II / Autochro-2 | Official history records `Autochro2` in 2012; a 2017 official item describes XP/Vista/7/8 use and YL6500/HPLC control | Multiple-channel and auxiliary-signal acquisition described | Native extension, project tree, method, sequence, calibration and report structures unresolved | ASCII/CDF compatibility mentioned; public SDK and license not found | Treat spelling equivalence and format generation as unresolved |
| Autochro-3000 | Current YOUNG IN Chromass training form lists it as a separate program | Supported GC models and Windows versions unresolved | Native extension, format version and project structure unresolved | Export, SDK and license unresolved | Separate research backlog; never alias to Autochro-2 |

## YL-Clarity investigation

[DataApex's 2008 OEM announcement](https://www.dataapex.com/news/26748/new-oem-cooperation)
establishes the product relationship. It does **not** prove that every YL-Clarity
version writes a byte-identical file to every vanilla Clarity release.

General DataApex Clarity documentation establishes this lifecycle:

1. acquisition begins with a channel run `.raw` file;
2. normal completion creates a last/recovery copy and a finalized `.prm` chromatogram;
3. `*RUN.RAW` can remain after abnormal termination and `*LAST.RAW` is a recovery copy;
4. recovery data may omit the last 10–90 seconds and can be reprocessed with a method
   selected during recovery rather than the original control method.

The future normal reader boundary is therefore a completed `.prm`, not `.raw`.
Recovery support, if ever added, must be a separate experimental capability that warns
about incompleteness and method provenance.

General Clarity supports multiple signals per chromatogram. Current public Clarity
documentation mentions up to 32 signals, while the current YL-Clarity page describes
up to 12 detector signals per instrument and older material mentions four. These are
version-sensitive limits, not a universal YoungIn channel layout.

Still unresolved without a YL-produced fixture:

- whether YL-Clarity actually finalizes every supported run as `.prm`;
- its `.prm` signature, internal format version, and vanilla-Clarity compatibility;
- whether FID/TCD signals share one `.prm` or are stored separately in each version;
- which instrument, detector, method, sequence, calibration, and result fields are
  embedded or sibling records;
- whether a YL and vanilla Clarity installation lawfully cross-open the same file.

## Autochro investigation

Official material confirms the product names and some ASCII/CDF export capability but
does not disclose a native extension or data model. `AUTOCHRO-II` and `Autochro-2`
may be spelling or generation variants, but that is not established. Autochro-3000 is
listed separately and must remain separate.

Do not create one `youngin_autochro` parser. Before design, obtain the exact product
name, version/build, supported Windows release, complete project tree, native data,
method, sequence, calibration and report extensions, multi-channel semantics, a paired
ASCII/CDF export, and written permission or an official format/API route.

## File-extension inventory

These meanings are verified for **general DataApex Clarity** only unless stated
otherwise.

| Extension or structure | Software | Claimed purpose | Verified purpose | Evidence | YoungIn fixture |
|---|---|---|---|---|---|
| `.prm` | General Clarity; YL-Clarity candidate | Completed chromatogram | Verified for general Clarity; YL-Clarity applicability unresolved | DataApex terminology, error-flow and recovery documentation | None |
| `.raw` | General Clarity; YL-Clarity candidate | Acquisition/recovery data | Verified temporary/recovery role for general Clarity; not a normal completed chromatogram | DataApex recovery and error-flow documentation | None |
| `.met` | General Clarity | Acquisition and processing method | Verified for general Clarity | DataApex terminology | None |
| `.seq` | General Clarity | Automatic analysis sequence | Verified for general Clarity | DataApex terminology | None |
| `.cal` | General Clarity | Calibration curves and levels | Verified for general Clarity | DataApex terminology | None |
| `.prj` | General Clarity | Project directory and recent state | Verified for general Clarity | DataApex terminology | None |
| `.sty` | General Clarity | Report layout | Verified for general Clarity | DataApex terminology | None |
| `.txt` | General Clarity | Detector-separated signal export | Verified; export settings affect range and bunching | DataApex export documentation | None |
| `.chr` | General Clarity | Multi-detector text export | Verified for general Clarity | DataApex export documentation | None |
| `.cdf` | General Clarity | AIA/NetCDF chromatogram export | Verified; signal/basic description only, not full results/method/calibration/GLP | DataApex export documentation | None |
| `.asc` | General Clarity | EZChrom ASCII export | Verified export choice | DataApex export documentation | None |
| Autochro native structure | Autochro family | Unresolved | Unresolved | No authoritative format document or file | None |

## Native versus exported data

For integrity comparison, request the same normal run as native completed data and as
official export. General Clarity export has important scope controls:

- AIA/CDF carries signal and basic description, not complete results, method,
  calibration, or GLP information.
- TXT and CDF can create one file per detector.
- CHR can put multiple detector signals in one text file.
- `Displayed Data` or a nonzero `Time Step` can crop or bunch values.
- A signal oracle should use `All Data`, include the x-axis, and use `Time Step=0` or a
  value below the acquisition sampling interval.

Until a real YoungIn header is verified, a Clarity export must not be labelled as
YOUNG IN Chromass solely because its producing software might be YL-Clarity.

## FID/TCD channel representation

Product literature confirms that ChroZen and YL6500 configurations can use FID and TCD.
General Clarity supports multiple signals, per-detector TXT/CDF exports, and combined
CHR export. A 2026-08-17 local-only intake now contains 23 distinct `.prm` completed-
chromatogram candidates carrying YL-Clarity 9.0.1 candidate markers. Ten filenames are
FID-labelled, ten are TCD-labelled, and three cannot be classified without reading the
native detector/channel structure. Filename labels are not detector evidence, so the
three remaining files are not claimed as FID+TCD runs. The intake still does not
establish whether native FID and TCD are in one `.prm`, separate chromatograms, or
version-dependent.

A future adapter must preserve channel names and detector types, retain the native
time axis without interpolation, keep multi-channel sample identity, and export
separate `Signals_FID_*` and `Signals_TCD_*` sheets. Missing peak tables are valid; it
must not perform peak detection or infer cross-detector compound identity.

## Public and locally supplied fixtures

Searches covered official YOUNG IN Chromass and YOUNGIN Scientific pages, DataApex,
GitHub, PyPI, Zenodo, Figshare, university/government repositories, supplementary data,
and application/service notes in Korean and English.

- Official application and service notes contain plotted chromatograms and conditions,
  not downloadable native signal files.
- No public redistributable YOUNG IN Chromass `.prm`, Autochro native run, paired
  official export, or open source parser was found.
- A University of York page advertises generic Clarity PRM/CDF/TXT teaching files, but
  it is not a YoungIn acquisition; its FTP timed out and an HTTPS substitute returned
  404 during this review.
- DataApex demo material is registration/EULA controlled and is not a YoungIn fixture.
- One owner-supplied local archive is now present only in the ignored YoungIn fixture
  path. It contains 23 unique `.prm` files and no `.raw`, `.txt`, `.chr`, `.cdf`,
  `.asc`, or other export companion. Its SHA-256 is
  `4af61e1aa8abef3694a4c24a28203b0a1d382a11b6442c3e9b43653487f97fe5`.
- Central-directory, path, member-type, encryption, compression-ratio, full-read, and
  CRC checks passed. Filename-derived sample identifiers and embedded local-path or
  operator-field candidates require local-only handling. No credential pattern was
  detected, and no original name, metadata value, or file byte is published.

No YoungIn data was downloaded from a third party. The owner-supplied material remains
local-only. Future material must stay under
`.external-fixtures/youngin/` or `.research-downloads/youngin/` and follow
[`youngin-fixture-request.md`](youngin-fixture-request.md).

## License, redistribution, readers, and SDKs

Clarity is proprietary. The DataApex EULA describes it as licensed, not sold, and
restricts reverse engineering, recompilation, disassembly, program-file manipulation,
and unauthorized distribution except where applicable law expressly permits otherwise.
The contractual control-module SDK is not evidence of a public chromatogram-reader API.

No Apache-2.0-compatible YoungIn/Clarity `.prm` or Autochro reader was found. Autochro
license, SDK, and native specification remain unresolved. Do not bundle vendor
software, request access-control bypasses, or implement a binary reader from protected
program files. A lawful public specification, reader API, or reviewed clean-room basis
is required in addition to a fixture.

OpenChrom's current converter catalogue lists a DataApex FID `.prm` converter, but the
vendor converter service is proprietary and does not establish source availability,
redistribution rights, TCD or multi-detector support, or compatibility with the
observed YL-Clarity 9.0.1 candidates. It may be a separately licensed comparison oracle
only after its terms and exact fixture behavior are reviewed; it is not an Ordifile
dependency or implementation source. `chromConverter` previously delegated this path
to OpenChrom and is GPL >= 3, so neither project supplies an Apache-2.0 implementation
basis.

Any user-provided file remains `ACCEPT_EXTERNAL_ONLY` unless written redistribution
permission, attribution, and privacy review establish otherwise.

## Recommended adapter boundaries

Do not create an umbrella “YoungIn adapter.” Use format boundaries with optional
provenance profiles:

```text
format adapters
  clarity_text_export
  clarity_multidetector_chr
  aia_cdf
  dataapex_clarity_prm        # deferred; only after lawful native evidence
  autochro2_<verified_format> # deferred; exact generation required
  autochro3000_<verified_format>

provenance profile, only when file evidence supports it
  youngin_chromass / source software / model / detector
```

- `youngin_yl_clarity` is too broad. If OEM binary equivalence is later proven, use a
  format-level `dataapex_clarity_prm` reader and a separate YoungIn provenance profile.
- `youngin_autochro` is too broad. Split by verified generation and internal format.
- `youngin_export` should usually be a documented Clarity/Autochro export profile or
  schema preset. If an existing generic adapter represents it exactly, do not duplicate
  conversion logic.
- A `.raw` recovery reader, if lawful and useful, is a separate experimental adapter
  and is never automatic normal-run detection.

The current single-file `FormatAdapter` v1 can support a self-contained completed
chromatogram or export. If a native run requires a project directory and siblings, add
a future source-kind API without changing v1 single-file semantics.

## First proprietary adapter priority

| Gate | BSEE Agilent ChemStation `.ch` v181 | YL-Clarity completed `.prm` | Autochro native |
|---|---:|---:|---:|
| Normal complete fixture | Yes | 23 local completed-file candidates; native health and scientific layout unresolved | No |
| Lawful public source | Yes | No | No |
| Redistribution basis | BSEE public-information guidance | No | No |
| Privacy review | Passed | Local-only intake reviewed; identifying metadata candidates withheld from every public surface | Impossible without bytes |
| Format/version marker | Exact `181` bytes; version role backed by public readers, not a vendor byte specification | YL-Clarity 9.0.1 candidate markers observed in all 23 files; binary profile role unresolved | Unresolved |
| Signal extraction | 36,501 structural decoded records; scientific point count and time axis unresolved | Not verified | Not possible |
| Detector meaning | FID-scoped evidence | Ten filenames each are FID- and TCD-labelled; three are unclassified; native mapping unresolved | Unresolved |
| Paired official export | No | No | No |
| Lawful implementation route | Independently written Experimental implementation; no reader dependency/code copy | Owner-file observation and official documentation are available, but no public specification, source reader, or paired export oracle | No public specification/reader |
| Current decision | Experimental decoded-record adapter; Verified gate remains open | `BLOCKED_BY_PAIRED_EXPORT_AND_FORMAT_EVIDENCE` | `BLOCKED_BY_FIXTURE` |

YOUNG IN Chromass takes priority as soon as a normal completed fixture, exact CDS and
format version, FID/TCD channel semantics, same-run unbunched official export, reproducible
test permission, and lawful implementation basis are all established. Until then, BSEE
v181 remains the highest-priority implemented Experimental candidate.

## Minimum verification before “Verified”

- at least three normal runs across multiple samples and two acquisition timestamps;
- at least one FID run and, for a TCD claim, at least one TCD run;
- for a multi-channel claim, at least one FID+TCD run;
- one blank, standard, or control;
- one corrupt/incomplete example and one unsupported version;
- exact software version/build, instrument model, detector configuration and channel
  order;
- one same-run official export with full range and no bunching;
- point count, time start/end, sampling interval, channel count, detector label, peak
  count/RT/area/height when stored, acquisition time, sample name and duration comparison;
- redistribution or local-test authorization, privacy review, and dependency/license
  review.

FID evidence cannot become a TCD claim. ChroZen evidence cannot become YL6500 support.

## Unresolved questions

- Exact YL-Clarity `.prm` signatures and version compatibility.
- Native FID/TCD and multi-channel storage layout.
- ChroZen TQ GC/MS CDS and native format.
- AUTOCHRO-II versus Autochro-2 naming and format identity.
- Autochro-3000 lineage, native extensions, export, SDK, and EULA.
- Current status of YL6900.
- Whether an approved demonstration run can be redistributed.
- Whether YOUNG IN Chromass or DataApex can provide a public reader specification or API.

## Implementation recommendation

Do not implement native YoungIn support from the current intake. Keep Issue #2 open and
obtain privacy-clean, same-run `.chr`, `.txt`, or `.cdf` exports plus confirmed
detector/channel configuration for at least one of the 23 local `.prm` candidates.
Native `.prm` work begins only after the exact scientific and privacy gates above pass.

The README may say only “Under investigation: YOUNG IN Chromass GC data formats.” It
must not claim ChroZen, YL-Clarity, YL6500, FID, TCD, or Autochro compatibility.

YOUNG IN Chromass, ChroZen, YL-Clarity, YL6500, AUTOCHRO, and related product names
are trademarks or product names of their respective owners. Ordifile is an independent
open-source project and is not affiliated with, endorsed by, or sponsored by YOUNG IN
Chromass, YOUNGIN Scientific, YL Instruments, or DataApex.

## Source register

| Source | Owner | Date | URL | Claim supported |
|---|---|---:|---|---|
| Company history | YOUNGIN Chromass | Events dated by year | [Official page](https://kor.youngincm.com/page/?M2_IDX=7532&SCL_CODE=io7tjkrj) | Corporate lineage, name change, product chronology |
| Greeting | YOUNGIN Scientific | Current | [Official page](https://www.youngin.com/ko/about/greeting.asp) | YOUNGIN Chromass is listed as a separate affiliate |
| Corporate Profile | YOUNGIN Chromass | Current | [Official page](https://eng.youngincm.com/page/?M2_IDX=7418) | Current manufacturing and product families |
| New OEM cooperation | DataApex | 2008-04-14 | [Official announcement](https://www.dataapex.com/news/26748/new-oem-cooperation) | YL-Clarity is a Clarity OEM product |
| YL-Clarity Software, SNSW-202112-02 | YOUNGIN Chromass | 2021-12-16 | [Official service note](https://file.younglin.com/Service_Note/23_YCM_Service_Note_SNSW-202112-02.pdf) | YL-Clarity 8.1/8.5/8.6.1 and ChroZen/YL6500 configuration guidance |
| YL-Clarity Chromatography Data System | YOUNGIN Chromass | Current | [Official product page](https://eng.youngincm.com/goods/read.php?M2_IDX=18459&SC_SC2_IDX=1082&SP_CODE=19113EE3) | Current CDS scope, detector-signal and export claims |
| YOUNGIN Lab. Highlight, issue 78 | YOUNGIN Scientific | 2017-12 | [Official group newsletter](https://www.youngin.com/upload/file/vol.78.pdf) | `AUTOCHRO-II` instrument control, supported Windows generations, multiple-channel and auxiliary-signal acquisition, and ASCII/CDF interoperability claims current in 2017 |
| LC practical-analysis workshop registration | YOUNGIN Chromass | Publication date not shown; accessed 2026-08-16 | [Indexed official training form](https://kor.youngincm.com/form/add.php?M2_IDX=39745) | Search index lists YL-Clarity, Autochro-2, and Autochro-3000 as separate choices; current direct access is login-gated and native-format compatibility remains unresolved |
| ChroZen GC | YOUNGIN Chromass | Current | [Official product page](https://kor.youngincm.com/goods/read.php?M2_IDX=18351&SC_BOOKMARK=N&SC_SC1_IDX=351&SP_CODE=1911IA7H) | Current GC and detector configurations |
| YL6500 Control | DataApex | Updated 2026-08-14 | [Official module page](https://www.dataapex.com/product/controls-gc-yl6500?language=en) | Young Lin LAN driver and method storage |
| YL6500 GC discontinuation notice | YOUNGIN Chromass | 2023-11-02 | [Official notice](https://eng.youngincm.com/board/read.php?B_IDX=88384&M2_IDX=7443) | Discontinuation and ChroZen replacement |
| ChroZen GC/MS | YOUNGIN Chromass | Current | [Official product page](https://kor.youngincm.com/goods/read.php?M2_IDX=18353&SC_SC2_IDX=896&SP_CODE=1912SQGW) | Single-quadrupole scope and YL-Clarity integration |
| ChroZen TQ GC/MS System | YOUNGIN Chromass | Current; documented 2020-03 | [Official product page](https://kor.youngincm.com/goods/read.php?M2_IDX=18353&SC_ALL=N&SC_SC2_IDX=1732&SP_CODE=2003BTSG) | Tandem-MS functions; no CDS name on page |
| List of terms | DataApex | Current | [Official documentation](https://www.dataapex.com/documentation/Content/Help/100-list-of-terms/100.000-list-of-terms/100-list-of-terms.htm) | `.prm`, `.raw`, `.met`, `.seq`, `.cal`, `.prj`, `.sty` meanings |
| Recovering data after crash or freeze | DataApex | Current | [Official documentation](https://www.dataapex.com/documentation/Content/user-guide/troubleshooting/13-recovering-data-after-crash-freeze.htm) | `RUN.RAW` and `LAST.RAW` recovery semantics |
| Clarity Error Messages | DataApex | Current | [Official documentation](https://www.dataapex.com/documentation/Content/Help/090-troubleshooting/090.010-error-messages/090.010-error-messages.htm) | Acquisition raw-to-finalized-PRM flow |
| Export Chromatogram | DataApex | Current | [Official documentation](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.010-file/030.010-export-chromatogram.htm) | CDF/TXT/CHR/ASC behavior and AIA limitations |
| Export Data | DataApex | Current | [Official documentation](https://www.dataapex.com/documentation/Content/Help/020-instrument/020.050-setting/020.050-export-data.htm) | Result export, all/displayed range, and time-step bunching |
| Business opportunities | DataApex | Updated 2026-07-29 | [Official page](https://www.dataapex.com/business-opportunities) | OEM and contractual control-module SDK scope |
| Clarity EULA | DataApex | 2024-01-12 | [Official EULA](https://www.dataapex.com/downloads/26027/view) | Proprietary license and reverse-engineering/distribution boundary |
