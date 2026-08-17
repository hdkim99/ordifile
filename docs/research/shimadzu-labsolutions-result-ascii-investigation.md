# Shimadzu LabSolutions result ASCII investigation

- Date: 2026-08-17
- Decision: Experimental GO for one exact 5.82 GC-2014, single-`SFID1` / `Ch1`
  standalone result-export profile
- Adapter: `shimadzu_labsolutions_result_ascii`
- Raw chromatogram dependency: none

## Evidence boundary

The primary fixture is the pinned `ladder.txt` file in the chromConverter repository:

- 971,258 bytes;
- SHA-256 `46d1dcde188d7844c32abb89cda1f0d773cac480f6d6c93f2b6ca7149fdb9297`;
- LabSolutions 5.82 `Data File`, GC-2014;
- one detector `SFID1`, one channel `Ch1`;
- 83 Peak Table rows;
- repository-level GPL >= 3, with no file-specific notice found; and
- privacy-bearing source metadata, so controlled external CI only.

The primary file bytes and GPL reader/test expressions are not committed, bundled,
logged, uploaded as Actions artifacts, translated or imported into Ordifile. The
implementation uses independently recorded file facts and canonical full-sequence
digests. The paired `FS19_214.gcd` is file-specific CC0. Published metadata and enforced
Peak Table comparisons support the same-run relationship; the published chromatogram
comparison itself is not an enforced assertion. Ordifile's controlled external test
separately asserts all 66,255 chromatogram points. That relationship is useful
cross-validation, not independent official vendor certification.

## Exact observed profile

The document is 7-bit ASCII with CRLF and contains the exact ordered sections:

1. Header
2. File Information
3. Sample Information
4. Original Files
5. File Description
6. Configuration
7. Peak Table(Ch1)
8. Compound Results(Ch1)
9. Chromatogram (Ch1)

The producer/profile markers are LabSolutions 5.82, `Data File`, GC-2014, one detector
`SFID1` and one channel. The Peak Table has 21 exact columns and a declared positive
variable row count. The golden file has 83 rows.

Every source `Peak#` is sequential. RT, I.Time, F.Time, Area and Height are finite;
I.Time <= RT <= F.Time; RT is strictly increasing; area and height are nonnegative.
The same-file chromatogram header names `R.Time (min)`, and the official LabSolutions
operator guide describes Peak Table retention/start/end time semantics in minutes.
This supports canonical RT/start/end unit `min`. No evidence in the exact export
establishes physical area or height units, so both remain unset.

The exact fixture has zero compound results and every Peak Table `ID#` / `Name` cell is
blank. It therefore provides no evidence for compound identity and the adapter emits
none. The source peak number is preserved independently from canonical observation
order.

## Clean-room and oracle boundary

The primary repository and parser are GPL >= 3. They are external research references,
not runtime/development dependencies and not implementation source. The implementation
does not copy parser source, constants tables, control flow, variable names, or test
expressions. Exact row schemas, bounds and conversions come from the fixture audit,
same-file invariants and official semantic documentation.

The separate MIT-declared
[`multichannel_chrom.txt`](https://github.com/ethanbass/chromConverterExtraTests/blob/f9cb88d90f6be00e3c0f16fa3e2bb7734a5da66b/inst/multichannel_chrom.txt)
is pinned at commit
`f9cb88d90f6be00e3c0f16fa3e2bb7734a5da66b`, 271,016 bytes, SHA-256
`8ba74785fa77b31ca08e984e905e4b76e8ced6e4f6de323a17cc74535f5e3cb6`.
It is a LabSolutions 5.54 SP2 HPLC/RID export with three Peak Tables containing 2, 7
and 7 rows. It is documentation-only grammar evidence and does not broaden the GC
adapter, is not fetched by CI, and is not a public support fixture. Its
[paired LCD](https://github.com/ethanbass/chromConverterExtraTests/blob/f9cb88d90f6be00e3c0f16fa3e2bb7734a5da66b/inst/multichannel_chrom.lcd)
is 880,640 bytes with SHA-256
`f54fd4008481b8f1146db674fec4c200a4a933ec35602a4a649b360c242f03a6`;
Ordifile does not read that LCD profile.

## Capability decision

| Capability | Decision |
|---|---|
| Exact-family detection | Experimental GO |
| Exact 5.82 GC-2014 / SFID1 / Ch1 boundary | Experimental GO |
| Peak number and source order | Experimental GO |
| RT, start and end in min | Experimental GO |
| Area and height numeric values | Experimental GO, units unset |
| Compound identity | Unsupported for this profile |
| Raw chromatogram signal | Unsupported by this result adapter |
| Multiple peak sections/detectors/channels | Unsupported |
| Other LabSolutions versions/instruments | Unsupported |

## Verified promotion gate

- at least two additional independent GC-FID result exports;
- another validated software/profile sample;
- variation in peak count, sampling interval and area/height ranges;
- explicit area/height unit evidence if a physical unit is to be claimed;
- identified-compound rows before compound support is widened;
- official or equivalently documented same-run result comparison on another run; and
- cross-fixture regression without loosening the exact-profile gates.
