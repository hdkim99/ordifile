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
