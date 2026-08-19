# LECO ChromaTOF 4.72 GCxGC Result text profile

Status: **Experimental**

Ordifile recognizes one exact tab-delimited Result profile established by the
non-human model-mixture member of the CC0 Dryad dataset
[10.5061/dryad.k98sf7m8m](https://doi.org/10.5061/dryad.k98sf7m8m). LECO and
ChromaTOF are used only to identify compatibility; this project is not affiliated
with or endorsed by LECO Corporation.

## Exact boundary

The reader accepts `.txt` inputs with 7-bit ASCII, CRLF records, and exactly these
nine tab-delimited columns in this order:

```text
Name
1st Dimension Time (s)
2nd Dimension Time (s)
Area
Height
Spectra
wb1
wb2
Retention Index
```

The selected external file is attributed to ChromaTOF `4.72.0.0` by the dataset
README. The software version is not independently embedded in the result bytes.
Consequently, this adapter does not claim other ChromaTOF versions or arbitrary
LECO, GCxGC, CSV, TXT, Sync, or Sync 2D exports.

Detection requires the rare dual-retention header family plus the full bounded
table structure; the `.txt` extension alone is never sufficient. A recognized but
malformed family remains an adapter-owned structured failure instead of falling
through to the generic TSV reader.

## Scientific mapping

| Source field | Canonical output |
|---|---|
| source row order | `observation_order` |
| `1st Dimension Time (s)` | `retention_time`, unit `s` |
| `2nd Dimension Time (s)` | `secondary_retention_time`, unit `s` |
| `Area` | `area`, documented arbitrary unit token `AU` |
| `Height` | `height`, documented arbitrary unit token `AU` |
| `Name` | exact row Metadata; non-`Unknown` values also map to `compound` |
| `Spectra` | exact row Metadata only |
| `wb1`, `wb2` | exact row Metadata with source-documented seconds |
| `Retention Index` | exact row Metadata only |

The adapter does not calculate, normalize, interpolate, sort, or merge source rows.
It does not infer detector, channel, peak number, integration boundaries, or raw
signals. `Spectra` is preserved as evidence but is not exposed as a supported mass
spectrum. Width and retention-index values are not repurposed as canonical time or
integration fields.

One source peak remains one `Peaks` row. `Peak_Order_Matrix_2D` contains atomic
RT1/RT2/area triples in source order, while the existing one-dimensional
`Peak_Order_Matrix` contract is unchanged. Compound `Peak_Matrix` behavior remains
identity-based and never matches peaks by retention-time tolerance.

## Validation evidence

The selected external member is 20,040 bytes, contains 100 peak rows, and has
SHA-256 `59f336c3e4bb91df32c5111d39a7fa76759a72242a4bd5d873eb623b020af6dd`.
The external regression compares every RT1, RT2, area, height, name, spectra, width,
retention-index, order, canonical row, Metadata row, workbook row, and 2D matrix
triplet. It also verifies that the input hash is unchanged.

The source archive contains unrelated human-derived members. Ordifile never commits,
packages, uploads, glob-extracts, or parses that archive. Only the exact non-human
member is supplied to a maintainer-controlled local external test. Public tests use
an independently invented Apache-2.0 synthetic table.
