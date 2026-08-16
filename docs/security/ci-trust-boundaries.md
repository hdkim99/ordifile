# CI trust boundaries

## Routing table

| Event | Code trust | Runner label | Secret | Token | Cache | Fixture |
|---|---|---|---|---|---|---|
| Internal PR | Trusted | `ordifile-trusted` | No | Read | Trusted only | No |
| External PR | Untrusted | `ordifile-pr-ephemeral` | No | Read | No | No |
| Main push | Trusted | `ordifile-trusted` | No | Read | Trusted only | Optional, separate workflow only |
| Scheduled fixture | Trusted | `ordifile-trusted` or dedicated fixture label | No | Read | Isolated | External |
| Release tag | Trusted | `ordifile-release` | OIDC only | Scoped | No | No |

The table describes policy, not current runner availability. The [runner
inventory](self-hosted-runner-inventory.md) is authoritative for operational readiness.

## Internal and external pull requests

`ci.yml` separates internal and external pull requests before runner selection. Internal
work targets only `ordifile-trusted`. An external fork, including an equivalent bot
fork, targets only `ordifile-pr-ephemeral`. Neither route can fall through to a bare
`self-hosted` runner. The stable required-check name is `CI / required`, and the
aggregator runs in the same trust class as the code it reports on.

External jobs receive `contents: read` only. They do not use environments, OIDC,
secrets, Actions cache, runner-local dependency caches, release artifacts, or external
scientific fixtures. A maintainer reviews workflow, dependency, build, shell, binary,
symlink, Unicode, network, subprocess, and credential-relevant changes before approving
the workflow run.

## Release boundary

Release jobs target only `ordifile-release`. OIDC is granted only to TestPyPI/PyPI
publication and attestation jobs that need it. The workflow does not use package-index
tokens and does not rebuild between TestPyPI, PyPI, and GitHub Release publication.
Until a compatible release runner is registered and verified, a future release is
`BLOCKED_BY_RELEASE_RUNNER`.

## Current readiness

- Self-hosted trusted CI: `BLOCKED_BY_RUNNER_PROVISIONING`
- External fork PR CI: `BLOCKED_BY_EPHEMERAL_RUNNER`
- Release CI: `BLOCKED_BY_RELEASE_RUNNER`

Repository settings verified on 2026-08-16:

- default `GITHUB_TOKEN`: read-only;
- fork workflow approval: `all_external_contributors`;
- send write tokens/secrets to fork workflows: not enabled by the workflow and must
  remain disabled in repository settings;
- main ruleset: none (application is blocked until `CI / required` has a real, recent
  successful self-hosted run);
- release tag ruleset: active `Protect release tags` for `refs/tags/v*`, restricting
  creation, update, deletion, and non-fast-forward changes with owner-only emergency
  bypass;
- registered self-hosted runners: zero.

Queued jobs are expected while a required label has no online runner. They must not be
rerouted to a GitHub-hosted runner to clear the queue.
