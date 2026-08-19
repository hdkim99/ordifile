# Standalone packaging decision

- Decision date: 2026-08-18
- Scope: unsigned, maintainer-triggered Windows and macOS prototypes for Issue #6
- Public signed binary release: **blocked**

## Decision

Use direct `Nuitka==4.1.3` with its `--zig` backend and an exact job-local official
Zig 0.16.0 archive for Windows. Retain Qt's `pyside6-deploy` frontend with
`mode = standalone` and the same exact Nuitka pin for macOS. Target a Windows onedir bundle ZIP through an
exact-SHA reusable workflow using a maintainer-owned caller repository's existing
self-hosted Windows x86-64 runner, and target a macOS `.app` bundle ZIP
through GitHub-hosted `macos-15`. Keep the ordinary Python package and `ordifile[gui]`
installation unchanged. There is no GitHub-hosted Windows fallback, and Windows
runner registration, service, labels, and original repository assignment are not
changed.

The standalone entry point launches the existing `ordifile.desktop` application. It
does not copy conversion, discovery, adapter, workbook, or privacy logic. Normal
operation is offline and contains no telemetry, updater, embedded browser, or vendor
software. The deployment spec excludes Qt TLS plugins because the application has no
network feature; platform, style, icon and image plugins remain available for the
desktop workflow.

## Compared paths

| Path | Fit | Decision |
|---|---|---|
| Direct Nuitka + job-local Zig, Windows | Avoids permanent Visual Studio/MSVC/SDK host provisioning; exact x86-64 compiler asset and native probes | Primary on Windows |
| `pyside6-deploy` + Nuitka standalone, macOS | Existing exact-head Qt-maintained frontend path and `.app` behavior | Primary on macOS |
| PyInstaller 6.22.2 onedir | Mature cross-platform fallback with Qt hooks; a second spec/toolchain would add drift | Documented fallback only |
| Briefcase 0.4.4 | Cross-platform BSD-3-Clause application/installer lifecycle, but introduces templates, support-package and installer policy beyond this existing Qt GUI wrapper | Rejected for the first prototype |
| Nuitka/PyInstaller onefile | Extraction and LGPL replacement/relinking behavior are less transparent | Excluded |
| MSI, DMG, signing and notarization | Requires publisher identity, platform credentials, installation policy and release operations | Deferred |

## Build and evidence boundary

`.github/workflows/standalone.yml` has only a manual `workflow_dispatch` trigger and
read-only repository permission. A no-build default-branch anchor first registers that
workflow identity. The full workflow accepts a required exact commit only as an
identity assertion, never as a checkout selector. The macOS job is restricted to the
expected repository, an allowlisted same-repository branch, and equality among the
selected ref SHA, reviewed commit, workflow-definition SHA, and checked-out commit.
An always-scheduled GitHub-hosted Ubuntu preflight rejects invalid dispatches so that
the native job cannot make a rejected request appear successful; it performs
no checkout, packaging, self-hosted execution, or artifact upload.
Windows validation is separately defined as the public
`.github/workflows/standalone-windows-reusable.yml` reusable workflow. A thin
maintainer-owned same-user caller pins it to an exact Ordifile commit, requires no
secrets, and supplies the caller repository's existing runner context. The called job
selects the cumulative `self-hosted`, `Windows`, and `X64` labels and checks the
called workflow repository, file, ref, and SHA before it checks out the hard-coded
Ordifile repository at that exact SHA. No runner registration, label, service, or
repository assignment is changed, and the caller repository identity remains an
infrastructure detail. The persistent job uses an isolated run-scoped environment, a
workflow-owned nested source checkout, a unique runner-temporary scratch directory,
runner-identifier log masks, and bounded cleanup under `if: always()`. macOS remains
fixed to `macos-15`. Both native jobs create unsigned
candidates, unpack the exact ZIP in runner-temporary space, clear Python import
overrides, and run the packaged executable there. The native candidate is never
uploaded from the public repository: only its path-free manifest, checksum inventory,
and smoke report are retained as Actions evidence.

The macOS build uses the exact arm64 Python 3.14.3 install-only archive from the reviewed
`python-build-standalone` release and verifies its release-asset SHA-256 before bounded
extraction into a fixed public prefix. This follows three fail-closed exact-head results:
the hosted tool-cache prefix was embedded in final bytes, the PSF 3.14 framework remained
dynamically required, and a PSF 3.13 static-main build still left extension and shared
components dependent on that framework. Upstream describes the selected install-only
runtime as a standalone, highly redistributable build; Ordifile does not infer blanket
relocatability and instead verifies its exact prefix and final bundle behavior. It uses
dynamic libpython and keeps both reviewed native targets on Python 3.14.3.
Its fixed prefix and executable are not private runner identities, but only those exact
literal values receive the narrow path-audit exception. Self-containment is separately
enforced by rejecting Mach-O dependencies or load commands that reference the build
runtime and moving the entire runtime out of place during packaged execution. Windows
continues to use `actions/setup-python` inside its run-scoped isolated job environment.
The Windows job pins the official Zig 0.16.0 x86-64 archive by URL, size and SHA-256,
performs bounded path/type/size extraction into an ownership-marked runner-temporary
root, and verifies the exact version. It must pass a native PE x86-64 compile/link/run
probe, a plain Python/Nuitka standalone probe, and a minimal extracted PySide6/Nuitka
window probe before building Ordifile.
The direct Nuitka subprocess alone receives the reviewed Zig directory at the front of
PATH; inherited `CC` and `CXX` are removed, stdin is closed to reject tool downloads,
and `--zig` is mandatory. The exact built-in PE dependency scanner is forced so the
default external legacy scanner cannot be downloaded. Its private SCons report must
prove Nuitka Zig mode, disabled
separate Nuitka MSVC and MinGW modes, the exact compiler path, and the
`-march=x86_64` mitigation proposed in open issue #3987. Generic and older x86-64
portability remains unresolved until physical validation.
The builder does not trust the deployment process exit code alone: before adding licenses or producing a manifest, it
requires one real, non-link, non-reparse bundle root and the exact platform entry point
to be a regular, non-empty, non-link, non-reparse file. It also rejects the pinned
deployment frontend's caught-exception marker on macOS. This closes a reviewed partial
bundle state. The Zig toolchain, caches and compiler report remain build-only and are
removed by exact marker/token cleanup. Visual Studio, Build Tools, MSVC, Windows SDK and
a host MinGW toolchain are not installed, and Nuitka's separate `--mingw64` fallback is
not selected. Zig's Windows GNU ABI uses MinGW-w64/libc build inputs, whose exact linked
runtime provenance and license obligations remain a public-distribution gate. macOS
continues to use the existing deployment frontend.

These controls reduce exposure but do not turn a persistent public-repository runner
into a clean or disposable security boundary. Dispatch additionally requires a
dedicated minimally privileged host, current runner/OS patches, no private data,
credentials, signing material, or sensitive network reachability, and a documented
post-job compromise/reprovisioning response. Runner and service-account display names
must be non-identifying because job setup output can precede in-job masking. A personal
workstation is not an approved runner for this workflow.

GitHub only dispatches a new manual workflow after its definition exists on the
default branch. The registration-only anchor performs no checkout, build, artifact
upload, or self-hosted execution. A pre-merge 404 is therefore classified as
`WORKFLOW_DISPATCH_REGISTRATION_LIMITATION`, not runner unavailability. GitHub
resolves a called reusable workflow's self-hosted runner from the caller repository
context when the caller and called repositories share the same owner. This allows the
existing repository-level Windows runner to remain assigned where it is; Ordifile
does not register, move, relabel, or reconfigure it. The prototype merge gate remains
blocked until the exact-SHA caller run and the macOS automated job both pass for the
same reviewed PR head.

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

The outer artifact is explicitly `publishable: false`. Prototype ZIPs are generated in
an allowlisted source-checkout directory, copied into bounded job scratch for smoke,
and removed from both locations after the job. They are not Actions artifacts and are
never attached to a GitHub Release by this workflow. Same-job scratch execution proves
checkout-independent use, but it is not a substitute for a separate clean-machine
test.

The source, exact direct toolchain versions, spec, inventory ordering and ZIP metadata
are deterministic. Functional rebuilds are expected to be repeatable. Byte-identical
Nuitka/native linker output has not been demonstrated and is not claimed.

## Licensing and publication gate

Ordifile selects LGPL-3.0 for the dynamically bundled Qt/PySide6/shiboken6 components.
Ordifile does not copy or modify their source code; native deployment tooling may
rewrite loader metadata in copied bundle binaries, so final modification and source
obligations remain a publication gate. Each prototype includes the full LGPL-3.0 text,
an exact component notice, the Python license, Ordifile license/notice, reviewed
application dependency licenses, and the exact Nuitka Runtime Library Exception from
Nuitka 4.1.3.

Nuitka 4.1.3 is an AGPL-3.0 build tool and is not bundled. Its Runtime Library
Exception permits qualifying generated target code under the program's own terms; it
does not relicense the compiler or remove the compiler's AGPL obligations. The current
prototype carries the reviewed application/package license set and the matching CPython
license. Complete third-party inventory for the standalone macOS runtime remains a
mandatory public-distribution gate; it is not implied by successful prototype assembly.

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
