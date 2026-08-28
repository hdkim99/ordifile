# Agilent ChemStation `.CH` internal version 179 investigation

- Status: Time axis resolved and validated against a paired vendor oracle; response scale
  supported by the same oracle but not proven exact
- Evidence: one owner-approved CC BY 4.0 corpus of 2,678 `.ch` files with paired report
  exports from one laboratory, one instrument and one method

## Why this generation was examined

The exact `.CH` v181 adapter emits structural decoded records only. Its own notes record the
retention-time construction, physical signal scaling, and unit as unresolved, and no paired
full-resolution export exists for the v181 fixture. The v179 corpus supplies what v181 lacks:
each acquisition directory carries a signal file and a sibling report export listing official
retention times and areas, so a decoded axis can be checked rather than assumed.

## The header is the same family

Every bounded marker the v181 reader validates is present at the same offset and with the same
value in v179: the ASCII version lexeme at 0, the numeric version at 248, `GC DATA FILE` at
347, `Asterix ChemStation` at 3089, and the sample, acquisition, instrument and method text
fields. The data-page field at 264 is 13, giving the same 6,144-byte payload boundary.

The generations differ in the payload, not the header. v181 stores compressed records with an
absolute-record marker; v179 stores an uncompressed little-endian binary64 array.

## Retention time

The two candidate numeric fields the v181 reader already isolates carry the axis:

```text
start_ms = big-endian float32 at offset 282
end_ms   = big-endian float32 at offset 286
step     = (end_ms - start_ms) / (point_count - 1)
```

Across eight sampled files the step is exactly 20.000 ms, so the axis is derived from the file
rather than assumed. Two independent checks support the decode:

| Check | Result |
|---|---|
| Step equals 20.000 ms | 8 / 8 files |
| Header float32 at 290 equals the decoded maximum | 8 / 8 files, within 1e-7 relative |
| Official report retention times land within 6 samples of a decoded maximum | 24 / 27 peaks large enough to have an unambiguous apex |

On one file, after a one-sample origin correction, the residual across thirteen unambiguous
peaks has median zero and ranges from -3 to +6 samples. That spread is consistent with the
vendor reporting an interpolated apex rather than the raw maximum sample.

## Response scale and unit

The header stores a response unit lexeme at 4172, which reads `pA` in this corpus, and a
big-endian float64 at 4732 whose reciprocal is exactly 7,680.

Integrating baseline-resolved peaks with a straight baseline and comparing against the official
areas gives a single constant factor of 7,717 with a standard deviation of 132 over 25 peaks.
The stored reciprocal of 7,680 sits 0.49 % from that measurement, and the residual bias is one
directional, which is what an integration window slightly wider than the vendor's produces. The
nearest competing round value, 8,192, is 3.6 standard deviations away and is excluded.

The same offset holds a different value in both v181 fixtures, `13/384` rather than `1/7680`,
and both are surrounded by zeroes. A field that varies between acquisitions and is isolated
from its neighbours behaves like a scale field.

## What is not established

The scale is supported, not proven. Proving it would require reproducing the vendor's own
integration boundaries, and unlike the YoungIn PRM work there is no stored marker stream to
supply them. This corpus also cannot settle whether offset 4732 *is* the scale field: it is one
laboratory with one instrument and one method, so the value is internally constant. A second
acquisition with a different attenuation or a different instrument, together with its paired
report, would settle it.

The response unit is therefore taken from the stored lexeme, and the calculated area a
researcher derives from the emitted signal is not claimed to reproduce the vendor's own area.
