# Unsigned standalone prototype

Ordifile has a maintainer-only prototype path for native Windows and macOS desktop
bundles. It is not a public binary release and does not change the supported
`pip install ordifile` or `ordifile[gui]` paths.

## Scope

- Windows x86-64: onedir ZIP
- macOS native arm64 or x86-64: `.app` ZIP
- Python 3.14.3, PySide6-Essentials/shiboken6 6.11.2, Nuitka 4.1.3
- unsigned or ad-hoc-signed evidence only
- public-safe synthetic inputs for every built-in Generic, Agilent, Shimadzu and
  YoungIn adapter, including UTF-8, UTF-8-BOM and YoungIn CP949
- no Qt TLS plugins or application network feature

Onefile, MSI, DMG, Linux bundles, auto-update, signing, notarization and GitHub Release
publication are excluded.

## Run the manual workflow

After the workflow definition exists on the default branch, a maintainer can dispatch
**Standalone prototype** for reviewed `main` in GitHub Actions. GitHub does not expose
a new branch-only manual workflow before that registration condition is met; the prior
pre-merge 404 is a workflow-registration limitation, not evidence that a native runner
does not exist. No token, signing secret, OIDC permission or vendor software is used.

The Windows job has no GitHub-hosted fallback. It requires the cumulative
`self-hosted`, `Windows`, and `X64` capability labels and runs only when that
repository-authorized runner is assigned and online. Because its workspace persists,
the job checks out into a workflow-owned source directory, uses a run-scoped virtual
environment and unique runner-temporary scratch root, masks runner-local identifiers,
and performs bounded cleanup before and after execution. The macOS job is fixed to
GitHub-hosted `macos-15`; changing that routing requires a separate review.
Both jobs check out read-only `main`, unpack the exact candidate into runner-temporary
space, clear Python import overrides, and run only the packaged executable for
scientific and window smokes. This is checkout-independent artifact execution, but not
a separate clean-machine result.

Manual/main-only routing, read-only repository permission, an isolated Python
environment, and cleanup reduce exposure; they do not make a persistent self-hosted
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

The manifest is deterministic and path-safe. It records the source commit, Ordifile
and toolchain versions, target, signature state, dynamic adapter registry, every inner
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

Valid targets are `windows-x86_64`, `macos-arm64`, and `macos-x86_64`. The builder
rejects a target that does not match the host. It withholds captured deployment output
on failure so local paths are not copied into public logs.

## What the smoke proves

The artifact-only smoke checks the outer checksum and non-publishable signature gate,
then runs the packaged executable with `--standalone-smoke`. It verifies:

- version and registry-derived adapter inventory;
- detection and parsing for all built-in Generic, Agilent, Shimadzu and YoungIn
  adapters, including CP949 codec and exact synthetic YoungIn Result detection;
- independent plain UTF-8 and UTF-8-BOM generic input handling;
- conversion using the same public API as CLI/GUI;
- workbook reopen plus ordered equivalence for `Samples`, `Peak_Matrix`, `Peaks`,
  `Peak_Order_Matrix`, `Metadata` and `Import_Log`;
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
