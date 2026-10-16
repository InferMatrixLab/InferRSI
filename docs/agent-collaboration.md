# Agent collaboration (issue-led)

Conventions for coordinating humans and agents through Issues and PRs, delivered
per the collaboration RFC
([#21](https://github.com/InferMatrixLab/OmniRSI/issues/21)). They are
documentation only: no new automation, permissions, merge gates or CI lanes.
Campaign acceptance, DCO, CI lanes and evidence rules stay in
[contributing](contributing.md); the agent entry contract stays in
[AGENTS](../AGENTS.md).

## Identity and authority

- Humans and agents may propose Issues. Proposal origin, assignment and labels do not grant authority.
- A GitHub account may represent a human and their authorized agent team. Assignment identifies accountability, not necessarily the executor. Record the acting person/agent and role when relevant; retain unknown identity rather than guessing.
- Work follows accepted scope and explicit or standing delegation. Record or link that authority. Material scope changes and exceptions return to the authorized owner.
- Routine PR review and integration may be delegated without fresh human approval per PR. Existing repository permissions and acceptance policies still apply.
- Completion is accepted by the named person or authorized agent. Acceptance/closure authority must be clear before those actions; it need not block already-authorized implementation.

## Roles

| Role | Responsibility |
| --- | --- |
| Accountable agent (parent) | Own the Issue outcome, plan and remaining criteria; implement or delegate bounded slices and independent review; report completion for acceptance. |
| Implementer | Own a bounded slice; plan, research, coordinate, change, check and report actual results. |
| Reviewer | Independently inspect accepted requirements, actual diff, affected consumers and evidence; return revision-scoped findings and a recommendation. |
| Integrator | Verify authorization, current head/base, dependencies and applicable review/check results; integrate or report a blocker. |

Assign the accountable agent to the Issue, not only its first PR. One Issue may
have several delivery PRs; a delegated subagent stays within its slice and
reports to the parent. The parent sends review tasks with accepted criteria,
exact head/base revisions, diff and check evidence, without prescribing the
verdict. If independent review is unavailable, report that gap rather than
relabel self-review.

Roles are responsibilities, not mandatory separate agents or services. Separate
agents may act under one account; an author's role switch is still self-review.
A substantive reviewer edit makes that reviewer a contributor requiring
appropriate independent review. Review recommendation is not merge permission.

## Interaction patterns

Illustrative responsibilities, not required services or new authority.

### Human–Human: shared decisions only

```mermaid
flowchart LR
    A["Goal owner"] --> I["Issue: goal and constraints"]
    B["Affected owner, if any"] --> I
    I --> D["Record agreement or unresolved dependency"]
    D -->|"When agreed by authorized owners"| S["Accepted scope and delegation"]
```

Shared-owner coordination is conditional; unresolved dependencies do not authorize blocked work.

### Human–Agent: delegate work, accept the goal

```mermaid
flowchart TB
    H["Authorized owner"] -->|"Scope and delegation"| I["Issue: goal and criteria"]
    I --> A["Accountable agent / parent"]
    A -->|"Implement or delegate"| W["Bounded PR slice"]
    A -->|"Delegate review with criteria and revisions"| R["Independent reviewer"]
    W -->|"Diff and evidence"| R
    R -->|"Findings and recommendation"| A
    A -->|"Resolve findings; refresh affected evidence"| W
    A --> G["Integrator checks authority and evidence"]
    G -->|"Conditions satisfied"| P["Merged PR"]
    P --> S["Parent assesses whole Issue and remaining gaps"]
    S --> O["Acceptance owner or authorized delegate"]
    O -->|"Goal accepted; closure authorized"| C["Close Issue"]
```

Review reports remain attributable and available to the integrator; the parent cannot substitute its own approval for independent findings. No human-per-PR gate. Blocked integration or incomplete goals remain open; material scope exceptions return to the authorized owner.

### Agent–Agent: isolated work and conditional handoff

```mermaid
sequenceDiagram
    participant A as Agent A
    participant B as Agent B
    participant E as Issue / PR / evidence
    opt Authorized parallel work
        A->>B: Coordinate slices and shared interfaces
        Note over A,B: Separate worktrees/indexes and private scratch
    end
    A->>E: Artifacts and checked-content results
    opt Actual handoff or accepted decision change
        A->>B: Acceptance link, delta, artifacts, next action
        A->>E: Recipient and communication status
        B->>E: Applied with evidence, pending or unknown
    end
```

## Working rules

1. **Scope:** identify requirements, exclusions, owner and relevant dependencies. The accountable agent tracks Issue-level criteria and delegates bounded work; PR readiness and Issue completion are reported separately. Keep each PR a coherent delivery slice; small follow-ups may reuse an Issue.
2. **Isolation:** concurrent writers use separate working directories/indexes and private scratch files. Branch names alone are insufficient. Inspect staged/committed content and coordinate shared IDs, schemas and interfaces.
3. **Evidence:** link checks to actual checked content and relevant environment/test definitions. Distinguish passed, failed, cancelled, skipped, timed-out and not-run. H/B/T—reviewed head, assessed base, tested content—may come from existing records, not mandatory worksheets.
4. **Refresh:** reassess affected evidence after relevant head/base/content/environment/check changes. Refresh checks or explain continued applicability. Neither blanket reuse nor full hardware reruns is the default; changed hashes alone prove neither content change nor equivalence.
5. **Handoff:** only for an actual transfer or accepted decision change, record the delta, recipient and next action. Keep acceptance status/link, communication status and application status separate. "Applied" needs artifact/evidence; otherwise retain pending or unknown. No full conversation traces or new ledger.
6. **Completion:** merged PR ≠ accepted goal ≠ campaign `PASS` ≠ release. Use non-closing `Refs #N` until closure is authorized. Subtasks cannot implicitly close a parent goal. Knowledge proposals to [#17](https://github.com/InferMatrixLab/OmniRSI/issues/17) are optional; no automatic promotion.

## Records

- **Issue:** goal/criteria; scope; accountable account and parent agent if assigned; acting contributor if known; acceptance/delegation link; completion/closure owner. Unknown fields may remain TBD while proposed. Ordinary work starts from the [scoped-task template](../.github/ISSUE_TEMPLATE/scoped-task.md); baseline-vs-candidate campaigns use the [campaign acceptance form](../.github/ISSUE_TEMPLATE/campaign-acceptance.yml).
- **PR:** governing Issue; delivered artifacts; checks/results/limitations; dependencies and gaps. Add requirement-to-artifact mapping only when useful, and handoff fields only when applicable. No author-prefilled independent approval. Start from the [PR template](../.github/PULL_REQUEST_TEMPLATE.md).
- **Commit:** short descriptive subject; why/what when useful. Keep governing Issue references out of commit subjects, bodies and trailers — the PR body carries them. Preserve author identity and the required DCO sign-off (`git commit -s`); never invent a signing identity. Agent-assisted commits identify material agent contributors with `Agent-assisted-by: <actual agent name> (<role>)` trailers; repeat for multiple contributors and retain attribution when squashing. A known model/version is optional. The trailer is self-reported provenance, not cryptographic signing, independent review or approval; review attribution belongs on the revision-scoped review record.
- **Squash merge:** the required integration method. Before an authorized merge, prepare a concise squash message: subject plus a short summary, no governing Issue references, no redundant intermediate-commit messages; preserve the required DCO sign-off and material `Agent-assisted-by` attribution. Never invent identities or sign-offs.

Labels document coordination intent; they do not grant it. Reuse existing labels
where adequate: type (`bug`, `enhancement`, `documentation`, optionally `rfc`),
decision (`proposed`, `accepted`, `deferred`, at most one), coordination
(`blocked`, with a blocker link). Do not duplicate native open/closed or
review/check states with labels. Decision labels are synchronized with recorded
decisions by an authorized owner or delegate; setting labels up is a separate
decision, not part of these conventions.

## Evidence refresh — hypothetical example

**Hypothetical illustration only; it records no actual PR, run or result in this
repository.**

Suppose a PR changing `src/omnirsi/harness/runner.py` was reviewed at head `H1`
against base `B1`, then is rebased onto `B2` (new head `H2`) because `B2` touched
the same file. Rule 4 asks what changed, not for a blanket rerun, and a
file-only comparison is insufficient on its own:

- Assess affected content, dependencies, environment and check definitions together: the `H1..H2` delta of the affected files, whether `B1..B2` changed anything the checks depend on (imports, fixtures, CI workflow steps, tool versions), and whether the earlier check definitions still test the same contract.
- If that assessment supports reuse, the earlier review and CI **may** remain applicable — say so with an explicit reason, and name in the PR exactly which earlier evidence is reused and why.
- If it does not, refresh the affected checks on `H2` — for example `ruff check src tests` plus the relevant `pytest` selection — and report which content each result ran on.
- Either way, distinguish passed, skipped and not-run checks instead of implying a full rerun. A changed hash alone proves neither content change nor equivalence.

## Historical evidence and limits

These conventions are OmniRSI proposals informed by the reviewed C1–C7 case pack.
The two pinned snapshots — the
[Magpie repository](https://github.com/yetone/magpie/tree/778000326adaa49cd790846acd2d535572ad5ceb)
and the separate
[release-workflow repository](https://github.com/yetone/magpie-releases/tree/fc85a074b1ba73417d2afda783e1c0a27ed79a1f)
— identify lineage; they are not themselves a link to the case pack. An
accessible case summary with concrete source pointers and stated limits — the
"Reviewed case pointers" section of
[RFC #21](https://github.com/InferMatrixLab/OmniRSI/issues/21) — covers C1–C7
at the level this guide relies on; the full reviewed pack remains with its
owner and is not imported here. C1–C3 inform ownership and review; C4–C5, CI trade-offs; C6,
completion states; C7, learning.

They are proposals, not demonstrated Magpie enforcement or a causal speedup.
Described practice, inspected implementation, observed records and proposed
adaptations remain distinct evidence classes; see #21 for the per-case limits,
including the unresolved C1 root cause and the unestablished final
tested/merged equivalence.
