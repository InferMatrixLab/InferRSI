---
name: red-main
description: Restore a red InferRSI main by finding the merge that broke it, reverting that merge first and fixing forward in a new PR. Use when a required check fails on main after a merge.
---

# Restore a red main

Follow the revert-first rule at the end of
[PR review and merge](../../../docs/agent-collaboration.md#pr-review-and-merge):
revert the merge that broke `main` before fixing forward.

## Find the breaking merge

1. List recent `main` runs and find the last green and first red run of the
   failing workflow:

   ```bash
   gh run list --repo InferMatrixLab/InferRSI --branch main --workflow <workflow> --limit 20
   ```

2. List the merges between those two commits with
   `git log --first-parent <last-green>..<first-red>`. Read the failing job
   log and match the failure to the change that caused it. Two PRs that each
   passed can fail together; the breaking merge is the one after which `main`
   first failed.
3. Search open Issues and PRs for an existing revert or fix, and claim the
   revert with the [claim-work skill](../claim-work/SKILL.md).

## Revert first

Branch from current `main` and revert the breaking merge:

```bash
git revert --signoff --no-edit <merge-sha>
```

Open the revert PR with the [open-pr skill](../open-pr/SKILL.md), naming the
breaking merge and the failing run. It merges through the
[merge-pr skill](../merge-pr/SKILL.md) like any other PR. Post one comment on
the original PR linking the revert.

## Fix forward

After `main` is green again, the original change returns in a new PR that
contains the fix, reviewed and merged under the same rules.
