# Automatic daily releases

The [release bot](../.github/workflows/release.yml) runs every day at **02:00
Asia/Shanghai** (18:00 UTC). GitHub schedules can be delayed. If the default
branch's source tree is unchanged from the highest successfully published numeric
version, it skips the release. Empty commits do not cause a release.

When changed, the bot chooses a version, builds and checks the packages, creates
the tag and publishes the GitHub Release as `github-actions[bot]`. There is no
manual version bump, tag push or draft publication step. The first release uses
`tool.inferrsi.release.initial_version` in `pyproject.toml` (initially `0.1.0`);
subsequent releases allocate the next unused numeric patch version. Major/minor
releases need a separately reviewed change to that initial-version floor.

The existing **Developer Preview** classification is preserved:
`tool.inferrsi.release.prerelease = true` marks automatic releases as GitHub
prereleases and does not mark them Latest. Changing to a stable channel is a
separately reviewed configuration decision. Published previews count as
successful releases for no-change detection; private drafts do not.

## Authority boundary

The bot's only repository mutations are creating a new `refs/tags/<version>`
at an existing reviewed commit and creating/uploading/publishing that version's
Release. It must not create code commits, edit repository files, create/update/
delete code branches, create/approve/merge PRs or enable auto-merge. Configuration
development and review are contributor work; they are not bot capabilities.

Plan/build jobs have Contents read access. Only the publisher receives Contents
write; Pull requests permission is explicitly none. The publisher validates its
tag/SHA inputs and never checks out or executes repository code. Regression
tests execute its actual shell commands against a recording GitHub mock that
rejects non-publication writes.

This is an enforced workflow behavior contract, not a tag-only token scope.
GitHub's Contents write permission also authorizes
[file commits](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents)
and [PR merging](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request);
setting Pull requests to none does not remove those Contents capabilities.
GitHub does not offer a separate tag/Release-only GITHUB_TOKEN permission.
Server-side branch restrictions need a separately scoped repository-policy
change: the GitHub Actions App identity is shared by other workflows, so this
configuration does not silently change their access or existing branch rules.

## Publication flow

1. Snapshot the default branch and inspect stable tags plus published Releases.
   Private drafts are not successful-release baselines. Compare exact
   source trees and reject a published source outside the default branch's
   history rather than silently release a rollback.
2. Create a local tag in a read-only build job. `setuptools-scm` derives both
   distribution and runtime versions from that tag. The build pins SCM's
   package-specific version override to the validated plan, avoiding ambiguous
   Git version discovery when failed reservations share a source commit.
   Tags point directly at the
   reviewed source commit; the bot does not write version commits to `main`.
3. Run CPU tests/lint, build the sdist and a wheel from the sdist, check metadata
   with `twine`, and run the complete installed-package checker in a clean wheel
   environment outside the checkout. Check tag/distribution/runtime parity and
   generate `SHA256SUMS`. `MANIFEST.in` limits sdist contents to package sources
   and build metadata; repository evidence/workflows are not release payload.
   Reuse `tools/build_codex_plugin.py` to build the self-contained
   `inferrsi-codex-plugin-vX.Y.Z.zip` installer from the same source revision.
   Its generated plugin metadata, bundled runtime and tag must have the same
   version. Verify every bundled runtime hash and exercise the extracted
   launcher/knowledge reads outside the checkout with isolated Python.
4. A separate write job verifies the artifacts, source ancestry and release
   state again. It creates the remote tag only after validation, creates an
   internal draft, uploads wheel/sdist/plugin ZIP/checksums and automatically publishes
   after confirming the attachments and tag identity. It does not execute
   repository code. These operations stay in the same workflow: tag events
   created with `GITHUB_TOKEN` do not trigger another workflow.

All source-tree changes, including documentation, are eligible. The
[notes configuration](../.github/release.yml) groups existing `enhancement`,
`bug` and `documentation` labels and includes other merged PRs. Notes use the
previous published tag rather than incomplete reserved tags. A release describes
software changes; CPU/package checks do not establish campaign `PASS`, model
quality or service performance. Such claims retain the acceptance and evidence
requirements in [contributing](contributing.md#evidence-and-claims).

Each Release contains a Python wheel, source distribution, the versioned Codex
plugin ZIP and `SHA256SUMS` covering all three packages. Extract the ZIP and
follow the [Codex plugin installation guide](codex-plugin.md#install-from-a-local-archive).
The ZIP contains the native local marketplace, plugin, complete bundled runtime
and knowledge, licenses and installation README. Plugin build failure or a
missing/corrupt installer blocks publication. It does not update a plugin branch,
account installation or marketplace listing.

## Setup and manual checks

Merge the configuration into the default branch. GitHub Actions and the listed
actions must be allowed by organization policy, and the publisher needs
`contents: write`. No extra secret, PAT, GitHub App or repository-wide write
default is needed. The workflow guards the canonical repository and default
branch; copies must deliberately update that repository guard.

Under **Actions → Release bot → Run workflow**, select the default branch and
leave **dry_run** checked. It plans and builds the next release without creating
a remote tag or Release; unchanged trees skip here too. Clearing **dry_run**
runs the same automatic publication immediately. It takes no version/tag input.

```bash
gh workflow run release.yml --repo InferMatrixLab/InferRSI --ref <default-branch> \
  -F dry_run=true
```

Actions artifacts are retained for seven days. Package versions come from Git
tags/build-generated `_version.py`; plain unbuilt source imports report
`0+unknown`. Build from a full checkout or the supplied sdist. Git archives use
the exported `.git_archival.txt`; when multiple tags share a commit, use the
uploaded wheel/sdist or explicitly select the SCM build version. Development
builds without a stable tag may
have a development version and are not stable releases.

## Failure and concurrency behavior

Runs are serialized across schedule and manual dispatch. A failed build creates
no remote tag or Release. A later tag/upload/publication failure can leave an
unused tag or private incomplete draft. The bot never moves tags, overwrites
notes/assets or uses `--clobber`. On a later eligible run it allocates the next
unused patch version, so failures may leave gaps in version numbers. Failed
attempts do not advance the successful-release baseline or suppress retry of
unreleased source. Old drafts remain for an authorized maintainer to inspect.

Tag creation and public publication are separate GitHub operations. Client
checks cannot lock out concurrent owner actions; manage tag protection/immutable
releases separately if needed. Public release corrections use a new version.
No PyPI upload, native installer, automatic merge, hardware experiment or new CI
lane is added. The existing four lanes remain unchanged.

## Sources and verification limits

[JiuwenSwarm v0.2.7](https://github.com/openJiuwen-ai/jiuwenswarm/releases/tag/v0.2.7)
shows bot-authored release notes and downloadable packages. Its publisher is a
[private GitHub App](https://github.com/apps/openjiuwen-release-bot); its pipeline
is not public. InferRSI uses its own built-in-token workflow following GitHub's
[token/trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow),
[generated notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes),
and [publication CLI](https://cli.github.com/manual/gh_release_edit), plus the
[setuptools-scm build/archive contract](https://setuptools-scm.readthedocs.io/latest/usage/).
Remote scheduled execution, repository policy and actual publication remain
unverified until observed in an actual release run.
