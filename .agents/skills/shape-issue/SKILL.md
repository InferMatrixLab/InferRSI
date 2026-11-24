---
name: shape-issue
description: Turn an InferRSI Issue into an accepted direction and bounded work. Use to discuss a proposal, update an authorized Issue body, or split accepted work into native sub-issues before claiming implementation.
---

# Shape an InferRSI Issue

Read the [collaboration guide](../../../docs/agent-collaboration.md#identity-and-authority),
including [where agents may act](../../../docs/agent-collaboration.md#where-agents-may-act)
and the [working rules](../../../docs/agent-collaboration.md#working-rules).

## Check authority

1. Run the [stop check](../../../docs/agent-collaboration.md#human-stop) on the
   Issue, governing and delegating Issues, and their real ancestors. On a
   stop or an unverifiable chain, report the state to the invoking operator
   and exit with zero GitHub writes.
2. Identify the accountable owner using the guide. If no owner is recorded or
   inferable, stay in discussion and ask a maintainer to record one when you
   have authority to reply. Apply the tracker and RFC boundaries in the guide.
3. Before the direction is accepted, use at most one authorized discussion
   comment for each material update. State the problem, ask the questions that
   change the outcome, and propose the smallest useful delivery with relevant
   options and evidence. Only the accountable owner accepts the direction.
4. After that owner records acceptance, the deciding agent or a delegate named
   on the Issue may shape it within the accepted direction. Link the acceptance
   when recording `status:accepted` under the guide's label rules. Verify the
   author's agreement before changing an existing Issue. Refer changes of
   direction to the accountable owner.

## Preserve and update the body

1. Preserve the exact current body using its edit history or an authorized
   snapshot. Keep the revision and restoration route. Use private storage for a
   snapshot containing material that needs redaction. Leave the body in place if
   you cannot preserve and restore it securely.
2. Keep the problem and intent. State the goal, scope, accountable owner,
   accepted decision link, completion condition and the evidence needed for
   acceptance. Record any real source prerequisite separately from completion.
3. Immediately before rewriting, changing a status label, creating a child, or
   attaching a child, re-read the exact current body, stop chain and recorded
   authority. If the body or authority changed, reconcile with the new version
   before retrying. Run the stop and authority checks again before posting the
   shaping record.

## Split only when needed

Use a single Issue for a single deliverable. Check the native children and
search open and closed Issues for each proposed slice. Reuse an existing
match within its current state and authority. Create a child only for a bounded
slice that can be owned, reviewed and completed on its own. Give it scope,
ownership or delegation, labels backed by the guide, and its own completion
condition expressed as a merged deliverable or a named check.

Attach it as a native sub-issue with exactly one parent. Before attaching,
check the child's stop chain as well as the parent's. Keep the child list and
shared acceptance evidence in the parent. Prevent dependency cycles and use
the [parent rule](../../../docs/agent-collaboration.md#working-rules) for any
real ordering constraints.

Keep the child number as soon as creation returns. If creation has an uncertain
result, locate the existing child before retrying. If attachment fails, check
the child's current parent and complete the same attachment once authorized.
Resolve any conflicting parent before continuing.

## Record the shaping decision

Post one authorized record on the Issue linking the accepted direction, the
previous revision and restoration route, the material changes and reasons, and
each child's owner and completion condition. Report any unresolved attachment
with the known child number.

Hand bounded work to [claim-work](../claim-work/SKILL.md). The deciding agent
retains integration responsibility. Use the guide's
[closure authorization](../../../docs/agent-collaboration.md#closure-authorization)
when assessing the Issue's eventual completion.
