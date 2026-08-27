# YoungIn YL-Clarity PRM marker-derived Area investigation

- Status: Experimental product capability; not vendor-Result equivalence
- Runtime input: PRM only
- Runtime dependency on Result CSV, YL-Clarity, Clarity, vendor DLL or executable: none
- Enabled producer boundary for the independent calculation: exact `9.0.1.19` and
  `9.1.0.76` only; official Area comparison coverage is listed below
- Compatible unknown 9.x: direct signal may remain available, derived Area is unavailable
- Product default: disabled; the GUI exposes a dedicated visible checkbox, while CLI/API
  callers require `--experimental-derived-area` or `experimental_derived_area=True`

## Product requirement

The researcher workflow is `PRM -> Ordifile -> Signals + Peaks/Area -> Excel`. Composite
Result CSV files are development oracles used to measure the calculation; they are not a
runtime input and are not silently paired with PRM files.

PRM does not expose the official Result rows as a repeatable stored RT/Area/Height table.
It does expose source-ordered integration markers. Their observed state machine is:

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
detector table by source channel order. An observed opcode-11 interval excludes a marker
candidate when its raw apex lies in that interval. Across the earlier controlled corpus this
one fixed rule explained 17/17 candidates absent from the displayed official Result and
excluded 0 official rows. The later non-fixed-format intake also contains processing-event
shapes that add or terminate official Result peaks without a one-to-one stored marker window.
Those shapes are not reconstructed: calculated Area fails closed for the affected channel while
scientific Signals remain available.

The observed optional-event fingerprint is also bounded: exact observed source-order opcode
sequences, blank text, one-space group text, canonical GUID framing, zero optional values and
acquisition-bounded time ordering are required. An unobserved payload or sequence disables
calculated Area for that channel while preserving scientific Signals.

For each remaining marker cluster, Ordifile constructs the lower convex envelope of the stored
binary32 signal. The retention time is the raw maximum inside the stored partition. Exact
9.0.1.19 Legacy clusters that originally contain one marker peak use the adjacent envelope
contacts around that maximum as an Ordifile boundary and a straight base-to-base baseline.
Multi-peak 9.0 clusters and exact 9.1 retain the shared lower-envelope partition calculation.
Area is the deterministic trapezoidal sum above the selected baseline using
`dt_seconds = 60 * DStep / MinTicks`.

Ordifile does not search outside stored partitions, move boundaries to match a Result row,
identify compounds, or run an automatic whole-curve peak detector. Exact 9.0.1.19 rows use
`youngin-prm-marker-timetable-hybrid-contact-envelope-v3`; exact 9.1 rows retain
`youngin-prm-marker-timetable-lower-envelope-v2`. Per-row evidence records which boundary rule
was used.

## Owner-controlled oracle comparison

The local-only probe compared 27 content-confirmed PRM/composite-export pairs. No private
filename, path, row value or measured array is recorded publicly.

| Evidence | Result |
|---|---:|
| Official Result rows | 347 |
| FID rows | 243 |
| TCD rows | 104 |
| 9.0 FID rows | 243 |
| 9.0 TCD rows | 83 |
| 9.1 FID rows | 0 — official Peak/Area not tested |
| 9.1 TCD rows | 21 |
| Emitted calculated rows | 340 |
| Rows omitted because the processing-event shape is not implemented | 7 |
| Official rows aligned by derived RT at the three-decimal export precision | 340/340 |
| Area equal after rounding both values to two decimal places | 112/340 |
| Area equal after rounding both values to three decimal places | 29/340 |
| Area equal after rounding both values to four decimal places | 2/340 |
| Area within 1% | 264/340 |
| Area within 5% | 288/340 |
| Median relative Area error | 0.00122% |
| 90th-percentile relative Area error | 0.11303% |
| Maximum relative Area error | 4.44614% |

The non-fixed-format exports add official Start Time and End Time for 25 rows. When those
official displayed boundaries are used only as a development diagnostic, a straight
base-to-base trapezoid matches 16/25 rows at two decimals, 7/25 at three decimals and 0/25 at
four decimals; 24/25 are within 1%. This shows that boundary recovery is the dominant remaining
problem, while residual baseline/integration details still prevent official equivalence. The
official boundaries are not a PRM runtime input. These non-fixed-format exports present official
Area at three decimals; their four-decimal column above is a numerical comparison, not source
display precision. Earlier fixed-format oracles present Area at four decimals.

The bounded calculation now improves the two-decimal result from 61/340 with the previous
lower-envelope-only rule to 112/340, but it still does not pass the requested all-row gate.
All rules were selected and evaluated on this same paired corpus; there is no untouched holdout.
The 340/340 emitted-row RT observation must not be generalized beyond this evidence.

### Decimal-place validation ladder

Area equivalence is evaluated from the least demanding requested presentation first. Candidate
and official values are independently rounded with decimal round-half-even; no percentage
tolerance is substituted for equality at the requested decimal place.

| Reproducible calculation | 2 decimals | 3 decimals | 4 decimals | Interpretation |
|---|---:|---:|---:|---|
| Current bounded hybrid calculation | 112/340 | 29/340 | 2/340 | Product estimate; not official-equivalent |
| Previous lower-envelope-only calculation on the same safely emitted rows | 61/340 | 16/340 | 0/340 | Development baseline |
| Official displayed boundaries plus straight baseline, new 25-row diagnostic | 16/25 | 7/25 | 0/25 | Oracle-only diagnostic; boundaries are not a runtime input |

The two-decimal gate is therefore `NO_GO`: no tested, reproducible calculation reproduces all
340 emitted rows, and 9.1 FID still has no official Result Area rows in the controlled corpus. This is
same-corpus descriptive evidence, not an untouched independent holdout. Three- or four-decimal
product claims are not evaluated as a promotion target until the two-decimal gate passes. The
next decisive evidence is a bounded PRM interpretation that reproduces official processing-event
peak creation/termination and baseline state across independent pairs.

## Product boundary

GUI, CLI and API callers opt in. Every emitted row is labelled `ordifile_marker_derived` and
`ordifile_derived_experimental` in the
canonical/workbook provenance. Its estimate is stored in `calculated_area`; canonical
source-explicit `area` stays empty. It must not be called a stored YL-Clarity Result, official
Area, or vendor-equivalent Result. Height remains unavailable. Calculated-area units are
derived from the validated response unit and seconds:

- exact 9.0 FID/TCD: `mV.s`;
- exact 9.1 FID: `pA.s`;
- exact 9.1 TCD: `mV.s`.

If markers, their sequence, the current processing-table fingerprint, its channel binding, the
integration-type gate or time metadata are unavailable, the
adapter preserves valid scientific Signals and omits derived Peaks/Area for the affected
capability. The standalone exact Result CSV adapter remains the path for explicit vendor
RT/Area/Height rows.

## Primary documentation

- [DataApex Result Table](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.060-results/030.060-result-table.htm)
  defines Area as the trapezoidal sum between peak start/end relative to the baseline and
  distinguishes calculated Result fields from the raw curve.
- [DataApex Integration](https://www.dataapex.com/documentation/Content/Help/030-chromatogram/030.050-method/030.050-integration.htm)
  documents that algorithm/settings and the Integration Table determine peak and baseline
  behavior. Ordifile therefore does not label its independent lower-envelope method as the
  vendor algorithm.
