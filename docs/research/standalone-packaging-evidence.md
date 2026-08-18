# Standalone packaging evidence

- Review date: 2026-08-18
- Versions evaluated: Python 3.14.3, PySide6-Essentials/shiboken6 6.11.2,
  Nuitka 4.1.3, PyInstaller 6.22.2, Briefcase 0.4.4
- Scope: official deployment, package metadata and license sources only

## Evidence

| Source | Observed fact | Project use |
|---|---|---|
| [Qt for Python deployment](https://doc.qt.io/qtforpython-6/deployment/index.html) | Qt documents `pyside6-deploy` as its deployment tool and identifies Nuitka as its compiler backend. | Select the Qt-maintained frontend. |
| [`pyside6-deploy` reference](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html) | The tool uses a `pysidedeploy.spec`, supports `standalone` mode, and accepts a Nuitka version. | Keep a reviewable template and pin the backend exactly. |
| [Python 3.14.3 release](https://www.python.org/downloads/release/python-3143/) and [macOS installation guidance](https://docs.python.org/3.14/using/mac.html) | The PSF publishes a universal2 macOS installer and its SHA-256; Python documents command-line installation of the official package with the macOS installer utility. | Pin and hash-check the official 3.14.3 package for the macOS native build. |
| [Nuitka 4.1.3 package](https://pypi.org/project/Nuitka/4.1.3/) | Exact build-tool release available for supported Python platforms. | Pin `Nuitka==4.1.3`; do not bundle the compiler. |
| [Nuitka license](https://github.com/Nuitka/Nuitka/blob/4.1.3/LICENSE.txt) and [runtime exception](https://github.com/Nuitka/Nuitka/blob/4.1.3/LICENSE-RUNTIME.txt) | Compiler is AGPL-3.0; the additional permission applies to qualifying generated target code and does not weaken compiler copyleft. | Bundle the byte-identical runtime exception; describe Nuitka as an AGPL build tool. |
| [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html) | PySide6/shiboken6 offer LGPL-3.0/GPL/commercial alternatives and include Qt modules under their applicable terms. | Select LGPL-3.0 and inventory the exact native components. |
| [Qt open-source obligations](https://www.qt.io/development/open-source-lgpl-obligations) | Qt's guidance calls out notice, source, modification, replacement/relinking and installation-information considerations. | Make these hard pre-publication gates. |
| [Qt for Python 6.11.2 sources](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/) and [Qt 6.11.2 sources](https://download.qt.io/official_releases/qt/6.11/6.11.2/single/) | Official corresponding-source locations exist for the selected version. | Candidate source locations only; archive/hash before public release. |
| [PyInstaller 6.22.2](https://pypi.org/project/pyinstaller/6.22.2/) and [license](https://github.com/pyinstaller/pyinstaller/blob/v6.22.2/COPYING.txt) | PyInstaller supports one-folder bundles and a permissive exception for generated applications. | Onedir fallback only; not present in the primary build lock. |
| [Briefcase 0.4.4 metadata](https://pypi.org/pypi/briefcase/0.4.4/json) and [platform documentation](https://briefcase.readthedocs.io/en/stable/reference/platforms/) | BSD-3-Clause tool with Windows/macOS application and installer lifecycle support. | Rejected for the first slice because its templates and support packages add a second application lifecycle instead of wrapping the existing Qt entry point. |
| [Using self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow) and [GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) | Self-hosted jobs require cumulative label matches; native hosted macOS images are available. Labels route jobs but do not replace repository assignment as a trust boundary. | Route Windows only to a repository-authorized self-hosted Windows x86-64 runner, keep `macos-15` for macOS, and never cross-compile a claimed target. |
| [Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) and [custom workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow) | Direct distribution uses Developer ID signing, hardened runtime and a secure timestamp; `notarytool` submits and `stapler` attaches the accepted ticket. | Keep signing/notarization out of the prototype and make them production gates. |
| [Microsoft signing options](https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options), [SHA-256 timestamping](https://learn.microsoft.com/windows/win32/seccrypto/time-stamping-authenticode-signatures), and [SmartScreen reputation](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation) | Trusted publisher identity and SHA-256 signing/timestamping are distinct from file/publisher reputation; new signed files can still warn. | Mark candidates unsigned, never promise warning-free launch, and require reviewed production signing evidence. |

## Local measurements

The reviewed environment reported Python 3.14.3, `PySide6-Essentials==6.11.2`,
`shiboken6==6.11.2`, and accepted an exact `Nuitka==4.1.3` installation. The
`pyside6-deploy` command exposes standalone mode and an explicit Nuitka-version
override. The generated default template named another Nuitka patch, so Ordifile does
not trust that mutable default and supplies the reviewed exact pin.

An exact-head `macos-15` prototype attempt using `actions/setup-python` reached the
final-byte audit but was rejected because the hosted tool-cache runtime prefix was
embedded in the bundle. Ordifile does not allowlist or redact such bytes after the
fact. The workflow instead downloads the official Python 3.14.3 macOS package from
`python.org`, verifies the release-page SHA-256
`50b709f72cb5ed87d5882901923face981dd657569717761832c36db3bf08238`, and installs
that exact framework on the disposable hosted runner before packaging.
Python 3.14.3 is the reviewed prototype baseline, not a claim that it remains the
latest maintenance release; a public standalone distribution must re-review the
runtime patch level and rebuild evidence.

The exact installed Nuitka 4.1.3 runtime-exception bytes have SHA-256
`20ff0ae581adf436a7b06e50e67a6c8913aec1ea4e60dba138d0a0bee7ee520c`; the copy in
`packaging/standalone/licenses/` must remain byte-identical. The included LGPL-3.0 text
has SHA-256
`a853c2ffec17057872340eee242ae4d96cbf2b520ae27d903e1b2fef1a5f9d1c`.

A local unsigned macOS arm64 `.app` bundle was produced from the reviewed configuration
and passed checkout-free packaged-window smoke, registry inventory for all 11 built-in
adapters, all 12 public-safe synthetic inputs, generic UTF-8 and UTF-8-BOM, YoungIn
CP949 Result, workbook reopen, overwrite refusal, and six-sheet scientific equivalence.
This is prototype evidence only. Windows native behavior, signed Windows trust, macOS
notarization, and signed/hardened replacement of LGPL components are not inferred from
that result.

## Exclusions

- No proprietary scientific fixture or vendor binary was inspected or bundled.
- No Qt, PySide, shiboken, Nuitka or PyInstaller implementation code was copied into
  Ordifile.
- No onefile, MSI, DMG, auto-update, signing, notarization or public release path was
  implemented.
- No signing credential, publisher identity, certificate, private key or notarization
  secret was requested or stored.
- License guidance is an engineering redistribution gate, not legal advice.
