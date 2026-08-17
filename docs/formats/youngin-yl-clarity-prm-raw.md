# YoungIn YL-Clarity PRM raw-record profile

- Status: Experimental
- Adapter: `youngin_yl_clarity_prm_raw`
- Observed producer profile: YL-Clarity `9.0.1.19`
- Real-fixture evidence: 23 owner-supplied, local-only completed `.PRM` files
- Scientific chromatogram status: not verified

This adapter is a structural converter, not a calibrated chromatogram reader. It
preserves the ordered native binary32 records from one exact observed PRM profile and
keeps every scientific interpretation that lacks evidence out of the output.

## Output

Each bounded current raw block becomes one decoded-record series:

- x: `decoded_record_index`, starting at zero;
- y: `decoded_raw_binary32`, preserving the native stored value;
- channel: the allowlisted `FID` or `TCD` label stored by the file, marked
  Experimental rather than independently verified;
- detector: unset;
- x and y units: unset;
- scaling: not applied;
- peaks: unsupported.

The workbook uses `Signals_Records_*` sheets. These rows are not ordinary scientific
`Signals_*` rows and the index is not retention time. Every runtime sample ID is the
content-derived `PRM_<first 16 source SHA-256 characters>` pseudonym. The adapter does
not inspect basenames for FID/TCD grouping and exports no filename-derived group.
Privacy-safe staged aliases are used only by the local maintainer oracle to aggregate
the owner-supplied fixture set; they are not runtime metadata or detector evidence.

Every public source reference for this adapter is the
core-generated `source-<full SHA-256>` alias. It is used by API and CLI results,
progress events, sort keys, issues, `Samples`, and `Import_Log`, including corrupt PRM
files that fail parsing. Files that cannot be hashed use a deterministic input-order
fallback. Adapter-provided aliases are never trusted. Generic tabular formats retain
their existing relative-path behavior; see the
[manufacturer-neutral policy](../architecture/source-identity-policy.md).

## Exact observed boundary

Detection requires all of the following, not only the `.prm` suffix:

- the observed four-byte start marker;
- the bounded YL-Clarity `9.0.1.19` producer prefix;
- consistent chromatogram revision and channel-count properties;
- one or two current raw blocks after the highest observed revision;
- the observed `RAWData6` / `RAWSize` / `PRMData` / `DetName` source order;
- matching duplicate compressed `RAWData6` and `PRMData` payloads;
- one exact gzip member per block, with CRC, length, decompression and record limits;
- a declared record count equal to the decoded byte length divided by four;
- only finite little-endian IEEE-754 binary32 records;
- an allowlisted stored label profile of `TCD` or source-ordered `FID`, `TCD`;
- the exact observed end-relative footer marker.

Unknown labels, channel layouts, producer profiles, malformed history, changed
duplicates, non-finite values, truncation, decompression overflow, and unexpected
boundaries are rejected with structured errors. One bad file does not invalidate
unrelated files in a batch.

## Evidence and limitations

All 23 local files passed the exact structural gates. Together they contain 43 current
raw blocks and 563,240 finite records. Repeated extraction is deterministic and a
local-only integration test reopens one workbook containing all files. The source
archive and native PRM files are neither committed nor uploaded as Actions artifacts.

OpenChrom publicly lists a separately distributed proprietary DataApex FID PRM
converter, but its current public application has no automated headless import path and
the converter is not bundled or used by Ordifile. DataApex documents official PRM
export routes; an independently confirmed same-run export has not yet been supplied.

The following remain unsupported or unresolved:

- retention-time origin, interval, axis and unit;
- physical/display scaling and calibrated response;
- physical detector units;
- independent verification of the stored FID/TCD label semantics;
- peak tables, integration, calibration and identification;
- profiles other than the exact observed producer/layout;
- acquisition/recovery `.RAW`, Autochro, GC-MS, directory grouping and write support.

Promotion to Verified requires paired official output and additional independent PRM
runs that confirm time, scaling, unit and detector semantics. See the
[research notes](../research/youngin-yl-clarity-prm-raw-format-notes.md).
