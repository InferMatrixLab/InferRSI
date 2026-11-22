---
name: open-pr
description: Open an InferRSI pull request from current main with local checks run, DCO and agent attribution on commits, and a complete PR body including the knowledge authorship declaration. Use when turning a claimed slice into a PR or updating its head.
---

# Open an InferRSI pull request

Follow [contributing](../../../docs/contributing.md#development), the
[records rules](../../../docs/agent-collaboration.md#records) and the
[knowledge authorship declaration](../../../docs/knowledge-model-policy.md#one-pr-body-declaration).
Claim the work first with the [claim-work skill](../claim-work/SKILL.md).

## Branch and commit

1. Fetch and branch from current `main` in a separate worktree:

   ```bash
   git fetch origin main
   git worktree add -b <branch> ../<dir> origin/main
   ```

2. Keep the PR one coherent delivery slice with a minimal diff.
3. Commit with `git commit -s` under your real identity. Add
   `Agent-assisted-by: <tool> / <model-id> [effort=<level>] (<role>)` for each
   material agent contributor. Keep Issue references out of commit subjects,
   bodies and trailers.

## Run the local checks

Run them on the content you will push and record the actual results:

```bash
ruff check src tests tools
pytest
```

If the skill library changed, also run
`python tools/build_skill_index.py --source-revision <source-commit> --check`.
Check every new or changed artifact against the
[privacy and security rules](../../../docs/privacy-security.md).

## Write the PR body

Start from the [PR template](../../../.github/PULL_REQUEST_TEMPLATE.md):

- The first line of the governing section is `Refs #<issue>`. Never write a
  closing keyword before an Issue reference, even in a negated sentence.
- Fill the `knowledge-model-policy` block with the current full head SHA and
  every material AI author's actual tool, model and effort. Changes to
  [protected paths](../../../docs/knowledge-model-policy.md#rollout-and-scope)
  fail the required check without it; after every push, update `head_sha`.
  #518 stalled because its declaration check stayed red on the final head.
- Report checks actually run, and failed, skipped or not-run ones, separately.
  Report PR readiness and Issue completion separately.
- If a revert cannot undo the change's external effect (credentials,
  published assets, access), add one line
  `recovery: owner=@<account>; containment=<steps>`.
- Do not prefill an independent approval or claim an authorized merge.

Open the PR with `gh pr create --base main` and show it on the Issue as the
claimed artifact. Review goes to an independent reviewer using the
[review-pr skill](../review-pr/SKILL.md).
