# Shimadzu LabSolutions result ASCII independent implementation notes

- Date: 2026-08-17
- Adapter: `shimadzu_labsolutions_result_ascii`
- Boundary: Experimental standalone result-only conversion
- Exact profile: LabSolutions 5.82, `Data File`, GC-2014, one `SFID1` / `Ch1`
- External fixture: 971,258 bytes; SHA-256
  `46d1dcde188d7844c32abb89cda1f0d773cac480f6d6c93f2b6ca7149fdb9297`

The implementation was derived from independently recorded fixture structure,
same-document invariants, the paired same-run GCD and official LabSolutions Peak Table
semantics. No GPL parser or test code was copied, translated, vendored, imported or
added as a dependency.

## Exact structural gate

- `.txt` suffix plus bounded 7-bit ASCII bytes, no BOM/NUL and exact CRLF envelope;
- exact nine-section names and order;
- newline-independent bounded LabSolutions family identification followed by exact
  producer/profile markers LabSolutions 5.82, `Data File`, GC-2014;
- exactly one configured detector `SFID1` and one channel `Ch1`;
- one `Peak Table(Ch1)` with the exact 21-column header and positive bounded declared
  count;
- sequential source `Peak#` values `1..N`;
- exact-lossless finite RT/I.Time/F.Time/Area/Height decimals, strictly increasing RT,
  bounded integration windows, same-file chromatogram range agreement, and
  nonnegative area/height;
- one zero-row `Compound Results(Ch1)` section; and
- exact observed Chromatogram header/time structure as a same-document profile check,
  without exporting its intensities.

Input bytes and rows have explicit size/count/lexeme bounds. CRLF record count is
preflighted before decoding and record materialization. Source mutation is
rejected by comparing the parser's bounded-read size/SHA-256 with core discovery and
the post-parse integrity check. Identified LabSolutions documents outside this exact
boundary are structured unsupported-profile failures and do not fall through to the
generic semicolon-TXT adapter.

The exact fixture's 40 ms chromatogram interval is asserted by the external golden
test but is not a detector/profile constant. Any positive bounded declared interval is
retained only as same-file structural metadata. `Instrument #` and `Line #` are
required fields but their values are deployment data, not format gates and are never
exported.

## Canonical mapping

`Peak Table(Ch1)` is the only canonical row source:

| Source | Canonical |
|---|---|
| `Peak#` | `PeakRecord.peak_number` |
| source row position | `PeakRecord.observation_order` |
| `R.Time` | `retention_time`, min |
| `I.Time` / `F.Time` | `start_time` / `end_time`, min |
| `Area` / `Height` | `area` / `height`, units unset |
| source `SFID1` / `Ch1` | canonical detector `FID`, channel `Ch1` |

The source peak number and source observation order are related but distinct canonical
facts and are both retained. Blank `ID#` / `Name` rows and the zero-row compound table
produce no compound identity. Ordifile does not infer names, units, calibrations,
identifications or raw-signal relationships.

## External golden facts

The external fixture contains 83 canonical rows. The following SHA-256 values use
UTF-8 encoding of exact source lexemes joined by LF with no trailing LF:

| Sequence | SHA-256 |
|---|---|
| retention time | `c19d2d264c606a3bf5407e0c511bc2d49e4d6cb302ec48f4be8c0f405be39b34` |
| integration start | `a0041097783b80adb6d24eb55892bb05c8a894fa1d8ac3b8d58b1170bccac2f3` |
| integration end | `1ce215fd315b602fec4e4555a568a7b43e1a35ab2255ca6855ad72a5c3556873` |
| area | `2a12071d874f79b02308ec8c86cf76be1c01efe26b62098926b4b31d56b38e3c` |
| height | `87a976f34205ee2a6b3a203fbedee09c07b0f86203116606345f696e00348c4c` |

The external test asserts every lexeme digest, every canonical row, the reopened
workbook, and all 66,255 paired same-run GCD chromatogram values. Source bytes,
privacy-bearing fields and generated workbooks are never logged or uploaded.

## Manufacturer-neutral output and privacy

The adapter produces the existing manufacturer-neutral `PeakRecord`, `Peaks`,
compound `Peak_Matrix` and conditional `Peak_Order_Matrix` model. Because all area
units are unresolved, validation preserves `None` consistently and the matrix area
unit cell is blank. Mixed unset/set or blank-string unit states are rejected.

The adapter opts into `SHA256_ALIAS`; its sample ID and every public source reference
are content-derived. Shared `.txt` discovery uses a provisional SHA alias while this
private owner is unresolved. A successful generic parser restores ordinary relative
provenance only after parsing, validation and integrity checks; no-match, ambiguity,
unsupported Shimadzu profiles and all failures retain the safe alias.
