# Self-hosted runner threat model

## Scope

Every Ordifile Actions job is routed only to a dedicated self-hosted trust label. This
document covers persistent trusted work, untrusted public-fork contributions, release
publication, local dependency state, external scientific fixtures, and cleanup.

## Principal risks

Self-hosted jobs execute repository-controlled programs. A malicious or compromised
change can read files, processes, credentials, network services, caches, or devices
that the runner account can reach and can leave persistence for later jobs. Merely
running the job in a container on a long-lived host does not erase the host boundary.

Important threats include:

- an external fork changing a workflow, build backend, dependency, test, shell script,
  or imported module to access the runner;
- a poisoned workspace, virtual environment, executable search path, or dependency
  cache affecting a later trusted job;
- credentials, SSH agents, NAS mounts, Docker sockets, cloud metadata, or internal
  services being reachable from untrusted code;
- a release job rebuilding or substituting artifacts after verification;
- an external pull request reaching fixture caches or redistributable-rights-restricted
  files;
- unsafe cleanup escaping the job checkout and damaging another repository or the
  Actions runner installation.

## Trust classes

### `ordifile-trusted`

This may be a persistent runner, but it accepts only a push to `main`, a branch or pull
request owned by `hdkim99/ordifile`, a maintainer dispatch, or a trusted schedule. It has
no package-index secret. It never runs external-fork code. Its workspace is cleaned at
the start and end of every job using the repository-scoped cleanup tool.

### `ordifile-pr-ephemeral`

This executes an external fork only after maintainer approval and only on a disposable
VM, microVM, or instance registered with `--ephemeral`. It has no internal network,
NAS, SSH key, Docker host socket, administrator privilege, persistent cache, fixture
cache, write token, environment, secret, or OIDC permission. Job completion must lead
to VM/disk destruction, not only GitHub runner deregistration.

### `ordifile-release`

This executes only release validation and annotated release tags from the trusted
repository. It never runs feature branches or pull requests. PyPI and TestPyPI access
uses short-lived GitHub OIDC in the exact publish job; no username, password, API token,
or `TWINE_PASSWORD` is stored. Artifact build-once, digest comparison, attestation, and
environment approval remain mandatory.

## Controls

- Every `runs-on` contains `self-hosted` and exactly one Ordifile trust-class label.
- External and internal pull-request jobs are mutually exclusive.
- No `pull_request_target`, `workflow_run`, or `issue_comment` path executes fork code.
- External jobs have read-only repository permission, no cache, and no fixture access.
- Actions are pinned to immutable commit hashes.
- A repository-scoped Python cleanup tool rejects paths outside the checkout and does
  not touch the runner installation, another checkout, or shared host state.
- Provisioned persistent hosts should also use runner-level
  `ACTIONS_RUNNER_HOOK_JOB_STARTED` and `ACTIONS_RUNNER_HOOK_JOB_COMPLETED` controls as
  defense in depth; repository scripts alone cannot protect a compromised host.
- Release jobs build once and pass a checksummed immutable artifact through the DAG.
- Missing runner capacity is a blocking condition, never a reason to use a hosted or
  generic fallback.

Custom labels perform scheduling, not authorization. A fork can propose a workflow
change that asks for a different label. The repository therefore requires approval for
all external contributors, a complete workflow/build diff review, and a disposable-only
operational policy. Where runner groups are unavailable to a user-owned public
repository, label-based routing plus mandatory approval remains a residual human control,
not a cryptographic isolation boundary.

## Residual risks

GitHub workflow controls cannot prove physical isolation, erase disks, or establish
network policy. Those controls are operational requirements recorded as `Unresolved`
until the maintainer verifies the provisioned host. A persistent runner remains a
high-value asset even after workspace cleanup; host-level patching, account isolation,
monitoring, and incident response remain required.
