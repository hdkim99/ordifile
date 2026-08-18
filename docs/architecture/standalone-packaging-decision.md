# Standalone packaging decision

- Decision date: 2026-08-18
- Scope: unsigned, maintainer-triggered Windows and macOS prototypes for Issue #6
- Public signed binary release: **blocked**

## Decision

Use Qt's official `pyside6-deploy` frontend with `mode = standalone` and an exact
`Nuitka==4.1.3` build-tool pin. Produce a Windows onedir bundle ZIP and a macOS `.app`
bundle ZIP on native GitHub-hosted runners. Keep the ordinary Python package and
`ordifile[gui]` installation unchanged.

The standalone entry point launches the existing `ordifile.desktop` application. It
does not copy conversion, discovery, adapter, workbook, or privacy logic. Normal
operation is offline and contains no telemetry, updater, embedded browser, or vendor
software. The deployment spec excludes Qt TLS plugins because the application has no
network feature; platform, style, icon and image plugins remain available for the
desktop workflow.

## Compared paths

| Path | Fit | Decision |
|---|---|---|
| `pyside6-deploy` + Nuitka standalone | Qt-maintained deployment frontend, native Qt plugin handling, onedir output and inspectable shared libraries | Primary |
| PyInstaller 6.22.2 onedir | Mature cross-platform fallback with Qt hooks; a second spec/toolchain would add drift | Documented fallback only |
| Briefcase 0.4.4 | Cross-platform BSD-3-Clause application/installer lifecycle, but introduces templates, support-package and installer policy beyond this existing Qt GUI wrapper | Rejected for the first prototype |
| Nuitka/PyInstaller onefile | Extraction and LGPL replacement/relinking behavior are less transparent | Excluded |
| MSI, DMG, signing and notarization | Requires publisher identity, platform credentials, installation policy and release operations | Deferred |

## Build and evidence boundary

`.github/workflows/standalone.yml` has only a manual `workflow_dispatch` trigger and
read-only repository permission. Native Windows and macOS build jobs create unsigned
candidates, unpack the exact ZIP in runner-temporary space, clear Python import
overrides, and run the packaged executable there. The native candidate is never
uploaded from the public repository: only its path-free manifest, checksum inventory,
and smoke report are retained as Actions evidence.

GitHub only dispatches a new manual workflow after its definition exists on the
default branch. While this infrastructure is under review, local native evidence can
validate a platform, but the Draft PR must not claim or check a hosted run. The
prototype merge gate therefore remains blocked until both native hosted runs can be
obtained through an approved bootstrap or follow-up path.

The packaged executable must prove all of the following before a prototype artifact is
accepted:

- its Ordifile version and complete adapter registry equal the source-built baseline;
- public-safe inputs exercise detection and parsing for every built-in Generic,
  Agilent, Shimadzu, and YoungIn adapter, including UTF-8, UTF-8-BOM and CP949;
- `Samples`, `Peak_Matrix`, `Peaks`, `Peak_Order_Matrix`, `Metadata`, and `Import_Log`
  reopen and have the same ordered cell digest as the source-built workbook;
- artifact files, hashes, signature state and license filenames are inventoried;
- the packaged existing Qt window becomes visible under an offscreen platform smoke,
  and non-ASCII/space output plus existing-output preservation pass;
- private build paths, credential markers, proprietary/native fixtures, vendor
  binaries and scientific workbooks are absent from the bundled application.

The outer artifact is explicitly `publishable: false`. Prototype ZIPs remain local to
the ephemeral builder, are not Actions artifacts, and are never attached to a GitHub
Release by this workflow. Same-job scratch execution proves checkout-independent use,
but it is not a substitute for a separate clean-machine test.

The source, exact direct toolchain versions, spec, inventory ordering and ZIP metadata
are deterministic. Functional rebuilds are expected to be repeatable. Byte-identical
Nuitka/native linker output has not been demonstrated and is not claimed.

## Licensing and publication gate

Ordifile selects LGPL-3.0 for the dynamically bundled Qt/PySide6/shiboken6 components.
Ordifile does not copy or modify their source code; native deployment tooling may
rewrite loader metadata in copied bundle binaries, so final modification and source
obligations remain a publication gate. Each prototype includes the full LGPL-3.0 text,
an exact component notice, the Python license, Ordifile license/notice, runtime
dependency licenses, and the exact Nuitka Runtime Library Exception from Nuitka 4.1.3.

Nuitka 4.1.3 is an AGPL-3.0 build tool and is not bundled. Its Runtime Library
Exception permits qualifying generated target code under the program's own terms; it
does not relicense the compiler or remove the compiler's AGPL obligations.

Before a public signed download, all of these gates remain mandatory:

1. archive and hash exact corresponding source for every included Qt, PySide6 and
   shiboken6 component, plus Qt's bundled third-party notices;
2. clean-machine test documented user replacement/relinking and any LGPLv3
   installation information for Windows and signed/hardened macOS;
3. establish the publisher identity and complete Windows signing plus macOS Developer
   ID signing/notarization verification;
4. independently review the final native inventories and licenses.

Until those gates pass, public signed release status is `BLOCKED`.

Windows production signing must use a reviewed trusted publisher identity and a
SHA-256 Authenticode/timestamp path; a valid signature does not guarantee immediate
SmartScreen reputation. macOS production distribution requires a Developer ID
signature, hardened runtime, secure timestamp, notarization review and ticket
stapling. No credentials for either path are configured by this prototype.

## Consequences

- The initial artifacts are larger onedir ZIPs but remain auditable and replaceable.
- Builds are platform-native and cannot cross-compile a claimed target.
- Linux standalone packaging, auto-update, onefile, installers and release publication
  are outside this prototype.
- PyInstaller remains a documented recovery option, not an automatically selected or
  silently substituted builder.
