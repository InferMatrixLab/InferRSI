---
name: claim-work
description: Claim an InferRSI Issue or fix before starting it, state when the next artifact will appear, and release the claim if nothing appears. Use before starting a fix, opening a PR or taking over a delegated slice.
---

# Claim work on an InferRSI Issue

Follow the [identity and authority](../../../docs/agent-collaboration.md#identity-and-authority)
rules and working rules 1, 7 and 8 in
[agent collaboration](../../../docs/agent-collaboration.md#working-rules).

## Check before claiming

1. Confirm the governing Issue and its accepted scope before changing code. If
   the Issue or the PR you would touch carries `bot:stop` or has a human's
   stop comment that has not been lifted there (see the
   [stop rule](../../../docs/agent-collaboration.md#identity-and-authority)),
   do not claim it. If you cannot tell whether a stop is present, do not
   claim it either.
2. Confirm the Issue has an accountable owner (recorded on the Issue, or else
   its assignee) and carries `status:accepted`:

   ```bash
   gh issue view <issue> --repo InferMatrixLab/InferRSI --json assignees,labels
   ```

   With no accountable owner, propose on the Issue and ask a maintainer to assign it;
   at `status:proposed` or `status:deferred`, discuss only. Do not claim
   either.
3. Confirm you are the deciding agent (the formal agent working for the
   accountable owner's account) or that the deciding agent delegated this slice to you
   on the Issue. Otherwise propose on the Issue instead of claiming.
4. Search open Issues and PRs for the same work, for example:

   ```bash
   gh search issues --repo InferMatrixLab/InferRSI --state open "<keywords>"
   gh search prs --repo InferMatrixLab/InferRSI --state open "<keywords>"
   ```

5. Read the governing Issue's recent comments. If someone holds a live claim,
   coordinate on that thread instead of starting a parallel fix.

## Claim on the Issue

Post one comment on the governing Issue, not on a PR or in a private channel:

```text
<agent name>, acting for @<human>: claiming <the slice>.
Next artifact: <draft PR / branch / findings> by <date and time, with time zone>.
```

Keep the claim to the slice you will deliver. A claim records intent; it does
not grant authority beyond the Issue's direction. Each Issue has one deciding
agent, the one acting for its accountable owner; other agents propose there.
Within the Issue's direction, the deciding agent settles scope and records the
reason on the Issue; only a change of direction goes back to the owner.

## Deliver or release

- Show the named artifact on the Issue by the stated time. Post again only for
  a new head, new evidence or a new question; no status-only updates.
- A claim that states no time allows 24 hours.
- If nothing appears by then, the claim lapses. Post one comment releasing it,
  with any partial findings in `<details>`, and leave the work to others.
