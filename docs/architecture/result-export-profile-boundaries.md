# Result export profile boundaries

- Status: Accepted for Wave-1 research
- Date: 2026-08-19
- Evidence: [`multivendor-result-wave1.md`](../research/multivendor-result-wave1.md)

## Context

Ordifile consolidates result peaks from multiple manufacturers into one workbook. A
manufacturer name alone is not a format boundary: CDS products expose configurable
report templates, multiple export types, one-run and multi-run reports, and one- or
two-dimensional retention coordinates.

The current canonical path is:

```text
exact result profile
  -> FormatAdapter
  -> DatasetBundle(peaks=...)
  -> PeakRecord
  -> Peaks
  -> Peak_Order_Matrix
  -> Peak_Matrix when explicit compound identity exists
  -> one workbook
```

## Accepted boundary

1. One adapter ID names one exact `manufacturer + software/version boundary + export
   profile`, not a manufacturer or file extension.
2. The current adapter API accepts one source file and returns one source/sample/run.
   A one-run, one-dimensional Result export with explicit finite RT and area fits the
   existing model without a core change.
3. Unknown units remain `None`; an adapter must not write `Unknown`, infer detector
   units, or normalize response values between manufacturers.
4. Source detector and channel become canonical fields only when the exact profile
   identifies them. Otherwise they remain unset and the evidence gap is recorded in
   namespaced Metadata.
5. Observation order and every source row are preserved. Duplicate source rows are not
   silently deduplicated, and malformed rows do not corrupt unrelated files.
6. A bounded producer/profile signature must outrank generic CSV/TXT/XLSX detection.
   Extension-only detection and a bare `RT,Area` header are insufficient.
7. A recognized vendor family with an unsupported exact profile retains ownership and
   fails structurally. It does not fall through to a generic parser that could mislabel
   the data or disclose a private basename.
8. Result-only conversion is the primary path. A raw sibling may be paired later, but
   cannot block an otherwise complete result export.

## Profiles that require a separate architecture decision

### Two-dimensional retention

LECO ChromaTOF 4.72 evidence contains explicit first- and second-dimension retention
times. The current `PeakRecord.retention_time` and atomic RT/Area columns in
`Peak_Order_Matrix` preserve only one retention coordinate.

Until a separate ADR defines an additive canonical second coordinate and workbook
representation, Ordifile must not:

- discard RT2;
- concatenate RT1/RT2 into one text retention value;
- hide RT2 in Metadata;
- reuse detector or channel as an RT2 carrier; or
- describe the GCxGC profile as supported.

Any future extension must preserve existing 1D workbook columns and public API
compatibility, define ordering and units for both coordinates, preflight Excel limits,
and compare every actual source row through workbook reopen.

### Multiple samples or runs in one export

Chromeleon sequence reports and ChromaTOF Sync combined peak tables can contain more
than one run. The current one-source/one-sample contract cannot merge such a file into
one `SampleRecord` without losing provenance. Support requires either a documented
one-run export profile or a separate canonical multi-sample input decision.

## Rejected alternatives

- One generic `vendor_results.py` containing manufacturer-specific exceptions.
- One adapter for all exports from a manufacturer or CDS family.
- Vendor detection by `.csv`, `.txt`, `.xlsx`, or `.pdf` extension alone.
- Inferring area from height, response, raw traces, or an ordinal column.
- Inferring RT from record order or an unlabeled x-axis.
- Normalizing or converting area values between manufacturers without an explicit
  source rule and separate scientific decision.
- Treating legacy Bruker/Varian/SCION lineage as identical without exact producer and
  profile evidence.
- Delaying Result support until proprietary raw formats are reverse engineered.

## Promotion states

```text
RESEARCH_ONLY
  -> evidence and lawful fixture
EVIDENCE_CANDIDATE
  -> bounded intake and exact profile
IMPLEMENTATION_GO
  -> adapter, source-to-canonical comparison, workbook tests
EXPERIMENTAL_GO
```

Profiles blocked by fixture licensing, multi-run structure, or 2D retention remain in
their explicit blocked state rather than being promoted by inference.
