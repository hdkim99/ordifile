# Project assets

These assets are generated from the current Ordifile source and the fully synthetic
files under `examples/basic/`:

- `ordifile-demo.gif` shows a real clean-install CLI conversion transcript.
- `ordifile-workbook.png` renders cells read back from the generated workbook.
- `ordifile-social-preview.png` is a deterministic project identity graphic.

Regenerate them on macOS from the repository root:

```bash
bash scripts/generate_demo_assets.sh
```

The generator uses Python, a temporary virtual environment, and the macOS system
AppKit/ImageIO frameworks. It does not add a production dependency. Generated text is
limited to repository-relative paths and synthetic data; external GC files are never
used in these assets.

## Application icon

`ordifile-icon.svg` is the canonical 1024×1024 vector master for the Ordifile
application icon. Its three chromatogram peaks continue into a compact workbook grid,
representing local scientific results becoming an ordered workbook. The artwork was
created for Ordifile without stock artwork, vendor marks, external images, fonts, or
network references.

Regenerate the committed PNG, Windows ICO, and macOS ICNS derivatives from the
repository root after installing the existing development dependencies:

```bash
python scripts/generate_app_icons.py
python scripts/generate_app_icons.py --check
```

The canonical artwork, generation script, and generated assets are Ordifile project
assets under Apache-2.0. They do not indicate affiliation with any instrument vendor
or spreadsheet product.
