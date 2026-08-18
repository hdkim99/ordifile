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
cannot accidentally restore a private basename. When a forced adapter declares
`SHA256_ALIAS`, or any owner of an input extension declares it, the policy is applied
before content detection so no-match, ambiguity, discovery and malformed-file errors
are also safe. This is a provisional privacy boundary for shared extensions. A
successfully selected `RELATIVE_PATH` adapter may restore ordinary relative provenance
only after its parse, canonical validation and source-integrity checks all succeed.
Every detection, ambiguity, unsupported-profile, parse, validation or integrity
failure retains the conservative SHA alias. SHA-aliased results use their public
reference for deterministic sorting; successful generic relative-path ordering is
unchanged.

When a `SHA256_ALIAS` adapter makes a positive content-ownership claim, detection
considers only positively matched SHA-policy owners for selection and ambiguity.
This rule is independent of confidence: a broader relative-path parser cannot win a
score comparison over a recognized but malformed private family and thereby expose
its basename or private fields. A generic adapter still regains relative provenance
when every privacy-sensitive owner returns no match and the generic parse, validation
and integrity gates succeed.

An adapter's `DetectionResult.reason` is untrusted text. Under an effective
`SHA256_ALIAS` policy, the core replaces reasons from privacy-sensitive owner IDs with
one fixed non-identifying explanation before constructing no-match or ambiguity errors
and before storing public probe evidence. If the selected adapter itself requires the
SHA policy, all exposed probe reasons are fixed. Match decisions and bounded confidence
values are unchanged. No-match and ambiguity errors under the provisional SHA boundary
replace every probe reason, including reasons from relative-path candidates. A generic
`RELATIVE_PATH` adapter that completes the success gate restores its existing
inspectable probe-reason behavior.

Adapter exceptions follow the same boundary. Under an effective `SHA256_ALIAS` policy,
the core preserves a valid structured error code but replaces its free-form message
and details with fixed non-identifying output. An ordinary exception becomes one fixed
generic error without exposing its class name or message. This includes a
`RELATIVE_PATH` adapter selected from an extension-owner set whose conservative
pre-detection policy was `SHA256_ALIAS`. `RELATIVE_PATH`-only inputs retain the existing
validated structured message/context and bounded ordinary-exception class behavior.
Canonical bundle warnings and metadata continue through their existing independent
validation boundary.

When an adapter returns SHA-256 and size from its own bounded read, the core compares
both with discovery provenance before source rebinding. A mismatch—including a file
that changes for parsing and is then restored—is a structured integrity failure and no
parsed bundle is exposed. The independent post-parse file hash remains a second gate.

The core retains the real path only while it must read and protect the input. Public
`inspect_file()` and `convert()` results replace `path`, `relative_path` and `name` for
a SHA-aliased source with the same public reference, including nested sample sources.
Generic results retain their original path provenance.

The YoungIn YL-Clarity PRM raw adapter is the first opt-in user. Its owner-supplied
fixtures can have privacy-bearing native basenames, while the full content hash already
provides stable provenance. The exact Agilent Result XML, Shimadzu LabSolutions result
ASCII and YoungIn YL-Clarity Result Table CSV adapters also opt in because their
fixture evidence shows privacy-bearing source metadata and names. This is not a
vendor-specific exception.

## Result sources

`ResultSource` is the policy boundary described here, not a new canonical model type.
A standalone vendor result adapter must bind every canonical `PeakRecord` and metadata
row to the same core-owned public source reference. RT/area result consolidation
remains manufacturer-neutral: the first exact Agilent Result XML adapter maps evidence-
backed rows to `PeakRecord`, `Peaks`, compound `Peak_Matrix`, and the conditional
source-order `Peak_Order_Matrix`; the exact Shimadzu result ASCII and YoungIn Result
Table CSV adapters map their evidence-backed peak rows to the same contract. YoungIn
signal sections remain independent source-order matrix streams without inferred
detector or compound identity. Future vendor-specific parsers or fields remain blocked
until an actual result fixture proves their boundaries and semantics.
