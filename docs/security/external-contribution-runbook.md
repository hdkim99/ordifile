# External contribution runbook

## Before approving a workflow

An external fork must have an online disposable runner with the
`ordifile-pr-ephemeral` label. If it does not, record
`BLOCKED_BY_EPHEMERAL_RUNNER`; do not run the contribution on `ordifile-trusted`, on
`ordifile-release`, or on a hosted fallback.

Review the complete pull-request diff and commit tree before approval:

1. `.github/workflows/**`, actions, permissions, events, checkout refs, and shells;
2. `pyproject.toml`, build backends, dependencies, lock/constraint files, and package
   entry points;
3. scripts, subprocess or network calls, generated files, and test collection hooks;
4. binary files, archives, executable modes, symbolic links, submodules, hidden Unicode,
   and path aliases;
5. environment, credential, runner path, service, Docker socket, SSH agent, NAS, or
   internal-network access;
6. proprietary raw data, personal information, local paths, metadata, and licensing.

Repository Actions settings must require approval for **all outside collaborators**.
Never enable write tokens or secrets for pull-request workflows.

Labels alone are not access control: an untrusted change can propose a different
`runs-on`. The approver must reject any attempt to request `ordifile-trusted`,
`ordifile-release`, a generic `self-hosted` runner, or an unreviewed runner group. If an
organization-level selected-workflow runner group is not available, keep trusted and
release runners offline while an approved external run is being serviced as an added
operational safeguard.

## Approved execution

- Register one disposable instance using the procedure in
  [ephemeral-runner-setup.md](ephemeral-runner-setup.md).
- Confirm it has `self-hosted` and `ordifile-pr-ephemeral`, but neither trusted nor
  release labels.
- Approve only the reviewed workflow run.
- Observe that `CI / required` ran on the ephemeral trust class.
- Do not attach a persistent cache or external fixture cache.
- After completion, retain sanitized diagnostics and destroy the VM and disk.

## Pull request #9

Static review on 2026-08-16 found no workflow, runtime dependency, release, source
package, symlink, executable, vendor raw-data, credential, or large-file change. The PNG
is a 3,345 × 405 synthetic workbook screenshot with Matplotlib software metadata only;
its visible source-file SHA-256 matches the submitted synthetic CSV. The README image
uses a `raw.githubusercontent.com/.../main/...` URL and should be changed to a repository
relative link before merge.

Execution and merge remain `BLOCKED_BY_EPHEMERAL_RUNNER`. Static inspection is not a
substitute for the required Ruff, mypy, pytest, build, audit, clean-wheel, workbook, and
Unicode round-trip checks.
