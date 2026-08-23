# Product concept

Ordifile is a local-first scientific chromatography data converter. It combines
explicit Result files and structured peak tables from different instrument or CDS
workflows into canonical records and one ordered, auditable Excel workbook without
changing measured scientific meaning.

## Target users and problem

Ordifile is for chromatography researchers, GC/GC-MS/GC×GC laboratories, non-Python
desktop users, and CLI/API users who repeatedly consolidate exports from more than one
instrument or template. The core problem is not scientific interpretation; it is the
reliable, reviewable conversion of heterogeneous result tables into one consistent
workbook.

The supported workflow is:

```text
known exact Result profile          -> exact adapter
unknown structured Result           -> explicit RT/Area mapping
repeated template                    -> Mapping Profile
multiple templates                  -> Mapping Set
changed template                     -> drift diagnostic and user-confirmed repair
large mixed input                    -> Conversion Preflight and review
repeated laboratory configuration   -> Conversion Recipe
reviewed plan                        -> revalidate, convert, and inspect one workbook
```

Exact Experimental profile support and generic mapping are different claims. An exact
adapter owns only the profile boundary proved by lawful fixture evidence and passing
tests. Generic mapping records the user's explicit column and unit choices; it does not
turn that input into vendor-supported evidence.

## Scientific non-goals

Ordifile is not intended to replace a CDS or LIMS, control acquisition, run vendor
software, detect peaks, identify or match compounds, align retention times, normalize or
aggregate scientific values, perform calibration or quantitation, provide a statistics
suite, or perform full mass-spectral analysis. Missing detector identity, units, or
scientific fields remain unresolved instead of being inferred.

## Local-first data handling

Scientific inputs are read-only and processing is local. Ordifile has no telemetry,
automatic upload, cloud account, or sync service. Workbooks use bounded public-safe
source references and do not add absolute source paths, Recipe paths, or full local
Mapping/Recipe JSON. Local Mapping and Recipe files may contain private headers or
labels and should be handled as privacy-bearing laboratory configuration.

## Long-term decision criteria

A proposed capability should proceed only when it solves a demonstrated researcher
workflow that existing features and documentation cannot solve, preserves scientific
semantics and fail-closed routing, works through the shared core contract, has lawful
test evidence, and has a maintenance cost proportional to its value. Documentation or a
small usability correction is preferred when it fully resolves the observed friction.
Format support requires exact evidence; popularity or filename resemblance is not
enough. Version numbers and release timing are separate decisions from capability work.
