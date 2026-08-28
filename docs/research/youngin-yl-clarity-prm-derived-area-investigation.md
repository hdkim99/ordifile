# YoungIn YL-Clarity PRM marker-derived Area investigation

- Status: Reproduces the displayed vendor Area for 304 of the 305 rows it emits across the
  controlled corpus, and for 304 of that corpus's 347 official rows; still labelled an Ordifile
  calculation, not a stored Result
- Runtime input: PRM only
- Runtime dependency on Result CSV, YL-Clarity, Clarity, vendor DLL or executable: none
- Enabled producer boundary: exact `9.0.1.19` and `9.1.0.76` only
- Compatible unknown 9.x: direct signal may remain available, calculated Area is unavailable
- Product default: disabled; the GUI exposes a dedicated visible checkbox, while CLI/API
  callers require `--experimental-derived-area` or `experimental_derived_area=True`

## Product requirement

The researcher workflow is `PRM -> Ordifile -> Signals + Peaks/Area -> Excel`. Composite
Result CSV files are development oracles used to measure the calculation; they are not a
runtime input and are not silently paired with PRM files.

PRM does not expose the official Result rows as a stored RT/Area/Height table. Every
uncompressed key and every gzip member of the controlled corpus was searched for the
displayed Area, Height and boundary values; none is stored. The file does expose
source-ordered integration markers. Their observed state machine is:

```text
start (0x20) -> apex marker (0x50)
               -> [valley (0x40) -> apex marker (0x50)]*
               -> end (0x80)
```

Adjacent repeated end markers and a final start-only marker occur in the controlled corpus.
They are recorded as ignored incomplete markers and never become synthetic peaks. Detached
end markers, direct start-to-end regions, and clusters without a final end are rejected for
this optional capability while valid Signals remain available.

## Calculation

Ordifile first validates the current-history 32-slot processing-table framing and binds the
detector table by source channel order. For each stored marker cluster it then resolves peak
groups, one straight baseline per group, and an Area:

1. **Retention time** is the stored-response maximum inside the stored marker partition. The
   stored apex marker itself drives the geometry; the stored-response maximum is what the row
   reports. Everything below reads the response series the PRM stores, which is what this work
   establishes; no claim is made about the instrument's pre-processing chromatogram.
2. **Peak groups.** The lower convex hull of the stored signal over the marker cluster gives
   the points where the baseline touches the response. The group is first narrowed to the
   contacts adjacent to its outer apexes. Any remaining contact that separates two stored
   apexes splits the cluster into two independent groups, and the rule is then applied to
   each of them until no further contact separates two apexes.
3. **Group boundary at a split.** The left group ends by walking back from the stored valley
   through response excursions no larger than the stored `Threshold` value, taking the lowest
   sample reached. The right group begins at the stored valley itself, before its own hull
   narrowing is applied.
4. **Fused peaks inside a group** are separated at the stored-response minimum between
   neighbouring
   stored apexes, which is a vertical drop line, not a baseline break.
5. **Baseline** is the straight line between the two contacts of the group.
6. **Area** is `sum over k in [start, end) of (response[k] - baseline(k + 0.5)) * dt_seconds`,
   with `dt_seconds = 60 * DStep / MinTicks`. This is not the general trapezoidal rule: the
   response is taken at the left edge of each interval and the baseline at its centre. The two
   forms are not algebraically identical, and only this one reproduces the compared rows, so it
   is named a controlled-corpus-derived left-edge/midpoint summation rather than a trapezoid.

A retention index that the narrowed partition does not contain is a structured failure, not a
clamped value: the affected channel fails closed.

Ordifile does not search outside stored partitions, move boundaries to match a Result row,
identify compounds, or run an automatic whole-curve peak detector.

## Owner-controlled oracle comparison

Four independent owner archives were compared, covering both validated producer versions,
both detectors and both composite-export layouts. Archives are referred to by alias; no
private filename, path, row value or measured array is recorded publicly.

| Archive | Producer | Official rows | Compared | Area exact at the export's own precision | Not compared |
|---|---|---:|---:|---:|---:|
| A — composite export | 9.0.1.19 mV | 263 | 241 | 241 | 22 |
| B — fixed-format export | 9.0.1.19 mV | 38 | 28 | 28 | 10 |
| C — fixed-format export | 9.1.0.76 pA/mV | 21 | 21 | 21 | 0 |
| D — non-fixed-format export | 9.0.1.19 mV | 25 | 15 | 14 | 10 |
| **Total** | | **347** | **305** | **304** | **42** |

The 42 rows that are not compared are exactly the rows of channels that fail closed; see the
next section. They are not failures of the calculation, but they are also not evidence for it,
so both denominators are reported: **304/305 of the rows the calculation emits, and 304/347 of
the official rows in the corpus.**

Retention time matches the displayed value for every compared row. Archive A also exists as a
vendor Excel export that publishes twelve significant digits instead of a rounded column. Against
that full-precision oracle the 241 compared rows agree as follows:

| Quantity | Result |
|---|---|
| Retention time | 241/241 identical |
| Start time and End time | 241/241 identical |
| Area, maximum relative difference | `4.025e-13` (`4.025e-11 %`) |
| Area, median relative difference | `6.4e-14` |

Against the rounded four-decimal columns of the same archive the maximum relative difference is
`6.9e-5` (`0.0069 %`). That residual is consistent with the oracle's own display rounding rather
than with a difference in the calculation: the same runs agree to twelve significant digits when
the oracle publishes them.

The single mismatch is one group end in one channel of archive D, where the vendor stops the
descending tail one noise excursion earlier than the stored `Threshold` rule does. Its relative
Area difference is `0.0073` (`0.73 %`). Archive D publishes Area at three decimals, so it has no
full-precision oracle.

This replaces the previous lower-envelope calculation, which reproduced 112/340 rows at two
decimal places on the same evidence.

The rules were selected on archives A and D. Archives B and C were not consulted while the rules
were being chosen and were measured only afterwards, so they are the closest available
independent check; they are not a formally reserved holdout.

## Channels that fail closed

Peak detection and termination change when a researcher adds timed processing events to the
method by hand. The controlled corpus contains three such stored opcodes, `11`, `12` and `32`.

Their meanings below are **not** taken from a published opcode specification. No such
specification was consulted. They are the only reading consistent with what the owner observed
while making the interventions themselves, compared against the resulting exports:

| Opcode | Observed correlation | Confidence |
|---|---|---|
| `11` | Every stored marker candidate whose stored-response apex falls inside the interval is absent from the official Result. | Consistent across every occurrence in the corpus. |
| `12` | No reading is consistent with the corpus. One occurrence spans nearly the whole run without suppressing any official peak. | **Unresolved.** |
| `32` | The first time equals an official peak's retention time and the second behaves like an offset from it toward that peak's end. | Directionally consistent; the exact snapping is not reproduced. |

Because a channel can carry any of the three, and because `12` is unresolved, none of them is
acted on. Ordifile **omits calculated Peaks/Area for any channel whose processing table carries
one of those events**, records the channel status `time_table_manual_event_unsupported`, and
preserves the scientific Signals. Had they been acted on with the readings above, measured
agreement on those channels would have been 16/39 rows. The 42 rows those channels contribute
are the difference between the 305 compared rows and the corpus's 347 official rows.

The same fail-closed behaviour applies when markers, their sequence, the processing-table
fingerprint, its channel binding, the integration-type gate or time metadata are unavailable,
and when the calculation itself produces a partition that does not contain its own retention
index, an Area that is not strictly positive, or a group resolution that exceeds its bounded
sample budget.

## Product boundary

GUI, CLI and API callers opt in. Every emitted row is labelled `ordifile_marker_derived` and
`ordifile_derived_experimental` in the canonical/workbook provenance. Its value is stored in
`calculated_area`; canonical source-explicit `area` stays empty. Height is calculated internally
so that it can be checked against owner exports, but it is **not** published as a product field:
`PeakRecord.height` stays empty for these rows, and no export profile carries a calculated
Height. Publishing it would need its own field, export-profile change and regression coverage.

The calculated Area must not be called a stored YL-Clarity Result or a vendor Result table: it
is an independent calculation that reproduces the displayed value on the evidence above. Rows use
`youngin-prm-marker-group-baseline-v4`. Calculated-area units are derived from the validated
response unit and seconds:

- exact 9.0 FID/TCD: `mV.s`;
- exact 9.1 FID: `pA.s`;
- exact 9.1 TCD: `mV.s`.

The standalone exact Result CSV adapter remains the path for explicit vendor
RT/Area/Height rows.

## Primary documentation

- [DataApex Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-result-table.htm)
  defines Area as the trapezoidal sum between peak start/end relative to the baseline and
  distinguishes calculated Result fields from the raw curve.
- [DataApex Integration](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.050-method/030.050-integration.htm)
  documents that algorithm/settings and the Integration Table determine peak and baseline
  behavior. Ordifile therefore does not label its independent calculation as the vendor
  algorithm, and does not claim its summation is the trapezoidal definition quoted above.
