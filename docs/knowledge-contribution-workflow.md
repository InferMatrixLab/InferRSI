# Knowledge contribution workflow

This tooling proposal implements the bounded contribution-cost scope in
[#355](https://github.com/InferMatrixLab/InferRSI/issues/355). It changes how
projections store provenance, not knowledge quality, acceptance or author policy.

## Author once, derive the rest

| Contributor supplies | Tools derive |
| --- | --- |
| Owner procedure, applicability, limitations, evidence judgments and source readsets | Owner resource hashes and discovery JSON |
| External source revision, inspected scope and attribution | Shared snapshot revision and registry hash, from committed Git bytes |
| Registry mapping for a new/moved owner; relevant matrix rows | Coverage view and navigation |
| Actual human contribution, every material AI author's tool/model/effort/role | Final head SHA and complete changed/protected path lists |
| Whether to request an exception and its reason | Exact exception scope, including generated files, deletions and both rename paths |

Do not copy metadata into discovery JSON or hand-edit generated files. Optional
sidecar fields stay absent when not supplied; the generator does not invent
evidence, license, efficacy, authorship or an exception decision.

1. Edit the canonical owner, supporting resources and only the relevant registry
   or matrix entries. Commit the source changes with accurate DCO/agent trailers.
2. Generate and check the derived files from that source commit:

   ```bash
   source_revision=$(git rev-parse HEAD)
   python tools/build_skill_index.py --source-revision "$source_revision"
   python tools/build_skill_coverage.py
   python tools/build_skill_index.py --source-revision "$source_revision" --check
   python tools/build_skill_coverage.py --check
   ruff check src tests tools
   pytest
   ```

   Inspect and commit the actual generated delta. Follow the ready lane's
   isolated noneditable-wheel check for resource/packaging changes. Tests and
   policy success establish their stated contracts, never skill efficacy.
3. Fetch the current target branch, then obtain the reviewable path report:

   ```bash
   python tools/knowledge_contribution.py --base <fresh-target-tip>
   ```

   Supply an external JSON file containing only explicit `human_only` and
   `material_ai_authors` facts to emit the current policy's single declaration:

   ```bash
   python tools/knowledge_contribution.py --base <fresh-target-tip> \
     --authors-file <outside-worktree-authors.json>
   ```

   Only add `--exception-reason '<explicit reason>'` when requesting an
   exception. The helper does not approve it. Unknown settings remain unknown;
   they do not become admitted settings. A dirty worktree or changed HEAD blocks
   declaration output. Rerun after any commit. Review the output before placing
   it in the PR body with substantive changes, generated changes and test limits.

The helper reads policy from the supplied target commit, not the proposed policy
in the worktree. Its PR-style comparison uses that target's merge base with HEAD.
Generated-path classification is a review aid, not proof that bytes are mechanical
or exempt from [knowledge-model policy](knowledge-model-policy.md).

## Representation and trade-offs

| Option | Benefit | Cost / reason for choice |
| --- | --- | --- |
| One commit and registry hash embedded in every owner JSON (previous) | Direct standalone attribution | A new snapshot rewrites every record; registry changes do too |
| Per-owner last Git commit | Ordinary owner edits can remain local | Squash replaces the source commit, so a later rebuild rewrites a previously merged owner; shallow history and shared registry changes add complexity |
| Reuse prior generated pins for unchanged owners | Smaller deltas | Generation depends on prior artifacts and possibly unavailable historical objects, rather than a declared complete snapshot |
| Shared snapshot with owner-local projections (this proposal) | Deterministic from one explicit source commit; no unrelated owner rewrites | One shared manifest may conflict; raw projection format migrates once and requires a resolver |

`knowledge/_provenance.json` stores the full repository/source commit and the
canonical registry path/SHA-256. Each stored schema-v2 skill record contains only
its owner resource paths/hashes and the fixed `_provenance.json` reference.
The catalog validates this local manifest and expands the record into the same
schema-v1 public shape: complete immutable Git URL/commit, paths and source hashes
including the registry. No arbitrary file path or network resolution occurs.
Legacy schema-v1 records continue to read without a manifest. Unsupported or
malformed manifests/records and missing manifests fail rather than falling back.

This is an explicit storage migration: older code reading raw schema-v2 JSON
cannot consume it as v1. Upgrade the generator and package reader together;
external consumers should use the catalog's resolved API or implement the v2
resolver. One migration regenerates all owner projections. Future owner-only
edits do not. The public schema, IDs, source URLs, resource reads, Collect and
selection logic stay unchanged. Resolved runtime bundle revisions may still
change with the shared source snapshot or whole-library dependency; this proposal
reduces committed-file churn, not runtime snapshot identity changes.

The shared manifest is touched because the complete source snapshot changes.
The generated README changes only when navigation/state rows change. Coverage
changes only when its declared source digest or view changes. Adding a registered
owner changes the registry, new owner JSON, manifest and navigation/coverage,
without rewriting existing owners' JSON.

## Parallel integration and squash provenance

Resolve canonical source conflicts first and preserve both accepted contributions.
Different-owner branches may conflict in the shared manifest or generated views.
Do not hand-merge owner JSON. For a manifest-only conflict, keeping either side's
manifest temporarily is safe only as an intermediate step before regeneration;
it is not a valid final combined snapshot. Resolve source/matrix/registry conflicts
explicitly, commit the combined canonical sources, then run both generators from
that commit and commit their outputs. Same-owner text conflicts remain conflicts.

After an ordinary GitHub squash, a pre-squash snapshot may no longer be an
ancestor or available in a clean clone. Package reads still resolve the recorded
snapshot and verify available source bytes, but the Git-backed planner correctly
reports its historical pin unavailable. This proposal does not make that first
squash ancestor-resolvable or add an automatic post-merge writer.

To restore an ancestor-resolvable snapshot on protected `main`, create a separate
projection-only repair branch from the landed source commit. Generate against
that already-landed commit and submit the small manifest repair through normal
PR review/checks and squash merge. No direct write to `main` is required or
authorized. The repair squash retains its source commit as an ancestor because
the repair does not change canonical sources. If `main` advances with another
knowledge contribution, integrate those accepted sources and regenerate from the
new landed snapshot instead. Unchanged owner JSON stays byte-identical.

This optional recovery PR is an explicit workflow cost when Git-history-based
planning is required after squash; the storage change does not remove it. A
future automated recovery mechanism would need its own reviewed design and
authority. The raw Git planner preserves its ancestor, source-byte and registry
digest checks instead of trusting missing or unrelated cached objects.

`build_skill_index.py --source-revision <commit> --check` requires that commit
locally and compares canonical Git path inventory and bytes before rendering.
It does not trust hashes from existing generated records. The shallow-checkout
test reconstructs projections from current packaged bytes plus the declared
manifest and checks content consistency. It does **not** independently prove that
an unavailable historical commit owned those bytes. Clean-wheel checks verify
every resolved source resource/hash without requiring historical Git objects.

## Reproducible acceptance controls

`tests/test_skill_provenance.py` exercises separate alpha/bravo owner branches,
both squash-integration orders, separate projection-only repair branches/PR
squashes, and a fresh clone. Charlie's JSON remains unchanged, both contributions
survive, and a second generation is identical. A depth-one clone also reproduces
the projection content without claiming unavailable historical proof. A separate
divergent same-owner edit must leave an explicit canonical conflict. These are
synthetic workflow controls, not new knowledge or efficacy evidence.

The suite also checks owner registration, v1/v2 reader compatibility, missing and
malformed manifests, bad source references and hashes, tampered provenance,
body/resource/registry drift and unavailable source commits. Existing binary,
CRLF, replacement-ref, retrieval, Collect and installed-wheel controls remain.
The helper tests renamed/deleted/generated paths, escaping, dirty state, changed
HEAD, explicit author facts and trusted-base policy selection.

Measured before/after counts and exact validation results belong in the PR's
revision-scoped evidence. Do not treat a small fixture's counts as a measurement
of the complete library or declare this Issue accepted from CI alone.
