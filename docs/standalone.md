# Unsigned standalone prototype

Ordifile has a maintainer-only prototype path for native Windows and macOS desktop
bundles. It is not a public binary release and does not change the supported
`pip install ordifile` or `ordifile[gui]` paths.

## Scope

- Windows x86-64: onedir ZIP
- macOS arm64: `.app` ZIP
- Python 3.14.3 on both platforms; macOS uses an exact standalone install-only runtime;
  PySide6-Essentials/shiboken6 6.11.2; Nuitka 4.1.3; Windows uses exact build-only
  Zig 0.16.0 x86-64 bytes
- unsigned or ad-hoc-signed evidence only
- public-safe synthetic inputs for every built-in Generic, Agilent, Shimadzu, YoungIn
  and LECO adapter, including UTF-8, UTF-8-BOM, YoungIn CP949 and dual-retention output
- no Qt TLS plugins or application network feature

Onefile, MSI, DMG, Linux bundles, auto-update, signing, notarization and GitHub Release
publication are excluded.

## Run the manual workflow

The default branch first registers **Standalone prototype** with a no-build anchor.
After registration, a maintainer may select either reviewed `main` or the fixed
same-repository prototype branch and must supply its exact reviewed 40-character commit
as `expected_commit`. The macOS job requires the selected ref SHA, expected commit,
and workflow-definition SHA to be identical, and checkout is pinned to that SHA. The
input never selects a checkout target. A non-skippable Ubuntu preflight fails the run
before the native job is eligible when any identity check disagrees. It performs no
checkout, build, or artifact upload. GitHub does not expose a new branch-only manual
workflow before default-branch registration; the prior pre-merge 404 was a workflow
registration limitation, not runner-availability evidence. No token, signing secret,
OIDC permission or vendor software is used.

Windows is not queued by this Ordifile manual workflow. Its reusable workflow is
invoked from a separate maintainer-owned same-user repository with an exact immutable
Ordifile SHA pin; that caller provides the existing Windows runner context.

Windows validation is defined in
`.github/workflows/standalone-windows-reusable.yml` and has no GitHub-hosted
fallback. A thin `workflow_dispatch` caller in a maintainer-owned repository pins
that public reusable workflow to an exact Ordifile commit. GitHub then routes the
called job through the caller repository's existing runner with the cumulative
`self-hosted`, `Windows`, and `X64` capability labels. The caller repository
identity is an infrastructure detail and is not recorded in public Ordifile evidence.
The existing runner registration, repository assignment, labels, service, and
installation remain unchanged. Because its workspace persists, the called job checks
out the hard-coded Ordifile repository and exact pinned commit into a workflow-owned
source directory, uses a run-scoped virtual environment and unique runner-temporary
scratch root, masks runner-local identifiers, and performs bounded cleanup before and
after execution. The macOS job remains in the manual Ordifile workflow and is fixed to
GitHub-hosted `macos-15`; changing that routing requires a separate review. Windows
uses the exact `actions/setup-python` version selected by the workflow. macOS downloads
the exact arm64 Python 3.14.3 install-only archive from the reviewed
`python-build-standalone` release and verifies its release-asset SHA-256 before
extracting it into a fixed public build prefix. Earlier exact-head attempts rejected
the hosted tool-cache prefix, the official PSF 3.14 framework's dynamic linkage, and an
official PSF 3.13 static-main build whose extension modules still loaded that framework.
The selected archive is described upstream as a standalone, highly redistributable
build; Ordifile does not treat that as a blanket relocatability guarantee. Its fixed
prefix is public rather than runner-identifying, so only the exact
literal prefix and executable are excluded from the private-path scan. Self-containment
is checked separately: no Mach-O dependency or load command may reference that build
runtime, and the entire runtime is moved out of place while the packaged smoke runs.
Both jobs check out the exact reviewed Ordifile SHA, unpack the exact candidate into
runner-temporary space, clear Python import overrides, and run only the packaged executable for
scientific and window smokes. This is checkout-independent artifact execution, but not
a separate clean-machine result.

Manual caller dispatch, immutable reusable-workflow pinning, exact-commit checkout,
read-only repository permission, an isolated Python environment, and cleanup reduce
exposure; they do not make a persistent self-hosted
machine an isolation boundary or undo a compromised job. Before dispatch, the Windows
runner must be a dedicated, minimally privileged build host with no private scientific
data, signing credentials, unrelated secrets, or sensitive network access. Its runner
and service-account display identities must be non-identifying because runner setup can
precede in-job log masks. The runner and operating-system patch state must be reviewed,
and the maintainer must have a post-job compromise response such as reprovisioning or
replacement. Do not register or use a personal workstation for this public-repository
workflow.

The public Actions evidence artifact contains no native candidate. It contains only:

```text
standalone-candidate/
  SHA256SUMS.txt
  standalone-manifest.json
standalone-smoke-report.json
```

The native ZIP and synthetic smoke-kit are first generated in allowlisted directories
inside the workflow-owned source checkout, then copied or expanded into the unique
runner-temporary smoke root. The source outputs and scratch root are both removed after
the job, including on failure.
This prevents the prototype workflow from bypassing the unresolved Qt redistribution
gates through a downloadable public Actions artifact.

The manifest is deterministic and path-safe. It records the source commit, Ordifile,
backend and toolchain versions, target, signature state, dynamic adapter registry, every inner
file hash, bundle total size, outer ZIP filename/size/SHA-256 and the license inventory.
`publishable` is always `false`.

This means deterministic configuration and functionally repeatable artifacts, not a
claim that native linker output or the outer ZIP is byte-identical across rebuilds.

## Local maintainer build

Use a fresh environment on the native target. Do not run this command from a private
fixture directory and keep output outside the repository:

```bash
python -m pip install --requirement packaging/standalone/requirements-build.lock
python -m pip install --no-deps .
python scripts/standalone/smoke.py make-kit \
  --output <temporary-smoke-kit> \
  --generator-root tests/fixtures/synthetic
python scripts/standalone/build.py \
  --source . --output <temporary-candidate> \
  --commit <exact-40-character-commit> --target <native-target>
```

The reviewed automated targets are `windows-x86_64` and `macos-arm64`. The builder
retains a native `macos-x86_64` target for future exact-runtime research, but no
automated x86-64 macOS support is claimed. It rejects a target that does not match the
host and withholds captured deployment output on failure so local paths are not copied
into public logs. A deployment exit code is not sufficient evidence of success: before
license injection, manifest generation, or archiving, the builder requires one real,
non-link, non-reparse bundle root and the exact native entry point (`Ordifile.exe` on
Windows or `Contents/MacOS/Ordifile` on macOS) to be a regular, non-empty, non-link,
non-reparse file. It also rejects the pinned deployment frontend's caught-exception
marker on macOS. Windows does not invoke `pyside6-deploy`. The reusable job downloads
the official Zig 0.16.0 x86-64 ZIP to an ownership-marked `RUNNER_TEMP` child, checks
its exact public size and SHA-256, rejects unsafe ZIP members, and extracts only into
that root. It requires `zig version`, a native x86-64 compile/link/execute probe, a plain
Python/Nuitka standalone probe, and a minimal PySide6/Nuitka standalone-window probe
before the full build. The full Windows command is direct
`python -m nuitka --standalone --enable-plugin=pyside6 --zig
--experimental=force-dependencies-pefile
--nofollow-import-to=PySide6.QtNetwork
--noinclude-qt-plugins=tls
--noinclude-qt-plugins=networkinformation`; only
that subprocess receives PATH prefixed with the reviewed Zig directory, with inherited
`CC` and `CXX` removed. `CFLAGS=-march=x86_64` applies the baseline mitigation proposed
in open Nuitka issue #3987; it does not establish portability on generic or older
x86-64 machines. The private SCons report must prove Nuitka Zig mode, disabled separate
Nuitka MSVC/MinGW modes, the exact compiler path, and the baseline flag. The invocation
forces Nuitka 4.1.3's built-in PE dependency scanner; closed standard input therefore
cannot trigger the default external legacy dependency-tool download. The Windows-only
module exclusion prevents PySide6 6.11.2's caught, OpenSSL-directory-dependent
`QtNetwork` import from expanding the reviewed offline QtCore/QtGui/QtWidgets bundle;
TLS and network-information plugin families are separately excluded. The PySide probe
and full bundle audit both reject any resulting network runtime. The report,
Zig archive, compiler, caches and native candidate are never uploaded. Exact
ownership-token cleanup removes the Zig root after ordinary failure. Visual Studio,
Build Tools, MSVC, Windows SDK and a host MinGW toolchain are not installed; the
workflow never selects Nuitka's `--mingw64` fallback, and it does not change the runner
service, registration, labels or machine PATH. Zig's Windows GNU ABI nevertheless uses
MinGW-w64/libc build inputs, so exact linked-runtime provenance, notices and source
obligations remain a hard public-distribution gate. macOS retains the reviewed
`pyside6-deploy` path.

## What the smoke proves

The artifact-only smoke checks the outer checksum and non-publishable signature gate,
then runs the packaged executable with `--standalone-smoke`. It verifies:

- version and registry-derived adapter inventory;
- detection and parsing for all built-in Generic, Agilent, Shimadzu, YoungIn and LECO
  adapters, including CP949 codec, exact synthetic YoungIn Result detection and the
  exact synthetic LECO dual-retention profile;
- independent plain UTF-8 and UTF-8-BOM generic input handling;
- a separate synthetic explicit RT/Area mapping JSON and mapped generic conversion,
  without changing the adapter inventory or automatic-detection input count;
- conversion using the same public API as CLI/GUI;
- workbook reopen plus ordered equivalence for `Samples`, `Peak_Matrix`, `Peaks`,
  `Peak_Order_Matrix`, conditional `Peak_Order_Matrix_2D`, `Metadata` and `Import_Log`;
- non-ASCII/space output paths and existing-output refusal without byte changes;
- an offscreen launch of the packaged existing `QApplication`/`MainWindow` path.

Actual instrument files, private exports and vendor executables are never copied into
the workflow or artifact.

## Prototype installation and removal

There is no end-user installer. A maintainer evaluating the Windows candidate extracts
the onedir ZIP into a dedicated temporary folder; macOS evaluation extracts the `.app`
ZIP into a dedicated temporary folder. Removing that complete folder or app removes the
prototype. Ordifile creates no persistent GUI settings, device identifier or telemetry
state. Output workbooks selected by the tester are user data and are not removed with
the prototype.

Updates are manual whole-bundle replacements. Do not mix files from two candidates.
Unsigned Windows reputation warnings and unsigned/ad-hoc, non-notarized macOS
Gatekeeper behavior are expected limitations. These instructions do not ask testers to
disable or bypass operating-system security controls; a candidate that the platform
refuses to launch remains unverified on that machine.

## Publication remains blocked

Do not redistribute these prototype ZIPs as Ordifile releases. Public signed binaries
remain blocked until publisher identity, Windows signing, macOS signing/notarization,
complete Qt/PySide/shiboken corresponding-source and third-party notice delivery, and
clean-machine LGPL replacement/relinking/installation-information tests all pass.
See the [decision record](architecture/standalone-packaging-decision.md) and
[evidence review](research/standalone-packaging-evidence.md).
