# Ephemeral external pull-request runner setup

## Required host

Use a disposable VM, microVM, or dedicated instance created from a clean, pinned image.
A container on a persistent trusted host is not sufficient isolation. The instance must
have no route to an internal network, NAS, cloud metadata service, host Docker socket,
SSH agent/key, package publishing account, external fixture cache, or other repository.
Run the Actions service as an unprivileged user without administrator or sudo access.

## Registration

1. Create the disposable instance and install only the pinned runner package and the
   Python/toolchain versions required by the workflow.
   The current pinned Node 24 Actions require runner version `2.327.1` or newer.
2. Request a short-lived registration token immediately before registration. Never
   store it in the repository, image, shell history, or logs.
3. Register against `https://github.com/hdkim99/ordifile` with `--ephemeral`,
   `--unattended`, and the exact custom label `ordifile-pr-ephemeral` plus the actual OS
   and architecture labels reported by GitHub.
4. Verify that neither `ordifile-trusted` nor `ordifile-release` is present.

Linux example; substitute the verified runner package and actual labels:

```console
./config.sh --url https://github.com/hdkim99/ordifile \
  --token '<short-lived-registration-token>' \
  --ephemeral --unattended \
  --labels 'ordifile-pr-ephemeral,<actual-os>,<actual-architecture>'
./run.sh
```

On Windows use the corresponding `config.cmd` and runner service procedure. Do not
copy a token into a script or documentation.

## Network and storage policy

- Allow only the endpoints needed to fetch the repository, pinned Actions, Python
  dependencies, and vulnerability data used by the approved job.
- Deny RFC1918/internal services, link-local/cloud metadata, NAS, remote shells, and
  host-management networks.
- Use a fresh virtual disk and empty workspace for one job.
- Do not restore or save Actions, pip, compiler, fixture, or workspace caches.
- Do not mount a host workspace, Docker socket, credential directory, or shared home.

## Completion and disposal

Detect the runner process exit and verify GitHub deregistration. Export only sanitized
runner diagnostics needed for incident response; do not retain repository contents,
secrets, fixture names, or contributor data unnecessarily. Power off and destroy the VM,
disk, snapshots made after job start, and temporary network identity. Deregistration
without storage destruction is not completion.

If setup, job execution, deregistration, log export, or destruction fails, quarantine
the instance and investigate it. Never relabel or reuse it as a trusted/release runner.

For persistent trusted/release hosts, configure runner-level job-started and
job-completed hooks outside the repository to verify the expected repository/ref and to
remove only that runner's workspace. Hook paths and host cleanup policy are deployment
configuration and must not be copied into a public workflow or exposed to fork code.
