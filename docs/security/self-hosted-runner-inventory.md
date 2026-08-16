# Self-hosted runner inventory

- Repository: `hdkim99/ordifile`
- Last verified: 2026-08-16
- Source: GitHub repository Actions runners API and repository settings

## Current inventory

The repository currently has **zero registered self-hosted runners**. No runner name,
operating system, architecture, custom label, persistence model, privilege level, or
network access can therefore be verified.

| Field | Verified value |
|---|---|
| Runner count | 0 |
| Runner names | None |
| Status | Not applicable |
| Busy | Not applicable |
| OS | Unresolved |
| Architecture | Unresolved |
| Existing labels | None |
| Persistent | Unresolved |
| Ephemeral | Unresolved |
| Physical host | Unresolved |
| Service privilege | Unresolved |
| Internal network access | Unresolved |
| NAS access | Unresolved |
| SSH credentials | Unresolved |
| Docker socket | Unresolved |
| Other repository use | Unresolved |
| Release use | Unresolved |

No internal IP address, user home, registration token, credential location, or other
machine identifier belongs in this document.

The pinned Node 24 Actions require a self-hosted runner version compatible with Node 24;
the minimum verified requirement is runner `2.327.1`. The registered runner version is
currently Unresolved because no runner exists.

## Required registrations

The workflows use trust-class labels as routing contracts. They do not fall back to a
GitHub-hosted runner or to a generic `self-hosted` label alone.

| Trust class | Required custom label | Current state |
|---|---|---|
| Trusted repository work | `ordifile-trusted` | `BLOCKED_BY_RUNNER_PROVISIONING` |
| External fork pull requests | `ordifile-pr-ephemeral` | `BLOCKED_BY_EPHEMERAL_RUNNER` |
| Release build and publication | `ordifile-release` | `BLOCKED_BY_RELEASE_RUNNER` |

The OS and architecture labels must be added to this inventory only after GitHub shows
the actual registered runner labels. A persistent trusted runner must never also carry
`ordifile-pr-ephemeral`. A release runner must never execute external pull-request code.
The pinned PyPI publish action is a Linux Docker action, so publication specifically
requires a verified GNU/Linux release runner with Docker support. Ordifile does not
replace OIDC publishing with a package token when that runner is absent.

## Capacity

Until an inventory update proves otherwise, Ordifile assumes capacity of one job at a
time per trust class. Workflow matrices use `max-parallel: 1`, and trusted/release runs
are not cancelled partway through. Registering a runner does not by itself make the
corresponding class ready: the host controls in the threat model and setup runbook must
also be verified.
