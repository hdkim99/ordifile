# Demo assets

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
