# YoungIn YL-Clarity PRM raw-record format notes

- Date: 2026-08-17
- Status: `RAW_CONVERSION_GO`; scientific semantics pending
- Scope: one observed YL-Clarity `9.0.1.19` completed-PRM profile
- Fixture policy: 23 owner-supplied files, local-only and not redistributable

These notes record independently observed file facts. They are not a vendor binary
specification. No vendor executable, DLL, proprietary OpenChrom converter, GPL source,
or protected source code was copied, translated, bundled, or used as a runtime
dependency.

## Aggregate fixture facts

The ignored source archive is 3,083,937 bytes with SHA-256
`4af61e1aa8abef3694a4c24a28203b0a1d382a11b6442c3e9b43653487f97fe5`.
Its safe intake contains 23 distinct PRM files. Public records use only aggregate
counts, hashes and privacy-safe aliases; original member names and embedded metadata
values remain local.

| Observation | Result |
|---|---:|
| PRM files | 23 |
| Current structural blocks | 43 |
| Dual stored-label profile | 20 files, `FID` then `TCD` |
| Single stored-label profile | 3 files, `TCD` |
| Total finite binary32 records | 563,240 |
| Record-count distribution | 11,970 x 2; 11,980 x 1; 13,180 x 32; 13,190 x 6; 13,210 x 2 |

The decoded values are deterministic. The canonical batch-digest scheme and aggregate
digest are public reference facts, and the local external test asserts that full
digest. Native bytes, original per-file names and per-file source hashes remain local
and are not placed in Git or release artifacts.

## Structural grammar

Every file starts with the same four bytes, `5a a5 00 08`. The value is an observed
signature only; it is not interpreted as software version 8. All files contain a
bounded UTF-16LE producer prefix for YL-Clarity `9.0.1.19`; the adjacent license/serial
suffix is sensitive and is never parsed or exposed.

The active raw blocks occur only after the greatest and last `ChromVersion1` entry.
The observed revision sequences are `[1]`, `[1, 2]`, or `[1, 2, 3]`, and the revision,
method and log-data counts agree. DataApex documentation describes the most recent
stored method as current and historical versions as read-only. Earlier revision
intervals contain no separate raw snapshot in these files, so the adapter exposes one
current/global raw set and records the revision boundary as Experimental metadata.

Each of the 43 active blocks has this source order:

```text
RAWData6 -> RAWSize -> PRMData -> DetName
```

`RAWData6` and `PRMData` are typed, little-endian-length-prefixed gzip blobs. Within
each block their compressed bytes are identical. `RAWSize` and the second structural
size candidate both equal the decompressed length divided by four. The observed step
and tick candidates are fixed structural values but are not converted into time.

The gzip payload is an array of little-endian IEEE-754 binary32 values. All observed
records are finite. Reinterpreting the same bytes as big-endian produces non-finite and
implausibly large values and is rejected by the evidence.

`DetName` is a bounded UTF-16LE field exactly associated with each active block. Only
the stored labels `FID` and `TCD` occur. The adapter uses these as Experimental native
channel labels while leaving `SignalSeries.detector` unset. The labels do not authorize
detector-specific scaling or units.

## Independent references

- DataApex documents `.PRM` as the completed Clarity chromatogram and documents
  `.CDF`, `.CHR`, `.TXT` and `.ASC` export routes, including `prm_export`.
- DataApex documents chromatogram history and the read-only role of older methods.
- YOUNGIN documents YL-Clarity as a Clarity OEM and documents FID/TCD configurations.
- OpenChrom lists a DataApex FID PRM converter, but the converter is proprietary,
  installed separately through the GUI, absent from the open-source core, and not a
  lawful implementation dependency. OpenChrom 1.5 and later removed the prior public
  command-line import path.
- chromConverter has no native PRM parser; its old GPL bridge depended on OpenChrom
  1.4 or earlier and is comparison-only.

The current OpenChrom converter could not be run in a privacy-safe automated local
mode. This is recorded as `Unavailable`, not as negative parser evidence.

## Peak-result audit and vendor-export bridge

The 23 local PRM files were also audited specifically for an integrated peak/result
table before any result parser or canonical-model change was considered. The current
revision contains 43 `RAWData6` blocks and 43 byte-identical `PRMData` duplicates, but
no separate deterministic result blob or populated table carrying retention time plus
area. Searches for structured peak-result fields tying retention time, area, height,
width, component/compound identity and result-channel references together did not
establish a result-record grammar. The separately validated `DetName` field labels raw
blocks; it is not a peak-result row. Observed `PeakWidth` configuration and `ATime` /
`BTime` event fields belong to method/event state and are not evidence of integrated
peaks. No populated calibration linkage or same-run result companion was present.

DataApex documents separate export paths. `prm_export` creates CDF/CHR/TXT/ASC
chromatogram curves and is a future signal/time-axis oracle. The GUI **Export Data**
Result Table path and command-line `export_results` path export active-chromatogram
results; the GUI can write result tables to TXT/CSV or XLS/XLSX. DataApex's Result Table
documentation identifies peak rows and retention-time ordering and explains that the
visible fields and units depend on active signal, calibration and table settings. The
current fixtures establish neither a YL-Clarity Result Table companion nor deterministic
RT/area extraction. YoungIn raw-record conversion therefore remains GO, while result
evidence is now generated actively through the ordinary licensed vendor application.
The local bridge stages a temporary SHA-addressed PRM copy, never passes the original
source to the vendor, invokes positional PRM open, `export_results` and
`prm_close_discard`, validates explicit RT+Area headers, and records a sanitized local
pairing manifest. No `PeakRecord` field or result adapter is introduced from marker
names alone. The exact OEM pilot is currently blocked because a bounded search found
no YL-Clarity installation in the accessible Windows environment; the operational
state is `LOCAL_VENDOR_EXPORT_BRIDGE_READY`, not an indefinite fixture request.

The eventual result path is manufacturer-neutral: standalone Agilent, Shimadzu and
YoungIn result adapters should map evidence-backed result rows into the existing
`PeakRecord` model and common `Peaks` / `Peak_Matrix` sheets. Raw-signal extraction is
optional and separate from the result-first consolidation path.

## Capability decision

| Capability | Status |
|---|---|
| Exact observed profile detection | Experimental, fixture-backed |
| Deterministic raw binary32 extraction | Experimental GO |
| Stored channel-label separation | Experimental |
| Maintainer FID/TCD fixture grouping | Local external oracle only; not runtime output |
| Independently verified detector identity | Unverified |
| Retention-time axis | Unsupported |
| Physical/display scaling | Unsupported |
| Physical unit | Unknown |
| Peak table | Unsupported |
| Batch PRM to one workbook | Experimental GO |
| Verified scientific chromatogram | Blocked by paired export |
| Vendor Result export bridge | Local-only ready; exact OEM pilot not yet run |

## Verified promotion inputs

- a same-run YL-Clarity/Clarity Result Table exported through GUI **Export Data** or
  `export_results` as CSV, TXT, XLS or XLSX, as the primary RT/area oracle;
- a separate same-run `prm_export` CDF, CHR, TXT or ASC chromatogram curve for signal
  and time-axis verification;
- independent PRM runs with different lengths and detector configurations;
- exact agreement for point count, full value sequence and channel identity;
- retention-time origin and interval confirmation;
- physical/display scaling and unit confirmation;
- cross-fixture malformed and regression coverage.

## Sources

- [DataApex: YL-Clarity OEM announcement](https://www.dataapex.com/news/26748/new-oem-cooperation)
- [DataApex: Clarity terms and PRM lifecycle](https://www.dataapex.com/documentation/Content/Help/100-list-of-terms/100.000-list-of-terms/100-list-of-terms.htm)
- [DataApex: chromatogram history](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.010-file/030.010-open-chromatogram.htm)
- [DataApex: chromatogram export](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.010-file/030.010-export-chromatogram.htm)
- [DataApex: Export Data](https://www.dataapex.com/documentation/Content/Help/020-instrument/020.050-setting/020.050-export-data.htm)
- [DataApex: Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-result-table.htm)
- [DataApex: `prm_export`](https://www.dataapex.com/documentation/Content/Help/110-technical-specifications/110.020-command-line-parameters/110.020-command-line-parameters.htm)
- [YOUNGIN: YL-Clarity configuration guidance](https://file.younglin.com/Service_Note/23_YCM_Service_Note_SNSW-202112-02.pdf)
- [OpenChrom format catalogue](https://www.openchrom.net/)
- [OpenChrom converter installer](https://converter.openchrom.net/)
