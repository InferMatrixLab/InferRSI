# InferRSI collaboration skills

## Choose a skill

Use one skill for the step you are carrying out.

- [shape-issue](shape-issue/SKILL.md) — discuss an Issue's direction, record an accepted scope, or split accepted work into native sub-issues.
- [claim-work](claim-work/SKILL.md) — verify acceptance, ownership and existing claims before starting or taking over a slice.
- [open-pr](open-pr/SKILL.md) — open a PR for a claimed slice or update its head.
- [review-pr](review-pr/SKILL.md) — independently review a specific PR revision.
- [merge-pr](merge-pr/SKILL.md) — check merge readiness and integrate when authorized.
- [red-main](red-main/SKILL.md) — recover when a merge breaks `main`.
- [submit-optimization-record](submit-optimization-record/SKILL.md) — submit a redacted trace for a selected optimization run after it ends.

To accept a delivered Issue or close it, see the
[closure rules](../../docs/agent-collaboration.md#closure-authorization).
For inference work, use the
[primary inference skills](../../plugins/inferrsi/skills/inferrsi/SKILL.md#load-the-primary-inference-task).
For post-run trace feedback, use the plugin's
[`inferrsi-feedback`](../../plugins/inferrsi/skills/inferrsi-feedback/SKILL.md) skill.

## Use a skill

Ask the agent to use the skill by name from the InferRSI checkout. For example,
`Use merge-pr to check whether this PR is ready to merge.` If the agent needs
a file path, ask it to read the linked `SKILL.md` directly.

Follow that skill and read the relevant sections it links in the
[collaboration guide](../../docs/agent-collaboration.md).
