# Shimadzu LabSolutions 5.82 GCD format notes

These notes define the independently observed profile implemented by
`shimadzu_gcsolution_gcd`. They are not a general Shimadzu specification.

| Location | Observed value | Interpretation | Evidence | Confidence | Test boundary |
|---|---|---|---|---|---|
| file bytes 0–7 | `d0 cf 11 e0 a1 b1 1a e1` | Microsoft Compound File Binary signature | MS-CFB specification and fixture | High | exact signature and read-only CFB open |
| CFB header | version 4, 4096-byte sectors, little endian | exact fixture container profile | MS-CFB specification and fixture | High | other CFB profiles rejected |
| `SystemCheckResult/SystemCheckResult` | XML `Summary/SWVersion=5.82` | producer software version | exact fixture and paired ASCII | High | exact `5.82` required |
| `File Property` | schema `5.01` | property schema, not software version | exact fixture | High | recorded separately |
| `LSS Raw Data/2D Data Item U` | one link for `[Chromatogram (Ch1)]` / `SFID1` | selects the only supported detector stream | fixture metadata and paired ASCII | High for this profile | missing, duplicate, multichannel, or non-SFID1 rejected |
| linked signal metadata | `Rate=40`, `AT=2650200`, `DLT=20`, `CF=1`, `GF=1`; selected `DUS=1` maps `US ID=1` to `uV` / `VF=1`; alternatives are ID 2 `mV` / 1,000 and ID 3 `V` / 1,000,000 | sample interval, total acquisition span, initial delay, identity scale, selected physical unit | fixture, paired ASCII, independent corpus | High for exact profile | missing, duplicate, or mismatched declarations rejected |
| `LSS Raw Data/Chromatogram Ch1` +0 | LE u32 `17234` (`0x4352`) | exact profile label | fixture observation | Medium | exact profile value required |
| same +4 | LE u32 `40` | interval in milliseconds | linked metadata and paired ASCII agree | High | must equal linked Rate |
| same +8 | LE u32 `66255` | point count | stream equation and paired ASCII | High | bounded positive count |
| same +12 | LE u32 `530045` | encoded payload length candidate, `n*8+5` | fixture and corpus equation | High for profile | exact equation required |
| same +16…23 | eight zero bytes | reserved profile bytes | fixture and corpus observation | Medium | nonzero rejected |
| same +24…EOF | 66,255 LE binary64 values | signal values in linked `uV` axis | paired ASCII pointwise comparison | High | finite only; exact stream length |
| SampleInfo FILETIME | `2019-07-18T23:45:56.388464Z` | UTC acquisition timestamp | MS FILETIME definition and fixture | High | bounded FILETIME conversion |

For point `i` from zero through `n-1`:

```text
retention_time_min = (DLT_ms + i * interval_ms) / 60000
signal_uV = stored_binary64                 # CF=GF=1 exact profile
```

Ordifile does not interpolate, drop, reorder, or silently repair points. It rejects a
count/length mismatch, non-finite binary64, extra nonempty channels, ambiguous metadata
links, unsupported producer version, unsupported detector/unit/factor, and container
defects at or above the strict `olefile` defect threshold. Input access is read-only,
with an adapter-level file-size cap, stream-count cap, required-stream allowlist, and
per-stream bounds.

## Golden summaries

The real file remains external. Tests may use only these derived digests:

- full chromatogram stream: `4be4c740cc62404387ced45285c42768d713d9b4f14f8a1c2247d6ac39173855`;
- native LE-float64 payload: `36acf7008bee509c5786656c025f5711fc3e723f3c7de3dc0df1773e15fa9d13`;
- decoded signal, concatenated big-endian float64: `b836371e5f8171788b2f3ebd0a3a75d07bfeb7ee8eed081992a9016192987b9a`;
- time axis, concatenated big-endian float64: `18c335833a87d10e59e997623f82ddc0e8b73f00031522d5b2339ab3f3b119e2`;
- point pairs, concatenated big-endian `(time, signal)` float64: `a1395b48d5f802b6772bf0351ee694bf63a89af10a822feea30baf4f28023f45`;
- paired ASCII rounded signal, concatenated big-endian signed int64:
  `7fe6f13daa282a19fe26b5f92669fb7d6730dabd0359e54826cc4fb00227d75d`.
- paired ASCII rounded time, each value rounded to five decimals and concatenated as
  little-endian float64:
  `5134dc0fa78155212116aa6f79f790223ce5058f678a7927dfe5a5aa932a52ab`.

All packing rules concatenate values without a header, delimiter, or count. These
digests validate the entire sequence, not just endpoints.


## Stored peak table

`LSS Data Processing/PT-*` holds the vendor's own processed peak rows. A duplicate copy is
kept under `LSS Data Processing Original/`; the two are byte-identical unless the document has
been reprocessed and saved.

```text
offset  0   4 bytes   magic "VER1"
offset  4   1 byte    processing revision; 0x02, 0x04, 0x05, 0x06, 0x07 and 0x53 observed
offset  5  15 bytes   reserved, zero in every observed stream
offset 20   N * 792   fixed-size peak records
```

Within one 792-byte record, five fields are established against paired vendor text exports:

| Record offset | Type | Field |
|---:|---|---|
| +4 | int32 | retention time, milliseconds |
| +8 | binary64 | Area |
| +24 | binary64 | Height |
| +56 | int32 | peak start time, milliseconds |
| +60 | int32 | peak end time, milliseconds |

The remaining bytes of each record are not decoded. The record count is derived as
`(stream length - 20) / 792`; a remainder is a structural failure.

The stored Area and Height carry full binary64 precision. LabSolutions' result-ASCII export
publishes them rounded to whole units, and across every compared row the stored value rounds
to exactly the exported value with a maximum absolute difference below 0.5. The stored table
is therefore the higher-precision source, not a derived view of the export.

Evidence: one same-run `.GCD`/result-ASCII pair (83 rows) and an owner-approved CC BY 4.0
corpus of 320 further stored tables, of which 318 have a paired text export carrying a peak
table (1,548 rows). Every retention, start, end, Area and Height value agreed. One corpus pair
disagreed on row count only; its `PT` and `PT Original` streams are identical, so the stored
table and the separately re-exported text describe different processing states of the same
acquisition rather than a decoding difference. The corpus spans LabSolutions 5.71 SP2 and
5.86, which shows the record layout is not specific to the 5.82 profile the adapter accepts.
Stored negative Area and Height occur and are preserved.
