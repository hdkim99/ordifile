# LabConvert

[한국어](README.ko.md)

[![CI](https://github.com/hdkim99/labconvert/actions/workflows/ci.yml/badge.svg)](https://github.com/hdkim99/labconvert/actions/workflows/ci.yml)

Batch-convert and merge scientific instrument files into one clean, ordered Excel
workbook.

LabConvert turns a file list or folder into one auditable workbook. Its built-in v0.1
scope is deliberately narrow: documented generic CSV, TSV, semicolon-delimited TXT,
and non-macro XLSX tables verified with synthetic fixtures. Proprietary vendor raw
formats are not supported.

```text
sample_1.csv   sample_2.tsv   exported_peaks.xlsx
          \          |          /
           labconvert convert ...
                    |
                    v
          LabConvert_Result.xlsx
          ├── Manifest
          ├── Samples
          ├── Peak_Matrix
          ├── Peaks
          ├── Metadata
          └── Import_Log
```

## 30-second quick start

LabConvert has not been published to PyPI. Install the verified source tree:

```bash
git clone https://github.com/hdkim99/labconvert.git
cd labconvert
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
labconvert convert examples/basic --sort filename --output LabConvert_Result.xlsx
```

The committed example produces:

```text
Input paths: 1
Discovered files: 3
Processed 1/3: success sample_1.csv
Processed 2/3: success sample_2.csv
Processed 3/3: success sample_10.csv
Export started: LabConvert_Result.xlsx
Output ready: LabConvert_Result.xlsx
Status: success
Output: LabConvert_Result.xlsx
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

## Verified formats

| Built-in format | Metadata | Peaks | Signals | Status | Synthetic fixture |
|---|---:|---:|---:|---|---:|
| Generic comma-delimited CSV | Yes | Explicit columns | Explicit `time` + `signal` rows | Verified | Yes |
| Generic tab-delimited TSV | Yes | Explicit columns | Explicit `time` + `signal` rows | Verified | Yes |
| Generic semicolon-delimited TXT | Yes | Explicit columns | Explicit `time` + `signal` rows | Verified | Yes |
| Generic non-macro XLSX table | Yes | Explicit columns | Explicit `time` + `signal` rows | Verified | Yes |

“Generic” means the first row uses the [documented column
schema](docs/formats/generic-tabular.md). It does not mean arbitrary vendor exports.
An extension is supporting evidence only; LabConvert also checks content and schema.
Run `labconvert formats` to see the adapters installed in the current environment.

## CLI

Inspect one file without writing output:

```bash
labconvert inspect sample.csv
labconvert inspect exported.xlsx --sheet PeakTable --verbose
```

Convert files or folders:

```bash
labconvert convert sample_1.csv sample_2.tsv --output LabConvert_Result.xlsx
labconvert convert ./exports --recursive --sort acquired_at --include-signals \
  --output LabConvert_Result.xlsx
labconvert convert ./exports --extension .csv --extension .xlsx \
  --sheet-mode sidecar-csv --output LabConvert_Result.xlsx
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

Rows and columns are split into deterministic numbered sheets before Excel limits are
reached. Data is never silently truncated. If workbook storage is impractical,
`--sheet-mode sidecar-csv` can create explicit CSV sidecars; the Manifest records each
relative path, row count, formula-escape count, and SHA-256.

## Python API

The CLI calls the same public API intended for future interfaces:

```python
from labconvert.api import convert, inspect_file, list_formats

inspection = inspect_file("sample.csv")
result = convert(
    ["sample_1.csv", "sample_2.tsv"],
    "LabConvert_Result.xlsx",
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
`labconvert.adapters` Python entry-point group. Adapters detect and parse; they do not
write worksheets or duplicate CLI logic. A new format needs bounded detection, format
evidence, structured errors, a redistributable or synthetic fixture, capability-specific
tests, and license review.

Start with [Adding a format adapter](docs/formats/adding-an-adapter.md). Installed
third-party adapters execute Python code and must be treated as trusted software.

Good first contributions include an additional synthetic delimiter fixture, a clearer
error-message test, a documentation translation, or a small adapter proposal backed by
an openly redistributable fixture.

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

- One input file represents one sample in v0.1.
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
- No proprietary GC raw parser and no GUI are included in v0.1.

These practical bounds are LabConvert safety policies, not claims about every valid
Excel file. See [the exact generic format contract](docs/formats/generic-tabular.md) and
[the architecture decision](docs/architecture/decision-record.md).

## Development

LabConvert targets Python 3.11–3.14. CI is configured for Linux, Windows, and macOS;
use the workflow result as the current compatibility record.

```bash
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy
pytest
python -m build
labconvert --help
pip-audit
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and the
[evidence register](docs/research/source-register.md). Do not attach proprietary raw
files or fixtures without confirmed redistribution permission to a public issue.

## Project name and trademarks

The source-distribution name is currently `labconvert`, but unrelated projects and
services use LabConvert or similar names. PyPI availability checked on 2026-08-15 is not
a trademark clearance. Vendor names, if mentioned in future compatibility notes, remain
the property of their owners and do not imply affiliation or endorsement.

## License

LabConvert is licensed under Apache License 2.0. See [LICENSE](LICENSE),
[NOTICE](NOTICE), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
