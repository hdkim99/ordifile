# YoungIn YL-Clarity Result export investigation

- Date: 2026-08-18
- Status: `LOCAL_VENDOR_EXPORT_BRIDGE_READY`; exact OEM pilot blocked because a
  bounded search found no YL-Clarity installation in the accessible Windows
  environment. License state was not assessed because no installation was found.
- Native source: 23 owner-provided YL-Clarity 9.0.1.19 PRM files, local-only
- Public support claim: none until an actual vendor-generated export passes the exact
  adapter and full source-to-workbook comparison gates

## Product boundary

The existing PRM adapter intentionally exposes deterministic structural records, not
computed peak results. Result support does not require reverse engineering a result
table inside PRM. The supported development path is instead:

```text
read-only PRM -> licensed YL-Clarity -> Result Table export
              -> exact result adapter -> PeakRecord -> workbook
```

YL-Clarity remains a local vendor oracle. It is not a runtime dependency, CI
dependency, redistributed binary, or authentication target.

## Official automation evidence

DataApex documents Young Lin's YL-Clarity as a Clarity OEM. Current Clarity command
documentation accepts a PRM path as a positional argument, then processes subsequent
commands in order. It documents `export_results=PATH` for the active chromatogram and
`prm_close_discard` for closing without saving. It does **not** document a `prm_open`
command. The exact YL-Clarity 9.0.1.19 OEM surface must therefore be proven by a
one-file pilot rather than inferred from generic Clarity documentation.

The command line has a documented 126-character limit and may be recorded in the
Audit Trail. The bridge consequently uses short SHA-derived staging names, passes no
credentials, handles one temporary PRM at a time, and never logs source basenames or
paths.

`export_results` uses the active desktop's **Export Data** settings. A usable export
must contain a Result Table, table headers, explicit retention time and explicit area.
Fixed Format is preferred when it provides those fields. For multi-signal runs, **All
Signals Results Table** may add `Signal Name`; total and all-signals-total rows are not
peak observations. Full Format is avoided because it can add private filename and time
metadata.

Official documentation describes retention/start/end time in minutes, area in
detector-units multiplied by seconds, and height in detector units. An eventual
adapter will nevertheless use the actual exported headers as its source of truth and
will leave physical units unknown when those headers do not establish them.

## Local environment result

One owner-provided archive was confirmed to contain 23 non-empty PRM members and to
pass ZIP integrity checks. It remains ignored, untracked and unmodified. An accessible
Windows environment is available for the bridge, but bounded registry, installed-app,
shortcut, program-directory and process discovery found no YL-Clarity, Clarity,
YoungIn or Chromass installation. No installer was found. The OEM command surface,
direct PRM open, export settings and Result Table contents are therefore unresolved,
not failed.

## Local bridge contract

The maintainer-only bridge under `scripts/local/`:

1. accepts a PRM file, directory or ZIP without changing the source;
2. computes each source SHA-256, uses short SHA-derived command-workspace names to
   satisfy the documented length bound, and uses `source-<full-sha256>` for every
   persistent output and manifest identity;
3. discovers a normal installed executable through explicit input or bounded Windows
   installation records, never by modifying PATH;
4. stages one temporary SHA-addressed copy, never passes the original source to the
   vendor, invokes positional PRM open, `export_results`, then `prm_close_discard`, and
   never requests save or reintegration;
5. verifies source SHA-256 again, bounds command length, time, count and output size,
   and isolates per-file failures;
6. requires a non-empty export with headers that identify retention time and area;
7. records only sanitized hashes, counts, statuses and header capabilities in a
   local-only manifest.

The manifest follows
[`youngin-yl-clarity-result-export-local-manifest.schema.json`](youngin-yl-clarity-result-export-local-manifest.schema.json).
Its table counts are explicitly structural: summary rows may be present, so no value
is labelled a peak count before the exact result grammar is established.

The `--batch` path is pilot-gated: it attempts the first deterministic input, stops
without opening the remaining sources if the explicit RT+Area gate fails, and only
then continues with per-file failure isolation. A normally licensed workstation can
run it once:

```powershell
py scripts/local/youngin_yl_clarity_export_bridge.py <prm-or-directory-or-zip> `
  --output <outside-git-or-ignored-local-output> --batch `
  [--executable <vendor-executable>]
```

If a Result export is created but explicit RT or Area headers are absent, the only
requested GUI action is to enable **Result Table**, **Table Headers**, **Text File** and
preferably **In Fixed Format** in **Export Data**, then rerun the bridge. The bridge
does not edit the binary `.DSK` settings.

To prevent an accidental `git add`, output inside any Git worktree is rejected unless
it is below Ordifile's fixed `.external-fixtures`, `.research-downloads`, or
`fixture-cache` ignored roots. Output outside a Git worktree remains permitted.

The bridge does not parse arbitrary result rows into the public API. Once an actual
export exists, adapter implementation starts from its exact encoding, delimiter,
producer/profile evidence, headers, signal layout and units. A bare generic TXT or CSV
without sufficient producer evidence must not be auto-claimed as YoungIn data.

## Adapter gate

`youngin_yl_clarity_result_export` remains unimplemented until a vendor-generated
pilot proves explicit RT and area. The next statuses are:

- bridge present, application unavailable: `LOCAL_VENDOR_EXPORT_BRIDGE_READY`;
- pilot export with RT and area: `RESULT_EXPORT_GENERATED`;
- exact adapter work begun: `IMPLEMENTATION_IN_PROGRESS`;
- full real comparison, synthetic collision tests, privacy/legal review and
  cross-vendor workbook validation complete: `EXPERIMENTAL_GO`.

No RT matching, compound inference, peak reintegration, raw/result runtime dependency,
or cross-vendor area normalization is introduced.

## Privacy, license and redistribution

The PRM files, generated exports, local manifests and vendor application remain
local-only. Only synthetic fixtures may be committed. The bridge uses ordinary
licensed product functionality and must not bypass a key, dongle, password,
registration or authentication control. Vendor executables, DLLs and keys are never
bundled. Manufacturer and product names are used only for compatibility
identification.

## Official sources

- [DataApex: New OEM cooperation](https://www.dataapex.com/news/26748/new-oem-cooperation)
- [YOUNGIN Chromass: YL-Clarity Chromatography Data System](https://eng.youngincm.com/goods/read.php?M2_IDX=18459&SC_BOOKMARK=N&SC_SC1_IDX=404&SC_SC2_IDX=1082&SC_SF_IDX=Array&SP_CODE=19113EE3)
- [DataApex: Command-line parameters](https://www.dataapex.com/documentation/Content/Help/110-technical-specifications/110.020-command-line-parameters/110.020-command-line-parameters.htm)
- [DataApex: Export Data](https://www.dataapex.com/documentation/Content/Help/020-instrument/020.050-setting/020.050-export-data.htm)
- [DataApex: Export of results](https://www.dataapex.com/documentation/Content/lims/020-workflows-in-clarity/020-070-export-results.htm)
- [DataApex: Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-result-table.htm)
- [DataApex: All Signals Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-all-signals-results.htm)
- [DataApex: Clarity End User License Agreement](https://www.dataapex.com/downloads/26027/view)
