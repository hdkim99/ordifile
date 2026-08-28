# Shimadzu GCMSsolution `.QGD` stored mass-chromatogram peak table

Status: **field meanings established from internal evidence only. Not validated
against any Shimadzu GCMSsolution export.** Read the limitation section before
relying on the Area, Height, or Area-percentage values this adapter emits.

## Why this investigation exists

Ordifile already read the `.QGD` total ion chromatogram. It did not read the peak
rows the same document stores, so a `.qgd` file produced no peak table at all.

## Corpus

| Alias | Scans | Grid | Stored peak rows |
| --- | --- | --- | --- |
| A | 9,100 | 390,000-3,119,700 ms, 300 ms | 58 |
| B | 9,100 | same | 30 |
| C | 9,100 | same | 54 |
| D | 9,100 | same | 31 |
| E | 9,100 | same | 122 |

Five University of Florida GC-MS acquisitions, published under CC BY 4.0
(Zenodo record 15428029). A sixth candidate from a public converter corpus was
rejected: its `MC Peak Table`, `MC Peak Table2`, and `Compound Peak Table2`
streams are all zero bytes, because the run was acquired but never integrated.

## Two acquisition profiles, one reader

The previously supported fixture and this corpus disagree on three structural
points, so the reader now derives them from the document and validates them
instead of pinning the single acquisition it had seen:

| Structure | Earlier fixture | This corpus |
| --- | --- | --- |
| Scan grid | 16,800 scans, 240,000 ms start, 200 ms | 9,100 scans, 390,000 ms start, 300 ms |
| `Spectrum Index` | `N` x u32 offsets | `01 00` tag + `N` x u64 offsets |
| Scan header bytes 12-16 | `0` | 1-based scan number |

The two `Spectrum Index` encodings can never be confused: a bare u32 array is a
multiple of four bytes, while the tagged u64 array is two modulo four.

The grid is now accepted when it is strictly increasing with one uniform
interval; a non-uniform grid still fails closed.

## Record layout

`GCMS Data Processing/MC Peak Table` is a headerless array of 208-byte records.
`GCMS Data Processing/MC Peak Info` stores the record count as a u32 at offset 0;
it agreed with the stream length in all five files.

| Offset | Type | Field |
| --- | --- | --- |
| 4 | i32 LE | Retention time, ms |
| 8 | f64 LE | Area |
| 16 | f64 LE | Height |
| 40 | i32 LE | Peak start time, ms |
| 44 | i32 LE | Peak end time, ms |
| 72 | f64 LE | Area percentage |
| 80 | NUL-terminated bytes | Compound name |

Offsets 24 and 32 hold two further f64 values whose meaning was not established.
They are deliberately **not** read.

## What the field meanings were checked against

No vendor export exists for any of these files, so the only available oracle was
each document's own raw data. Four independent internal checks were run.

1. **Retention time.** All 295 stored rows across the five files place their
   retention time within one scan of a local maximum of the file's own TIC.
2. **Area percentage identifies the Area column.** The offset-72 values sum to
   exactly 100.000000 in every file, and `100 x area / sum(area)` computed from
   the offset-8 column reproduces them to at most 3.6e-15. The offset-16, -24,
   and -32 columns do not reproduce them, so offset 8 is the Area column and no
   other candidate is.
3. **Absolute Area scale.** Integrating the file's own TIC between each row's
   stored start and end time, above a straight line joining those two endpoints,
   reproduces the stored Area with a median ratio of 1.0018 across 293 rows.
   The alternative units are excluded by factors of 60 and 300, not by a margin.
4. **Height.** The same reconstruction gives a median ratio of 1.0000 for the
   offset-16 column, with 279 of 294 rows within 2 percent.

Checks 3 and 4 spread wider than their medians for peaks that share a baseline
with a neighbour, which is expected: the reconstruction uses a per-row straight
baseline, while the vendor resolves peak groups.

## Limitation: not validated against a vendor export

Everything above establishes that Ordifile reads the *correct bytes with the
correct meaning and units*. It does **not** establish that the emitted table
reproduces what GCMSsolution would print. Column selection, rounding, displayed
units, and the treatment of unidentified peaks are all unverified, because no
raw-plus-export pair is available for any file carrying a populated table.

Every parse that yields peaks therefore raises
`SHIMADZU_QGD_STORED_PEAK_TABLE_UNVALIDATED`, and the metadata key
`stored_peak_value_validation` reports `internal_only_no_vendor_export`.

Closing this gap needs one `.qgd` file with a populated `MC Peak Table` together
with the GCMSsolution report produced from that same file.

## Compound names

Names are read only up to their first NUL. The bytes after the terminator are
uninitialised writer memory: in this corpus they hold fragments of unrelated
strings, including tails of other compound names and a stray `T:42.515`
annotation. Scanning past the terminator would leak that residue into output, so
the reader never does. An empty name means the peak was not identified; 14 of
the 295 rows are unidentified.

The document does not record the code page for the name bytes, so a non-ASCII
name is reported as undecodable and omitted rather than guessed at.
