# Shimadzu GCMSsolution `.QGD` `4.00` TIC profile

Status: **Experimental** (included in the v0.2.1 source tree; published availability is
shown by the PyPI badge)

Ordifile reads the TIC from one exact GCMSsolution compound-file profile identified by
the File Property marker `4.00`. It is not general Shimadzu, GCMSsolution,
LabSolutions, GC-MS, or QGD support.

## Exact capability

| Capability | Status |
|---|---|
| CFB and exact profile detection | Experimental, real-fixture tested |
| Retention-time axis | Experimental; source unsigned milliseconds converted to minutes |
| Sampling interval | Experimental; 200 ms in the tested file |
| TIC | Experimental; all 16,800 source `u64` integers in order |
| TIC physical unit | Unknown; no scaling or unit label applied |
| MS1 presence and block structure | Structurally validated |
| Scientific MS1 spectra / m/z | Not exported / not supported |
| Safe metadata | Field-specific; privacy-bearing paths are not exposed |
| Acquisition timezone | Unresolved; no reliable acquired-time claim |
| Peaks, identifications, quantitation, calibration | Not supported |
| Other QGD profiles, versions, SIM/MRM, width-4 recovery variants | Not supported |
| Write support | Not supported |

Use `--include-signals` to write the TIC:

```bash
ordifile inspect B4NF.7_C23.qgd --verbose
ordifile convert B4NF.7_C23.qgd --include-signals --output Ordifile_Result.xlsx
```

The output is one `SeriesKind.SCIENTIFIC_SIGNAL` series with retention time in minutes
and raw TIC integers. Ordifile does not convert TIC integers to a physical unit,
interpolate points, detect peaks, identify compounds, or export the MS1 payload.

## Detection and safety

The `.qgd` extension is supporting evidence only. Detection also checks the Microsoft
Compound File v4/4096 profile, exact case-sensitive required stream paths, the
NUL-terminated `4.00` File Property marker, RT/TIC/index count equations, monotonic RT
and offsets, per-scan headers and record lengths, supported intensity widths, terminal
stream consumption, and exact scan-intensity-sum equality with the native TIC.

Files with another profile, missing or ambiguous streams, malformed CFB metadata,
unequal counts, non-monotonic RT or offsets, out-of-range blocks, unsupported widths,
inconsistent point counts, or trailing bytes fail with a structured error. Inputs are
opened read-only and file, stream, directory-entry, scan, point, and work limits are
bounded.

## MS1 boundary

The tested file contains 16,800 scan blocks and 9,508,566 encoded spectral records.
Ordifile validates their complete block envelope without materializing or exporting
those rows. The warning `QGD_MS1_NOT_EXPORTED` prevents this omission from being
silent.

MS1 is deferred because the candidate encoded-mass-to-m/z transform lacks an
independent numeric oracle and the current two-dimensional signal model cannot
preserve scan boundaries. Exporting about 9.5 million long-form rows also requires a
bounded streaming workbook or sidecar design. No records are summarized or silently
discarded under a scientific MS1 capability claim.

## Evidence and limitations

The real `B4NF.7_C23.qgd` fixture is fetched only by a maintainer-controlled external
workflow. It is CC0 at its Dryad source but remains outside Git and Actions artifacts
because it contains local-path and user-originated text. Whole-array TIC/RT digests and
per-scan structural digests are stored instead.

See the [investigation](../research/shimadzu-gcmssolution-qgd-investigation.md) and
[format notes](../research/shimadzu-gcmssolution-qgd-format-notes.md). Verified TIC
promotion requires multiple in-scope runs, physical-unit and timezone evidence, and
cross-fixture regression. Scientific MS1 additionally requires independent m/z and
intensity validation plus a bounded mass-spectrum output model.

Shimadzu, GCMSsolution, and related names are names or marks of their respective
owner. Ordifile is independent and is not affiliated with or endorsed by Shimadzu.

## Stored mass-chromatogram peak table

The adapter also reads the peak rows the document stores in
`GCMS Data Processing/MC Peak Table`, a headerless array of 208-byte records
whose count is corroborated by `GCMS Data Processing/MC Peak Info`. It emits
retention, start and end time (minutes), Area, Height, and the stored compound
name. Ordifile does not integrate the signal here; every value is source-explicit.

**These stored values are not validated against a Shimadzu GCMSsolution export.**
No raw-plus-export pair is available for any file carrying a populated table, so
the field meanings were established only against each file's own TIC. Retention
time, the Area column identity, the Area scale, and Height were each corroborated
that way, but column selection, rounding, displayed units, and the treatment of
unidentified peaks remain unverified. Every parse that yields peaks raises
`SHIMADZU_QGD_STORED_PEAK_TABLE_UNVALIDATED`, and the metadata key
`stored_peak_value_validation` reports `internal_only_no_vendor_export`.

Two f64 fields in each record whose meaning was not established are deliberately
not read. Compound names are read only up to their NUL terminator, because the
bytes after it are uninitialised writer memory that holds fragments of unrelated
strings; a non-ASCII name is omitted rather than guessed at, since the document
does not record its code page.

Full evidence:
[the investigation](https://github.com/hdkim99/ordifile/blob/main/docs/research/shimadzu-gcmssolution-qgd-mc-peak-table-investigation.md).

## Accepted acquisition profiles

The scan grid is read from the document rather than pinned. It is accepted when
it is strictly increasing with one uniform interval; non-uniform grids fail
closed. The `Spectrum Index` stream is accepted in both observed encodings, a
bare u32 offset array and a `01 00`-tagged u64 offset array, which can never be
confused because a u32 array is a multiple of four bytes while the tagged u64
array is two modulo four.

Two compound-document generations are accepted: CFB v3 with 512-byte sectors
carrying `File Property` schema `2.00`, and CFB v4 with 4096-byte sectors
carrying schema `4.00`. Nothing is read out of `File Property` beyond that token.
Scans that carry zero data points are accepted, since their length is
self-consistent and they contribute no intensity; a non-empty scan still has to
name an observed intensity width.
