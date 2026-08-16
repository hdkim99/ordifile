# Format feasibility

- Research date: 2026-08-15
- Scope: GC acquisition containers versus exports, openly analyzable interchange
  formats, and the first proprietary GC candidate.
- Source details: exact titles, publishers or owners, source types, update dates when
  available, URLs, and access date are consolidated in
  [`source-register.md`](source-register.md).

## Raw acquisition data and exported results

Agilent's official articles distinguish [chromatogram signal CSV export](https://community.agilent.com/knowledge/chromatography-software-portal/kmp/chromatography-software-articles/kp331.export-chromatogram-signal-as-csv-with-openlab-cds-version-2-4-or-higher),
[peak area/retention-time Excel reports](https://community.agilent.com/knowledge/chromatography-software-portal/kmp/chromatography-software-articles/kp908.reporting-peak-area-and-retention-time-of-sequence-in-excel-format-with-openlab-cds),
and [AIA file export](https://community.agilent.com/knowledge/chromatography-software-portal/kmp/chromatography-software-articles/kp1566.how-to-export-aia-files-in-openlab-cds).
These exports do not have equivalent semantics:

- A signal export can preserve sampled axes while omitting method and provenance.
- A peak table contains processed integration/assignment results and cannot recreate
  the source signal.
- AIA CDF can contain raw or processed data depending on the export procedure.

Therefore adapters declare `metadata`, `peaks`, and `signals` separately. Ordifile
does not identify compounds from retention time alone.

## v0.1 feasibility

| Format | Evidence | Decision |
|---|---|---|
| CSV/TSV/semicolon TXT | Public text structures, but no universal instrument schema | Support only documented headers and synthetic fixtures. |
| XLSX/OOXML | Public container, but vendor sheets and columns have no universal semantics | Support an explicit generic peak/signal schema and deterministic sheet selection. |
| AIA/ANDI netCDF CDF | [netCDF format specification](https://docs.unidata.ucar.edu/netcdf-c/current/file_format_specifications.html); ASTM catalog identifies a chromatography interchange standard, but the paid standard text was not used | Future open-format candidate; defer from v0.1. |
| mzML | Public MS schema maintained by HUPO-PSI | Future GC-MS candidate; not general GC support. |
| Vendor `.D`, `.ch`, `.raw` | Public parsers exist, but formats remain proprietary | No v0.1 support claim. |

## Proprietary candidate: Agilent ChemStation `.ch`

Public readers provide enough evidence for a structural Experimental boundary, but
not for Verified scientific signal support:

1. no complete official versioned structure was obtained;
2. retention-time construction and physical signal scaling were not verified against
   an authoritative export;
3. the raw unit lexeme cannot be trusted or expanded into a scientific unit;
4. one exact external fixture and synthetic structural tests now exist;
5. public readers disagree on the time-axis length or share unverified upstream
   assumptions.

Decision: add one explicit Experimental v181 decoded-record adapter. It retains every
record by ordinal and raw integer and does not expose retention time, physical scaling,
units, or peaks. The selected BSEE fixture has a documented digest, privacy review,
redistribution basis, and maintainer-only integration test. Verified promotion still
requires paired vendor exports and additional independent runs. See
[`agilent-chemstation-ch-v181-investigation.md`](agilent-chemstation-ch-v181-investigation.md).

## Proprietary candidate: Shimadzu LabSolutions `.GCD`

One CC0-declared `FS19_214.gcd` fixture and a non-redistributed, same-run LabSolutions
ASCII reference support a narrower but more scientific Experimental boundary than the
Agilent structural decoder. Independent byte inspection establishes a CFB v4 container,
an exact LabSolutions 5.82 / GC-2014 / `Ch1` / `SFID1` profile, 66,255 finite binary64
values in `uV`, and a DLT-based 40 ms retention-time axis. The paired ASCII matches
every signal after its integer rounding and every time after its five-decimal rounding.

Decision: add one Experimental scientific-signal adapter for that exact profile. Reject
other LabSolutions/GCsolution versions, detectors, units, factors, channels, GCD
generations, `.QGD`, and `.LCD`. The native file remains external because it contains
personal and machine-local text. See
[`shimadzu-gcsolution-gcd-investigation.md`](shimadzu-gcsolution-gcd-investigation.md).

## Proprietary candidate: Shimadzu GCMSsolution `.QGD`

One CC0 Dryad QGD provides a narrower TIC profile with exact whole-array and internal
scan constraints. The `4.00` compound-file profile stores 16,800 unsigned retention-
time milliseconds and 16,800 unsigned TIC integers. A bounded scan walk proves that
every scan header has the same RT and every scan intensity sum equals its native TIC.

Decision: add Experimental TIC-only support for that exact profile. Retention time is
exported in minutes; raw TIC integers are preserved with unknown physical unit. The
9,508,566 MS1 records are structurally checked, but scientific MS1 export remains
unsupported because the candidate m/z scale lacks an independent numeric oracle and
the current model/exporter cannot preserve scan boundaries with bounded memory. See
[`shimadzu-gcmssolution-qgd-investigation.md`](shimadzu-gcmssolution-qgd-investigation.md).
