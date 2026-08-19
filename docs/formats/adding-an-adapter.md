# Adding a format adapter

> Development preview: the public adapter API is stabilized by tests before v0.1. Check
> the current protocol and API version in the source tree when implementing a plugin.

Ordifile adapters detect and parse one source format into the canonical data model.
They do not discover files, sort batches, write workbooks, or implement user interfaces.

## Evidence and license gate

Before implementation, document:

- an official specification, vendor manual, standard, or independently verifiable
  technical source;
- the exact distinction between metadata, peaks, signals, spectra, and write support;
- every new dependency's maintenance state, actual LICENSE file, transitive dependencies,
  and distribution impact;
- fixture ownership, anonymization, and explicit redistribution permission;
- any trademark, patent, proprietary format, vendor SDK, or binary redistribution risk.

Do not copy code from another project without an explicit compatible license review. Do
not include vendor SDKs, DLLs, executables, licensed documentation, or real user files.

## Interface

An adapter implements the typed `FormatAdapter` protocol:

```python
class FormatAdapter(Protocol):
    api_version: ClassVar[str]
    adapter_id: ClassVar[str]
    adapter_version: ClassVar[str]
    descriptor: ClassVar[AdapterDescriptor]

    def probe(self, path: Path) -> DetectionResult: ...
    def parse(self, path: Path, options: ParseOptions) -> DatasetBundle: ...
```

`adapter_id` is a stable, globally unique lowercase identifier. `adapter_version`
describes the implementation. `api_version` declares compatibility with Ordifile's
plugin contract.

## Detection

- `probe` must be read-only, side-effect free, and bounded.
- Never decide from an extension alone. Combine extension evidence with content magic,
  delimiter/header structure, archive members, or other documented internal evidence.
- Return confidence and human-readable evidence.
- Do not claim a match for an unsupported format variant.
- If multiple adapters make equally strong claims, Ordifile returns a structured
  ambiguity error rather than choosing one silently.

## Parsing

- Preserve original values, units, axes, channels, detector names, and source row
  provenance wherever available.
- Map only documented headers and fields. Preserve unknown fields without inventing
  semantics.
- Never interpolate, truncate, aggregate duplicate compounds, infer identity from
  retention time, or silently coerce invalid values.
- Return structured warnings for recoverable conditions and structured errors for data
  that cannot be interpreted safely.
- In v0.1, return exactly one `SourceFile` and one `SampleRecord` for each parsed input.
- Set `MetadataEntry.source` only to a relative logical locator such as
  `sheet:1:cell:D2`. Absolute paths, Windows drive paths, and control characters are
  rejected to prevent local machine details from entering a workbook.
- Treat exact empty values, whitespace-only values, and non-empty text as distinct cases.
  Preserve leading/trailing whitespace and original numeric or timestamp lexemes when a
  parser uses a normalized copy.
- Keep canonical integers within Ordifile's documented bounds. Check lexeme length and
  exponent before constructing an integer; do not allow a tiny source value to allocate an
  unbounded Python integer.
- Use exact built-in canonical types and immutable tuples. Do not return subclasses with custom
  conversion hooks; Ordifile runtime-validates and isolates malformed plugin bundles, but
  adapter tests should catch contract violations at their source.
- Put only `Severity.WARNING` issues in `DatasetBundle.warnings` and only `Severity.ERROR` issues
  in `DatasetBundle.errors`. Codes use bounded uppercase ASCII identifiers. Issue messages,
  sources, and context must not contain absolute machine paths or local file URLs.
- Keep text that must appear in `Samples` or `Import_Log` within Excel's 32,767-character cell
  boundary. Preserve larger scientific values through the documented Metadata/sidecar policies,
  not by overloading audit identity fields.
- Do not catch process-level exceptions such as `KeyboardInterrupt`, `SystemExit`, or
  `MemoryError` as ordinary parse failures.

## Canonical output

Populate only the capabilities supported by evidence:

- `SampleRecord` for one logical sample/run;
- `MetadataEntry` for namespaced key/value metadata;
- `PeakRecord` for explicit peak fields and compound assignments;
- `SignalSeries` for original ordered x/y points without default interpolation;
- `Issue` for warnings and errors with stable codes and actionable messages;
- `DatasetBundle` as the adapter result.

For evidence-backed two-dimensional chromatography, keep the first coordinate in
`PeakRecord.retention_time` and provide both
`PeakRecord.secondary_retention_time` and
`PeakRecord.secondary_retention_time_unit`. Never drop RT2, concatenate coordinates,
or reuse metadata, detector, channel, or compound fields as a coordinate carrier. A
stream must be wholly 1D or wholly 2D. See the
[`secondary-retention-coordinate`](../architecture/secondary-retention-coordinate.md)
ADR for workbook and validation requirements.

Use `SeriesKind.DECODED_RECORDS` when byte-level records do not yet have verified
scientific signal semantics. Such records must not be presented as calibrated or
time-based data. In the descriptor, `signals=True` means that the adapter returns a
`SignalSeries`; callers must inspect `series_kind` before treating it as a scientific
signal. The CLI labels Experimental decoded-record output separately.

## External registration

External packages register an adapter factory in the `ordifile.adapters` entry-point
group. The registry rejects duplicate adapter IDs and incompatible API versions. Because
Python entry points execute installed code, third-party adapters must be treated as
trusted software.

Descriptors use bounded stable IDs, versions, extension tuples, exact Boolean capability flags,
and workbook-representable display names. Set `tested_fixture=True` only when the declared
capabilities have a redistributable or synthetic fixture and passing tests; `list_formats()` and
the CLI support table omit descriptors without that declaration.
Set `support_status` independently to `VERIFIED`, `EXPERIMENTAL`, or the default
external `FIXTURE_DECLARED` evidence level.

Example registration in an adapter package's `pyproject.toml`:

```toml
[project.entry-points."ordifile.adapters"]
my_format = "my_ordifile_adapter:MyFormatAdapter"
```

## Fixtures and tests

Every supported capability requires a synthetic or explicitly redistributable fixture
and tests covering:

1. positive and negative detection;
2. a valid parse with exact values and units;
3. corrupt, truncated, empty, and wrong-version inputs;
4. Unicode and space-containing paths;
5. duplicate or ambiguous fields;
6. large-input boundaries and resource preflight;
7. integration through the public batch API and workbook reopen checks;
8. failure isolation when a valid and invalid file are processed together.

Document each fixture's generator or provenance, license, checksum, and expected values.
Tests must not rely on installed vendor software or network access.

## Documentation checklist

- Add a format page under `docs/formats/` describing exact capabilities and limits.
- Update both `README.md` and `README.ko.md` support matrices only after tests pass.
- Mark metadata, peaks, and signals independently.
- Identify the tested fixture and format/software version.
- Do not count `Planned` or `Experimental` entries as supported.
- Add dependency notices and changelog entries when applicable.
