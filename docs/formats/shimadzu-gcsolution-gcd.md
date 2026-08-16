# Shimadzu LabSolutions 5.82 `.GCD` GC-FID profile

Status: **Experimental** (unreleased development capability)

Ordifile reads one exact scientific chromatogram profile: a LabSolutions 5.82 file
from a GC-2014 with one `Ch1` stream linked to `SFID1`, unit `uV`, and identity
conversion/gain factors. It is not general GCsolution, LabSolutions, Shimadzu, or GCD
support.

## Exact capability

| Capability | Status |
|---|---|
| CFB and exact profile detection | Experimental, real-fixture tested |
| Retention-time axis | Experimental; same-run ASCII compared, minutes |
| Sampling interval | Experimental; 40 ms in the tested profile |
| Signal | Experimental; all 66,255 finite values in source order |
| Signal scale/unit | Identity factors, `uV`, exact profile only |
| Acquisition timestamp | UTC FILETIME when exact bounded field is present |
| Sample/software/instrument metadata | Field-specific |
| Peaks | Not supported |
| Other LabSolutions versions, detectors, units, channels, factors, `.GCD` profiles | Not supported |
| `.QGD`, `.LCD`, GCMSsolution, methods, or write support | Not supported |

Use `--include-signals` to write the scientific signal:

```bash
ordifile inspect FS19_214.gcd --verbose
ordifile convert FS19_214.gcd --include-signals --output Ordifile_Result.xlsx
```

The output is a `SeriesKind.SCIENTIFIC_SIGNAL` series with retention time in minutes
and response in `uV`. Ordifile does not interpolate, truncate, or detect peaks.

## Detection and safety

The `.gcd` extension is supporting evidence only. Detection also checks the Microsoft
Compound File signature/profile, exact LabSolutions 5.82 producer evidence, required
stream inventory, one unambiguous `Ch1`/`SFID1` mapping, signal header, point-count and
stream-length equations, 40 ms rate, 20 ms delay, `uV`/`VF1`, and identity conversion
and gain factors.

Files with another producer version, detector, unit, factor, multiple populated
channels, ambiguous links, malformed XML, non-finite values, unsupported CFB profile,
or inconsistent lengths fail with a structured error. The reader opens inputs
read-only and applies file, stream, directory-entry, and point-count limits.

## Evidence and limitations

The real `FS19_214.gcd` fixture is fetched only by a maintainer-controlled external
workflow. It is not committed or uploaded as an artifact. A paired same-run
LabSolutions ASCII chromatogram validates every rounded signal and time value, but is
not redistributed and is not described as an official conformance export.

See the [investigation](../research/shimadzu-gcsolution-gcd-investigation.md) and
[format notes](../research/shimadzu-gcsolution-gcd-format-notes.md). Verified promotion
requires multiple independent in-scope FID files and additional vendor/export evidence.

Shimadzu, LabSolutions, GCsolution, and GC-2014 are names or marks of their respective
owner. Ordifile is independent and is not affiliated with or endorsed by Shimadzu.
