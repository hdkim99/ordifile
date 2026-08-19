# Standalone candidate license inventory

This directory is copied inside every unsigned Ordifile standalone prototype.

- `LGPL-3.0.txt` is the GNU Lesser General Public License version 3 selected for
  dynamically bundled Qt, PySide6, and shiboken6 components.
- `QT-PYSIDE-SHIBOKEN-NOTICE.md` identifies the exact reviewed components and
  corresponding-source and replacement/relinking obligations.
- `NUITKA-RUNTIME-EXCEPTION.txt` is the exact Nuitka 4.1.3 runtime exception covering
  generated targets. Nuitka itself remains an AGPL-3.0 build tool and is not bundled.
- `PYTHON-PSF-LICENSE.txt` records the Python 3.13 runtime terms used for the pinned
  macOS prototype toolchain; Windows retains its separately pinned Python 3.14 build.
- `LICENSE` and `NOTICE` are copied from Ordifile, and per-distribution license files
  for embedded permissive Python packages are copied under `python-packages/`.
- `THIRD_PARTY_NOTICES.md` is copied from the Ordifile source tree at build time.

These files do not authorize a public binary release. Publisher identity, Windows
signing, macOS signing/notarization, complete Qt third-party inventory, corresponding
source delivery, and tested replacement/installation information remain hard gates.
