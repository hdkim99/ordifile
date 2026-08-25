# Researcher pilot checklist

Use this checklist to learn the complete Ordifile workflow with public-safe synthetic
data, then repeat it with a small, representative copy of your own exports. The pilot
files are neutral demonstrations, not vendor-generated data and not evidence of exact
vendor support.

## 1. Choose and record the pilot build

Use one installation channel and record which one you used. The published PyPI release
and an unreleased build from `main` can have different capabilities even when both report
the same package version.

For the latest published release:

```console
python -m pip install ordifile
ordifile --version
ordifile formats
```

For its Python-package desktop interface:

```console
python -m pip install "ordifile[gui]"
ordifile-gui
```

For an unreleased field pilot, use a standard wheel built by the maintainer from one
reviewed exact commit. Do not use the PyPI command above as evidence that you tested that
commit. The maintainer records the source commit and wheel SHA-256, then provides the
wheel and the install command privately. Install each pilot build in a fresh virtual
environment where Ordifile is not already installed. This prevents pip from retaining
different bytes that have the same `0.5.0` package version. Use the same fresh environment
for the CLI and GUI.

Create and activate the environment using the command for the operating system:

```console
python -m venv ordifile-pilot
# macOS or Linux
source ordifile-pilot/bin/activate
# Windows PowerShell, instead of the preceding activation command
.\ordifile-pilot\Scripts\Activate.ps1
```

Install either the CLI-only wheel or the same artifact with its `gui` extra. The direct
wheel-reference example below uses a macOS/Linux file URI; the maintainer supplies the
equivalent private command for the pilot computer:

```console
# CLI-only pilot
python -m pip install /path/to/ordifile-0.5.0-py3-none-any.whl
# Or GUI pilot, which also installs the CLI
python -m pip install "ordifile[gui] @ file:///path/to/ordifile-0.5.0-py3-none-any.whl"
ordifile --version
ordifile formats
ordifile-gui
```

Replace the placeholder with the private local wheel path supplied for the pilot. Record
the exact commit and wheel SHA-256 separately because `ordifile --version` remains the
package version. The wheel is a maintainer/researcher pilot artifact, not an official
release, tag, PyPI upload, GitHub Release, `.exe`, or `.app`.

No public standalone `.exe` or `.app` is distributed. Record only the OS family,
architecture, Python version, Ordifile version, the privacy-safe commit and wheel-hash
prefixes when applicable, and relevant dependency versions when reporting a compatibility
problem. Supported Python versions are 3.11 through 3.14.

## 2. Run the neutral Mapping Set and Recipe pilot

From a repository checkout:

```console
ordifile inspect examples/pilot/inputs/template-a.csv \
  --peak-mapping examples/pilot/template-a.mapping.json

ordifile convert examples/pilot/inputs \
  --recipe examples/pilot/laboratory.recipe.json \
  --output Pilot_Result.xlsx \
  --dry-run
```

The dry run must report two inputs routed by Mapping Profile and must not create
`Pilot_Result.xlsx`. Then convert using the same runtime inputs and output:

```console
ordifile convert examples/pilot/inputs \
  --recipe examples/pilot/laboratory.recipe.json \
  --output Pilot_Result.xlsx
```

Expected synthetic result:

- 2 successful sources and 0 failed sources;
- 2 sample/run streams and 4 canonical peaks;
- Template A RT values `1.25` and `2.50` in `min`, Areas `10` and `20` in `pA*s`,
  and Heights `2` and `4` in `pA`;
- Template B RT values `30` and `45` in `s`, and Areas `100` and `200` in `AU`;
- input bytes unchanged;
- `Manifest`, `Samples`, `Peak_Matrix`, `Peak_Order_Matrix`, `Peaks`, `Metadata`, and
  `Import_Log` present when applicable.

The local display labels in the example JSON are not scientific provenance. A real
Recipe can contain private headers or labels. Keep it local and do not attach it to a
public issue without reviewing every field.

## 3. Desktop pilot

First use without creating or locating JSON:

1. Select **Add Files** and choose both `examples/pilot/inputs/template-a.csv` and
   `examples/pilot/inputs/template-b.tsv`.
2. Choose a new `.xlsx` output path.
3. Select **Refresh Preflight** and confirm that only the two generic inputs require
   mapping.
4. Expand **Mappings & reusable workflow**. In **Selected files and folders**, select
   exactly one of the two files, then choose **Map Peak Columns…**. Confirm its explicit
   RT, Area, optional Height or Compound columns, and units.
5. Choose **Add Current**, give that Mapping Profile a local name, then repeat the mapping
   and **Add Current** steps for the other input. Confirm that **Use mapping set for batch
   routing** is selected.
6. Select **Refresh Preflight** and confirm two Mapping Profile routes.
7. Choose **Save Current…** and give the reviewed setup a local Recipe name.
8. Convert, then open the output and review `Samples` and `Import_Log` first.

To reuse this laboratory setup:

1. Select its local name in **Recipe (optional)**.
2. Add the experiment folder and choose a new output.
3. Select **Refresh Preflight** and confirm two Mapping Profile routes. Selecting a Recipe,
   changing its effective settings, changing inputs, or changing output invalidates the
   previous preview.
4. Convert. Recipe selection never starts conversion or bypasses Preflight.

The repository's `examples/pilot/laboratory.recipe.json` remains an optional portability
demonstration. **Manage… → Import Recipe…** may import it, and **Export Recipe…** may move a
reviewed setup to another computer or a CLI/API workflow, but neither JSON action is
required for ordinary desktop use.

The GUI uses the same Mapping, Recipe, Preflight, and conversion contracts as the CLI.
It does not silently overwrite an existing workbook or silently save changes back to a
loaded Recipe. The local Recipe library may contain private headers or labels, but it stores
no measured rows, input paths, or output paths.

## 4. Review the workbook

Follow the [workbook interpretation guide](workbook-guide.md). At minimum:

- compare every pilot RT, Area, Height, and unit with the two source tables;
- confirm `Samples` and `Import_Log` contain the same two source outcomes;
- use `Peaks` as the canonical row-level review table;
- treat matrices as derived views, not replacements for `Peaks`;
- verify unresolved units remain unresolved and are not combined with known units.

## 5. Move to a laboratory pilot

Use copies of a small representative batch, keep the originals read-only, and review the
Conversion Plan before converting. For an unfamiliar structured table, explicitly map
RT and Area first. Reuse a Mapping Profile only for an exact structure. If a template
drifts, review the diagnostic and create a new confirmed profile; do not accept automatic
remapping. Save a Recipe explicitly only after its effective configuration is reviewed.

Compare source rows with `Peaks`, confirm every unit, and inspect partial failures in
`Import_Log`. Do not publish source files, measured rows, filenames, local paths, Mapping
or Recipe JSON, detailed logs, or workbooks. Use the privacy-safe pilot feedback issue
template for status codes and workflow friction.
