# Agilent ChemStation `.CH` internal version 179

- Support status: Experimental
- Emits: one scientific signal per file
- Does not emit: peaks, area, height, compound identity

## What is read

Internal version 179 shares the `.CH` header family with version 181 and differs only in its
payload, which is an uncompressed little-endian binary64 array rather than compressed records.

```bash
ordifile inspect FID3A.CH --verbose
ordifile convert FID3A.CH --include-signals --output Ordifile_Result.xlsx
```

The output is a `SeriesKind.SCIENTIFIC_SIGNAL` series. Retention time is constructed from the
file itself:

```text
start_ms = big-endian float32 at offset 282
end_ms   = big-endian float32 at offset 286
step     = (end_ms - start_ms) / (point_count - 1)
```

The response uses the scale stored as a big-endian float64 at offset 4732 and the unit lexeme
stored at offset 4172. Only a unit lexeme observed in the validated corpus is promoted to a
physical unit; any other lexeme preserves the numeric response with no unit and reports
`response_unit_status: unresolved`.

Ordifile does not integrate, detect peaks, or derive an area for this format.

## Evidence and its boundary

The retention-time construction is validated against paired vendor report exports: the step is
exactly 20.000 ms across the sampled files, the header float32 at offset 290 equals the decoded
maximum, and official retention times land on decoded maxima. The response scale agrees with
the same exports to within 0.5%, with a one-directional residual consistent with an integration
window slightly wider than the vendor's.

That scale is therefore **supported but not proven exact**, and `response_scale_status` records
this as `stored_supported_not_proven`. An area a researcher derives from the emitted signal is
not a vendor Result. Confirming the scale needs an acquisition with a different attenuation or
instrument together with its paired report; the validated corpus is one laboratory with one
instrument and one method. See the
[v179 investigation](../research/agilent-chemstation-ch-v179-investigation.md).

## Detection and safety

The `.ch` extension is supporting evidence only. Detection validates the shared bounded header:
the ASCII and numeric version fields, the `GC DATA FILE` marker, the producer text, and the
data-page field that fixes the payload boundary. The basename must keep the official
`FID<module><channel>` convention; a renamed file is recognised but not routed.

A payload that is not a whole number of stored values, a non-finite stored value, run
boundaries that do not increase, a non-positive response scale, or a decoded maximum that
disagrees with the value stored in the header each fail closed with a structured error.

Version 181 files are not claimed by this adapter, and the separate v181 adapter continues to
expose structural decoded records only.
