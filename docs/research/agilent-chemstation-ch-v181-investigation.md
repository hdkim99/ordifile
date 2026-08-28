# Agilent ChemStation `.CH` internal version 181 investigation

- Research and access date: 2026-08-16
- Implementation decision: **Experimental GO for structural decoded records**
- Runtime adapter: `agilent_chemstation_ch_v181`
- Public support claim: Experimental and capability-specific only
- Related fixture: `bsee-g6151510-fid1a-v181` in
  [`external-fixture-manifest.json`](external-fixture-manifest.json)

## Purpose

This investigation evaluates whether one exact Agilent ChemStation GC-FID channel
file is sufficient evidence for Ordifile's first proprietary adapter. The decision is
deliberately narrower than a general `.CH`, ChemStation, Agilent, or `.D` compatibility
claim.

The exact bytes and current public-reader signal outputs are reproducible. Retention
time, physical scaling, signal unit, and the final record's scientific role remain
unresolved. The owner-approved Experimental boundary therefore exposes all decoded
records by ordinal and raw integer only. It does not expose a retention-time axis,
apply the candidate slope/intercept, assign a physical unit, or claim Verified support.

## Fixture identity and handling

| Field | Verified value |
|---|---|
| Publisher | Bureau of Safety and Environmental Enforcement (BSEE) |
| Source page | [Side Wall Core Trim Extract GC Data Files](https://www.bsee.gov/stats-facts/ocs-regions/alaska/arctic-drilling/arctic-exploration-burger-j-well-data-2015/side-wall-core-trim-extract-gc-data) |
| Artifact | [FID1A.CH](https://www.bsee.gov/sites/bsee.gov/files/Alaska%20Region/Burger%20J%20Well%20Data/41_GC_EXTGC_Data_Files_FPC6188_Shell%20MC_HH-77445%209.30.15/G6151510.D/fid1a.ch) |
| HTTP last-modified | 2017-10-30 17:06:23 GMT |
| Size | 298,146 bytes |
| SHA-256 | `9abeb86b09d54c10e81f46648804acc0319b6e1d014cee54034eae91331f97ef` |
| Internal marker | `181` |
| Local handling | Gitignored external fixture only; not committed |
| Privacy review | No email, user-profile path, hostname, or absolute path observed |
| Redistribution basis | [BSEE privacy, copyright, and disclaimer](https://www.bsee.gov/bsee.gov/privacy-disclaimer) permits copying and distribution of BSEE public information with source acknowledgement |

The BSEE statement is an evidence-based redistribution decision, not a warranty about
every possible third-party right and not legal advice.

## Reproduced byte structure

All offsets below are zero-based and apply only to the exact fixture above. Numeric
header fields and the signal payload are big-endian. Text fields are length-prefixed
UTF-16LE strings. A repeatable observation is not automatically an authoritative
scientific interpretation.

| Offset | Encoding | Observed value | Evidence status |
|---:|---|---|---|
| `0` | one-byte length plus ASCII | length `3`, text `181` | Exact bytes verified; version role is public-reader evidence, not a vendor specification |
| `248` | big-endian `u32` | `181` | Exact value verified; discriminator role inferred from public readers |
| `264` | big-endian `u32` | `13` | Exact value verified; data-page role inferred from public readers |
| derived | `(13 - 1) * 512` | candidate payload begins at `6144` | Consistent with this file and public readers; role not vendor-specified |
| `278` | big-endian `u32` | `583` | Meaning unresolved; not the point count |
| `282` | big-endian `f32` | `-92.25` | Time-start candidate; semantics unresolved |
| `286` | big-endian `f32` | `7299708.0` | Time-end candidate; semantics unresolved |
| `347` | UTF-16LE Pascal text | `GC DATA FILE` | Exact text verified; discriminator role inferred |
| `858` | UTF-16LE Pascal text | sample text present | Encoding verified; value intentionally omitted |
| `1880` | UTF-16LE Pascal text | operator text present | Encoding verified; value intentionally omitted |
| `2391` | UTF-16LE Pascal text | local date/time text | Encoding verified; timezone absent |
| `2492`, `2533` | UTF-16LE Pascal text | generic inlet/GC text | Insufficient for a model claim |
| `2574` | UTF-16LE Pascal text | method identifier | Verified field presence |
| `3089` | UTF-16LE Pascal text | exact `Asterix ChemStation` | Exact producer-profile discriminator; other producer strings are outside the Experimental boundary |
| `4106` | big-endian `i16` | `2` | Detector-code meaning unresolved |
| `4122..4125` | two big-endian `u16` candidates | `10000`, `50000` | Sampling-ratio interpretation unresolved |
| `4134` | big-endian `u32` | `4` | Meaning unresolved; not used as a version |
| `4172` | UTF-16LE Pascal text | `cou` plus padding | Exact lexeme verified; unit meaning unresolved |
| `4213` | UTF-16LE Pascal text | empty | No separate description |
| `4724` | big-endian `f64` | `0.0` | Intercept candidate |
| `4732` | big-endian `f64` | `0.033854166666666664` | Slope candidate |
| `5524` | big-endian `i16` | `0` | Datatype mapping unresolved |

No header field containing the candidate decoded-record count `36501` was found, and
the scientific point count is not yet established. A future parser must bound record
decoding and require exact end-of-file consumption rather than trust a fixed-width size
formula or the unrelated value at offset `278`.

## Candidate signal payload interpretation

Starting the candidate decoder at byte `6144` consumes the remaining `292002` bytes
exactly. The public readers use this record interpretation:

- an ordinary record is interpreted as one big-endian signed 16-bit second delta;
- `0x7FFF` marks an absolute record;
- the marker is followed by a signed high 16-bit word and an unsigned low 32-bit word;
- the candidate absolute value is `high * 2^32 + low`;
- the candidate recurrence resets the first delta to zero after an absolute record.

For the selected file this yields:

| Observation | Value |
|---|---:|
| Candidate decoded records | 36,501 |
| Ordinary 2-byte records | 1 |
| Absolute 8-byte records | 36,500 |
| Raw integer range | 12,878 to 910,054 |
| Trailing bytes | 0 |
| Non-finite candidate scaled values | 0 |

The only ordinary record in this file has value zero and repeats the preceding
candidate absolute value. It could be a scientific sample or a terminal/padding
record. The file therefore exercises candidate absolute-record reconstruction and
exact EOF consumption, but it cannot establish a scientific point count or
independently validate the nonzero recurrence `delta += value; signal += delta` used by
the public readers.

ChromStream 0.2.0 and rainbow 1.4.0 produce the same 36,501 candidate signal values.
Applying the candidate expression `raw * slope + intercept` gives
`435.9739583333333` through `30809.119791666664`. This agreement does not verify the
physical scale: the readers may share upstream implementation assumptions, and no
paired ChemStation export exists for this run.

## Retention-time boundary

The public reader implementations disagree or rely on an unverified convention:

- ChromStream and the chemplexity/chromConverter lineage divide the two header
  candidates by `60000` and create an inclusive 36,501-value linear axis. This gives
  `-0.0015375` through `121.6618` minutes and approximately
  `0.1999945274` seconds between points.
- rainbow derives 36,500 time positions from `(file_size - 0x1800) // 8` while decoding
  36,501 signal values, so its result is internally misaligned for this file.
- Reading offsets `4122..4125` as the ratio `10000/50000` suggests `0.2` seconds, but
  that interval, 36,501 candidate records, and the two header endpoints do not all
  agree exactly. Treating the final zero record as terminal and using 36,500 values
  yields approximately `0.2000000068` seconds, which is close to the ratio candidate,
  but there is no evidence that authorizes dropping that record.

The evidence does not establish whether the header endpoints are inclusive, whether
the first point precedes or follows the stored start, whether the end is the last
sample or run stop time, whether the two `u16` values define a sampling interval, or
what the small negative start represents. Ordifile must not choose among these
possibilities by approximation. The Experimental adapter uses record ordinal x values
and leaves retention time unsupported.

## Scaling and unit boundary

Multiple readers apply the candidate slope and intercept, but the selected run has no
full-resolution ChemStation CSV or AIA/ANDI export for comparison. Parser agreement is
therefore structural evidence, not vendor validation of the physical values.

Agilent's [ChemStation G2070BA defect record](https://www.agilent.com/cs/library/support/patches/ssbs/G2070BA.html)
states in KPR 1652 that a signal unit read from `FID1A.CH` can have been recorded
incorrectly by the acquisition software. The selected fixture's exact header lexeme
`cou` must not be expanded to `count`, `counts`, `pA`, `mAU`, or another unit.

Current status:

- raw integer records: structurally decoded and exposed as Experimental;
- slope/intercept-transformed numeric signal: candidate transform only;
- physical signal unit: unresolved.

## Channel, detector, and time metadata

Agilent's [Understanding Your Agilent ChemStation](https://www.agilent.com/cs/library/usermanuals/public/G2070-91126_Understanding.pdf)
(G2070-91126, edition 07/09, ChemStation B.04.xx) describes `.D` as a data directory,
`*.CH` as signal data, and channel filenames as detector/module/channel identifiers.
That documentation supports the narrow reading of `FID1A.CH` as FID, module 1,
channel A. It does not establish that header code `2` means FID, that every `.CH` is
GC-FID, or that a single file represents a complete multi-channel acquisition.

The embedded date/time text is reproducible, but it has no timezone or UTC offset. It
may be retained as source text or a timezone-naive local value, but cannot establish an
absolute acquisition ordering across timezones. The exact GC model is not identified.

## Reader and license review

The readers were used only as research oracles. No parser code was copied into
Ordifile.

The external manifest records rainbow as `rejected` because `validated_with.result`
describes whether a reader is suitable as a complete fixture validator. The separate
reference summary records its narrower signal-sequence agreement and time-axis
failure; these are not contradictory acceptance claims.

| Reader | Inspected version or commit | Result | License and decision |
|---|---|---|---|
| [ChromStream parser](https://github.com/MyonicS/ChromStream/blob/2150f244d7054c0f48d9036a2a68673bd906826e/src/chromstream/parsers/agilent.py) | 0.2.0 / `2150f244d7054c0f48d9036a2a68673bd906826e` | Produces 36,501 candidate x/y values; declares adaptation from chemplexity | [MIT](https://github.com/MyonicS/ChromStream/blob/2150f244d7054c0f48d9036a2a68673bd906826e/LICENSE.md); research oracle only, no code copy |
| [chemplexity/chromatography](https://github.com/chemplexity/chromatography/blob/670ed772342a9c0440344682a02394a062c2467d/Development/File%20Conversion/ImportAgilentFID.m) | `670ed772342a9c0440344682a02394a062c2467d` | Public source of v181 offsets, delta decoding, axis, and scaling assumptions | [MIT](https://github.com/chemplexity/chromatography/blob/670ed772342a9c0440344682a02394a062c2467d/LICENSE); independent implementation preferred; notice required if adapted |
| [rainbow parser](https://github.com/evanyeyeye/rainbow/blob/da9b4f5babddaa5bf780539ac23b6a3f289f2997/rainbow/agilent/chemstation.py) | 1.4.0 / `da9b4f5babddaa5bf780539ac23b6a3f289f2997` | Signal values agree; overall fixture-reader result is rejected because its time count is one short | [LGPL-3.0](https://github.com/evanyeyeye/rainbow/blob/da9b4f5babddaa5bf780539ac23b6a3f289f2997/COPYING.LESSER); comparison only, no dependency or code copy |
| [Entab parser](https://github.com/bovee/entab/blob/e442ba72bd452c2ac2a1d0c98af55bb7316c2f22/entab/src/parsers/agilent/chemstation.rs) / [version switch](https://github.com/bovee/entab/blob/e442ba72bd452c2ac2a1d0c98af55bb7316c2f22/entab/src/parsers/agilent/metadata.rs#L56-L64) | source `e442ba72bd452c2ac2a1d0c98af55bb7316c2f22`, PyPI 0.3.3 | Version switch does not accept v181 | [MIT](https://github.com/bovee/entab/blob/e442ba72bd452c2ac2a1d0c98af55bb7316c2f22/LICENSE.md); not an implementation basis for this version |
| [chromConverter parser](https://github.com/ethanbass/chromConverter/blob/9137b85f341ceb4f2bc71cc171650af75449ac96/R/read_chemstation_ch.R) | 0.9.1 / `9137b85f341ceb4f2bc71cc171650af75449ac96` | Uses the same chemplexity-derived axis/scaling assumptions | [GPL >= 3 metadata](https://github.com/ethanbass/chromConverter/blob/9137b85f341ceb4f2bc71cc171650af75449ac96/DESCRIPTION) and [GPL text](https://github.com/ethanbass/chromConverter/blob/9137b85f341ceb4f2bc71cc171650af75449ac96/LICENSE.md); behavior comparison only, no code copy or integration |

The Apache Software Foundation's
[third-party license policy](https://www.apache.org/legal/resolved.html) classifies MIT
as Category A and GPL/LGPL as Category X. Ordifile is not an ASF project, but uses this
as a conservative Apache-2.0-only distribution review aid. It is not legal advice.

## Architecture decision

The present `FormatAdapter` v1 could represent a verified standalone,
single-channel `.CH` as one source, one sample, and one uninterpolated signal. It
cannot represent a complete `.D` directory, required siblings, or multi-channel run
grouping without a future compound-input API.

The adapter uses that v1 boundary for a standalone file only. It introduces an
explicit `decoded_records` series kind and Experimental descriptor status so structural
records cannot be mistaken for verified scientific signals. Every 36,501 candidate
record is retained; x is record ordinal and y is the unscaled decoded integer. A `.D`
directory, siblings, multi-channel grouping, other versions, and write support remain
outside this adapter.

## Required evidence before Verified status

For the same run, obtain:

1. the original `FID1A.CH`;
2. exact ChemStation product, revision, and build;
3. GC model and FID front/back, module, and channel configuration;
4. a full-resolution official signal CSV export;
5. an AIA/ANDI `SIGNALxx.CDF` export;
6. a record showing that neither export was bunched or downsampled;
7. vendor UI or file-information values for first/last time, point count, sampling
   interval or rate, run duration, signal unit, and selected signal values;
8. SHA-256 digests for native `.CH`, CSV, and CDF;
9. first, middle, and last ten-point comparisons;
10. the export rounding precision and acquisition timezone setting; and
11. explicit permission for local reproducible testing or redistribution.

At least three normal v181 runs with different durations and signal scales are
preferred. At least one must contain a nonzero ordinary record so the second-delta
recurrence can be checked rather than inferred. At least one must be the exact BSEE
file opened in ChemStation and exported by the official software so that its current
hash can be compared directly.

Verified scientific-signal support requires all of the following:

- a nonzero chained ordinary record agrees with the candidate second-delta recurrence and the
  official export;
- first/last time and interval construction are unambiguous;
- header start/end and offsets `4122..4125` have verified meanings;
- the official export resolves whether there are 36,500 or 36,501 scientific points
  and whether the final zero record is a sample or terminal record;
- `raw * slope + intercept` agrees with the official export under a justified
  tolerance;
- the unit is verified, or an explicit scientifically acceptable unitless policy is
  approved;
- timestamp reliability and timezone policy are defined;
- normal, unsupported-version, corrupt, and truncated cases are reproducible; and
- fixture use, privacy, attribution, and redistribution boundaries are documented.

Until then, Issue #3 remains open and the adapter remains **Experimental**. No release
may describe its output as calibrated intensity, retention-time signal, or Verified
Agilent raw support.


## Where Agilent keeps its peak table (v179 evidence)

A CC BY 4.0 Agilent 6890N GC-FID corpus of 2,677 `.D` run directories was inspected without
downloading the 481 MB archive: the ZIP64 central directory and a few individual members were
read with HTTP range requests.

The `.ch` signal file does **not** carry the vendor peak table. Every Area and retention time
of one run's official report was searched in its paired `\x03179` `.ch` as binary32 and
binary64, little- and big-endian; the only hit was a zero Area matching zero bytes in the
header. The vendor's processed rows live instead in a sibling report export inside the same
`.D` directory.

That export is a headerless UTF-16LE CSV with a byte-order mark and seven columns - peak
number, retention time, separation code such as `BB`/`BV`/`VB`, width, Area, Area percent, and
compound name. Eight files sampled from different months and instrument folders all had the
same shape. There is no Start or End time. Its filename is produced by a site macro rather
than by ChemStation itself, so any adapter must detect it by content, never by name.

This places Agilent in a third category, distinct from the two already implemented:

| Format | Signal in the raw file | Vendor result table |
|---|---|---|
| YoungIn `.PRM` | yes | nowhere in the file; only integration markers, so the calculation is reconstructed |
| Shimadzu `.GCD` | yes | inside the same document, read directly |
| Agilent `.ch` | yes | only in a sibling file inside the `.D` directory |

Supporting Agilent results therefore needs `.D` directory intake, which decision record entry
for the v181 adapter currently lists as unsupported, plus a content-only fingerprint strong
enough to tell a headerless seven-column report CSV from any other CSV. Neither is a
calculation problem.

## `.D` directory shape, and why directory intake is not the next step

The same corpus was inventoried from its ZIP64 central directory, so all 2,692 `.D`
directories were measured without downloading the archive.

| Observation | Count |
|---|---:|
| `.D` directories | 2,692 |
| Distinct top-level skeletons | 7, one covering 2,653 |
| `RUN.LOG` and `SAMPLE.MAC` present | 2,692 (100%) |
| `ACQ.M/` and `DA.M/` present | 2,675 |
| Exactly one `*.CH` present | 2,678 |

A candidate container key of "`.D` suffix, plus `RUN.LOG`, `SAMPLE.MAC`, `ACQ.M/` and
`DA.M/`, plus exactly one `*.CH`" selects 2,675 directories and rejects 17, with no
directory passing the skeleton yet failing the single-signal condition.

Two limits matter more than that consistency.

First, the corpus is one laboratory, one instrument and one method: every signal file is
named `FID3A.CH`, and every report export is named from the site's own macro
(`OGE00.CSV`, `OGE01.CSV`, and `A` duplicates). Consistency here shows that a workflow is
internally regular. It does not establish that the skeleton generalises to other
ChemStation installations, and it positively demonstrates that the report filename cannot
belong to any shared key. The container shape does not say which of the four exports is
the peak table either; that assertion has to come from the researcher.

Second, and decisively for sequencing: the signal these directories contain is internal
version `179`, which the exact v181 adapter rejects. Directory intake exists to join peaks
to their signal in one workbook source, and there is no readable signal to join. Until a
`.ch` generation in this corpus is decodable, `.D` intake would add a container model, a
reuse-key store and a per-directory question to the interface while producing exactly what
mapping the export alone already produces.

Directory intake is therefore deferred. The evidenced next step for Agilent is signal
support for the `179` generation, which is an ordinary single-file adapter question and
changes no interface.
