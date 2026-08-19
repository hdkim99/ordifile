# Multi-vendor result expansion: Wave 1

- Research and access date: 2026-08-19
- Scope: one-run GC/CDS result and peak-table exports with explicit retention time
  and peak area
- Manufacturers researched: Thermo Fisher Scientific, PerkinElmer, SCION
  Instruments, LECO, and Bruker
- Decision: the exact LECO ChromaTOF 4.72 GCxGC profile is Experimental after the
  accepted secondary-retention ADR and full external comparison; all Wave-1 1D
  profiles remain blocked or evidence candidates

This matrix records exact software/export profiles rather than claiming support for a
manufacturer. A profile enters the public format list only after a lawful actual fixture,
bounded detection, explicit finite RT and area mapping, complete source-row comparison,
workbook regression, and privacy/license review all pass.

## Status vocabulary

- `RESEARCH_ONLY`: official product or export evidence exists, but the exact profile is
  not ready for intake.
- `BLOCKED_FIXTURE`: export capability is documented, but no lawful actual fixture with
  a stable grammar is available.
- `EVIDENCE_CANDIDATE`: a potentially lawful artifact exists but its table, units,
  privacy, or profile identity still requires bounded intake.
- `IMPLEMENTATION_GO`: one exact profile has passed fixture, grammar, scientific,
  privacy, and legal intake and may receive an adapter in a separate PR.
- `EXTERNAL_ORACLE_ONLY`: observed bytes may inform research but their file-specific
  redistribution permission is unresolved.
- `ADR_REQUIRED`: lawful actual evidence exists, but the canonical model cannot retain
  its scientific coordinates without an explicit architecture decision.
- `EXPERIMENTAL_GO`: an exact adapter and all evidence, scientific, privacy, and legal
  gates pass. The exact LECO ChromaTOF 4.72.0.0 GCxGC profile has this status.

## Capability matrix

| Vendor | Software / exact profile | Export | Fixture and license | RT | Area | Height | Detector / channel | Detection boundary | Decision |
|---|---|---|---|---|---|---|---|---|---|
| Thermo Fisher Scientific | Chromeleon 7.3, one-injection Result Text from one fixed report template | ASCII `.txt`; report-template fields and layout are configurable | No lawful exact GC Result Text fixture found | Official report variable: Retention Time, min | Official report variable: Signal x min | Official report variable: Signal | Official report variables exist, but exact exported labels are template-dependent | Must bind an exact report template, channel, headers, delimiter, encoding, and one-run grammar; generic Chromeleon TXT detection is prohibited | `BLOCKED_FIXTURE` |
| PerkinElmer | SimplicityChrom, one-run Data Review Result export | Export is shown by the official product material; exact container and text grammar unresolved | No lawful exact Result fixture found | Unresolved | Unresolved | Unresolved | Unresolved | Requires exact producer/profile markers and a bounded export grammar | `BLOCKED_FIXTURE` |
| PerkinElmer | TotalChrom Navigator 6.3.2.0646, Clarus 500 GC-FID dataset PDF evidence candidate; exact template/profile unresolved | PDF report | Dryad CC0 calibration-standard candidate; exact selected PDF is 39,418 bytes with two finite rows, but contains privacy-bearing metadata and is not a machine-readable Result export fixture | `Time [min]`, min | `Area [uV*sec]` | `Height [uV]` | Channel `A` observed; dataset supplies instrument/software provenance | PDF supplies grammar evidence only; no PDF parser is authorized, and an exact machine-readable export is still required | `EVIDENCE_CANDIDATE` |
| PerkinElmer | Chromera, exact Result export profile unresolved | Unresolved | No lawful exact Result fixture found | Unresolved | Unresolved | Unresolved | Unresolved | Must remain separate from SimplicityChrom and TotalChrom | `RESEARCH_ONLY` |
| SCION Instruments | CompassCDS, exact Print Manager Result export profile unresolved | Official material lists ASCII, Excel, and AIA conversion; encrypted `.DATA` is not an export target for this work | No lawful exact ASCII/Excel Result fixture found | Result semantics documented generally; exact field/unit unresolved | Result semantics documented generally; exact field/unit unresolved | Unresolved | Unresolved | Requires exact exported headers, delimiter/worksheet grammar, encoding, software marker, and one-run boundary | `BLOCKED_FIXTURE` |
| LECO | Published ChromaTOF 4.50.8.0 one-dimensional peak-list grammar; two observed MSDK 1D CSV variants have no embedded version marker | Quoted comma CSV with 16- and 17-column observed variants | Two 594-row MSDK resources are externally observable, but their README identifies third-party provenance without a fixture-specific redistribution grant; neither is fetched by CI or committed | `R.T. (s)`, seconds | `Area`, unit unresolved | `Height`, unit unresolved | Not established by the observed tables | The exact 1D header families can be studied, but implementation cannot claim a lawful test fixture or assign the MSDK bytes to version 4.50.8.0 | `EXTERNAL_ORACLE_ONLY` |
| LECO | ChromaTOF 4.72.0.0 GCxGC model-mixture result text | Tab-delimited, 7-bit ASCII-compatible, CRLF; exact RT1/RT2/Area/Height/Spectra profile | Dryad CC0 actual fixture; non-human model-mixture subset only; 100 rows, 20,040 bytes, SHA-256 `59f336c3e4bb91df32c5111d39a7fa76759a72242a4bd5d873eb623b020af6dd` | Explicit first- and second-dimension retention times, seconds | Explicit, documented arbitrary units (`AU`) | Explicit, documented arbitrary units (`AU`) | Not established by the selected table | Exact rare-header ownership, bounded nine-column parser, full-row external comparison, SHA-derived source identity, and separate 2D order matrix | `EXPERIMENTAL_GO` |
| LECO | ChromaTOF Sync / Sync 2D combined peak table | Combined sample-set peak table | No exact lawful export fixture with a stable table grammar found | Present as an application concept; exact field unresolved | Relative quantitation is described; exact field/unit unresolved | Unresolved | Unresolved | Multi-sample combined tables do not fit the current one-source/one-sample adapter contract | `RESEARCH_ONLY` |
| Bruker | Current EVOQ GC-TQ / TASQ exact Result export profile unresolved | Official material establishes a current sample-to-report software suite; exact export container and grammar unresolved | No lawful exact current Bruker GC-MS Result fixture found | Unresolved | Unresolved | Unresolved | Unresolved | Requires a current producer/software marker and exact fixture; legacy Varian/Bruker GC or GC-SQ must not be duplicated as current Bruker support | `BLOCKED_FIXTURE` |

## Evidence details

### Thermo Fisher Scientific / Chromeleon

The official [Chromeleon 7.3 Functional Specifications](https://docs.thermofisher.com/api/khub/documents/fcN7nLsBEBuVy1IExPb1rw/content)
define ASCII Result Text export and report variables for retention time, area, height,
peak number/name, peak start/stop, chromatogram channel, detector, and signal unit. The
[Chromeleon 7.3.2 Quick Start Guide](https://docs.thermofisher.com/r/Chromeleon-7.3.2-Quick-Start-Guide/1561513995v2)
shows that an export can cover an injection, sequence, or multiple sequences and that
the report template and channel are selected at export time. Those choices prevent a
generic `Chromeleon TXT` claim: Ordifile needs one actual one-injection export from one
fixed template before it can define headers, delimiter, encoding, units, or cardinality.

### PerkinElmer

The official [SimplicityChrom product page](https://www.perkinelmer.com/category/simplicitychrom-cds)
and vendor-hosted Data Review export material establish result generation and export,
but not a stable RT/area file grammar. SimplicityChrom, TotalChrom, and Chromera remain
separate profile families.

The [Dryad TotalChrom dataset](https://datadryad.org/dataset/doi%3A10.25338/B8C35T)
is a lawful CC0 evidence candidate for a TotalChrom Navigator 6.3.2.0646 / Clarus 500
GC-FID PDF report. The inspected calibration-standard candidate has two finite peak
rows with `Time [min]`, `Area [uV*sec]`, and `Height [uV]`, but also contains
privacy-bearing metadata. It remains external-only grammar evidence. This cycle does
not add a PDF parser; an exact lawful machine-readable export is still required.

### SCION Instruments

The official [CompassCDS product page](https://scioninstruments.com/products/compass-cds/)
and [2022 brochure](https://scioninstruments.com/wp-content/uploads/2020/11/Compass-CDS_Brochure_2022_Stg06.pdf)
describe processing/reporting, an encrypted all-in-one `.DATA` container, and Print
Manager conversion of chromatogram results to ASCII, Excel, and AIA. Ordifile will not
bypass `.DATA` encryption. The export grammar remains blocked until a lawful actual
ASCII or Excel Result fixture establishes exact headers, units, and profile identity.

### LECO

The official [ChromaTOF-GC legacy page](https://www.leco.com/documents/chromatof-gc-legacy-version/)
confirms automatic CSV export. The peer-reviewed
[Maui-VIA profile description](https://pmc.ncbi.nlm.nih.gov/articles/PMC4301187/)
records a ChromaTOF 4.50.8.0 one-dimensional CSV peak-list grammar with `Name`,
`Retention Index`, `Area`, `R.T. (s)`, signal-to-noise, and integration boundaries.

The pinned [MSDK repository](https://github.com/msdk/msdk/tree/a1dbc365194c6e054e6a19a207c26186be7cdb92/msdk-io-chromatof/src/test/resources)
contains two original 1D ChromaTOF report variants with 16 and 17 columns respectively;
each has 594 rows with explicit finite RT, area, and height. Its top-level
LGPL-2.1-only OR EPL-1.0 code license does not supply an unambiguous file-specific
grant for the externally provided reports. They are therefore external research oracles
only. No fixture bytes or implementation code are copied.

The lawful [Dryad ChromaTOF 4.72 dataset](https://datadryad.org/dataset/doi%3A10.5061/dryad.k98sf7m8m)
establishes a real tab-delimited GCxGC profile with RT1, RT2, area, and height. The
exact non-human model-mixture member passes the full 100-row external comparison and
supports the narrowly bounded Experimental adapter. Its source archive and unrelated
human-derived subsets are excluded from Git, CI extraction, packages, workbooks, and
artifacts. ChromaTOF Sync and Sync 2D are separately
described by the official [Sync product page](https://www.leco.com/products/chromatof-sync/)
and must not be conflated with the legacy single-run CSV profile.

### Bruker and SCION lineage

Bruker's official [2014 divestiture notice](https://ir.bruker.com/press-releases/press-release-details/2014/Bruker-Completes-Divestiture-of-its-Gas-Chromatography-Product-Lines/default.aspx/1000/)
states that its GC and GC single-quadrupole product lines moved to the business that
became the current SCION lineage. Current Bruker GC-TQ and Compass software require
their own producer/profile fixture. Legacy Varian/Bruker exports must not become both
a SCION adapter and a broad Bruker adapter without exact producer evidence.

## Implementation gate

The next adapter PR may start only when one exact profile satisfies all of the following:

1. an actual vendor-generated fixture has explicit lawful use and redistribution terms;
2. manufacturer, software/version boundary, and export profile are evidenced;
3. one input represents exactly one sample/run, or a separately accepted multi-sample
   architecture exists;
4. RT and area are explicit, finite source fields rather than inferred quantities;
5. RT and area units are preserved when stated and remain unresolved when absent;
6. a bounded signature distinguishes the profile from generic CSV/TXT/XLSX/PDF;
7. every source row is compared with canonical `PeakRecord` and workbook output;
8. malformed family members remain structured vendor failures instead of falling
   through to a generic adapter;
9. privacy-bearing values are excluded from public fixtures, logs, workbooks, and CI
   artifacts; and
10. no proprietary vendor code, DLL, executable, or protected-format bypass is used.

The current implementation order is therefore evidence-driven, not the manufacturer
list order. The lawful ChromaTOF 4.72 GCxGC dual-retention profile is first because its
exact fixture, grammar, scientific values, privacy review, and canonical architecture
are all established. The TotalChrom PDF remains intake evidence only; this cycle does
not implement a PDF parser.

## Explicit non-decisions

- The LECO support claim is limited to the exact adapter and selected 100-row
  non-human external comparison; it is not a broad LECO or ChromaTOF claim.
- No broad manufacturer support claim is made.
- No 2D retention coordinate is discarded or silently mapped to metadata/channel.
- No MSDK or other reference implementation code is copied or translated.
- No raw binary reverse engineering is required before a lawful Result profile.
- No version number, release, tag, or public standalone artifact is authorized.
