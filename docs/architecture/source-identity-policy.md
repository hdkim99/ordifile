# Public source identity policy

Ordifile keeps the filesystem path needed to read an input inside the core, but every
adapter descriptor declares how that source is named on public surfaces. This policy is
manufacturer-neutral and applies equally to successful records, failures, progress
events, the Python API, CLI output and workbook audit sheets.

## Policies

- `RELATIVE_PATH` is the default. It preserves the existing behavior for generic,
  non-sensitive tabular inputs.
- `SHA256_ALIAS` emits `source-<full source SHA-256>`. When discovery cannot hash an
  input, the core emits `source-input-<six-digit input order>` instead.

The core creates these aliases. Adapter-provided aliases are discarded, so a parser
cannot accidentally restore a private basename. When a forced adapter, or every owner
of an input extension, declares `SHA256_ALIAS`, the policy is applied before content
detection so discovery and malformed-file errors are also safe. The selected adapter's
policy is applied again after detection. SHA-aliased files use their public reference
for deterministic sorting; generic relative-path ordering is unchanged.

The core retains the real path only while it must read and protect the input. Public
`inspect_file()` and `convert()` results replace `path`, `relative_path` and `name` for
a SHA-aliased source with the same public reference, including nested sample sources.
Generic results retain their original path provenance.

The YoungIn YL-Clarity PRM raw adapter is the first opt-in user. Its owner-supplied
fixtures can have privacy-bearing native basenames, while the full content hash already
provides stable provenance. Future Agilent, Shimadzu or YoungIn result adapters may opt
in to the same policy when their fixture evidence shows that source names are unsafe;
this is not a vendor-specific exception.

## Result sources

`ResultSource` is the policy boundary described here, not a new canonical model type.
A future standalone vendor result adapter must bind every canonical `PeakRecord` and
metadata row to the same core-owned public source reference. RT/area result
consolidation remains manufacturer-neutral: evidence-backed vendor results map to the
existing `PeakRecord` model and then to `Peaks` / `Peak_Matrix`. A vendor-specific
result parser, new result fields, or a new matrix is not added until an actual result
fixture proves the required source fields and semantics.
