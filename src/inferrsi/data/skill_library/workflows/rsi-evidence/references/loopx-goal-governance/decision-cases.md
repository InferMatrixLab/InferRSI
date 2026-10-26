# Decision cases

These are source-supported review cases for the [mechanisms](mechanisms.md).
They are not recorded executions. `not_run` applies to runtime and agent
evaluation. Inputs below describe the relevant facts; they are not complete
LoopX API requests or authorization to run work.

## Goal and next-action cases

| Case | Relevant input or observation | Expected interpretation / next check | Unsupported conclusion |
| --- | --- | --- | --- |
| G1: missing active state | The selected Goal has `state_file_missing`; an old recommendation and unused quota remain visible | Goal health is false. Inspect reconnect/retire guidance; do not manufacture intent, acceptance or stop conditions from the recommendation | Budget availability makes this a runnable Goal |
| G2: display versus authority | Markdown says a Todo is open; the selected provider is unavailable | Retain an authority failure, not a valid empty or Markdown-backed work list. Restore/inspect the owning provider through an authorized recovery | Readable Markdown is sufficient fallback authority |
| G3: valid empty source | Canonical read is loaded and complete, with zero Todos | Empty source is real input. Separately inspect closure/frontier evidence before terminal classification | Empty display or zero count proves terminal completion |
| G4: budget and recovery | No execution lane is open and state is `throttled`; compare with a separately admitted recovery lane | Closed throttled case skips. An explicitly admitted recovery can select `outcome_floor_recovery`; inspect its own boundary | A recovery action permits arbitrary delivery or enforces a supplier cost cap |
| G5: capability and workspace | Capability requests `repair_bridge`, and workspace guard is present; no later inbox/terminal override | Normal/recovery delivery and capability repair are closed; workspace repair is the selected action. `should_run=true` is repair permission at this layer | `should_run=true` permits the original selected Todo |
| G6: inbox exception | Required prompt upgrade plus due reply; compare nonterminal facts with terminal-source inbox facts | Nonterminal upgrade blocks. Terminal-source inbox exception preserves the reply action. Read source conditions rather than applying a universal priority slogan | Inbox always wins, or terminal always closes every possible lane |
| G7: terminal and resume | Complete user/agent Todo sources and validated empty frontier derive terminal-no-follow-up, with no inbox priority | All execution lanes close and recurring automation stops until explicit resume. Missing/incomplete source evidence cannot substitute for this derivation | A resumed receipt grants a fresh future task or makes incomplete sources terminal |

G1 is grounded in `decision_summary.goal_missing_state_blocker` /
`goal_status_health_ok` and `should_run._apply_missing_state_health_guidance`.
G2/G3 use `local_authority.read_canonical_todos_if_promoted`,
`shared_goal_work_source.read_shared_goal_work_source`, and
`test_real_directory_lifecycle_uses_canonical_state_despite_stale_audit`.
G4–G6 use the shared `quota_run_decision.json` fixture and the Python/TypeScript
decision tests. G7 uses the Python terminal projection in
`test_terminal_closure_precedes_automation_upgrade`; the terminal helper's full
implementation is outside this readset. The [ledger](source-ledger.json) and
[decision ownership](mechanisms.md#decision-ownership-and-order) link these
sources.

## Accounting and retirement cases

| Case | Relevant input or observation | Expected interpretation / next check | Unsupported conclusion |
| --- | --- | --- | --- |
| A1: repeated commit | Same effect, full semantic request and Goal instance; a matching committed receipt exists | Validate receipt and artifacts. Return replay without a second index row, or repair missing artifacts under the original receipt | A new timestamp or lost response justifies a new effect ID |
| A2: conflicting request | Reuse an effect ID but change `source`, preview or another digest-covered semantic field | Reject with `effect_id_conflict`. Top-level transport timestamp/CAS changes are different from changes inside the complete preview | Identity equality alone makes a changed request equivalent |
| A3: competing new effect | Two different effects were prepared against the same observed index digest | The later new transaction fails its stale basis. Refresh the decision/basis; do not replace the digest merely to force admission | A new effect ID bypasses stale state |
| A4: partial local publication | Receipt exists; one expected artifact is missing or the final index row is its verified truncated prefix | Repeat the original commit to repair the receipt's artifacts. Conflicting existing bytes or an unrelated malformed row must fail; lookup-only replay does not run this repair | Any malformed index can be rewritten, or replay lookup is a repair command |
| A5: recreated Goal alias | Same Goal ID now refers to a new instance, or an alias-only caller encounters an exact-source row | Preserve and validate the exact `GoalRef`; reject incompatible ownership. Do not consume old-instance accounting as current | Same display ID means same lifetime |
| A6: external effect before receipt | External host/provider work may have completed; no durable local receipt or matching lookup row exists | Record uncertainty. Inspect the operation's independent identity/readback before any authorized retry | Local accounting guarantees external exactly-once, or a miss proves no charge |
| R1: retired event source | A legacy source has nonempty `events.jsonl` or one of the three retired aliases, including malformed bytes | Refuse that source, preserve bytes and expose incomplete coverage. Inspect/export with a compatible release before deliberately changing its active binding | Ignore events, replay them silently, delete them automatically, or fill the gap with rollout history |

A1–A4 use `spend_commit.ts`, `accounting_artifact_transaction.ts`,
`test_quota_spend_commit_runtime.py` and the selected
`quota_spend_commit.test.ts` cases: exact-effect replay, changed-request/CAS
conflicts, partial-artifact repair and conflicting-identity/index rejection.
A5 follows `source_admission.ts` and the exact GoalRef checks in the transaction
and replay owners. A6 is an explicit deduction from the local accounting scope
and the retirement document's separately stated external-effect crash window;
it is not a reproduced failure. R1 uses `legacy_event_source.py` and
`test_retired_todo_event_source.py`.

## Record a decision

For an actual use, retain the applicable source revision, Goal/source identity,
observed input, selected action or refusal, and unresolved evidence. For an
accounting recovery, also retain effect identity, request semantics, index basis
and receipt availability. Separate an inspected source assertion, a locally
observed result and a proposed next action. Keep the original campaign verdict
and authorization unchanged.
