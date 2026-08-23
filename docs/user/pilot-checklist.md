# Researcher pilot checklist

Use this checklist to learn the complete Ordifile workflow with public-safe synthetic
data, then repeat it with a small, representative copy of your own exports. The pilot
files are neutral demonstrations, not vendor-generated data and not evidence of exact
vendor support.

## 1. Install and identify the environment

```console
python -m pip install ordifile
ordifile --version
ordifile formats
```

For the Python-package desktop interface:

```console
python -m pip install "ordifile[gui]"
ordifile-gui
```

No public standalone `.exe` or `.app` is distributed. Record only the OS family,
architecture, Python version, Ordifile version, and relevant dependency versions when
reporting a compatibility problem.

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

First use:

1. Select **Add Folder** and choose `examples/pilot/inputs`.
2. Choose a new `.xlsx` output path.
3. Select **Refresh Preflight** and review the routing table.
4. Convert, then open the output and review `Samples` and `Import_Log` first.

To reuse this laboratory setup without managing JSON in normal GUI use:

1. Open **Manage…**, choose **Import Recipe…**, and import
   `examples/pilot/laboratory.recipe.json` once.
2. Select its local name in **Recipe (optional)**.
3. Add the experiment folder and choose a new output.
4. Select **Refresh Preflight** and confirm two Mapping Profile routes. Selecting a Recipe,
   changing its effective settings, changing inputs, or changing output invalidates the
   previous preview.
5. Convert. Recipe selection never starts conversion or bypasses Preflight.

After configuring a new Mapping or Mapping Set, **Save Current…** asks only for a local
Recipe name. Use **Manage… → Export Recipe…** only when moving that strict JSON to another
computer or a CLI/API workflow.

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
