# Researcher acceptance suite

The researcher acceptance suite answers one question: can a researcher complete the
supported Ordifile workflows without silent routing, scientific, or output changes? It
selects existing public-boundary integration tests instead of duplicating a second
conversion engine or a parallel fixture set.

Run the focused suite from a development installation:

```console
pytest --no-cov -m researcher_acceptance
```

Run ordinary `pytest` separately for the full coverage gate. The focused command disables
only the repository-wide coverage threshold for the selected subset; it does not replace
the full test suite.

## Scenario map

| Scenario | Researcher journey | Representative test contract |
|---|---|---|
| A | Four public-safe synthetic exact profiles route automatically into one workbook | `test_four_vendor_synthetic_results_share_one_1d_and_2d_workbook` |
| B | Neutral CSV/TSV/semicolon and XLSX tables use explicit RT/Area mapping | `test_explicit_text_mapping_creates_ordered_peaks`; `test_explicit_xlsx_mapping_reuses_audited_reader` |
| C | New values with an unchanged structure reuse the same exact Mapping Profile | `test_recipe_reuses_same_profile_for_new_values_and_surfaces_drift` |
| D | CSV and XLSX templates plus exact inputs use one Mapping Set with exact-owner precedence | `test_mapping_set_routes_multiple_generic_templates_into_one_workbook` |
| E | Schema drift is not applied automatically; confirmed repair creates a new profile and preserves the old one | `test_mapping_set_reports_schema_drift_without_applying_a_candidate`; `test_repaired_profile_routes_old_and_new_templates_separately` |
| F | An embedded-Mapping-Set Recipe goes through Preflight, freshness validation, conversion, and workbook reopen | `test_recipe_routes_mapping_set_and_convert_runs_mandatory_preflight`; stale Recipe tests |
| G | A mixed folder reports exact, mapped, drifted, unmapped, unsupported, and duplicate outcomes consistently | `test_mixed_preflight_routes_exact_profiles_and_failures_then_matches_conversion` |
| H | One workbook keeps 1D and 2D peaks, matrices, coordinates, and units separate | Scenario A plus the LECO exact pipeline assertions |
| I | Valid, malformed, and unsupported inputs produce an explicit partial result | `test_valid_malformed_and_unsupported_files_preserve_partial_workbook` |
| J | Dry run creates no workbook, existing output is not silently replaced, and source bytes are unchanged | `test_convert_dry_run_prints_privacy_safe_plan_and_creates_no_artifact`; `test_overwrite_and_input_output_protection` |
| K | A desktop user saves a repeated setup by name, restarts, and reuses it without a JSON dialog | `test_save_first_named_recipe_uses_no_json_dialog_and_persists_after_restart` |
| L | Selecting a named desktop Recipe applies its immutable settings and requires a new Preflight review | `test_window_selects_named_recipe_and_requires_explicit_preflight_refresh` |

The README Quick Start output is also selected so the copyable first-use claim remains
consistent with the generated workbook.

## Evidence boundaries

All selected repository tests use synthetic or redistributable data. Vendor-labelled
synthetic files exercise an exact parser boundary but are not vendor-generated evidence.
The controlled actual baseline of Agilent 36, Shimadzu 83, YoungIn 6, and LECO 100 peaks
(225 total) remains a separate, non-distributed scientific regression contract.

Acceptance checks public APIs, typed Mapping/Recipe/Plan models, CLI behavior, and
read-only workbook reopening. Detailed unit tests continue to own format parsing,
transaction finalization, Excel limits, and bounded validation.

## Scale and reliability method

Use small (10–20), medium (about 100), and practical large (500–1,000) public-safe batches
for local measurement. Record file count, peak count, planning and conversion wall time,
workbook size, peak memory, repeated semantic result, and temporary-file cleanup. Do not
turn one machine's timing into a general performance promise.

Reliable file identity avoids pairwise path checks, but filesystems without stable
identity can require fallback comparisons. Ordered matrices are rectangular by stream
count and maximum peak count. Therefore no blanket linear-complexity claim is made.
Acceptance requires deterministic routing and canonical values, source-byte preservation,
no `.ordifile_*` leftovers, and the existing 10,000-input/64-GiB Preflight bounds.
