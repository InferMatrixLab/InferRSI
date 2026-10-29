# Releases

The [release bot](../.github/workflows/release.yml) builds a stable version tag
and creates a **draft** GitHub Release as `github-actions[bot]`. It uploads a
wheel, source distribution and `SHA256SUMS`, and generates notes from merged PRs.
The [notes configuration](../.github/release.yml) uses existing `enhancement`,
`bug` and `documentation` labels, with a catch-all for other PRs.

This is release automation, separate from the four CI lanes. It does not bump
versions, merge changes, publish the draft, upload to PyPI or run accelerator
experiments. Building a release does not establish campaign `PASS`.

## Setup

Merge the release configuration into the default branch. GitHub Actions must be
enabled and organization policy must allow the listed GitHub-owned actions and
the publisher job's `contents: write` permission. No additional secret, PAT,
GitHub App or repository-wide write-token default is needed. Build jobs have
read-only access; only the draft job receives write access, without executing
repository code.

The initial bot supports stable tags `vMAJOR.MINOR.PATCH` only. Pre-release and
local-version tags are rejected. Release commits must be reachable from the
default branch. Use tags containing this release tooling and the corresponding
installed-package checker; this is not a retroactive publisher for older tags.

## Prepare a version

1. Choose the version and scope in the governing release Issue. Update both
   `project.version` in `pyproject.toml` and `__version__` in
   `src/inferrsi/__init__.py` in a reviewed PR. No version is chosen or bumped by
   this configuration change.
2. Complete the applicable CI/review checks and merge the version PR. The bot
   rebuilds and checks package installation, but does not replace PR validation.
3. Fetch the default branch and create an annotated tag at the intended merged
   revision. Substitute the selected tag and commit below; `<remote>` is the
   canonical repository remote, which may differ from a contributor's fork.

   ```bash
   git fetch <remote> <default-branch> --tags
   git tag -a <version-tag> <release-commit> -m "InferRSI <version-tag>"
   git push <remote> refs/tags/<version-tag>
   ```

Pushing the tag starts the bot. It resolves the exact tag ref, checks default
branch ancestry and the push-event commit, builds the sdist and a wheel from
that sdist, runs `twine check`, and reuses `tests/check_installed.py` from a
clean wheel installation outside the checkout. Distribution metadata and the
installed runtime version must both equal the tag's version.

The bot rechecks the remote tag and ancestry before creating the draft. Avoid
moving/deleting release tags, including during a run; these checks are not a
server-side lock against concurrent tag changes. Tag protection can be managed
separately by repository owners.

## Dry run and retry

Under **Actions → Release bot → Run workflow**, select the default branch,
enter an existing version tag and leave **dry_run** checked. This runs the
read-only build and uploads the package/checksum Actions artifact for seven
days. It skips the write job and creates no Release. Clearing **dry_run**
requests a draft for that existing tag. The equivalent CLI is:

```bash
gh workflow run release.yml --repo InferMatrixLab/InferRSI --ref <default-branch> \
  -f tag=<version-tag> -F dry_run=true
```

Same-tag runs are serialized. A failure before draft creation can be retried.
An existing draft or published Release stops creation; the bot never overwrites
notes/assets or uses `--clobber`. If an upload left an incomplete draft, inspect
its tag/source and assets first. An authorized maintainer may remove only that
unpublished incomplete draft and rerun, or recover it manually. Published
release corrections require a new version and a separate release decision.

## Review and publish

Inspect the draft notes, source revision and all three attachments. Verify the
downloaded package hashes with `sha256sum --check SHA256SUMS`. Review generated
PR titles and any performance/quality claims: such claims need the acceptance
Issue, pinned experimental revisions and complete frozen evidence described in
[contributing](contributing.md#evidence-and-claims). Preserve failed and
inconclusive results; a software version does not qualify hardware or models.
Then publish the draft through GitHub under the maintainer's release authority.

The first release may include many historical PRs. Review and edit its generated
notes before publishing; later releases use GitHub's previous-release selection.

## Reference and limits

[JiuwenSwarm v0.2.7](https://github.com/openJiuwen-ai/jiuwenswarm/releases/tag/v0.2.7)
demonstrates bot-authored releases with release notes and downloadable packages.
Its publisher is a [private GitHub App](https://github.com/apps/openjiuwen-release-bot);
the publishing workflow is not present in the inspected public source. InferRSI
implements its own flow using the built-in token, following GitHub's
[token permissions](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token),
[generated notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes)
and [draft-release CLI](https://cli.github.com/manual/gh_release_create) contracts.
Remote release execution is verified only by an actual Actions run; local
checks alone do not establish that repository/organization policies permit it.
