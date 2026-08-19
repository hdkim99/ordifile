# Standalone packaging evidence

- Review date: 2026-08-18
- Versions evaluated: Python 3.13.15 and 3.14.3, python-build-standalone 20260203,
  PySide6-Essentials/shiboken6 6.11.2, Nuitka 4.1.3, PyInstaller 6.22.2,
  Briefcase 0.4.4
- Scope: official deployment, package metadata and license sources only

## Evidence

| Source | Observed fact | Project use |
|---|---|---|
| [Qt for Python deployment](https://doc.qt.io/qtforpython-6/deployment/index.html) | Qt documents `pyside6-deploy` as its deployment tool and identifies Nuitka as its compiler backend. | Select the Qt-maintained frontend. |
| [`pyside6-deploy` reference](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html) | The tool uses a `pysidedeploy.spec`, supports `standalone` mode, and accepts a Nuitka version. | Keep a reviewable template and pin the backend exactly. |
| [`pyside6-deploy` 6.11.2 control flow](https://github.com/pyside/pyside-setup/blob/v6.11.2/sources/pyside-tools/deploy.py) and [finalization](https://github.com/pyside/pyside-setup/blob/v6.11.2/sources/pyside-tools/deploy_lib/deploy_util.py) | The pinned frontend catches backend exceptions and still finalizes an existing partial deployment directory; its process status alone is therefore not a complete success signal. | Reject the caught-exception marker and require the exact native entry point before adding licenses or constructing evidence. |
| [Python 3.14.3 release](https://www.python.org/downloads/release/python-3143/) | Exact CPython version and license baseline for both prototype targets. | Keep the application runtime version aligned at 3.14.3. |
| [python-build-standalone releases](https://github.com/astral-sh/python-build-standalone/releases/tag/20260203), [running guide](https://github.com/astral-sh/python-build-standalone/blob/20260203/docs/running.rst), [distribution details](https://github.com/astral-sh/python-build-standalone/blob/20260203/docs/distributions.rst), and [license](https://github.com/astral-sh/python-build-standalone/blob/20260203/LICENSE) | The reviewed release publishes an arm64 macOS CPython 3.14.3 install-only archive; upstream describes the builds as standalone and highly redistributable, while documenting build-path quirks rather than a blanket relocatability guarantee. The build project is MPL-2.0. | Pin the exact asset URL and GitHub asset SHA-256, verify bounded archive paths, exact prefix, and final bundle self-containment, and use it only as the macOS arm64 build runtime. The build project is not bundled. |
| [Nuitka 4.1.3 package](https://pypi.org/project/Nuitka/4.1.3/), [README](https://github.com/Nuitka/Nuitka/blob/4.1.3/README.rst), and [static-libpython gate](https://github.com/Nuitka/Nuitka/blob/4.1.3/nuitka/options/Options.py) | Exact build-tool release supports Python through 3.14; on Windows its pinned documentation excludes MinGW64 for Python 3.13+ and requires Visual Studio 2022 or newer. Pinned source also rejects official Python 3.14+ static linking. | Pin `Nuitka==4.1.3`, require a discoverable Visual Studio 2022-or-newer native compiler on Windows, use dynamic libpython from the standalone macOS runtime, and do not bundle the compiler. |
| [`vswhere` Find VC](https://github.com/microsoft/vswhere/wiki/Find-VC), [Visual Studio versions](https://github.com/microsoft/vswhere/wiki/Versions), [Build Tools component IDs](https://learn.microsoft.com/en-us/visualstudio/install/workload-component-id-vs-build-tools), [MSVC version mapping](https://learn.microsoft.com/en-us/cpp/overview/compiler-versions), and [developer shells](https://learn.microsoft.com/en-us/visualstudio/ide/reference/command-prompt-powershell) | Microsoft's discovery guidance uses `vswhere -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64`; Visual Studio major 17 identifies 2022, MSVC 19.30 maps to its initial compiler, and `VsDevCmd.bat` is the supported developer-shell entry point. | Accept a registered Visual Studio 2022-or-newer toolchain or prove an already active x64 MSVC 19.30+ environment with a run-scoped compile-link-execute probe, without installing software, changing runner state, or printing paths. |
| [Nuitka 4.1.3 Windows compiler selection](https://github.com/Nuitka/Nuitka/blob/4.1.3/nuitka/build/SconsUtils.py) and [executable lookup](https://github.com/Nuitka/Nuitka/blob/4.1.3/nuitka/utils/Execution.py) | The pinned backend directly uses an active `cl` found on `PATH` and skips its Visual Studio setup discovery in that case. | Require the active compiler probe to pass whenever `cl` is found; use registered Visual Studio discovery only when active `cl` is absent, and do not mutate `PATH` or invoke a developer shell. |
| [Nuitka license](https://github.com/Nuitka/Nuitka/blob/4.1.3/LICENSE.txt) and [runtime exception](https://github.com/Nuitka/Nuitka/blob/4.1.3/LICENSE-RUNTIME.txt) | Compiler is AGPL-3.0; the additional permission applies to qualifying generated target code and does not weaken compiler copyleft. | Bundle the byte-identical runtime exception; describe Nuitka as an AGPL build tool. |
| [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html) | PySide6/shiboken6 offer LGPL-3.0/GPL/commercial alternatives and include Qt modules under their applicable terms. | Select LGPL-3.0 and inventory the exact native components. |
| [Qt open-source obligations](https://www.qt.io/development/open-source-lgpl-obligations) | Qt's guidance calls out notice, source, modification, replacement/relinking and installation-information considerations. | Make these hard pre-publication gates. |
| [Qt for Python 6.11.2 sources](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/) and [Qt 6.11.2 sources](https://download.qt.io/official_releases/qt/6.11/6.11.2/single/) | Official corresponding-source locations exist for the selected version. | Candidate source locations only; archive/hash before public release. |
| [PyInstaller 6.22.2](https://pypi.org/project/pyinstaller/6.22.2/) and [license](https://github.com/pyinstaller/pyinstaller/blob/v6.22.2/COPYING.txt) | PyInstaller supports one-folder bundles and a permissive exception for generated applications. | Onedir fallback only; not present in the primary build lock. |
| [Briefcase 0.4.4 metadata](https://pypi.org/pypi/briefcase/0.4.4/json) and [platform documentation](https://briefcase.readthedocs.io/en/stable/reference/platforms/) | BSD-3-Clause tool with Windows/macOS application and installer lifecycle support. | Rejected for the first slice because its templates and support packages add a second application lifecycle instead of wrapping the existing Qt entry point. |
| [Reusing workflow configurations](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations), [contexts reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts), [using self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow), and [GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) | A reusable workflow owned by the same user can use self-hosted runners available to the caller repository. Called jobs expose their defining workflow repository, path, ref, and SHA through the `job.workflow_*` context. Self-hosted routing still requires cumulative label matches. | Keep the Windows build logic in an exact-SHA Ordifile reusable workflow, route it through the existing same-owner caller repository's Windows x86-64 runner, retain `macos-15` for macOS, and never move the runner or cross-compile a claimed target. |
| [Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) and [custom workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow) | Direct distribution uses Developer ID signing, hardened runtime and a secure timestamp; `notarytool` submits and `stapler` attaches the accepted ticket. | Keep signing/notarization out of the prototype and make them production gates. |
| [Microsoft signing options](https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options), [SHA-256 timestamping](https://learn.microsoft.com/windows/win32/seccrypto/time-stamping-authenticode-signatures), and [SmartScreen reputation](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation) | Trusted publisher identity and SHA-256 signing/timestamping are distinct from file/publisher reputation; new signed files can still warn. | Mark candidates unsigned, never promise warning-free launch, and require reviewed production signing evidence. |

## Local measurements

The reviewed environment reported Python 3.14.3, `PySide6-Essentials==6.11.2`,
`shiboken6==6.11.2`, and accepted an exact `Nuitka==4.1.3` installation. The
`pyside6-deploy` command exposes standalone mode and an explicit Nuitka-version
override. The generated default template named another Nuitka patch, so Ordifile does
not trust that mutable default and supplies the reviewed exact pin.

An exact-head `macos-15` attempt using `actions/setup-python` reached the final-byte
audit but was rejected because the hosted tool-cache prefix was embedded in the bundle.
A second attempt using the PSF Python 3.14.3 Framework left real dynamic dependencies
on that build-host framework. A third attempt used PSF Python 3.13.15 and a static main
executable, but extension and shared components still referenced the framework. Ordifile
does not allowlist those bytes or rewrite Mach-O dependencies after the fact.

The selected macOS runtime is the exact
`cpython-3.14.3+20260203-aarch64-apple-darwin-install_only.tar.gz` asset. Its reviewed
GitHub asset digest is
`5bb1ad03aa2d8afe15140f56fedaab2ba95033785ad0367775899d42ac8aeb3c`.
The archive has one `python/` top-level tree, includes dynamic libpython, and its CPython
license bytes match the tracked `PYTHON-PSF-LICENSE.txt`. The reviewed asset contains
only regular files, directories, and eight exact relative symlinks; the workflow rejects
path, member-type, or link-inventory drift before extraction and uses a fixed public
prefix. Only that exact literal
prefix/executable pair is exempt from the private-path scan; resolved aliases and every
source, stage, temporary, home, workspace, tool-cache, or other runtime path remain
forbidden. The native job then rejects Mach-O dependencies or load commands that
reference the build runtime, moves the whole runtime away, and only then runs the
packaged scientific and window smokes. This tests the inspected prototype paths; it is
not a signed clean-machine result. A public distribution must independently complete
the runtime's full third-party license inventory and all Qt redistribution gates.

The exact installed Nuitka 4.1.3 runtime-exception bytes have SHA-256
`20ff0ae581adf436a7b06e50e67a6c8913aec1ea4e60dba138d0a0bee7ee520c`; the copy in
`packaging/standalone/licenses/` must remain byte-identical. The included LGPL-3.0 text
has SHA-256
`a853c2ffec17057872340eee242ae4d96cbf2b520ae27d903e1b2fef1a5f9d1c`.

A local unsigned macOS arm64 `.app` bundle was produced from the reviewed configuration
and passed checkout-free packaged-window smoke, registry inventory for all 11 built-in
adapters, all 12 public-safe synthetic inputs, generic UTF-8 and UTF-8-BOM, YoungIn
CP949 Result, workbook reopen, overwrite refusal, and six-sheet scientific equivalence.
This is prototype evidence only. A Windows exact-head attempt reached native deployment
but produced a partial `.dist` containing only injected licenses and no executable;
downstream artifact-only validation rejected it. Review of the pinned PySide frontend
and Nuitka output lifecycle showed why a backend exception can leave that state while
the frontend exits successfully. Ordifile therefore treats process status as secondary,
rejects the caught-exception marker, and validates the platform entry point before any
license injection or manifest generation. The underlying Windows backend failure remains
unresolved until a controlled rerun classifies it; it is not attributed to Python,
Nuitka, or the runner without evidence. Signed Windows trust, macOS notarization, and
signed/hardened replacement of LGPL components are not inferred from these results.

## Exclusions

- No proprietary scientific fixture or vendor binary was inspected or bundled.
- No Qt, PySide, shiboken, Nuitka or PyInstaller implementation code was copied into
  Ordifile.
- No onefile, MSI, DMG, auto-update, signing, notarization or public release path was
  implemented.
- No signing credential, publisher identity, certificate, private key or notarization
  secret was requested or stored.
- License guidance is an engineering redistribution gate, not legal advice.
