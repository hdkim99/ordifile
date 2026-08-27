# Automatic official Result acquisition

Status: phase-1 foundation implemented; no production provider is registered.

## Product intent

Ordifile should preserve every directly validated capability from a native source and may
enhance that same logical source with an official Result export produced by normally installed,
licensed vendor software. The export is a private intermediate, not a second user input.

```text
native source
  -> exact/family adapter (direct Signals or structural records)
  -> optional Result acquisition provider
  -> existing exact Result adapter
  -> logical-source merge
  -> one workbook source with Signals and Peaks
```

The acquisition provider does not interpret scientific values. It only invokes a documented
official export path in a bounded temporary workspace. The existing Result adapter owns the
export grammar and canonical `PeakRecord` conversion.

## Contracts

- `ResultAcquisitionProvider` describes environment availability and produces one bounded
  Result artifact.
- The internal `ResultAcquisitionRegistry` has deterministic ownership: at most one provider
  may claim a native adapter.
- The coordinator owns source staging, hashes, temporary-file cleanup, exact Result-adapter
  validation, canonical validation, and failure isolation.
- `merge_acquired_result` preserves the native `SourceFile`, `SampleRecord`, Signals, source
  alias, and sample identity. It rebinds only acquired Peaks and exact-adapter-vetted canonical
  metadata. It rejects
  vendor mismatches, acquired signals, acquired errors, or replacement of native direct Peaks.
- Provider unavailability or export failure preserves direct data and returns a warning.
  Mutation of the original source is a hard integrity failure.
- Intermediate filenames and paths never become workbook provenance.

`DIRECT_ONLY` is the reproducible default while no provider has passed its actual local-vendor
gate. `AUTO` is a typed coordinator policy, not a claim that a provider is available.

## Security, privacy, and interoperability boundary

Providers may use only ordinary documented functionality of software already installed and
licensed by the user. Ordifile does not download vendor software, search arbitrary executable
paths, change installation or application settings, patch binaries, copy DLLs or source, alter
authentication or licensing, or bypass an exact Result adapter. Original inputs are read-only.
Temporary source copies and Result exports are removed by the coordinator.

Provider discovery must remain deterministic and must not take ownership from unrelated exact
or generic adapters. Stateful vendor applications are serialized per provider when a production
provider is eventually enabled.

## Provider gates

### YoungIn YL-Clarity

The repository's existing maintainer-only local bridge models the documented positional-open,
`export_results`, and discard-close command sequence. Package tests cover the vendor-neutral
orchestration, exact Result parsing, merge, cleanup, unavailable/failure fallback, and
fail-closed integrity handling. No executable-invocation provider is shipped in the package.

Production registration still requires an owner-controlled Windows validation with a normally
installed exact YL-Clarity build. The automatically acquired Result must match the same-run
manual baseline for every peak count, RT, Area, Height, channel, unit, and row position. Active
Result Table/profile settings must also be recorded because they determine export grammar.

### Agilent and Shimadzu

Official documentation establishes Result export or system-linkage capabilities, but the
current evidence does not establish a safe unattended replay from Ordifile's supported native
source to the exact supported Result grammar. These remain `FEASIBILITY_ONLY`.

### LECO

The current supported ChromaTOF input is already a Result table containing RT1, RT2, Area, and
Height. An acquisition provider is `NOT_NEEDED` without a lawful native-source workflow.

## Scientific boundary

Automatic Result acquisition never substitutes vendor peak detection, unit inference, or
vendor-algorithm imitation. Without a validated provider, YoungIn PRM produces validated
Signals and, after explicit GUI/CLI/API selection for exact marker/integration profiles, explicitly
Ordifile-derived experimental RT/`calculated_area` rows. A user-supplied exact Result remains an independent source and is not called
equivalent or deduplicated; filenames are never used to merge user inputs.
