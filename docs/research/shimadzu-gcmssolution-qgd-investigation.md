# Shimadzu GCMSsolution `.QGD` investigation

- Status: **Experimental GO for TIC; MS1 export not supported**
- Research date: 2026-08-17
- Runtime boundary: one GCMSsolution compound-file profile with the exact `4.00`
  File Property marker and the stream invariants below
- Tracking issue: [#17](https://github.com/hdkim99/ordifile/issues/17)

This investigation does not establish general Shimadzu, GCMSsolution, LabSolutions,
or `.QGD` compatibility. It establishes a reproducible TIC and retention-time profile
for one real file. Its MS1 payload is structurally validated, but is not exported as a
mass spectrum because the m/z scale lacks an independent numeric oracle and Ordifile
does not yet have a lossless, bounded mass-spectrum workbook model.

## Fixture and provenance

| Item | Evidence |
|---|---|
| Native file | `B4NF.7_C23.qgd`, 39,964,672 bytes, SHA-256 `64b2faab81c0ad10bc36c57b23ed770751dbe5253f48d2a13b8b15df1de23f5d` |
| Original source | [Dryad dataset DOI 10.5061/dryad.8gtht76s4](https://doi.org/10.5061/dryad.8gtht76s4), published 2022-10-04 |
| License | CC0 1.0 in the Dryad dataset and file API records |
| Pinned mirror | `chromConverterExtraTests`, commit `f9cb88d90f6be00e3c0f16fa3e2bb7734a5da66b`; byte-identical |
| Privacy | Contains absolute paths and user-originated metadata; external, transient, and non-logged only |
| Additional files | The Dryad dataset contains nine other QGD runs; they are future cross-profile evidence, not part of this first runtime gate |

Dryad's [file API record](https://datadryad.org/api/v2/files/1851685) reports the
original object. The [pinned fixture register](https://github.com/ethanbass/chromConverterExtraTests/blob/f9cb88d90f6be00e3c0f16fa3e2bb7734a5da66b/README.md)
identifies the same Dryad source and CC0 terms. The native file is not committed or
uploaded as an Actions artifact despite that permission because its embedded local
paths and source text are unnecessary for public tests.

## Official product evidence

Shimadzu's [ChromSquare specifications](https://www.shimadzu.com/an/products/gas-chromatograph-mass-spectrometry/gc-ms-software/chromsquare/spec.html)
identify `.QGD` as a GCMSsolution MS data file and describe TIC and mass-spectrum
display. Shimadzu's [TIC fundamentals](https://www.shimadzu.com/an/service-support/technical-support/analysis-basics/gcms/fundamentals/retention/total_ion.html)
define a TIC point as the sum of the mass-spectral peak intensities in one scan. These
sources establish scientific context, but they do not specify the QGD binary layout,
integer widths, physical TIC unit, or m/z encoding.

The study associated with the fixture reports a GC2010 plus / QP2010 plus full-scan
acquisition. Its aggregate method description does not exactly reproduce this file's
200 ms scan interval or observed candidate mass range, so it is not used as byte-level
truth for the adapter.

## Reference implementations and clean-room boundary

| Reader | Fixture result | License and independence |
|---|---|---|
| Ordifile independent research decoder | Exact stream, count, TIC, retention-time, index, scan-boundary, and per-scan TIC-sum checks | Independently written from observed bytes and public CFB semantics |
| `chromConverter` 0.9.1, commit `9137b85f...` | TIC 16,800 rows and MS1 9,508,566 records agree with normalized research digests | GPL >= 3; research-only behavior oracle, no copy, translation, dependency, or vendoring |
| `shimadzu-qgd2csv` 0.2.4, commit `992daeff...` | Normalized output agrees | GPL-3.0 and explicitly based in part on chromConverter; not an independent lineage |
| OpenChrom QGD converter | Dryad notes that the dataset can be opened, but no inspectable or redistributable numeric oracle was available | Proprietary plug-in; not executed, copied, decompiled, or bundled |
| `olefile` 0.47 | Read-only CFB access only | BSD/PIL-style permissive dependency; no Shimadzu parsing semantics |

The agreement is therefore not described as two independent open-source parser
families. The stronger independent constraint is internal: every decoded scan has the
stored scan number and retention time, consumes exactly its indexed block, and its
intensity sum equals the corresponding native TIC value for all 16,800 scans.

## Exact container profile

| Field | Observed value | Runtime treatment |
|---|---:|---|
| CFB signature | `D0 CF 11 E0 A1 B1 1A E1` | Required |
| CFB major/minor | 4 / 62 | Required exact profile |
| Byte order | little-endian | Required |
| Sector / mini-sector | 4,096 / 64 bytes | Required |
| Stream / storage count | 340 / 23 | Bounded inventory; exact total is external evidence, not a universal rule |
| `File Property` marker | NUL-terminated `4.00` at offset 4 | Required exact profile |
| `GCMS Raw Data/Retention Time` | 67,200 bytes | Required; `16,800 * 4` |
| `GCMS Raw Data/TIC Data` | 134,400 bytes | Required; `16,800 * 8` |
| `GCMS Raw Data/Spectrum Index` | 67,200 bytes | Required; `16,800 * 4` |
| `GCMS Raw Data/MS Raw Data` | 38,814,089 bytes | Required for bounded structural validation |

The exact count equation is:

```text
len(Retention Time) / 4
= len(TIC Data) / 8
= len(Spectrum Index) / 4
= 16,800 scans
```

## TIC and retention time

Retention Time is a little-endian unsigned 32-bit millisecond array. TIC Data is a
little-endian unsigned 64-bit integer array. Ordifile preserves every TIC integer and
constructs `time_min = raw_ms / 60000` without interpolation.

| Capability | Exact result | Status |
|---|---:|---|
| Point count | 16,800 | Experimental, real-fixture tested |
| RT start / end | 4.0 / 59.99666666666667 min | Experimental |
| RT interval | exactly 200 ms for all 16,799 intervals | Experimental |
| TIC minimum / maximum | 289,349 / 25,764,044 | Experimental |
| TIC sum | 9,258,016,526 | External golden |
| TIC unit | unresolved | `None`; no `counts` or `a.u.` claim |
| Peaks / identifications | not read | Unsupported |

The normalized whole-array digests are recorded in
[`reference_results/shimadzu-gcmssolution-qgd.json`](reference_results/shimadzu-gcmssolution-qgd.json).

## MS1 structural result

Spectrum Index is a strictly increasing little-endian unsigned 32-bit offset array.
Appending the exact MS Raw Data stream length as the terminal offset partitions the
stream into 16,800 blocks with no overlap, gap, or trailing byte.

Each validated block has a 32-byte header, followed by `point_count` records of one
little-endian `u16` encoded-mass value and one unsigned little-endian intensity of the
header-selected width. Only widths 2 and 3 occur in this fixture:

- total records: 9,508,566;
- records per scan: 356 through 567;
- width 2: 16,372 scans;
- width 3: 428 scans;
- decoded intensity range: 102 through 4,851,696;
- every scan number equals its ordinal;
- every scan-header RT equals the Retention Time stream;
- every scan intensity sum equals its native TIC value;
- every block satisfies `32 + point_count * (2 + width)` exactly.

Two common-ancestry readers divide encoded mass by 20, but no independent numeric
oracle or same-run vendor export establishes that scale. Width-4/high-bit recovery is
documented by a separate parser bug history but does not occur in this file. The first
adapter therefore performs only bounded structural validation and records that MS1 is
present. It does not decode or export scientific mass spectra, does not call the
encoded value m/z, and emits `QGD_MS1_NOT_EXPORTED`.

## Metadata and privacy

The File Property stream contains sample text, an operator field, timestamps, and
absolute data, batch, and method paths. Public tests and logs do not expose those
values. The profile marker `4.00`, product-family markers, and safe structural fields
may be reported. FILETIME conversion produces plausible timestamp candidates, but
the software's UTC-versus-local-wall-time convention is unresolved, so the adapter
must not present a timezone-reliable acquisition timestamp.

## GO decision and remaining gates

Stage A TIC support is justified because the extension is not trusted alone, the
container/profile and required streams are bounded, the entire time and TIC arrays are
reproducible, every scan supplies a strong TIC-sum constraint, and malformed variants
can be rejected without reading beyond declared bounds.

Stage B scientific MS1 output remains blocked by:

1. independent confirmation of the encoded-mass scale and bin semantics;
2. a same-run vendor AIA/ANDI, mzML, or equivalent spectrum export;
3. a canonical mass-spectrum model that preserves scan boundaries;
4. a streaming workbook/sidecar design for 9.5 million rows;
5. lawful real fixtures covering width 4 and large-value behavior;
6. additional QGD profiles and verified SIM/MRM discriminators.

Verified promotion of either capability additionally requires at least three
independent in-scope runs, cross-fixture regression, physical TIC-unit evidence, and
timezone semantics. Other QGD versions, compound identification, quantitation,
calibration, peak picking, deconvolution, and write support remain unsupported.
