# Secondary retention coordinate

- Status: Accepted
- Date: 2026-08-19
- Issue: [#42](https://github.com/hdkim99/ordifile/issues/42)
- Scope: Canonical retention data and workbook representation

## Context

Ordifile's existing result model represents one chromatographic retention coordinate
per peak as `PeakRecord.retention_time` plus `retention_time_unit`. The lawful CC0
Dryad evidence for one LECO ChromaTOF 4.72 GCxGC export profile contains explicit
first- and second-dimension retention times, area, and height for every observed row.
Dropping or hiding the second coordinate would make a Result adapter scientifically
lossy.

The decision must preserve the existing Agilent, Shimadzu, YoungIn, generic, plugin,
and workbook behavior. The evidence establishes two coordinates, not an arbitrary
number of dimensions.

## Decision

`PeakRecord.retention_time` remains the primary, or first-dimension, retention
coordinate. Two optional vendor-neutral fields are appended to `PeakRecord`:

```python
secondary_retention_time: float | None = None
secondary_retention_time_unit: str | None = None
```

The fields are an all-or-none pair. A two-dimensional peak stream must provide finite
numeric primary retention time, secondary retention time, and area values, preserve
source observation order, and use one consistent nonempty unit for each retention
coordinate. Primary and secondary units are independent and are never normalized.

The stream identity remains `(sample_id, source_file, detector, channel)`. A stream is
entirely one-dimensional or entirely two-dimensional; mixed dimensionality within one
stream is invalid. Different streams in one source or workbook may have different
dimensionality.

Source field names and exact profile provenance remain adapter evidence. Canonical
field names do not contain `LECO`, `ChromaTOF`, or `GCxGC`.

## Workbook representation

`Peaks` keeps one row per peak. A one-dimensional-only workbook retains the exact
existing 18-column schema. When any two-dimensional peak is present, these columns are
appended to `Peaks`:

```text
secondary_retention_time
secondary_retention_time_unit
```

The new cells are blank for one-dimensional rows.

`Peak_Order_Matrix` remains a one-dimensional stream sheet with its existing seven
identity columns and atomic `peak_N_rt`, `peak_N_area` pairs. Two-dimensional streams
are not projected into or duplicated in that sheet.

A conditional `Peak_Order_Matrix_2D` sheet holds two-dimensional streams. Its fixed
columns are:

```text
sample_id
source_file
manufacturer
detector
channel
retention_time_unit
secondary_retention_time_unit
area_unit
```

Each source-order peak is an atomic triple:

```text
peak_N_rt1
peak_N_rt2
peak_N_area
```

With Excel's 16,384-column limit, eight fixed columns leave room for 5,458 complete
triples per column segment. A triple is never split. Height remains in `Peaks`; it is
not duplicated in the wide sheet.

`Peak_Matrix` remains an area matrix based only on explicit compound identity. Neither
retention coordinate is used for automatic compound matching or tolerance inference.

## Alternatives

### Generic retention-coordinate collection

A tuple or list could represent arbitrary dimensions, but it would introduce a second
source of truth beside `retention_time` or require a breaking migration of every 1D
adapter and consumer. The current evidence does not justify arbitrary N-dimensional
complexity.

### GCxGC-specific canonical model

A separate peak type would duplicate validation, exporter, and plugin behavior while
putting one technique or vendor into the core model. The canonical layer must remain
usable for other two-dimensional chromatography.

### Separate metadata object

Metadata cannot provide typed, row-aligned scientific coordinates to `Peaks` and the
ordered matrix. This would preserve bytes but lose the product contract.

## Rejected approaches

- Discarding the second retention coordinate.
- Storing it only as a metadata string.
- Concatenating RT1 and RT2 into one text value.
- Emitting separate RT1 and RT2 rows as if they were separate peaks.
- Reusing detector or channel as a retention-coordinate carrier.
- Encoding RT2 in a compound or peak name.
- Sorting peaks by RT1 or RT2 instead of preserving explicit source observation order.
- Normalizing either retention coordinate or area across manufacturers.

## Backward compatibility

The new dataclass fields are appended with `None` defaults, so existing positional and
keyword `PeakRecord` construction remains valid. `DatasetBundle`, the adapter protocol,
public API functions, and adapter API version are unchanged.

Existing one-dimensional adapters require no semantic migration. For a 1D-only batch:

- `Peaks` headers and values are unchanged;
- `Peak_Order_Matrix` headers, values, pair segmentation, and 8,188-peak capacity are
  unchanged;
- `Peak_Order_Matrix_2D` is absent; and
- the existing standalone scientific digest is unchanged.

This is an additive model and conditional workbook capability. It does not decide a
release version; `NEXT_VERSION` remains unresolved.

## Testing strategy

Core tests cover optional defaults, exact types, finite values, value/unit pairing,
unit consistency, mixed-dimensional stream rejection, and source-order preservation.
Workbook tests cover 1D-only, 2D-only, and mixed batches; conditional long-form
columns; separate stream sheets; atomic triple segmentation; the 5,458/5,459 boundary;
sidecar placeholders; reopen; and an unchanged 1D contract.

An exact Result adapter must additionally compare every lawful actual source row
through canonical values and a reopened workbook for RT1, RT2, area, height, units, and
order, with zero loss, duplication, interpolation, or normalization. Standalone
semantic evidence includes `Peak_Order_Matrix_2D` whenever that conditional sheet is
present.

## Migration impact

No existing fixture or stored workbook must be rewritten. Code that consumes
`PeakRecord` may opt into the new fields. Code that reads `Peaks` sees two appended
columns only in workbooks containing two-dimensional peaks. Existing 1D matrix
consumers keep their current sheet contract.

## Future scope

This ADR does not define arbitrary N-dimensional retention tensors, second-dimension
integration boundaries, multi-sample exports in one source file, raw GCxGC data,
spectral deconvolution, or retention-based compound matching. Each requires separate
evidence and, where necessary, another architecture decision.
