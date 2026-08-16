# Shimadzu GCMSsolution `.QGD` `4.00` format notes

- Status: clean-room facts for one Experimental TIC profile
- Fixture: `B4NF.7_C23.qgd`
- Fixture SHA-256: `64b2faab81c0ad10bc36c57b23ed770751dbe5253f48d2a13b8b15df1de23f5d`
- Scope: byte observations, equations, confidence, and test coverage; not a vendor
  specification

No proprietary byte range is stored in this repository. GPL sources are not copied or
translated. The implementation uses the independently recorded facts below, public
Microsoft CFB semantics, external normalized outputs, and generated structural tests.

## Container and stream facts

| Location | Observed value | Interpretation | Confidence / agreement | Test boundary |
|---|---|---|---|---|
| CFB header 0..7 | `D0 CF 11 E0 A1 B1 1A E1` | Compound-file signature | Verified by MS-CFB and fixture | Wrong magic rejected |
| CFB header 24..33 | minor 62, major 4, LE, shifts 12/6 | CFB v4, 4096-byte sectors, 64-byte mini-sectors | Verified by header and `olefile` | Other major/order/shifts rejected |
| `File Property` +4 | NUL-terminated ASCII `4.00` | Exact supported profile marker | Exact fixture observation; not called a general GCMSsolution version | Alias, missing NUL, other value rejected |
| Directory | required paths below | Exact stream identity | Fixture and external readers agree | Missing, duplicate, case-ambiguous path rejected |

Required exact paths:

```text
File Property
GCMS Raw Data/Retention Time
GCMS Raw Data/TIC Data
GCMS Raw Data/Spectrum Index
GCMS Raw Data/MS Raw Data
```

The real-file stream inventory has 340 streams and 23 storages. Runtime code caps the
inventory and individual reads, but must not require those two counts for every future
fixture inside the same explicitly reviewed profile.

## TIC and retention-time arrays

| Stream | Encoding | Equation | Interpretation | Confidence | Coverage |
|---|---|---|---|---|---|
| Retention Time | contiguous LE `u32` | `size % 4 == 0` | milliseconds | External readers, exact scan-header equality, monotonic 200 ms sequence | Whole-array digest and corrupt lengths/order |
| TIC Data | contiguous LE `u64` | `size % 8 == 0` | raw TIC integer | External readers and every scan intensity sum | Whole-array digest, max-range integer, count mismatch |
| Both | equal element count | `RT/4 == TIC/8` | one TIC point per scan | 16,800/16,800 exact | Mismatch rejected |

The public signal is:

```text
x[i] = retention_time_u32_ms[i] / 60000
y[i] = tic_u64[i]
x_unit = "min"
y_unit = None
```

TIC values are not converted to float before model construction. No scale or physical
unit is applied. `raw_tic_intensity` is a descriptive field label, not a physical unit.

## Spectrum index and block envelope

| Block location | Type | Exact-profile rule | Scientific exposure |
|---:|---|---|---|
| +0 | LE `u32` | scan number equals zero-based ordinal | structural metadata only |
| +4 | LE `u32` | equals corresponding RT milliseconds | structural metadata only |
| +8 | LE `u32` | fixture value `0x01D60000`; meaning unresolved | not exposed semantically |
| +12, +16 | LE `u32` | zero | required profile invariant |
| +20 | LE `u16` | intensity width, only 2 or 3 accepted | width summary only |
| +22 | LE `u16` | positive point count within configured bound | count summary only |
| +24, +28 | LE `u32` | zero | required profile invariant |
| +32 | repeated records | LE `u16` encoded mass + unsigned LE intensity of selected width | not exported as MS1 |

For each offset interval:

```text
block_bytes = next_offset - offset
block_bytes = 32 + point_count * (2 + intensity_width)
```

Offsets are strictly increasing, the first offset is zero, the terminal offset is the
MS Raw Data stream size, every access is checked before reading, and all blocks must be
consumed exactly. Python integers avoid overflow when summing intensities.

The candidate `encoded_mass / 20` transform appears in two common-ancestry GPL readers
and is therefore recorded only in external research summaries. Runtime code does not
apply it or claim m/z. Width 4, high-bit masking, SIM/MRM, and any correction that makes
an invalid header fit its block are unsupported rather than guessed.

## Metadata fields

| Location | Observed fact | Runtime status |
|---|---|---|
| File Property +4 | profile marker `4.00` | Required and exposed as exact profile string |
| File Property +172 | sample-type token `Unknown` | Raw-only if retained |
| File Property +204 | sample text | Bounded safe mapping or filename fallback; raw provenance without public golden text |
| File Property +300 | operator text | Optional, privacy-sensitive, never logged |
| File Property +52/+56, +92/+96, +508/+512 | FILETIME pairs | Raw values or timezone-unreliable candidates only |
| File Property +580/+1604/+2116 | absolute data/batch/method paths | Never exposed or logged |
| Other streams | `GCMSsolution`, `GCMS-QP2010`, adjacent `2.20` tokens | Product/profile evidence only; exact component-version semantics unresolved |

## Resource and corruption boundaries

- input opened read-only with `olefile 0.47` and strict defect handling;
- bounded file, directory inventory, metadata stream, signal stream, scan count, and
  per-scan point count;
- exact case-sensitive required paths plus casefold ambiguity rejection;
- exact stream reads and divisibility/count equations;
- monotonic RT and spectrum offsets;
- offset, block-size, header, point-count, and terminal-bound checks;
- unsupported intensity width is a structured failure;
- no scan correction, no trailing-byte acceptance, no silent truncation;
- invalid files fail independently inside a batch.

The generated structural fixture uses invented sample and numeric payload values. It
reproduces only the documented container/profile grammar and contains no byte slice
copied from the real QGD file.
