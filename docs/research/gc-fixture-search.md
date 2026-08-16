# GC raw-fixture search

- Research and access dates: 2026-08-15 through 2026-08-17
- Purpose: identify a lawful, structurally complete, independently readable real GC
  fixture for a future proprietary adapter.
- Scope: government and institutional repositories, Zenodo, NIST Public Data
  Repository, existing parser fixtures, vendor documentation, and maintained reader
  implementations.

This research does **not** add a proprietary format to Ordifile v0.1.0. A format can
enter the support table only after an adapter, a reproducible fixture, capability
documentation, and success and failure tests all exist.

## What “normal raw” means here

A candidate must be a vendor-native acquisition file or a complete acquisition
directory, nonempty and structurally consistent, with a stable source and verified
digest. It should expose a real signal and enough acquisition metadata to distinguish
it from a peak-table export. Public access is not treated as permission to
redistribute. Licensing, attribution, privacy, archive safety, and reader scope are
separate gates.

Preferred acquisitions are standards, controls, blanks, or ordinary research samples.
Clinical or case data, files containing personal identifiers, damaged examples, and
partial exports rank lower or are rejected.

## Candidate comparison

“Inspected” means that the artifact, its central directory, or a selected member was
opened during this review. “Claimed” is only the repository description. Sizes are
archive sizes unless otherwise stated.

| Candidate | Publisher / persistent ID | Instrument, vendor, detector | Claimed / inspected format | Native raw | Size / smallest useful run | Integrity and independent reader |
|---|---|---|---|---|---|---|
| [YOUNG IN Chromass Track C](youngin-chromass-format-investigation.md) | YOUNG IN Chromass and DataApex official material | ChroZen GC and legacy YL-series; FID/TCD priority | YL-Clarity completed `.prm` candidate, temporary/recovery `.raw`, Autochro native formats, and documented exports | Unresolved for YL-Clarity/Autochro | No public native fixture found | YL-Clarity OEM relationship and general Clarity file lifecycle verified; no YoungIn-produced complete file, paired export, or independent reader |
| [BSEE Side Wall Core Trim Extract GC Data](https://www.bsee.gov/stats-facts/ocs-regions/alaska/arctic-drilling/arctic-exploration-burger-j-well-data-2015/side-wall-core-trim-extract-gc-data) | BSEE; official data page | Agilent ChemStation; FID | `.CH` / internal version 181 single-channel file | Yes | 298,146 B / same | SHA-256 fixed below; ChromStream 0.2.0 produced 36,501 candidate x/y values; rainbow 1.4.0 exposed a time/signal length defect |
| [chromConverterExtraTests `FS19_214.gcd`](https://github.com/ethanbass/chromConverterExtraTests/blob/f9cb88d90f6be00e3c0f16fa3e2bb7734a5da66b/README.md) | chromConverterExtraTests; pinned fixture register | Shimadzu LabSolutions 5.82, GC-2014; FID | CFB `.GCD`, single `Ch1`/`SFID1`, plus same-run ASCII reference | Yes | 1,433,600 B / same | Exact SHA-256; independent decoder and paired ASCII agree on 66,255-point time/signal; file-specific CC0, but embedded personal/local text requires controlled external handling |
| [Dryad ant GC-MS chromatograms](https://doi.org/10.5061/dryad.8gtht76s4) | Csata et al. / Dryad | Shimadzu GCMSsolution; GC-MS | Ten CFB `.QGD` files | Yes | 408.17 MB set / 39,964,672 B selected file | CC0; exact selected SHA-256; 16,800-point RT/TIC arrays and every scan intensity sum independently verified; embedded paths require controlled external handling |
| [Cambridge Apollo chromatography corpus](https://doi.org/10.17863/CAM.108306) | University of Cambridge; DOI dataset | Shimadzu LabSolutions 5.71 SP2/5.86; BID | 320 `.GCD`, 353 text, 306 exact pairs | Yes | Corpus-level | CC BY 4.0; independently corroborates GCD stream/time/signal equations but not the initial FID/5.82 profile |
| [IODP Expedition 384 gas safety report](https://doi.org/10.5281/zenodo.15122350) | IODP / Zenodo 15122350 | Agilent ChemStation; FID and TCD | Raw and method ZIPs / v179 `.ch` plus complete method files | Yes | 827,059 B / 104,074 B paired run+method archives | Zenodo MD5 and local SHA-256 verified; Entab main read 4,680 points per channel; rainbow agreed on signals but not time origin or TCD classification |
| [Rapid GC-MS methods](https://doi.org/10.18434/mds2-2862) | NIST, ARK mds2-2862 | Agilent 5977 GC-MS | Native `.D` / `data.ms`, scan files, XML and exported TIC | Yes | 24,934,205 B / 4,188,635 B run | Provider SHA-256 matched; rainbow 1.4.0 read all 26 runs; selected run 286 scans |
| [NIST/NIJ CADS](https://doi.org/10.18434/mds2-3628) | NIST, ARK mds2-3628 | GC-FID and GC-MS, multiple instruments | “Raw & processed” / FID TXT and MS mzXML | No for proprietary FID/MS | about 21 GB / member-level only | Official ZIP64 inventories inspected; FID members are exported `Time (min)` / `Value (pA)` tables |
| [GC-FID-ALS volatile liquids](https://doi.org/10.5281/zenodo.14886857) | University of Twente / Zenodo | Agilent 7820A, EZChrom; FID | `.7z` / OLE `.dat`, sequences and methods | Yes | 283,847,706 B / about 1 MiB `.dat` | Zenodo MD5 matched; 3,708 entries inventoried; selected `.dat` identified as EZChrom compound document |
| [GC-FID-TCD headspace gas samples](https://doi.org/10.5281/zenodo.14886808) | University of Twente / Zenodo | Chromeleon; FID and TCD | ZIP / `.cmbx` container with paired channel `.raw` | Yes | 1,206,933,171 B / 10,300,242 B smallest CMBX | ZIP central directory and smallest CMBX inspected; full outer MD5 not independently recomputed |
| [Paper-wasp GC-FID chromatograms](https://doi.org/10.5061/dryad.wpzgmsbr8) | Cornell University / Dryad mirror Zenodo 7378368 | Shimadzu GC-2014, LabSolutions; FID | “Raw” / documented ASCII export from `.gcd` | No | 159,967,343 B set / 1,320,305 B sample | CC0 record; complete metadata, peaks, compounds and signal; embedded local paths require a documented derived fixture |
| [Grob Mix GC-FID replicates](https://doi.org/10.5281/zenodo.19946728) | University of Duisburg-Essen / Zenodo | Agilent 6890N; FID | Raw and integration outputs / v179 `.ch` plus CSV | Yes | 481,259,756 B / 438,136 B `.ch` plus siblings | Central directory and representative v179 member CRC inspected; useful raw/export pairing, but attribution and privacy keep it external |
| [OpenLab GC-FID `.dx`](https://doi.org/10.5281/zenodo.14316687) | Zenodo | OpenLab; FID | `.dx` / two FID channels | Yes | record artifact / selected file | rainbow 1.4.0 read two 34,000-point channels; embedded absolute path found |
| [Nieto GC-FID](https://doi.org/10.5281/zenodo.12220242) | CONICET La Plata / Zenodo | PerkinElmer Clarus 500; FID | `.raw` / `PENX` proprietary container | Yes | 13,464,217 B set / 83,392 B file | Provider MD5s matched; instrument and detector strings inspected; local paths and names present |
| [GC-MS raw data for MLOD](https://doi.org/10.5281/zenodo.8193580) | Memorial Sloan Kettering Cancer Center / Zenodo | Agilent GC-MS | ZIP / 40 `.D` directories with `data.ms` | Yes | 483,320,760 B / run directory | Archive structure inspected; CC BY and size favor external-only use |
| [Raw GC/MS data](https://doi.org/10.5281/zenodo.14720186) | University of Bologna / Zenodo | Agilent 7890/5975; MS | ZIP / 19 `.D`, `.MS`, methods | Yes | 40,479,147 B / run directory | Archive structure and method identity inspected |
| [GC-MS raw files dataset](https://doi.org/10.5281/zenodo.15428029) | University of Florida / Zenodo | Shimadzu GCMSsolution; MS | ZIP / OLE `.qgd` | Yes | 61,373,839 B / `.qgd` file | Representative file magic and product strings inspected; user metadata present |
| [GC-MS tutorial data](https://doi.org/10.5281/zenodo.10604540) | Zenodo | nominal-mass GC-MS | CDF / AIA/ANDI netCDF export | No | 311,937,750 B | netCDF structure inspected; upstream redistribution chain unresolved |
| [Thermo/Finnigan GC-MS RAW](https://doi.org/10.5281/zenodo.10798153) | Zenodo | Thermo/Finnigan Xcalibur; MS | `.RAW` / proprietary Thermo RAW | Yes | selected file 33,309,998 B | Zenodo MD5 matched and header inspected; reader and redistribution boundary remain unresolved |
| [GC signal workbook](https://doi.org/10.5281/zenodo.8388636) | Karlsruhe Institute of Technology / Zenodo | Vendor unresolved; GC signal | “Raw” / XLSX sheets with retention time and counts | No | 3,988,923 B | Workbook inspected; useful external export corpus, not proprietary raw |
| [Large Agilent GC-MS collection](https://doi.org/10.5281/zenodo.4942519) | Zenodo | Agilent MassHunter; MS | `.D.tar.gz` / `data.ms` and scan files | Yes | about 6.1 GB collection / selected run archive | Selected archive MD5 matched; rainbow read a 13,968 x 466 signal matrix |
| [Pyrogram/library data](https://doi.org/10.5281/zenodo.4998084) | Zenodo | Library data | `.elu`, MSP / library and pyrogram output | No | record artifact | Not a native acquisition fixture |

### Legal, privacy, and adoption decisions

| Candidate | License / redistribution | Attribution | Personal or machine data | Parser candidate and maintenance | Apache-2.0 reuse | Decision and reason |
|---|---|---|---|---|---|---|
| YOUNG IN Chromass / YL-Clarity / Autochro | Proprietary CDS terms; no native fixture redistribution permission or public reader specification found | Product names only for factual compatibility research; no affiliation claim | Impossible to review without bytes | No public `.prm` or Autochro reader found; DataApex control SDK is not a public chromatogram-reader SDK | No implementation basis established | `BLOCKED_BY_FIXTURE`; required priority candidate, but not an Ordifile-supported format |
| BSEE v181 `.CH` | BSEE public-information terms permit copying and distribution with source acknowledgement | Institution, exact page, unchanged-file statement, access date | No email, user-profile path, hostname or absolute path found | ChromStream 0.2.0 is recent; rainbow 1.4.0 is recent but fails point alignment; Entab does not read v181 | Independently written implementation; no reader code or dependency | `ACCEPT_REDISTRIBUTABLE`; external fixture backs a narrow Experimental decoded-record adapter |
| `FS19_214.gcd` | Source README assigns file-specific CC0 1.0 | Source repository, exact commit and unchanged-file statement | Contributor and machine-local text are embedded | GPL reader is comparison-only; independent decoder plus paired LabSolutions ASCII validate values | `olefile` is permissive; Shimadzu semantics are independently implemented | `ACCEPT_CONTROLLED_CI`; exact Experimental LabSolutions 5.82 FID profile only, never committed/logged/uploaded |
| `B4NF.7_C23.qgd` | Dryad dataset and file API declare CC0 1.0 | Dataset DOI, authors, original file record, and unchanged pinned mirror | Absolute data/method/batch paths and user-originated text are embedded | GPL readers are comparison-only; independent decoder plus exact scan-to-TIC equations validate Stage A | Existing permissive `olefile`; QGD semantics independently implemented | `ACCEPT_CONTROLLED_CI`; exact Experimental `4.00` TIC profile only, never committed/logged/uploaded |
| Cambridge LabSolutions GCD corpus | CC BY 4.0 | Dataset/DOI attribution and change status required | File-level review required before any reuse | Independent corpus comparison performed from external files | No code reused | `ACCEPT_EXTERNAL_ONLY`; structural corroboration only because detector/version profiles differ |
| IODP v179 FID/TCD | CC BY 4.0; lawful external research use, but attribution and embedded third-party rights remain separate | Full record attribution required | Method history contains names, machine identifiers and Windows paths | Entab 0.3.3/main is MIT but has packaging and CLI defects; rainbow is LGPL-3.0 and misclassifies TCD | Entab code license compatible, packaging/semantic scope not ready | `ACCEPT_EXTERNAL_ONLY`; strong signal evidence, unresolved time/detector semantics |
| NIST mds2-2862 | NIST Open License; redistribution with attribution and change notice | NIST record and derived-file notice | Whole `.D` includes paths and instrument identifiers | rainbow LGPL-3.0 and Entab MIT both read `data.ms` | Direct dependency deferred | Whole run `ACCEPT_EXTERNAL_ONLY`; isolated `data.ms` only conditionally redistributable after privacy review |
| NIST CADS | NIST Open License | NIST record and extraction/change notice | Member-specific review still required | Open-format readers available | Compatible for derived test data | `ACCEPT_EXTERNAL_ONLY` as a generic TXT/mzXML corpus; `REJECT` as proprietary evidence |
| Zenodo CC BY native candidates | CC BY 4.0; public access is not a waiver of attribution or third-party rights | Record-specific attribution required | Multiple archives contain user names, machine IDs, or absolute paths | Reader coverage varies; several formats lack maintained portable readers | Case-by-case; vendor runtimes may be incompatible | Mostly `ACCEPT_EXTERNAL_ONLY` or `RESEARCH_ONLY`; not bundled |
| Dryad/Zenodo 7378368 export | CC0 | Source citation recommended | Local paths and names present in original | Text format is documented; no proprietary reader needed | Yes for a documented derived fixture | Conditional `ACCEPT_REDISTRIBUTABLE` only after explicit redaction/change manifest |

## Downloaded and independently verified fixtures

### Shimadzu LabSolutions 5.82 GC-FID GCD

- Source register: [chromConverterExtraTests README](https://github.com/ethanbass/chromConverterExtraTests/blob/f9cb88d90f6be00e3c0f16fa3e2bb7734a5da66b/README.md)
- Artifact: `FS19_214.gcd`
- Size: 1,433,600 bytes
- SHA-256: `d670806265f994507ac99fc676f17098bf9b9d1c362c98df1cb31154ac7a5180`
- License: file-specific CC0 declaration in the pinned source register
- Privacy: embedded personal and local-machine text; external controlled-CI only
- Result: 66,255 finite `uV` samples, 40 ms interval, 20 ms initial delay, and
  DLT-based minute axis match the same-run LabSolutions ASCII reference after its
  documented rounding.
- Scope: Experimental LabSolutions 5.82 / GC-2014 / one `Ch1` / `SFID1` only.

The native and ASCII files are not committed. The ASCII has no separate file-level
license and is used only to derive non-reversible numeric summaries and digests.

### Shimadzu GCMSsolution QGD `4.00` TIC

- Source: [Dryad DOI 10.5061/dryad.8gtht76s4](https://doi.org/10.5061/dryad.8gtht76s4)
- Artifact: `B4NF.7_C23.qgd`
- Size: 39,964,672 bytes
- SHA-256: `64b2faab81c0ad10bc36c57b23ed770751dbe5253f48d2a13b8b15df1de23f5d`
- License: CC0 1.0 in the original dataset and file records
- Privacy: absolute local paths and source text; external controlled-CI only
- Result: exact `4.00` CFB profile, 16,800 retention-time/TIC points, 200 ms
  intervals, whole-array digests, and all scan intensity sums equal to native TIC.
- Scope: Experimental TIC with unknown physical unit. MS1 blocks are structurally
  validated but not exposed as scientific spectra.

The file is not committed or uploaded as an artifact. GPL readers are behavior
oracles only; the runtime implementation uses independent byte facts and the existing
permissive CFB dependency.

### BSEE Agilent ChemStation GC-FID v181

- Source page: [Side Wall Core Trim Extract GC Data Files](https://www.bsee.gov/stats-facts/ocs-regions/alaska/arctic-drilling/arctic-exploration-burger-j-well-data-2015/side-wall-core-trim-extract-gc-data)
- Direct artifact: [FID1A.CH](https://www.bsee.gov/sites/bsee.gov/files/Alaska%20Region/Burger%20J%20Well%20Data/41_GC_EXTGC_Data_Files_FPC6188_Shell%20MC_HH-77445%209.30.15/G6151510.D/fid1a.ch)
- Downloaded: 2026-08-16 into the ignored `.external-fixtures/gc/` cache
- Size: 298,146 bytes
- SHA-256: `9abeb86b09d54c10e81f46648804acc0319b6e1d014cee54034eae91331f97ef`
- HTTP last-modified: 2017-10-30 17:06:23 GMT
- Internal format marker: `181`
- Acquisition: coded ordinary research sample, 2015-09-29 13:35:45; timezone absent
- Embedded method: `G02.M`

ChromStream 0.2.0 produced 36,501 candidate time values and 36,501 candidate signal
values. The
candidate time range was -0.0015375 through 121.6618 minutes and the candidate signal
range was 435.9739583333333 through 30,809.119791666664. rainbow 1.4.0 produced the
same 36,501 candidate signal values but only 36,500 candidate time values. That
mismatch disqualifies rainbow
as the production v181 reader. A deeper evidence gate also found that the inclusive
time-axis formula differs slightly from the stored sampling-ratio candidate, and that
the slope/intercept transformation lacks a paired official export. The encoded unit is
not trustworthy. These gaps block a retention-time or physically scaled scientific
signal claim, but do not block a structural decoded-record adapter. Ordifile therefore
retains all 36,501 records by ordinal and raw integer without applying time, scaling,
or unit semantics. Exact findings are in
[`agilent-chemstation-ch-v181-investigation.md`](agilent-chemstation-ch-v181-investigation.md).

The direct file is a native signal channel, not proof that Ordifile can read a whole
ChemStation `.D` directory, integration results, or other `.ch` versions. It is not
committed to this repository despite the redistribution finding.

### IODP Expedition 384 FID/TCD v179

- Record: [Zenodo 15122350](https://zenodo.org/records/15122350)
- Outer artifact: `NGAFID.zip`, 827,059 bytes
- Zenodo MD5: `d03116b61b91bf4ef8d23ecaefb8bba7`
- Local SHA-256: `81a03e9f81b41d84a1786553d4eab137b397cf4cc77a8fd27c726628b7054c91`
- Outer inventory: 22 regular files, 847,380 uncompressed bytes, no encrypted,
  linked, absolute, or parent-traversing member
- Selected raw run archive: `supplementary_material/raw_data_files/384-NGAFID-56334741-dataFile_118663011.zip`
- Raw archive: 73,217 bytes, 23 files, SHA-256
  `56462efe3c387eff99107d54e23710fbf2f19a5de2258f50814bddd0f7273646`
- Paired method archive: 30,857 bytes, 9 files, SHA-256
  `799f6e0de0fbd5afc627bbc2e7b58013fd99c1b0dbf19532275fccb113ab702f`
- Complete selected raw+method tree digest: `d1065a9c9a176bcb89cba4a9a266d93859faaf03c2e8b082c410a16f2b715906`

Entab main at commit `e442ba72bd452c2ac2a1d0c98af55bb7316c2f22` read
4,680 values from both `FID1A.ch` and `TCD2B.ch`. It reported `pA` and `25 µV`,
acquisition time 2020-07-27 23:59:50, and method `384_NGA2.M`. rainbow 1.4.0
agreed bit-for-bit on intensity but shifted the time axis by one sampling interval and
classified TCD incorrectly. The archive is therefore excellent external evidence, but
not yet a support oracle.

## Reader and dependency assessment

| Reader | License and observed state | Decision |
|---|---|---|
| [Entab](https://github.com/bovee/entab), package 0.3.3 | MIT; latest parser read v179 FID/TCD, but published wheels are limited and the current CLI required a local CLI-only compatibility patch | Research oracle only; no v0.1 dependency |
| [rainbow](https://github.com/evanyeyeye/rainbow), 1.4.0 | LGPL-3.0; maintained, but v181 time/signal lengths differ and v179 TCD detection is wrong | Research comparison only; no production adoption |
| [ChromStream](https://github.com/MyonicS/ChromStream), 0.2.0 | MIT-labelled and reads v181 consistently; says its parser is adapted from an upstream MIT project whose notice handling must be resolved | Research oracle only pending provenance review |
| [chemplexity/chromatography](https://github.com/chemplexity/chromatography) | MIT MATLAB reference implementation for several `.ch` generations | Byte-structure reference only; any use requires preserved MIT notice and independent review |
| [ProteoWizard](https://github.com/ProteoWizard/pwiz) / OpenChrom | Open cores have separate vendor-runtime or converter boundaries | Do not bundle or invoke proprietary components |

## First proprietary adapter decision

The BSEE **Agilent ChemStation GC-FID `.ch` internal version 181** file remains the
highest-priority proprietary candidate. The 2026-08-16 revised gate is **Experimental
GO** for structural decoded records and **NO-GO** for Verified scientific signal
support. The runtime adapter and README row use those exact limitations.

YOUNG IN Chromass was included as a mandatory priority candidate. It does not rank
first today because no normal completed YL-Clarity or Autochro fixture, paired official
export, exact producer version, redistribution basis, or independent reader was found.
It remains `BLOCKED_BY_FIXTURE`, not rejected. It should be reconsidered immediately
when the gate in
[`youngin-chromass-format-investigation.md`](youngin-chromass-format-investigation.md)
is satisfied.

Why:

- the file is small, stable, public, and has clear copying guidance;
- it is a native FID signal rather than an exported table;
- two independent readers exposed both the reliable signal result and a concrete
  off-by-one hazard;
- its exact version marker lets detection be bounded rather than extension-only;
- it keeps the first vertical slice to one detector and one byte-level generation.

The independently written decoder reproduces the current fixture and public-reader signal output, but the
only ordinary short record has value zero, so its status as a scientific sample or
terminal record and the nonzero second-delta recurrence are not independently
exercised. The exact scientific point count, retention-time construction, physical
meaning of the slope/intercept transformation, and signal unit are also not verified
against an official export or specification. The Experimental adapter therefore uses
ordinal x and raw integer y, retains the ambiguous final record, and records these
unknowns. It verifies version 181, bounded offsets, exact EOF, arithmetic limits, and
equal x/y lengths while returning structured errors for malformed or unsupported
inputs. It does not claim TCD, v179, peak tables, full `.D` directories, write support,
or all Agilent data.

## Confirmed facts, inferences, and unresolved questions

Confirmed facts are the sizes, digests, archive inventories, licenses shown on the
opened records, byte markers, and reader outputs above. The recommendation that BSEE
v181 is the smallest practical first slice is an engineering inference.

Unresolved items:

- no official public byte-level Agilent `.ch` specification was found;
- the v181 retention-time construction, physical signal scaling, and unit are
  unresolved;
- no paired full-resolution ChemStation CSV or AIA/ANDI export exists for the selected
  run;
- jurisdiction-specific interoperability and reverse-engineering questions are not a
  legal clearance;
- v179 readers disagree on time origin and TCD identification;
- CC BY uploaders' rights over every embedded vendor file were not independently
  established;
- no complete, small, privacy-clean TCD fixture is approved for bundling.

These gaps block both implementation and support claims for the v181 adapter, not the
generic-format v0.1.0 release.
