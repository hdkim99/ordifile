# YoungIn YL-Clarity exact PRM profiles

- Status: Experimental
- Adapter: `youngin_yl_clarity_prm_raw`
- Observed producers: YL-Clarity `9.0.1.19` and `9.1.0.76`
- Runtime dependency on YL-Clarity, Clarity, vendor DLLs or executables: none
- Peaks, Area and Height from PRM: unsupported

PRM contains stored chromatographic data. The adapter applies scientific meaning only to
the exact producer/layout for which same-run full-curve evidence exists.

## Profile-specific output

### YL-Clarity 9.0.1.19 — structural records

Twenty-three local-only files contain 43 current blocks and 563,240 finite little-endian
binary32 records. They are preserved in `Signals_Records_*` with
`decoded_record_index` and no detector, retention-time, scaling or unit claim. The
allowlisted stored FID/TCD text remains a native channel label only.

### YL-Clarity 9.1.0.76 — scientific signal

Five distinct local-only PRMs were paired by content with five same-run composite exports.
Each PRM has one FID and one TCD channel with 13,800 points. Across all five runs:

- all 138,000 exported time lexemes equal `format(i / 600, ".5f")`;
- `DStep=1`, `MinTicks=600`, time origin zero and the explicit export unit `min` agree;
- all 138,000 exported responses equal the stored binary32 values within the half-unit
  bound derived from the export's four decimal places;
- the transformation is identity, with explicit FID `pA` and TCD `mV` headers;
- every paired run has a unique full-series match; filename matching is not used.

This exact profile produces `Signals_FID` and `Signals_TCD`. Its x axis is retention time
in minutes; its y values are detector response in pA and mV respectively. It does not
write duplicate `Signals_Records_*` sheets for this previously unsupported profile.
The desktop writes these signal sheets automatically through **Inputs → Output → Preflight
→ Convert**. CLI users request the same rows explicitly:

```console
ordifile convert run.prm --include-signals --output Ordifile_Result.xlsx
```

## Exact detection boundary

Both profiles require the observed start/footer markers, an exact producer prefix,
consistent history/channel properties, duplicate byte-identical `RAWData6` and `PRMData`
gzip payloads, bounded decompression, record-size equations, finite binary32 values and an
allowlisted stored-label sequence. The 9.1 scientific profile additionally requires its
observed single-history, source-ordered FID/TCD layout with equal point counts. Unknown
versions and layouts fail closed.

The 9.0 profile retains its existing one-to-three history and TCD or FID/TCD structural
boundaries. Scientific equations validated for 9.1 are not transferred to 9.0.

## Peak-result boundary

The five 9.1 composite exports contain 21 TCD Result rows, but no repeatable bounded PRM
record containing their RT, Area and Height values was identified. Exact decimal, bounded
little-endian float32/float64 and evidence-guided candidate searches did not match those
rows. Stable `Integration`/`Peak` neighborhoods behaved as method/configuration data rather
than varying result records. Ordifile therefore emits no `PeakRecord`, does not perform
numerical integration and does not run automatic peak detection. The separate exact Result
CSV adapter remains the production route for explicit RT/Area/Height rows in its validated
standalone grammar.

## Privacy and interoperability

The two owner archives and all native/export members remain outside Git, wheels, sdists and
Actions artifacts. Runtime identities are SHA-256 aliases; private filenames, paths,
operator/sample/instrument values and measured arrays are not public output. Only hashes,
counts, units and comparison status are recorded in the sanitized manifest.

The parser is an independent interoperability implementation based on owner-controlled
bytes and paired official exports. It bundles no vendor source, DLL, executable or SDK and
changes no license, authentication or access-control mechanism. See the
[research notes](../research/youngin-yl-clarity-prm-raw-format-notes.md) and the
[sanitized 9.1 evidence manifest](../research/youngin-yl-clarity-prm-scientific-external-fixture-manifest.json).
