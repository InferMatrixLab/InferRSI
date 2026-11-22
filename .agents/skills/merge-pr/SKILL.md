---
name: merge-pr
description: Decide whether an InferRSI pull request may merge now and, if so, squash-merge it. Use before merging and whenever reporting a PR as merge-ready; this is the one merge-ready check, not private criteria.
---

# Merge an InferRSI pull request

Follow [PR review and merge](../../../docs/agent-collaboration.md#pr-review-and-merge)
and the [squash merge rules](../../../docs/agent-collaboration.md#records).
Report a PR as merge-ready only when every check below holds on its current
head; otherwise report the first failing check.

## Read the current state

```bash
gh pr view <pr> --repo InferMatrixLab/InferRSI \
  --json state,isDraft,headRefOid,baseRefName,baseRefOid,body,labels,reviews,reviewDecision,statusCheckRollup,files
```

Also read the governing Issue's labels, accountable owner and recorded
authorization. Note `headRefOid` and `baseRefOid`: the checks below hold for
that pair only.

## Check every condition

1. **Open and ready:** the PR is open and not a draft.
2. **Authorized to integrate:** the governing Issue has an accountable owner
   (recorded on the Issue, or else its assignee) and carries `status:accepted`, and you are its deciding agent, were delegated
   integration on the Issue, or are a human maintainer.
3. **No stop:** neither the PR nor its governing Issue carries `bot:stop`;
   a stop on the Issue also covers its linked PRs. If you
   cannot read the labels, do not merge.
4. **Base and dependencies:** the PR's base is its intended target: `main`,
   or for a stacked PR its lower PR's branch until that PR merges, after which
   the base is changed back to `main` and the checks run again. Every PR it
   depends on has merged; until then, do not merge or queue it.
5. **Two approvals on the current head:** at least two **Approve** reviews
   with `LGTM` alone on the first non-empty line, each from a different
   eligible account with write access, none stale. Each account votes once,
   through its one formal reviewer agent.
6. **Independence:** the author, material contributors and the accountable
   parent supplied none of them, including through another agent under their
   account. At least one comes from a different agent or a human.
7. **No open blocker:** every **Request changes** review is re-reviewed to
   **Approve** or dismissed with a recorded reason.
8. **Required checks green** on the head. Windows/macOS `host-compatibility`
   results are advisory and never block.
9. **Not high-risk:** the diff changes none of CI workflows or required
   checks, releases (release workflow, version, tags, publishing), secrets and
   credentials, or permissions (workflow `permissions`, repository access,
   rulesets). If it changes any of them, or you cannot tell, report "needs a
   human maintainer to merge" and stop: never report it merge-ready, merge it
   or queue it. A human maintainer merges it personally, after two approvals
   with at least one from a human maintainer.

Right before merging, read the PR and the governing Issue again. Recheck the
stop labels; `headRefOid`, `baseRefName` and `baseRefOid` against the pair you
noted; the Issue's `status:accepted` and your authorization; and the approvals
on the current head. If anything changed or no longer holds, start over.

## Merge

Prepare the squash message: subject plus a short summary, no Issue references,
DCO sign-off and material `Agent-assisted-by` attribution kept. Squash-merge
directly; the repository ruleset and merge controls apply unchanged. There is
no merge queue yet; once one is enabled, the rules for queueing are added here.
Record the merge on the PR with an identity line. If `main` turns red afterwards, use the
[red-main skill](../red-main/SKILL.md).
