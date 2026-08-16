# Ordifile

[한국어](https://github.com/hdkim99/ordifile/blob/main/README.ko.md)

[![CI](https://github.com/hdkim99/ordifile/actions/workflows/ci.yml/badge.svg)](https://github.com/hdkim99/ordifile/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ordifile)](https://pypi.org/project/ordifile/)
[![Python 3.11–3.14](https://img.shields.io/badge/Python-3.11%E2%80%933.14-blue)](https://github.com/hdkim99/ordifile/blob/main/pyproject.toml)
[![Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue)](https://github.com/hdkim99/ordifile/blob/main/LICENSE)

Batch-convert scientific instrument exports into one clean, ordered and auditable
Excel workbook.

**Verified stable formats:** CSV, TSV, semicolon-delimited TXT, and audited non-macro
XLSX using Ordifile's documented schema. v0.2.0 also includes three narrowly bounded
Experimental proprietary readers described below; this is not general vendor-format
support.

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

Install Ordifile v0.2.0 from PyPI:

```bash
python -m pip install --no-cache-dir ordifile==0.2.0
```

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
| Shimadzu LabSolutions 5.82 `.GCD`, GC-2014 / single `SFID1` profile | Field-specific | No | Retention time (min) + signal (uV) | Experimental | One external CC0-declared file + paired same-run ASCII reference |
| Shimadzu GCMSsolution `.QGD`, exact `4.00` TIC profile | Field-specific | No | Retention time (min) + raw TIC (unit unknown); MS1 not exported | Experimental | One external Dryad CC0 file |

These Experimental adapters are included in PyPI v0.2.0 with the exact capability
boundaries below. Unsupported profiles are rejected rather than interpreted broadly.

The Agilent adapter retains every
decoded record in source order. Its x values are `decoded_record_index`, not retention
time; its y values are `decoded_raw_integer`, not physically scaled intensity. Units,
scientific point count, and the final record's role remain unresolved. It does not
claim other `.CH` versions, `.D` directories, TCD, MS, peaks, calibrated values, or
write support. See the [exact capability and safety boundary](https://github.com/hdkim99/ordifile/blob/main/docs/formats/agilent-chemstation-ch-v181.md).

The Shimadzu adapter is limited to an exact LabSolutions 5.82, GC-2014,
single-channel `SFID1`, `uV`, identity-factor profile. Its 66,255-point retention-time
and signal series were compared point by point with a same-run LabSolutions ASCII
reference. It does not claim other LabSolutions or GCsolution versions, detectors,
channels, factors, GCD profiles, peaks, `.QGD`, `.LCD`, or write support. See the
[exact capability and safety boundary](https://github.com/hdkim99/ordifile/blob/main/docs/formats/shimadzu-gcsolution-gcd.md).

The separate QGD adapter is limited to one exact GCMSsolution `4.00` compound-file
profile. It preserves all 16,800 TIC integers and the verified millisecond-derived
retention-time axis. The physical TIC unit is unknown. MS1 blocks are checked for
bounded scan structure and exact TIC-sum agreement, but spectra are not exported and
encoded mass values are not called m/z. It does not claim other QGD versions,
SIM/MRM, identifications, quantitation, or write support. See the
[exact capability and safety boundary](https://github.com/hdkim99/ordifile/blob/main/docs/formats/shimadzu-gcmssolution-qgd.md).

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
| `Samples` | One row per discovered input, status, relative path, adapter facts, peak count, and SHA-256 |
| `Peak_Matrix` | One row per sample only for explicit compound names; duplicate peaks remain separate |
| `Peaks` | All explicit peaks in long form without retention-time identity inference |
| `Metadata` | Unknown fields, invalid raw lexemes, and provenance without invented semantics |
| `Import_Log` | Every success, warning, failure, duplicate, skipped artifact, sort key, and hash |
| `Signals_<channel>` | Original uninterpolated x/y values, only when requested and actually parsed |
| `Signals_Records_<channel>` | Experimental structural decoded records, explicitly not a retention-time signal |

Rows and columns are split into deterministic numbered sheets before Excel limits are
reached. Data is never silently truncated. If workbook storage is impractical,
`--sheet-mode sidecar-csv` can create explicit CSV sidecars; the Manifest records each
relative path, row count, formula-escape count, and SHA-256.

## Python API

The CLI calls the same public API intended for future interfaces:

```python
from ordifile.api import convert, inspect_file, list_formats

inspection = inspect_file("sample.csv")
result = convert(
    ["sample_1.csv", "sample_2.tsv"],
    "Ordifile_Result.xlsx",
    sort="auto",
    include_signals=False,
)

print(result.success_count, result.failure_count, result.sort.effective)
```

`convert()` also accepts folders, recursion, extension filters, explicit adapters and
XLSX sheets, error policy, overwrite policy, CSV sidecars, and a presentation-neutral
progress callback.

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

**Under investigation:** YOUNG IN Chromass GC data formats are a required priority
candidate for a future proprietary adapter. No compatibility is claimed yet; the work
is blocked until completed-file semantics and reproducible FID/TCD fixtures are
verified.

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
- Source identities in XLSX audit cells use a reversible display encoder: unsafe code
  points become `~uXXXXXX;` and a literal `~` is doubled. The Manifest records the
  policy and affected-file count; input paths, bytes, and hashes remain unchanged.
- CLI output renders terminal control and bidirectional-format characters as visible,
  single-line escapes while preserving normal Unicode and Windows paths.
- XLSX packages pass ZIP, relationship, Content-Type, XML namespace, coordinate,
  dimension, cell-type, and resource audits before openpyxl reads a selected sheet.
- Normal conversion is offline and does not upload instrument data.

## Limits

- One input file represents one sample.
- Text input is UTF-8 or UTF-8 with BOM. Delimiters are fixed per adapter; guessing is
  not supported.
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
- Proprietary readers are limited to the exact Experimental profiles above. No GUI is
  included.

These practical bounds are Ordifile safety policies, not claims about every valid
Excel file. See [the exact generic format contract](https://github.com/hdkim99/ordifile/blob/main/docs/formats/generic-tabular.md) and
[the architecture decision](https://github.com/hdkim99/ordifile/blob/main/docs/architecture/decision-record.md).

## Development

Ordifile targets Python 3.11–3.14. The v0.2.0 release CI and external real-fixture
workflows target Python 3.14 on a shared Linux DGX self-hosted runner, with no current
Windows or macOS CI matrix.
Public-fork workflows require maintainer approval before they run on that machine and
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
