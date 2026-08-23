# Releasing Ordifile

This runbook is for maintainers of `hdkim99/ordifile`. Releases use GitHub Actions
OpenID Connect (OIDC) trusted publishing. Do not create a PyPI API token or add a
publishing token to GitHub secrets.

The release workflow has two routine entry paths:

- a manual `workflow_dispatch` from the current `main` commit performs a dry run only;
- an annotated `vX.Y.Z` tag contained in `main` performs the one-time TestPyPI and PyPI
  publication path.

An additional, code-allowlisted `promote-existing` dispatch may be present temporarily
to recover one audited immutable artifact after its DGX build and wheel smoke succeeded
but publication did not start. It is not a general manual publishing interface. Its
run, tag, commit, artifact ID, artifact digest, filenames, and package hashes must all
match reviewed constants before any package-index environment is entered.

The normal `dry-run` path has read-only repository permission and cannot run TestPyPI,
attestation, package publication, or GitHub Release jobs. Pull requests never trigger
the release workflow. The tag path builds once, stores one immutable Actions artifact,
tests its default wheel on the shared Linux DGX runner, and installs that exact wheel
with the GUI extra on hosted macOS, all with Python 3.14. Hosted Ubuntu jobs then publish
and verify the same wheel and sdist on TestPyPI, create attestations and a draft GitHub
Release, publish the same bytes to PyPI, and only then make the GitHub Release public. A
pull request, ordinary branch push, fork, or `dry-run` cannot publish.

Only `Validate and build once` and `Wheel smoke / shared DGX / Python 3.14` use the
self-hosted runner with the `dgx-spark` label. `GUI wheel smoke / macOS / Python 3.14`
uses hosted macOS to install `ordifile[gui]` from the same immutable wheel, create the
desktop window with the prepared offscreen Qt plugin, and require a normal process exit.
TestPyPI/PyPI publishing, index-byte verification, attestation, and GitHub Release jobs
use GitHub-hosted Ubuntu. The pinned PyPA publisher is a Docker container action; keeping
publication hosted means the DGX does not need unrelated host changes. Do not use a
package-index token as a fallback.

## One-time account configuration

Configure both package indexes before creating a release tag. PyPI and TestPyPI have
separate accounts and separate trusted-publisher records.

### TestPyPI pending trusted publisher

Open <https://test.pypi.org/manage/account/publishing/> while signed in to TestPyPI.
Under **Add a new pending publisher**, enter exactly:

| Field | Value |
|---|---|
| PyPI project name | `ordifile` |
| Owner | `hdkim99` |
| Repository name | `ordifile` |
| Workflow name | `release.yml` |
| Environment name | `testpypi` |

If the project already exists under the repository owner's account, add the publisher
from that project's **Manage → Publishing** page instead of creating a pending
publisher. Stop if the name belongs to another owner.

### PyPI pending trusted publisher

Open <https://pypi.org/manage/account/publishing/> while signed in to PyPI. Under
**Add a new pending publisher**, enter exactly:

| Field | Value |
|---|---|
| PyPI project name | `ordifile` |
| Owner | `hdkim99` |
| Repository name | `ordifile` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

As with TestPyPI, use an existing project's **Manage → Publishing** page if the
project is already controlled by the repository owner. A package-index search result
is not proof of ownership or a reservation.

### GitHub environments

In <https://github.com/hdkim99/ordifile/settings/environments>, create these exact
environment names:

- `testpypi`
- `pypi`

For both environments:

1. Disable administrator bypass where the available repository settings permit it.
2. Restrict deployment branches and tags to the release-tag pattern `v*.*.*`.
3. Do not add publishing secrets; OIDC supplies a short-lived identity to the package
   index.

The normal policy permits only the release-tag pattern. A reviewed existing-artifact
recovery dispatched from `main` requires a temporary exact `main` branch policy in both
environments because GitHub evaluates the workflow run ref before entering an
environment. Add that branch policy only after the recovery PR and current-main dry run
are green. Keep the existing tag policy and the `pypi` reviewer. Remove both temporary
`main` policies immediately after the recovery run succeeds, fails, or is cancelled.

The `testpypi` environment normally does not need a required reviewer: the annotated
tag, exact-version gate, and TestPyPI byte verification are its pre-production gates.
An optional TestPyPI reviewer may be added when another maintainer is available.

The `pypi` environment must have a required reviewer so production publication pauses
for explicit manual approval. Prefer a second trusted maintainer or team. In a
single-maintainer repository, selecting only the initiating maintainer while enabling
**Prevent self-review** makes the deployment impossible to approve. Until a second
reviewer exists, the repository owner may be the required reviewer only with self-review
prevention disabled; this preserves an explicit approval click but is weaker than
two-person review. Do not remove the `pypi` approval gate to avoid that limitation.

Before approving `pypi`, verify the job summary, version, tag commit, wheel name, sdist
name, and checksums. TestPyPI publication is also irreversible for that index even when
it has no approval pause.

These setup steps follow the PyPI trusted-publisher model. They do not grant access to
Codex or require a maintainer to disclose a PyPI password, recovery code, or API key.

## Prepare a version

1. Start a release branch from a clean, current `main`.
2. Set the same strict `X.Y.Z` version in `pyproject.toml` and
   `src/ordifile/_version.py`.
3. Update `CHANGELOG.md` with the actual release date and accurate supported features,
   privacy and data-integrity behavior, and limitations.
4. Create `docs/releases/vX.Y.Z.md`. The workflow refuses a version without matching
   notes.
5. Update installation text only when it accurately describes the publication state.
6. Open a pull request, require the normal CI and independent review, and merge without
   bypassing branch protection.

Normal pull-request quality, package, and wheel checks belong to `ci.yml`. Owner-authored
internal branches use the shared DGX runner with read-only repository permission.
Public-fork and bot-authored pull-request jobs are skipped; reviewed external or
dependency changes must be reproduced on an owner-authored same-repository branch.
Pull-request jobs cannot publish. A green pull-request check does not replace
the post-merge release dry run from the exact current `origin/main` commit.

Adapter protocol versions are not automatically the package version. Do not change
adapter versions merely to make a package release unless their public adapter behavior
changed.

## Release-candidate validation

Run the repository checks in a clean environment:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy
pytest
pip-audit
python -m build
python scripts/verify_release.py \
  --dist-dir dist \
  --expected-version X.Y.Z \
  --checksums dist/SHA256SUMS.txt
```

The verifier must find exactly one wheel and one sdist, matching package metadata,
required Apache-2.0 files, expected package contents and entry point, and an installable
CLI. Preserve `dist/SHA256SUMS.txt` with the reviewed candidate.

After the release preparation is merged, run the Actions dry run from the exact current
`main` commit:

```bash
gh workflow run release.yml --ref main -f mode=dry-run
gh run watch --exit-status
```

The manual run performs all quality, build, checksum, default-wheel, and macOS GUI-extra
smoke jobs but has no publishing job. TestPyPI is intentionally not a manual preview
channel: PyPI indexes do not allow the same version file to be uploaded twice. A
pre-release candidate that needs index-level testing must use a new PEP 440 pre-release
version in a future release plan; it must not consume the final version filename early.

Before tagging, independently confirm all of the following:

- the release commit is on `origin/main` and normal CI is green;
- the dry-run Release workflow is green;
- the exact wheel's default and macOS GUI-extra smoke jobs are green;
- PyPI and TestPyPI still have the expected `ordifile` ownership state;
- both trusted-publisher records contain the exact fields above;
- both GitHub environments and required approvals are active;
- `CHANGELOG.md`, release notes, README, and package version agree;
- the verifier has no Critical, High, or release-related Medium findings.

If either trusted publisher, either GitHub environment, or its approval policy is not
ready, stop after the dry run. Do not create or push the release tag and do not use an
API token as a fallback.

## Create the release tag

Never tag an unmerged release branch. From a clean, synchronized `main`:

```bash
git switch main
git pull --ff-only origin main
git status --short
git rev-list --left-right --count main...origin/main
git tag -a vX.Y.Z -m "Ordifile vX.Y.Z"
git push origin vX.Y.Z
```

The workflow rejects lightweight tags, non-`vX.Y.Z` tags, mismatched package versions,
and tagged commits outside `origin/main`. Do not move or force-update a release tag.

Watch the tag workflow. The TestPyPI job proceeds under its tag-restricted environment.
The workflow reads only the TestPyPI JSON endpoint, requires the exact wheel and sdist
filenames and hashes, downloads both files directly from TestPyPI, and compares their
bytes with the reviewed build. It does not combine TestPyPI and PyPI package indexes.
It then creates attestations and a draft GitHub Release. Only after those gates should
the maintainer approve `pypi`.

The production publish job cannot use a token, rebuild a distribution, or silently
skip an existing file. After PyPI succeeds, the workflow performs the same exact
filename, index digest, and downloaded-byte checks against PyPI. The final job makes the
existing GitHub Release public only after that verification succeeds.

## Promote one existing immutable artifact

Use `promote-existing` only when all of the following are true:

- the original tag workflow completed the DGX build and wheel smoke successfully;
- upload to TestPyPI did not begin and both package indexes still return 404 for the version;
- no GitHub Release exists for the tag;
- the source artifact is unexpired and its ID, archive digest, filenames, and package
  SHA-256 values have been independently recorded;
- the annotated tag still points directly to the original build commit in `main`;
- a reviewed workflow change allowlists that exact recovery and passes normal CI,
  release dry run, and independent verification.

For the audited v0.2.1 recovery, dispatch the current `main` workflow with the exact
recorded run, tag, commit, and artifact name:

```bash
gh workflow run release.yml --ref main \
  -f mode=promote-existing \
  -f source_run_id=31980576873 \
  -f release_tag=v0.2.1 \
  -f expected_head_sha=33e1b6ec4d6d822e1a0b532e0d075adc4d79c788 \
  -f artifact_name=ordifile-distributions-31980576873
```

The validation job reads the source run and tag through the GitHub API, requires the
reviewed build/smoke conclusions and artifact ID/digest/size, downloads that artifact
by exact ID, verifies archive metadata and package bytes against the tagged source, and
does not invoke a build or wheel-smoke job. The hosted promotion chain then follows the
same irreversible order as a normal release:

```text
TestPyPI publish → exact-byte verification → attestation → draft GitHub Release
→ PyPI approval/publish → exact-byte verification → public GitHub Release
```

The recovery attestation proves the reviewed promotion workflow handled those exact
bytes. It does not retroactively claim that the hosted job built them; the source run,
artifact ID/digest, and wheel/sdist hashes preserve the link to the DGX build.

Never rerun the failed v0.2.1 publish job, move either v0.2-series tag, rebuild the
archives, enable `skip-existing`, or introduce PyPI/TestPyPI credentials. If any expected
identity differs, stop without publishing. After completion, remove the temporary
environment policies and the one-time promotion mode in a separate reviewed cleanup PR;
keep the normal hosted publication jobs.

If the audited promotion has already published and byte-verified both indexes, generated
the attestation, and created the exact draft Release but fails before making that draft
public, do not upload either distribution again. After a reviewed workflow fix, dispatch
the same immutable inputs with `mode=finalize-existing`. That path reruns the source,
artifact, and live-tag gates; verifies the existing TestPyPI/PyPI bytes, each attested
subject, and every draft asset; then makes the existing draft public. It has no package
index environment, OIDC publication permission, build, artifact upload, or publish action.

## Post-release verification

Download the GitHub Release assets and verify the checksums before installation:

```bash
sha256sum -c SHA256SUMS.txt
python -m pip install --no-cache-dir ordifile==X.Y.Z
ordifile --version
ordifile --help
ordifile formats
```

On Windows PowerShell, compare each release checksum with
`Get-FileHash -Algorithm SHA256 <file>`.

In a new directory and clean virtual environment, also inspect and convert a committed
synthetic fixture, reopen the result workbook, and confirm `Manifest`, `Samples`,
`Peak_Matrix`, `Peaks`, `Metadata`, and `Import_Log`. Verify on the PyPI project page:

- version, Python requirement, Apache-2.0 metadata, and repository URL;
- exactly the reviewed wheel and sdist and their hashes;
- trusted-publishing provenance or attestation information;
- README rendering.

Verify that the public GitHub Release contains the same wheel and sdist bytes plus
`SHA256SUMS.txt`, and that its tag points to the reviewed `main` commit. Only after all
checks pass should README installation text and badges describe PyPI publication as
available.

## Failure handling and version immutability

PyPI files are immutable release records. A file uploaded for a version is not a
replaceable object, and deletion does not make reusing that filename or version a safe
release process.

- If validation fails before either index receives a file, fix the release branch,
  merge normally, and rerun the manual dry run. Do not move an existing tag. An
  existing-artifact promotion is allowed only for an explicitly audited artifact under
  the stricter procedure above; it is not an automatic retry.
- If TestPyPI received `0.1.0` and a later job fails, preserve the evidence, do not
  re-upload or overwrite `0.1.0`, and prepare `0.1.1` from a new reviewed commit.
- If PyPI received a file, never rebuild or reuse that version. Correct the project in
  a new version such as `0.1.1`.
- If PyPI succeeded but the final GitHub Release publication failed, verify the PyPI
  files against the draft assets and publish that existing draft; do not rerun the
  PyPI upload.
- If only a draft GitHub Release exists and no package index accepted a file, leave it
  private while investigating. Remove it only after retaining the run logs and failure
  record.
- Do not add `skip-existing`, change a tag target, delete a test, lower a quality gate,
  or introduce an API token to make a failed release appear successful.

There is no true rollback for an installed PyPI file. A harmful version may be yanked
to discourage new resolver selection, but the incident must still be disclosed and a
fixed version released. Yanking is not deletion and does not authorize version reuse.

## Compromised-release response

If a tag, workflow run, artifact, GitHub account, or package-index publisher may be
compromised:

1. Do not approve any waiting environment deployment; cancel active release runs.
2. Disable or remove the affected PyPI and TestPyPI trusted-publisher records.
3. Preserve workflow logs, artifact digests, tag objects, audit records, and timestamps.
4. Keep a draft GitHub Release private, or mark a public release as compromised without
   replacing its files.
5. Yank an affected PyPI version when warranted and publish a security advisory through
   the repository's documented security channel.
6. Revoke affected GitHub sessions or credentials and restore branch, tag, environment,
   and account protections before resuming.
7. Release a reviewed fix under a new version, normally the next patch such as `0.1.1`.

Do not delete evidence, rewrite published Git history, or claim that a yanked artifact
was never distributed.

## Authoritative references

- [PyPI: Creating a project through OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [PyPI: Adding a trusted publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
- [Python Packaging User Guide: Publishing with GitHub Actions](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [GitHub: Managing environments for deployment](https://docs.github.com/actions/deployment/targeting-different-environments/managing-environments-for-deployment)
- [GitHub: Artifact attestations](https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/use-artifact-attestations)
