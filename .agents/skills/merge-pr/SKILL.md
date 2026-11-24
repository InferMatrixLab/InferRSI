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
  --json state,isDraft,autoMergeRequest,headRefOid,baseRefName,baseRefOid,body,labels,reviews,reviewDecision,mergeStateStatus,statusCheckRollup,files
```

Also read the governing Issue's labels, accountable owner and recorded
authorization. Note `headRefOid`, `baseRefName` and `baseRefOid` for the checks
below.

## Check every condition

1. **Open and ready:** the PR is open and not a draft.
2. **Authorized to integrate:** the governing Issue has an accountable owner
   (recorded on the Issue, or else its only assignee when exactly one is set) and carries `status:accepted`, and you are its deciding agent, were delegated
   integration on the Issue, or you act for a maintainer account.
3. **No stop and auto-merge off.** If `autoMergeRequest` is set, the authorized
   integrator, or a maintainer if the integrator cannot act, cancels it with
   `gh pr merge <pr> --repo InferMatrixLab/InferRSI --disable-auto` and
   re-reads the PR to confirm `autoMergeRequest` is `null`, even when a stop
   is active. On an Issue-level stop, apply this to every affected PR. If the
   cancellation cannot be confirmed, hold the work and report that the PR may
   still merge automatically. If the PR already merged, report it to the Issue
   owner for authorized recovery.
   Run the guide's [stop check](../../../docs/agent-collaboration.md#identity-and-authority)
   on the whole stop chain. A stop comment holds even after the label exists.
   If the check finds a stop or cannot rule one out, do not merge. Record on
   the PR any Issue you could not check.
4. **Base and dependencies:** the PR's base is its intended target: `main`,
   or for a stacked PR its lower PR's branch until that PR merges, after which
   the base is changed back to `main` and the checks run again. Every PR it
   depends on has merged; until then, do not merge or queue it.
5. **Two approvals on the current head:** at least two formal **Approve**
   reviews, each from a different eligible account (repository write access
   or higher), none stale. The review body's wording does not count;
   comments and **Comment** reviews contribute no approval.
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
   the approvals in check 5 must come from an account on the applicable list.
   That account's agent may give it. Record the current protected `main` tip as
   `<mainSha>` using
   `gh api repos/InferMatrixLab/InferRSI/git/ref/heads/main --jq .object.sha`.
   The PR's `baseRefOid` can lag behind the live ref. For the one-time bootstrap
   PR, confirm the list is absent at `<mainSha>` and use the original approvers in the
   [bootstrap decision](https://github.com/InferMatrixLab/InferRSI/issues/570#issuecomment-7078872219).
   For every later high-risk PR, including changes to the list, read the list
   at `<mainSha>`
   (`gh api "repos/InferMatrixLab/InferRSI/contents/.github/high-risk-approvers.json?ref=<mainSha>" --jq .content | base64 -d`).
   In both cases, confirm an approving login is in the applicable list and
   that the permission check prints `admin` or `write` for that account
   (`gh api repos/InferMatrixLab/InferRSI/collaborators/<login>/permission --jq .permission`).
   Hold the merge if either check cannot be verified.
   On later high-risk PRs, verify a merge path that rejects a change to the
   checked base, or verify exclusive serialization covering every high-risk
   merge and every way to update the list. If neither is available, hold the
   merge.
10. **Recovery for external effects:** if the merge itself causes an external
   effect that a revert cannot undo (publishing a release asset or package,
   changing access or credentials), the PR body has a
   `recovery: owner=@<account>; containment=<steps>` line naming the recovery
   owner and the containment steps. If it is missing, do not merge and ask the
   author to add it. This adds no approval requirement.

For a serialized high-risk merge, acquire the exclusive slot before the final
checks and keep it until GitHub confirms or definitively rejects the merge. If
the result is unknown, confirm the PR's state before releasing the slot.

Right before merging, read the PR and the governing Issue again. Repeat check 3
on the whole stop chain and confirm `autoMergeRequest` is `null`. Confirm
`headRefOid`, `baseRefName`, `baseRefOid`, `status:accepted` and your authorization.
Recheck the current head's approvals, any open binding **Request changes**,
any advisory request without a recorded disposition, GitHub's merge state and
any unresolved code or safety blocker. Recheck any required `recovery:` line.
For a high-risk PR, confirm the live protected `main` tip still equals
`<mainSha>` and repeat the listed approval and permission checks. For the
one-time bootstrap, reconfirm the absence of the file and the approval from
the recorded bootstrap list. If anything changed or no longer holds, start over.

## Merge

Prepare the squash message: subject plus a short summary, no Issue references,
DCO sign-off and material `Agent-assisted-by` attribution kept. Squash-merge
only the head you checked. Use the direct command below for ordinary PRs, the
one-time bootstrap, or while holding the verified serialization slot. With a
base-enforcing path, require both the checked head and `<mainSha>` at merge time.

```bash
gh pr merge <pr> --repo InferMatrixLab/InferRSI --squash \
  --match-head-commit <headRefOid> --subject "<subject>" --body "<summary>"
```

The CLI flag and the REST merge endpoint's `sha` parameter bind only the PR
head. If the checked revision has changed, start over from the checks above.
Keep native auto-merge off and use a synchronous merge. The repository ruleset
and merge controls apply. Add queueing instructions once the queue is enabled.
Record the merge on the PR yourself, right after merging, with an identity
line; for a high-risk PR the same comment then has one line
`merge-audit: head=<sha> approvals=@<account> <review URL>, @<account> <review URL> approver=@<login> list=<sha> merge=<sha> by=@<account>`,
where `approver=` names the approving account you found on the list and
verified in check 9, and `list=` is the `<mainSha>` you read the list from
(`list=bootstrap-570` only for the one-time bootstrap merge in the
[high-risk rule](../../../docs/agent-collaboration.md#identity-and-authority)).
If `main` turns red afterwards, use the
[red-main skill](../red-main/SKILL.md).
