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
   (recorded on the Issue, or else its only assignee when exactly one is set) and carries `status:accepted`, and you are its deciding agent, were delegated
   integration on the Issue, or you act for a maintainer account.
3. **No stop:** neither the PR nor its governing Issue carries `bot:stop`
   or has a human's stop comment that has not been lifted there (see the
   [stop rule](../../../docs/agent-collaboration.md#identity-and-authority));
   a stop comment holds even after the label exists. A stop on the Issue also
   covers its linked PRs. If you cannot tell whether a stop is present, do not
   merge.
4. **Base and dependencies:** the PR's base is its intended target: `main`,
   or for a stacked PR its lower PR's branch until that PR merges, after which
   the base is changed back to `main` and the checks run again. Every PR it
   depends on has merged; until then, do not merge or queue it.
5. **Two approvals on the current head:** at least two **Approve** reviews
   with `LGTM` alone on the first non-empty line, each from a different
   eligible account (repository write access or higher), none stale.
   Each account counts once, whether its human votes directly or its one
   formal reviewer agent does.
6. **Independence:** the author, material contributors and the accountable
   parent supplied none of them, including through another agent under their
   account. At least one comes from a different agent or a human. The
   author's own approval never counts, nor does one from an account without
   write access.
7. **No open blocker:** every binding **Request changes** review (from an
   account with write access or higher) is re-reviewed to **Approve** or
   dismissed with a recorded reason, by those the
   [guide](../../../docs/agent-collaboration.md) allows to dismiss it. An
   advisory review, such as one from `cursor[bot]`, does not count as a vote
   but has a substantive answer on the PR and a recorded disposition (fixed in
   a named commit, or declined with the reason). If GitHub's merge state still
   shows the PR blocked by it on the current head, someone the guide allows to
   dismiss reviews dismisses it, and the PR records who did and why, before
   you merge. An unresolved code or safety
   blocker still stops the merge, whoever raised it.
8. **Required checks green** on the head. Windows/macOS `host-compatibility`
   results are advisory and never block.
9. **High-risk:** if the diff changes CI workflows or required checks,
   releases (release workflow, version, tags, publishing), secrets and
   credentials, or permissions (workflow `permissions`, repository access,
   rulesets, the high-risk approver list), or you cannot tell, at least one of
   the approvals in 5 comes from an account listed in
   `.github/high-risk-approvers.json`; that account's agent may give it. Other
   approvals count toward the two but not as this one. Read the list from the
   protected `main` commit you noted as `baseRefOid` (the base is `main` by
   check 4), never from the PR head or a stacked branch, so a PR that changes
   the list is judged by the list before it
   (`gh api "repos/InferMatrixLab/InferRSI/contents/.github/high-risk-approvers.json?ref=<baseRefOid>" --jq .content | base64 -d`).
   Confirm the approving login is on it, and confirm the account still has
   write access:
   `gh api repos/InferMatrixLab/InferRSI/collaborators/<login>/permission --jq .permission`
   must print `admin` or `write`. If you cannot read the list or the
   permission, or no approving account passes both, do not merge. The PR that
   creates the list is approved once as the
   [high-risk rule](../../../docs/agent-collaboration.md#identity-and-authority)
   says.
   Otherwise follow the normal flow.
10. **Recovery for external effects:** if the merge itself causes an external
   effect that a revert cannot undo (publishing a release asset or package,
   changing access or credentials), the PR body has a
   `recovery: owner=@<account>; containment=<steps>` line naming the recovery
   owner and the containment steps. If it is missing, do not merge and ask the
   author to add it. This adds no approval requirement.

Right before merging, read the PR and the governing Issue again. Recheck the
stop labels and stop comments; `headRefOid`, `baseRefName` and `baseRefOid` against the pair you
noted; the Issue's `status:accepted` and your authorization; and, on the
current head, the approvals, any open binding **Request changes** review, any advisory
request without a recorded disposition, GitHub's merge state, and any
unresolved code or safety blocker from check 7, and, on a
high-risk PR, the listed approver and its write access from check 9, against
the list at the same `baseRefOid`; and the PR body's `recovery:` line from
check 10, since the body can change without a new head. If anything changed or
no longer holds, start over.

## Merge

Prepare the squash message: subject plus a short summary, no Issue references,
DCO sign-off and material `Agent-assisted-by` attribution kept. Squash-merge
only the head you checked, so GitHub refuses the merge if the head has moved:

```bash
gh pr merge <pr> --repo InferMatrixLab/InferRSI --squash \
  --match-head-commit <headRefOid> --subject "<subject>" --body "<summary>"
```

With the REST merge endpoint, pass the same head as `sha`. If the merge is
refused because the head changed, start over from the checks above; never retry
without the expected head. The repository ruleset and merge controls apply
unchanged. There is
no merge queue yet; once one is enabled, the rules for queueing are added here.
Record the merge on the PR yourself, right after merging, with an identity
line; for a high-risk PR the same comment then has one line
`merge-audit: head=<sha> approvals=@<account> <review URL>, @<account> <review URL> approver=@<login> list=<sha> merge=<sha> by=@<account>`,
where `approver=` names the approving account you found on the list and
verified in check 9, and `list=` is the `baseRefOid` you read the list from
(`list=bootstrap-570` only for the one-time bootstrap merge in the
[high-risk rule](../../../docs/agent-collaboration.md#identity-and-authority)).
If `main` turns red afterwards, use the
[red-main skill](../red-main/SKILL.md).
