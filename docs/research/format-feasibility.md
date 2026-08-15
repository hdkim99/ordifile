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

Entab (MIT) and rainbow (LGPL-3.0) both provide partial public implementation evidence,
but the candidate fails the project inclusion gate:

1. no complete official versioned structure was obtained;
2. public fixture redistribution provenance is unresolved;
3. detector/channel/unit semantics were not verified against an authoritative export;
4. no Ordifile fixture or passing test exists;
5. Entab's published wheels do not cover the intended Python/OS matrix.

Decision: record `.ch` only as a research candidate. Do not add an adapter skeleton that
could be mistaken for support. A future implementation requires redistributable fixtures,
vendor-export cross-checks, corrupt/truncated cases, documented checksums, and all-platform
tests without vendor SDKs or binaries.
