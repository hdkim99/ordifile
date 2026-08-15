# Generic tabular export format

LabConvert v0.1 reads explicitly labeled peak tables and signal rows from four verified
containers:

- comma-delimited UTF-8 or UTF-8-BOM text (`.csv` convention);
- tab-delimited UTF-8 or UTF-8-BOM text (`.tsv` convention);
- semicolon-delimited UTF-8 or UTF-8-BOM text (`.txt` convention);
- one selected compatible worksheet in an OOXML `.xlsx` workbook.

An extension is supporting evidence only. Detection also checks content structure and a
documented header. Delimited files above 512 MiB and XLSX archives outside the documented
archive preflight limits are rejected before unbounded parsing.

The first row is always the header. Delimited text must be UTF-8 or UTF-8 with BOM; encoding
guessing is deliberately not performed. CSV uses comma, TSV uses tab, and TXT uses semicolon.
Delimiter auto-guessing is outside the verified v0.1 contract.

## Documented columns

Column names are case-insensitive; spaces and hyphens normalize to underscores. Only these
meanings are mapped:

| Canonical field | Accepted headers |
|---|---|
| Sample | `sample_id` |
| Acquisition | `acquired_at`, `sequence`, `runtime` |
| Instrument | `instrument_type`, `instrument`, `vendor`, `channel`, `detector` |
| Peak | `peak_number`, `retention_time`, `rt`, `retention_time_unit`, `area`, `height`, `compound`, `compound_source` |
| Signal | `time`, `x`, `signal`, `response`, `y`, `x_unit`, `y_unit` |

Unknown columns and invalid raw values are retained in the `Metadata` worksheet. A duplicate
header or two headers mapping to the same canonical field are errors. Rows with explicit peak
fields populate `Peaks`; rows containing both a time and signal value populate an original,
uninterpolated signal series. A table may contain either or both.

## Sample and scientific semantics

- One input file represents one sample in v0.1.
- A timezone-aware ISO 8601 `acquired_at` value is reliable for automatic cross-file sorting.
  A timestamp without a timezone is preserved but excluded from that automatic decision.
- Units are copied; they are not converted.
- Empty cells are absent values. A non-empty, whitespace-only mapped cell is preserved in
  Metadata with a warning. Leading and trailing whitespace in mapped text is otherwise retained
  exactly.
- Numeric and timestamp fields may be parsed from a trimmed copy, but the original lexeme and a
  warning are retained whenever trimming occurred. Unknown header and cell text is never trimmed
  for Metadata provenance.
- Canonical integer construction is limited to 1,000 decimal digits, and an integer source
  lexeme is limited to 4,096 characters. Values outside those bounds remain raw Metadata with a
  structured warning.
- Compound names must be explicit in the input. Retention time never implies compound identity.
- Repeated compounds are never silently summed, reduced, or selected.
- Signal points retain their original axes and are not interpolated.
- Spreadsheet formulas in XLSX inputs are read as literal formula text, never evaluated, and
  produce a warning.

## XLSX sheet selection

Automatic selection ignores hidden worksheets by default and requires exactly one compatible
visible worksheet. `--include-hidden-sheets` adds hidden sheets to automatic detection. An exact
`--sheet NAME` is itself an explicit selection and can select a hidden sheet without that flag.

Only the transitional, non-macro `.xlsx` workbook content type and namespaces are verified.
Macro-enabled workbooks, templates, Strict OOXML, and namespace-mismatched elements are rejected
rather than silently stripped or interpreted as generic workbooks.
Before openpyxl reads a sheet, LabConvert audits the OOXML package relationships and the actual
worksheet row/cell coordinates. The declared worksheet dimension is recorded but is not trusted
as an allocation or end-of-data boundary. Duplicate, unordered, missing, invalid, or out-of-grid
coordinates are rejected instead of selecting one conflicting value.

The XLSX archive preflight policy is:

- at most 10,000 ZIP members;
- at most 512 MiB total declared uncompressed content;
- at most a 1,000:1 compression ratio for an individual member of at least 1 MiB;
- at most 8 MiB for an individual package-control XML part parsed in memory;
- no encrypted, absolute, parent-traversing, duplicate-normalized, or required-missing members;
- at most 250,000 physical rows, 1,000,000 physical cells, a maximum logical row of 250,000,
  and 5,000,000 projected materialized cells per worksheet;
- XML nesting depth at most 128 and an individual captured raw cell lexeme at most 32,767
  characters.

The worksheet limits after the archive limits are conservative LabConvert v0.1 resource-safety
policies, not Excel format maxima. A limit breach fails that input file; rows and cells are never
silently truncated.

Numeric `<v>` text is inspected before openpyxl can round it. A decimal that cannot be represented
exactly by LabConvert's canonical float remains raw Metadata with a warning instead of becoming a
different number. Numeric and index lexemes must use bounded ASCII grammar; Python-specific
underscores, Unicode digits, internal whitespace, and non-finite spellings are rejected. Date-styled
numeric values retain their raw serial, style, and workbook epoch; Excel numeric dates have no
timezone and are not promoted to reliable acquisition times. OOXML `t="d"` cells are kept separate:
their audited raw ISO lexeme is recorded, and only a timestamp with an explicit time is mapped to
`acquired_at`; an explicit offset makes it reliable. Formula text and its cached value are recorded
separately, and cached formula results are never treated as measured scientific values.

Mapped text fields accept explicit OOXML string cell types. Boolean, error, numeric, or date cells
in a text field—and otherwise incompatible cell/field combinations—retain their raw lexeme, type,
and coordinate as Metadata with a structured warning instead of being converted through Python's
display string.

Formula character data is limited to 32,766 characters because the literal value written to
Metadata includes a leading `=` and must remain within Excel's 32,767-character cell boundary.
Inline and shared strings accept one direct text node or a valid sequence of rich-text runs;
LabConvert reconstructs the audited text for mapping and rejects duplicate text payloads,
unexpected wrappers, or namespace mismatches instead of trusting a lossy decoded value.

Workbook output rejects cell text that cannot be represented and independently reopened without
ambiguity by the verified XlsxWriter/openpyxl combination. This includes unsupported control or
Unicode noncharacter values and reserved OOXML escape-token patterns. LabConvert reports a
structured error rather than silently stripping or substituting that text.

Source filenames that need those characters for filesystem identity are not renamed. Workbook
audit fields use the reversible `~uXXXXXX;` display encoding, double a literal `~`, and record the
policy and affected-file count in Manifest. Mandatory workbook audit cells remain subject to the
32,767-character limit; an oversized file identity or per-file issue aggregate fails only that
input. Batch warning/error summaries are bounded and report how many codes were omitted.

## Verified fixtures

The source-controlled fixtures are under [`tests/fixtures/synthetic/`](../../tests/fixtures/synthetic/).
Every value is invented and the XLSX fixture has a committed generator. Integration tests inspect
all four formats, parse peaks and signals, sort them by acquisition time, and reopen the generated
workbook to verify the result.

This support does not imply compatibility with every vendor's CSV or XLSX schema, and it is not
support for proprietary raw acquisition containers.
