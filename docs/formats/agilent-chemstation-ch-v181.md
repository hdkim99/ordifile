# Agilent ChemStation `.CH` internal version 181

Status: **Experimental** (included in the v0.2.0 source tree; published availability is
shown by the PyPI badge)

Ordifile can detect one narrowly bounded ChemStation GC data profile and expose its
decoded structural record stream. This is not a verified chromatogram signal and is
not a claim of general Agilent, OpenLab, ChemStation, `.D`, or `.CH` compatibility.

## Exact capability

| Capability | Status |
|---|---|
| Bounded header and internal version 181 detection | Experimental, real-fixture tested |
| All decoded records in source order | Experimental, cross-reader compared |
| Record ordinal x values | Available |
| Retention-time axis | Not supported |
| Raw decoded integer y values | Experimental |
| Physical/display scaling | Not applied |
| Signal unit | Unknown |
| Sample/method/local timestamp text | Raw metadata only; century/timezone unresolved |
| FID/channel identity | Filename convention only |
| Peaks | Not supported |
| Other `.CH` versions or detector families | Not supported |

Use `--include-signals` to write the decoded records:

```bash
ordifile inspect FID1A.CH --verbose
ordifile convert FID1A.CH --include-signals --output Ordifile_Result.xlsx
```

The complete basename must exactly match the strict `FID<module><channel>` convention;
renamed files and other detector names are rejected as unsupported. The extension is
supporting evidence, so a structurally exact file with the original FID basename can
still be recognized after an extension change. The output sheet is named
`Signals_Records_FID`. Its x axis is `decoded_record_index`, not retention time. Its y axis
is `decoded_raw_integer`, not a calibrated or physically scaled response.

Every record is retained, including the exact fixture's ambiguous final zero record.
Metadata and `Import_Log` explicitly mark the Experimental representation, unresolved
scientific point count, absent time axis, unapplied scaling, and unknown unit.

## Detection and rejection

The `.CH` suffix is supporting evidence only. Detection also requires both version
fields to equal 181, the bounded `GC DATA FILE` marker, the exact validated producer
text `Asterix ChemStation`, the validated data-page field, and a payload inside the file.
Parsing rechecks the header and rejects unsupported detector/renamed basenames, truncated
absolute records, unmatched trailing bytes, unsupported versions, version conflicts,
overflow, and the adapter record limit.

## Evidence and limitations

The real external BSEE fixture is not committed. Its size and SHA-256 are pinned in
the external fixture manifest and its record summaries are tested on a maintainer-only
path. See the [investigation](../research/agilent-chemstation-ch-v181-investigation.md)
and [independent implementation notes](../research/agilent-chemstation-ch-v181-format-notes.md).

Verified status requires additional independent v181 runs and a same-run official
ChemStation CSV/AIA/CDF or vendor display comparison that resolves scientific point
count, retention time, scaling, and unit semantics.

Agilent and ChemStation are trademarks or product names of their respective owner.
Ordifile is independent and is not affiliated with or endorsed by Agilent.
