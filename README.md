# Ordifile

[한국어](https://github.com/hdkim99/ordifile/blob/main/README.ko.md)

[![CI](https://github.com/hdkim99/ordifile/actions/workflows/ci.yml/badge.svg)](https://github.com/hdkim99/ordifile/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ordifile)](https://pypi.org/project/ordifile/)
[![Python 3.11–3.14](https://img.shields.io/badge/Python-3.11%E2%80%933.14-blue)](https://github.com/hdkim99/ordifile/blob/main/pyproject.toml)
[![Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue)](https://github.com/hdkim99/ordifile/blob/main/LICENSE)

Batch-convert and consolidate scientific instrument results into one clean, ordered
and auditable Excel workbook.

Ordifile's proprietary-format direction is **result-first**: evidence-backed retention
time and area tables from Agilent, Shimadzu, YoungIn and LECO should converge on the same
`Peaks` / `Peak_Matrix` workbook model. Raw signals are an optional, independently
validated capability: a result export does not require its raw file to be present.
Each vendor result adapter remains a separate exact-format
reader, but its verified peak rows behave identically after canonical conversion. No
vendor result parser is claimed before an actual result fixture proves its field
boundaries and semantics.

**Verified stable formats:** CSV, TSV, semicolon-delimited TXT, and audited non-macro
XLSX using Ordifile's documented schema. The current development source tree also
includes eight narrowly bounded Experimental proprietary readers described below; this
is not general vendor-format support. Published availability is shown by the PyPI badge.

![An actual Ordifile CLI conversion of three synthetic files](https://raw.githubusercontent.com/hdkim99/ordifile/main/docs/assets/ordifile-demo.gif)

```text
sample_1.csv   sample_2.tsv   exported_peaks.xlsx
          \          |          /
           ordifile convert ...
                    |
                    v
          Ordifile_Result.xlsx
          ├── Manifest
          ├── Samples
          ├── Peak_Matrix
          ├── Peaks
          ├── Metadata
          └── Import_Log
```

## Install

Install the latest published Ordifile release from PyPI. The PyPI badge above shows the
currently available version.

```bash
python -m pip install --no-cache-dir ordifile
```

The Experimental desktop interface is first included in Ordifile v0.4.0. Until the
PyPI badge shows v0.4.0 or newer, use a source checkout. The optional extra keeps
existing CLI installations free of a Qt runtime dependency:

```bash
python -m pip install -e ".[gui]"
ordifile-gui
```

After v0.4.0 is published, the same interface can be installed with
`python -m pip install 'ordifile[gui]'`. This is a Python-package GUI, not a standalone
`.exe` or `.app`.

## Quick start

```bash
python -c "from pathlib import Path; p=Path('ordifile_demo'); p.mkdir(exist_ok=True); [(p / f'sample_{n}.csv').write_text(f'sample_id,retention_time,area,compound\nsample_{n},{n / 10:.1f},{n * 10},demo\n', encoding='utf-8') for n in (1, 2, 10)]"
ordifile convert ordifile_demo --sort filename --output Ordifile_Result.xlsx
```

This package-independent synthetic example produces:

```text
Input paths: 1
Discovered files: 3
Processed 1/3: success sample_1.csv
Processed 2/3: success sample_2.csv
Processed 3/3: success sample_10.csv
Export started: Ordifile_Result.xlsx
Output ready: Ordifile_Result.xlsx
Status: success
Output: Ordifile_Result.xlsx
Successful files: 3
Files with warnings: 0
Failed files: 0
Duplicate files: 0
Sort requested: filename
Sort used: filename
Sort reason: User requested filename ordering.
Sheets: Manifest, Samples, Peak_Matrix, Peaks, Metadata, Import_Log
```

The source files remain unchanged. Natural filename ordering keeps `sample_2` before
`sample_10`.

![The Samples sheet read back from the generated Ordifile workbook](https://raw.githubusercontent.com/hdkim99/ordifile/main/docs/assets/ordifile-workbook.png)

## Experimental desktop interface

The optional desktop interface provides **Add Files**, **Add Folder**, and local
file-manager drag and drop, followed by authoritative format inspection through the
same public registry and pipeline used by the CLI. Choose one of the five existing
sort modes and an `.xlsx` output, then convert in a background worker while progress
and per-file success, warning, or failure remain visible.

![The implemented Ordifile desktop interface using synthetic public-safe inputs](https://raw.githubusercontent.com/hdkim99/ordifile/main/docs/assets/ordifile-desktop.png)

The interface is offline-only: it has no upload, cloud, telemetry, embedded browser,
or vendor-executable integration. It does not silently replace an existing workbook.
Add buttons, visible labels, keyboard focus order, and accessible names provide a
keyboard path equivalent to drag and drop. Forced cancellation is intentionally
omitted until the public core can preserve workbook transaction safety during
cancellation. Issue #6 now has a maintainer-only unsigned standalone prototype,
documented in the [standalone runbook](docs/standalone.md). No `.exe` or `.app` is
publicly released: publisher identity, signing, notarization, LGPL
replacement/relinking evidence and the final redistribution gate remain blocked. The
Python-package interface above is the supported installation path.

## Verified formats

| Built-in format | Metadata | Peaks | Signals | Status | Synthetic fixture |
|---|---:|---:|---:|---|---:|
| Generic comma-delimited CSV | Yes | Explicit columns | Explicit `time` + `signal` rows | Verified | Yes |
| Generic tab-delimited TSV | Yes | Explicit columns | Explicit `time` + `signal` rows | Verified | Yes |
| Generic semicolon-delimited TXT | Yes | Explicit columns | Explicit `time` + `signal` rows | Verified | Yes |
| Generic non-macro XLSX table | Yes | Explicit columns | Explicit `time` + `signal` rows | Verified | Yes |

“Generic” means the first row uses the [documented column
schema](https://github.com/hdkim99/ordifile/blob/main/docs/formats/generic-tabular.md). It does not mean arbitrary vendor exports.
An extension is supporting evidence only; Ordifile also checks content and schema.
Run `ordifile formats` to see the adapters installed in the current environment.

## Experimental proprietary adapters

| Format boundary | Metadata | Peaks | Output | Status | Real fixture |
|---|---:|---:|---|---|---:|
| Agilent ChemStation `.CH` internal version 181, exact GC-FID profile | Field-specific | No | All structural decoded records | Experimental | One external BSEE file |
| Agilent ChemStation Result XML, exact `C.01.10 [201]` single `FID1/A` Percent/Area profile | Scientific allowlist | ResultsGroup peaks | RT (min) + area (pA\*s) + height (pA); no raw signal | Experimental | One external CeCILL-2.1 fixture |
| Shimadzu LabSolutions 5.82 `.GCD`, GC-2014 / single `SFID1` profile | Field-specific | No | Retention time (min) + signal (uV) | Experimental | One external CC0-declared file + paired same-run ASCII reference |
| Shimadzu LabSolutions result ASCII, exact 5.82 GC-2014 / single `SFID1` `Ch1` profile | Scientific allowlist | Peak Table rows | RT/start/end (min) + area + height (units unresolved); no raw signal | Experimental | One external controlled-CI fixture + paired same-run GCD |
| Shimadzu GCMSsolution `.QGD`, exact `4.00` TIC profile | Field-specific | No | Retention time (min) + raw TIC (unit unknown); MS1 not exported | Experimental | One external Dryad CC0 file |
| YoungIn YL-Clarity `.PRM`, exact observed `9.0.1.19` profile | Structural allowlist | No | Stored-label channels + ordered raw binary32 records; no time axis or unit | Experimental | 23 owner-supplied local-only files |
| YoungIn YL-Clarity Result Table, exact owner-validated CP949/tab `.csv` profile | Scientific allowlist | Source peak rows | RT (min) + area (mV.s) + height (mV); no raw signal | Experimental | Two owner-generated local-only exports |
| LECO ChromaTOF 4.72.0.0 GCxGC Result text, exact observed profile | Scientific allowlist | Source peak rows | RT1/RT2 (s) + area/height (AU); no raw signal | Experimental | One external Dryad CC0 non-human file |

These Experimental adapters have the exact capability boundaries below. Unsupported
profiles are rejected rather than interpreted broadly.

The Agilent `.CH` adapter retains every
decoded record in source order. Its x values are `decoded_record_index`, not retention
time; its y values are `decoded_raw_integer`, not physically scaled intensity. Units,
scientific point count, and the final record's role remain unresolved. It does not
claim other `.CH` versions, `.D` directories, TCD, MS, peaks, calibrated values, or
write support. See the [exact capability and safety boundary](https://github.com/hdkim99/ordifile/blob/main/docs/formats/agilent-chemstation-ch-v181.md).

The separate Agilent Result XML adapter reads one exact ChemStation
`C.01.10 [201]`, single `FID1/A`, `Percent`/`Area` report profile without requiring a
raw sibling. It maps the canonical `ResultsGroup/Peak` rows to source-order peaks,
retains explicit min, pA\*s and pA units, and checks every RT/area/height decimal string
against its duplicate integration row. Peak boundaries are preserved, calibrated
nonblank `Name` values map to `compound`, and source labels `FID1`/`A` map separately
to canonical detector/channel `FID`/`FID1A`. Other revisions, multiple signals,
detectors, quantitation modes, raw chromatograms and write support are rejected or
unsupported. The external fixture remains controlled-CI only because it includes
privacy-bearing run metadata. See the [exact capability and safety boundary](https://github.com/hdkim99/ordifile/blob/main/docs/formats/agilent-chemstation-result-xml.md).

The Shimadzu adapter is limited to an exact LabSolutions 5.82, GC-2014,
single-channel `SFID1`, `uV`, identity-factor profile. Its 66,255-point retention-time
and signal series were compared point by point with a same-run LabSolutions ASCII
reference. It does not claim other LabSolutions or GCsolution versions, detectors,
channels, factors, GCD profiles, peaks, `.QGD`, `.LCD`, or write support. See the
[exact capability and safety boundary](https://github.com/hdkim99/ordifile/blob/main/docs/formats/shimadzu-gcsolution-gcd.md).

The separate Shimadzu result ASCII adapter reads one exact LabSolutions 5.82,
GC-2014, single `SFID1` / `Ch1` export without requiring a raw sibling. It preserves
all source `Peak#` values and independent source observation order, maps `R.Time`,
`I.Time`, and `F.Time` to retention/start/end time in minutes, and retains area and
height without inventing physical units. The exact fixture has no compound IDs or
names, so no compound identity is emitted. Its embedded private metadata is omitted
and its public source is a SHA-256 alias. Other software versions, instruments,
detectors, channels, identified-compound tables, multiple peak sections and arbitrary
LabSolutions text exports are unsupported. See the
[exact capability and safety boundary](https://github.com/hdkim99/ordifile/blob/main/docs/formats/shimadzu-labsolutions-result-ascii.md).

The separate QGD adapter is limited to one exact GCMSsolution `4.00` compound-file
profile. It preserves all 16,800 TIC integers and the verified millisecond-derived
retention-time axis. The physical TIC unit is unknown. MS1 blocks are checked for
bounded scan structure and exact TIC-sum agreement, but spectra are not exported and
encoded mass values are not called m/z. It does not claim other QGD versions,
SIM/MRM, identifications, quantitation, or write support. See the
[exact capability and safety boundary](https://github.com/hdkim99/ordifile/blob/main/docs/formats/shimadzu-gcmssolution-qgd.md).

The YoungIn adapter is a structural converter for one observed YL-Clarity `9.0.1.19`
PRM profile. It preserves 563,240 finite stored binary32 records from 43 current blocks
across 23 local-only files and separates the allowlisted FID/TCD labels stored in those
files, while leaving the canonical detector field unset. Its x coordinate is record
ordinal, not retention time. No physical scaling or unit is applied, and peaks are not
exported. Runtime sample IDs are content-derived, and no filename-derived grouping is
exported. It does not claim other PRM generations, recovery `.RAW`, Autochro, calibrated
chromatograms, or write support. See the [exact capability and safety boundary](https://github.com/hdkim99/ordifile/blob/main/docs/formats/youngin-yl-clarity-prm-raw.md).

The separate YoungIn Result adapter reads the exact CP949-compatible, tab-delimited
Result Table grammar established by two owner-generated exports. It preserves six
source rows with explicit RT (min), area (mV.s), height (mV), signal number/name and
source order without requiring PRM. One observed FID section explicitly has no peaks;
the two populated TCD sections remain independent channels. `Signal Name` is not
promoted to detector identity, W05 is not an integration boundary, and Total,
percentage and empty compound-table rows are not peaks. The bytes contain no OEM or
software-version marker, so broader YL-Clarity/Clarity CSV support is not claimed. See
the [exact capability and safety boundary](https://github.com/hdkim99/ordifile/blob/main/docs/formats/youngin-yl-clarity-result-csv.md).

The LECO adapter reads one exact ChromaTOF 4.72.0.0 GCxGC tab-delimited Result profile
established by a Dryad CC0 non-human model-mixture file. It preserves all 100 source
rows, explicit first- and second-dimension retention times in seconds, area and height
in documented arbitrary units (`AU`), source order, names, spectra text, width values,
and retention-index lexemes. `Peak_Order_Matrix_2D` keeps atomic RT1/RT2/area triples;
the existing one-dimensional matrix remains unchanged. Software version is external
dataset provenance rather than an embedded byte marker, detector/channel are not
invented, and spectra are not claimed as supported mass-spectral data. Broader LECO,
ChromaTOF, Sync, CSV, TXT, or GCxGC support is not claimed. See the
[exact capability and safety boundary](docs/formats/leco-chromatof-472-gcxgc-result-txt.md).

## CLI

Inspect one file without writing output:

```bash
ordifile inspect sample.csv
ordifile inspect exported.xlsx --sheet PeakTable --verbose
```

Convert files or folders:

```bash
ordifile convert sample_1.csv sample_2.tsv --output Ordifile_Result.xlsx
ordifile convert ./exports --recursive --sort acquired_at --include-signals \
  --output Ordifile_Result.xlsx
ordifile convert ./exports --extension .csv --extension .xlsx \
  --sheet-mode sidecar-csv --output Ordifile_Result.xlsx
```

Important behavior:

- existing output is not replaced unless `--overwrite` is present;
- folder discovery is non-recursive unless `--recursive` is present;
- `--on-error continue` preserves valid files and reports partial success;
- `--on-error stop` stops after the first file failure and writes no workbook;
- `--adapter` forces one installed adapter; `--sheet` selects one XLSX worksheet;
- signals are parsed when present but written only with `--include-signals`;
- `--verbose` adds detection evidence and detailed structured diagnostics.

Exit codes are stable for automation:

| Code | Meaning |
|---:|---|
| 0 | Workbook created; no file failed |
| 1 | Fatal error or no successful input |
| 2 | Usage or configuration error |
| 3 | Valid workbook created with one or more failed files |
| 130 | Interrupted |

## Sorting

`--sort auto` uses acquisition time only when every successful file has a reliable,
timezone-aware timestamp. Otherwise it uses a complete sequence number, then natural
filename order. Explicit modes are `acquired_at`, `sequence`, `filename`, and
`input_order`. Missing or unreliable values receive a recorded filename fallback.

The effective mode, requested mode, reason, and per-file sort key are written to the
workbook.

## Workbook layout

| Sheet | Contents |
|---|---|
| `Manifest` | Version, UTC generation time, counts, options, sorting, limits, warnings, and sidecars |
| `Samples` | One row per discovered input, status, public source reference (relative path by default or core hash alias), adapter facts, peak count, and SHA-256 |
| `Peak_Matrix` | One row per sample only for explicit compound names; duplicate peaks remain separate |
| `Peak_Order_Matrix` | Conditional source-order RT/area pairs with sample, source, manufacturer, detector, channel and units; pairs split atomically before Excel limits |
| `Peak_Order_Matrix_2D` | Conditional two-dimensional streams with atomic source-order RT1/RT2/area triples; existing 1D pairs are not redefined |
| `Peaks` | All explicit peaks in long form, including manufacturer and evidence-backed units/boundaries; secondary retention columns appear only for 2D data, without retention-time identity inference |
| `Metadata` | Unknown fields, invalid raw lexemes, and provenance without invented semantics |
| `Import_Log` | Every public source reference, success, warning, failure, duplicate, skipped artifact, sort key, and hash |
| `Signals_<channel>` | Original uninterpolated x/y values, only when requested and actually parsed |
| `Signals_Records_<channel>` | Experimental structural decoded records, explicitly not a retention-time signal |

Rows and columns are split into deterministic numbered sheets before Excel limits are
reached. Data is never silently truncated. If workbook storage is impractical,
`--sheet-mode sidecar-csv` can create explicit CSV sidecars; the Manifest records each
relative path, row count, formula-escape count, and SHA-256.

## Python API

The CLI calls the same public API intended for future interfaces:

```python
from ordifile.api import convert, inspect_file, inspect_inputs, list_formats

inspection = inspect_file("sample.csv")
preview = inspect_inputs(["sample_1.csv", "sample_2.tsv"], sort="auto")
result = convert(
    ["sample_1.csv", "sample_2.tsv"],
    "Ordifile_Result.xlsx",
    sort="auto",
    include_signals=False,
)

print(preview.outcome, result.success_count, result.failure_count, result.sort.effective)
```

`inspect_inputs()` performs the same bounded discovery, detection, parsing, validation,
and sorting without writing an artifact. `convert()` intentionally reads and validates
the inputs again, and also accepts folders, recursion, extension filters, explicit
adapters and XLSX sheets, error policy, overwrite policy, CSV sidecars, and a
presentation-neutral progress callback.

## Add an adapter

External packages can register a typed adapter through the
`ordifile.adapters` Python entry-point group. Adapters detect and parse; they do not
write worksheets or duplicate CLI logic. A new format needs bounded detection, format
evidence, structured errors, a redistributable or synthetic fixture, capability-specific
tests, and license review.

Start with [Adding a format adapter](https://github.com/hdkim99/ordifile/blob/main/docs/formats/adding-an-adapter.md). Installed
third-party adapters execute Python code and must be treated as trusted software.

Good first contributions include an additional synthetic delimiter fixture, a clearer
error-message test, a documentation translation, or a small adapter proposal backed by
an openly redistributable fixture.

**YoungIn Result export confirmed:** two owner-generated YL-Clarity exports establish
the exact Result Table RT/area/height grammar used by the Experimental standalone
adapter. The maintainer bridge remains available for future local batch generation,
but it is not a runtime or CI dependency. Native PRM inputs and actual exports remain
local-only; public tests use independent synthetic values.

On a normally licensed Windows workstation, the one-command pilot-gated batch is:

```powershell
py scripts/local/youngin_yl_clarity_export_bridge.py <prm-or-directory-or-zip> `
  --output <outside-git-or-ignored-local-output> --batch `
  [--executable <vendor-executable>]
```

If a future pilot reports that explicit RT and Area headers are absent, enable **Result
Table**, **Table Headers**, **Text File**, and preferably **In Fixed Format** once in
YL-Clarity's **Export Data** settings, then rerun the bridge. Do not add the vendor
application, generated exports, or native inputs to the repository.
The bridge rejects output inside a Git worktree unless it is below Ordifile's fixed
`.external-fixtures`, `.research-downloads`, or `fixture-cache` ignored roots.

## Integrity and security boundaries

- Inputs are opened read-only, SHA-256 is recorded, and content is checked again after
  parsing.
- Symbolic links are rejected. Duplicate paths and hard links are recorded instead of
  parsed twice; equal content hashes alone are not deduplicated.
- One ordinary parse failure is isolated from other inputs. Successful data can still
  produce a workbook and the failed file remains visible in `Import_Log`.
- Formula-like strings are written as literal text with formula and URL conversion
  disabled.
- Values that the verified XLSX writer/reader combination cannot represent exactly are
  rejected for that file instead of being silently changed.
- Generic source identities in XLSX audit cells use a reversible display encoder:
  unsafe code points become `~uXXXXXX;` and a literal `~` is doubled. Privacy-sensitive
  adapters can instead request a core-owned `source-<full SHA-256>` alias; this also
  applies to API/CLI/progress and malformed-file issues. Input paths, bytes and hashes
  remain unchanged. See the [source identity policy](docs/architecture/source-identity-policy.md).
- CLI output renders terminal control and bidirectional-format characters as visible,
  single-line escapes while preserving normal Unicode and Windows paths.
- XLSX packages pass ZIP, relationship, Content-Type, XML namespace, coordinate,
  dimension, cell-type, and resource audits before openpyxl reads a selected sheet.
- Normal conversion is offline and does not upload instrument data.

## Limits

- One input file represents one sample.
- Generic delimited-text input is UTF-8 or UTF-8 with BOM. Exact proprietary text
  adapters use only their documented fixture-backed encoding. Delimiters are fixed per
  adapter; guessing is not supported.
- Extension filters are normalized to lowercase dotted ASCII before discovery. At most
  32 unique filters are accepted; each has at most 32 ASCII characters after the
  leading dot, and the Manifest form is capped at 1,024 characters.
- Only exact documented headers are mapped. Units are copied, not converted.
- Compound identity is never inferred from retention time. RT-tolerance matching and
  duplicate-compound aggregation are not enabled.
- XLSX support is limited to an audited transitional, non-macro `.xlsx` workbook with
  explicit uppercase row and cell coordinates. Templates, macros, implicit coordinates,
  and other OOXML variants are rejected.
- XLSX formula text is preserved, but cached formula results are never treated as
  measured values.
- Numeric Excel date-style cells have no timezone and remain unreliable for automatic
  acquisition-time sorting. An OOXML `t="d"` ISO timestamp is parsed from its audited
  raw lexeme; an explicit offset can make that timestamp reliable.
- OOXML numeric lexemes must use ASCII sign, decimal, and exponent characters without
  whitespace. A cell type incompatible with its documented field is preserved as raw
  Metadata with a warning, not converted through Python stringification.
- Files at or above 256 MiB receive a warning; files above 2 GiB are hashed but not
  parsed. Delimited inputs and declared XLSX uncompressed content are capped at 512 MiB.
- The XLSX audit additionally caps 10,000 archive members, 8 MiB control XML parts,
  250,000 physical rows, 1,000,000 physical cells, a 250,000 logical row, 5,000,000
  projected cells, XML depth 128, and raw cell lexemes at 32,767 characters. Raw
  formula text is capped at 32,766 because the exported literal includes a leading `=`.
- Canonical integers are limited to 1,000 decimal digits; integer source lexemes are
  limited to 4,096 characters. Excel numbers beyond 15 exact integer digits are written
  as literal strings and counted.
- Mandatory audit cells are limited to 32,767 characters. A file that cannot fit its
  own `Samples`/`Import_Log` identity or issue summary is isolated before workbook
  planning; batch summaries are bounded and report omitted-code counts.
- The practical workbook cap is 512 sheets and the conservative portable output-path
  cap is 218 Unicode code points.
- Proprietary readers are limited to the exact Experimental profiles above. The
  optional Experimental GUI exposes only those same registry capabilities and does not
  broaden format support.

These practical bounds are Ordifile safety policies, not claims about every valid
Excel file. See [the exact generic format contract](https://github.com/hdkim99/ordifile/blob/main/docs/formats/generic-tabular.md) and
[the architecture decision](https://github.com/hdkim99/ordifile/blob/main/docs/architecture/decision-record.md).

## Development

Ordifile targets Python 3.11–3.14. Required tests, release builds, wheel smoke tests,
and external real-fixture workflows target Python 3.14 on a shared Linux DGX
self-hosted runner. TestPyPI/PyPI publishing, byte verification, attestations, and
GitHub Release publication use GitHub-hosted Ubuntu. Core CI has no Windows or macOS
matrix. The maintainer-triggered standalone prototype path targets Windows x86-64
through an exact-SHA reusable workflow called by the existing runner's same-owner
repository and uses GitHub-hosted `macos-15` for macOS. The existing runner
registration and assignment remain unchanged. The persistent Windows job uses a
run-scoped environment, bounded pre/post cleanup, and checkout-independent artifact smoke. Neither platform
uploads native candidate binaries; only path-free evidence is retained. The standalone
workflow runs only an allowlisted same-repository branch whose selected SHA, required
reviewed commit, workflow SHA, and checkout all match. It has no GitHub-hosted Windows fallback.
Caller assignment, capability labels, and online state must be confirmed before
dispatch; the workflow is not authorized for a personal workstation.
Public-fork core workflows require maintainer approval before they run on the shared
Linux runner and
receive read-only repository permission without publishing secrets or OIDC permission.
Runner availability is an operational setting visible in GitHub Actions; this describes
the configured target, not a guarantee that the runner is currently online.

```bash
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy
pytest
python -m build
ordifile --help
pip-audit
```

See [CONTRIBUTING.md](https://github.com/hdkim99/ordifile/blob/main/CONTRIBUTING.md),
[SECURITY.md](https://github.com/hdkim99/ordifile/blob/main/SECURITY.md), the
[release runbook](https://github.com/hdkim99/ordifile/blob/main/docs/releasing.md),
[GC fixture research](https://github.com/hdkim99/ordifile/blob/main/docs/research/gc-fixture-search.md),
[external-fixture policy](https://github.com/hdkim99/ordifile/blob/main/docs/research/external-fixture-policy.md), and the
[evidence register](https://github.com/hdkim99/ordifile/blob/main/docs/research/source-register.md). Do not attach proprietary raw
files or fixtures without confirmed redistribution permission to a public issue.

## Project name and trademarks

Ordifile was selected after a technical collision screen on 2026-08-16. No exact-name
record was found in the checked GitHub and package-registry searches at that time, but
search absence is not a reservation or legal trademark clearance. See the
[renaming research](https://github.com/hdkim99/ordifile/blob/main/docs/research/project-renaming.md). Vendor names, if mentioned in
future compatibility notes, remain the property of their owners and do not imply
affiliation or endorsement.

Agilent, ChemStation, Shimadzu, LabSolutions, GCsolution, YOUNG IN Chromass, ChroZen,
YL-Clarity, AUTOCHRO, and related product names are
trademarks or product names of their respective owners. Ordifile is not affiliated with
or endorsed by Agilent, Shimadzu, or YOUNG IN Chromass.

## License

Ordifile is licensed under Apache License 2.0. See
[LICENSE](https://github.com/hdkim99/ordifile/blob/main/LICENSE),
[NOTICE](https://github.com/hdkim99/ordifile/blob/main/NOTICE), and
[THIRD_PARTY_NOTICES.md](https://github.com/hdkim99/ordifile/blob/main/THIRD_PARTY_NOTICES.md).
