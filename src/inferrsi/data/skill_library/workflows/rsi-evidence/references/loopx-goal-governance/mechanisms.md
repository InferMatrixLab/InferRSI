# Mechanisms and operating boundaries

All source links below name LoopX commit
`f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9`. **Code** describes inspected control
flow; **test** describes assertions in upstream tests, not a local test result;
**document** describes stated intent; **deduction** is the resulting review
guidance. The [ledger](source-ledger.json) gives the inspected sections.

## Authority and projections

**Code:** `read_canonical_todos_if_promoted` retains a historical name but no
longer permits a Markdown fallback. It requires a loaded native result with a
recognized `source_authority`, `decision_read_from_provider=true`,
`legacy_fallback_used=false` and a consistent Todo read model. A requested
Todo/lease snapshot also requires leases and `provider_revision`. Missing or
failed authority raises its cause; it does not become a valid empty Todo list.
[Python reader](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/coordination/local_authority.py#L245-L333)

The TypeScript list owner loads the selected provider once and builds Todos,
optional leases and acceptance guards from that head. It returns revision and
source-authority facts. `read_shared_goal_work_source` requires a declared state
path and runtime root, but takes its work items from this canonical read and
records its provider basis; it does not read Todo text from the display file.
[List owner](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/coordination/local_authority_read.ts#L292-L354),
[work-source caller](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/goals/shared_goal_work_source.py)

| Layer | Responsibility | Unsafe substitution |
| --- | --- | --- |
| Provider selection and canonical snapshot | Choose and read current Todo authority; carry source, revision and record identity | A readable old Markdown file cannot rescue a lost provider |
| Source registration / exact Goal identity | Bind an observation or accounting request to its source and Goal instance | A registry witness is neither a grant nor a transaction spanning registry and provider |
| Markdown, Todo index and rollout annotations | Present current state and historical context | A historical event status cannot overwrite current Todo status or claim |

**Code:** a missing provider selector does not redirect an existing SQLite
authority to File. The selector opener reports the missing selector. The
registry-source witness checks the recorded bytes and explicitly does not span
provider storage. This readset inspects these seams, not all provider internals.
[Provider selection](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/coordination/local_authority_provider.ts#L218-L252),
[source witness](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/coordination/authority_source.ts)

**Test:** the retirement suite keeps current Todo status and claims when audit
events disagree. Its File/SQLite lifecycle case makes the provider unavailable
while readable stale Markdown remains; reads must fail or expose no authoritative
work, then recover after the provider is restored. This is different from a
successful empty snapshot.
[Authority counterexamples](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/tests/control_plane/test_retired_todo_event_source.py#L32-L48),
[provider-loss case](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/tests/control_plane/test_retired_todo_event_source.py#L229-L326)

## Decision ownership and order

**Code:** Python prepares source facts, Goal-scoped health, replan applicability,
terminal evidence and compatibility text. `resolve_quota_run_decision` sends
typed facts to `effect_runtime_result("quota.run_decision", ...)`. TypeScript's
`resolveQuotaRunDecision` owns the ordered base decision. Python merges only the
returned `quota_patch`, retaining source numbers and unrelated quota metadata.
The managed runtime call crosses to Node/TypeScript; this is not a standalone
pure Python quota kernel.
[Python adapter](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/decision_summary.py#L242-L312),
[typed owner](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/run_decision.ts),
[runtime boundary](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/effect_runtime.py#L1274-L1372)

Read the following sequence with its conditions; it is not a universal ranking
of all work in LoopX.

| Step in the typed owner | Condition and effect |
| --- | --- |
| Delivery guards | A non-running capability gate without monitor fallback closes normal/recovery delivery; `repair_bridge` enables capability repair. A workspace guard clears all lanes then enables workspace repair. A required automation-prompt upgrade clears all execution lanes. |
| Base action | Choose normal delivery, recovery, workspace repair, self-repair or capability repair from the remaining lanes. With none open, map operator/health/throttle/wait states to their skip/notify actions. |
| Replan | Without inbox priority, an applicable required replan needs healthy Goal facts, no workspace guard and no required prompt upgrade. It selects a bounded replan instead of normal/recovery delivery. |
| Terminal | Validated terminal-no-follow-up with no inbox priority clears execution lanes and stops recurring automation until explicit resume. It requires complete source/frontier evidence supplied by the Python side, not merely a zero visible count. |
| Inbox | A nonterminal required prompt upgrade still blocks inbox work. Otherwise a due reply or material review clears other lanes and selects its own bounded action; reply wins when both are due. Terminal-source inbox work retains its explicit exception. |
| Task coordination | A ready coordination contract refines only an admitted `normal_run`. It does not capture an inbox or repair action. A route hint is a separate returned patch, not permission to create work. |

**Code:** `goal_missing_state_blocker` recognizes the selected Goal's
`state_file_missing` finding. `goal_status_health_ok` returns false for it;
unrelated Goal diagnostics are scoped separately. The final should-run facade
can replace an otherwise eligible health skip with `blocked_health` and the
finding's reconnect/retire guidance. Do not create a substitute Goal from a
generic recommendation when its declared active state is gone.
[Health input](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/decision_summary.py#L74-L137),
[missing-state guidance](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/should_run.py#L507-L543)

**Test:** Python and TypeScript consume the same ordered-rule fixture. It covers
throttled/waiting/health states, explicit recovery, capability/workspace guards,
replan and terminal/inbox exceptions. Python also asserts that large integer
quota values and nested metadata survive the adapter. The small
`test_quota_decision_summary.py` tests only plan-item flattening; it does not
prove the complete decision system.
[Shared fixture](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/tests/control_plane_ts/fixtures/quota_run_decision.json),
[Python assertions](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/tests/control_plane/test_quota_run_decision.py),
[TypeScript assertions](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/tests/control_plane_ts/quota_run_decision.test.ts)

**Deduction:** `should_run=true` alone is insufficient. Retain `effective_action`,
normal/recovery/repair lane flags, state and reason. A throttle skip blocks the
closed delivery lane; an explicitly admitted recovery/repair action has its own
semantics. None of these fields enforces a provider-side currency ceiling.

## Accounting identity and recovery

**Code:** Python constructs a complete preview request, validates the Goal/path
boundary and requires an index basis for execution. It preserves the complete
preview across the large-local-snapshot transport. TypeScript owns spend
validation and the durable accounting transaction. It requires an eligible
preview, positive integer slots, and `after.spent_slots = before.spent_slots +
slots`, with a permitted spend disposition. The caller's validated
delivery-completion attribution survives a later repair frontier.
[Python facade](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/spend_commit.py),
[typed validation](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/spend_commit.ts#L258-L420)

| Identity / observation | Inspected behavior |
| --- | --- |
| `effect_id` | Use explicit request identity; otherwise `preview.effect_ref`, settlement effect plus `#quota_spend`, or a deterministic hash of selected semantic fields. It identifies the accounting effect, not a proof that external work ran. |
| `request_digest` | Hash canonical key-sorted semantics: effect, root, Goal, source, complete preview, compact before/after, agent and exact GoalRef when present. Top-level `generated_at`, `execute` and CAS observation are excluded. Fields inside the complete preview still participate. |
| `expected_index_digest` | Compare the current run-index bytes before creating a new transaction. Another new effect from the same stale basis is rejected. A matching existing receipt is resolved before this new-effect CAS. |
| Exact `GoalRef` | Source-owned accounting requires Goal ID plus instance ID and source admission together. Admission checks current ownership under the handed-off local locks. An alias-only replay cannot consume an exact-source record. |

Source identity and digest are defined in
[spend_commit.ts](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/spend_commit.ts#L278-L361).
The [source-admission seam](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/source_admission.ts)
and [Python lock handoff](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/accounting_admission.py)
are local ownership checks. Distributed lease correctness is outside this
readset.

**Code:** preview constructs a record and, when a runtime root is present,
prospective paths and the observed index digest without publishing artifacts.
Execution serializes the local transaction, writes a per-effect `prepared`
receipt, materializes JSON/Markdown/index, then marks the receipt `committed`.
The receipt retains the expected index prefix's digest and byte length.
[Preview/commit owner](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/spend_commit.ts#L787-L931),
[transaction sequence](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/accounting_artifact_transaction.ts#L894-L1044)

Distinguish two operations when recovering:

- **Repeat the same commit:** a matching receipt must have the same effect,
  request digest and Goal instance. Its artifacts are checked and missing
  artifacts may be repaired; the result is `repaired` or `replayed`. Different
  existing bytes are conflicts. A truncated final index row is repaired only
  when it is the expected row prefix after the receipt's verified prior bytes.
- **Replay lookup (`operation="replay"`):** inspect existing spend-index rows,
  resolve effect identity, and check Goal and valid agent identity. It does not
  execute the commit repair sequence. `read_only=true` also avoids the index
  mutation lock; a lookup miss is a miss, not evidence that external work never
  happened.

Relevant rows with conflicting `effect_ref` and commit metadata are rejected in
either direction. Non-quota or unrelated-effect rows are not treated as a
matching spend. An index match without a matching receipt is not silently
adopted as a newly committed transaction.
[Identity/replay lookup](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/accounting_artifact_transaction.ts#L418-L536),
[repair constraints](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/accounting_artifact_transaction.ts#L734-L891),
[Goal/agent replay check](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/spend_commit.ts#L556-L677)

**Test:** upstream cases assert no-write preview, one row for repeated or
concurrent identical commits, conflict on changed request/stale index basis,
artifact repair, and refusal of conflicting identity/index content. These are
local accounting assertions, not tests of an external provider's billing.
[TypeScript accounting cases](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/tests/control_plane_ts/quota_spend_commit.test.ts#L737-L1103),
[Python facade cases](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/tests/control_plane/test_quota_spend_commit_runtime.py#L148-L251)

The settlement event is append-only, while visible `spent_slots` is a rolling
window aggregate. The recorded before/after is a same-status-payload projection.
Later totals can stay flat or decrease when old spends expire; that does not
undo the event or prove a refund.
[Projection semantics](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/quota/spend_commit.ts#L462-L505)

## Retirement and external effects

**Code/document:** a nonempty legacy `events.jsonl` or any bound
`state_event_log`, `state_events_file` or `event_log` is refused on the retired
Todo source route. The guard detects nonempty bytes without treating malformed
content as empty. The prescribed recovery preserves the file and inspects or
exports it with a compatible older release before deliberate removal of its
active binding/file. There is no automatic replay, deletion or Markdown
substitution. Empty/absent files contain no event-owned Todos. Current canonical
reads remain provider-owned and do not import stale audit files.
[Retirement guard](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/loopx/control_plane/goals/legacy_event_source.py),
[retirement document](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/docs/architecture/rfcs/ledger/shared-goal-authority-state-provider-v0/2026-09-25-todo-event-retirement.md)

**Test:** read/write selectors refuse without changing original state/event
bytes; completion requires canonical authority before validation effects. A
retired source makes that Goal unavailable and the Todo index incomplete while
healthy Goals remain visible. Historical rollout records cannot fill the gap.
[Refusal and portfolio cases](https://github.com/loopx-project/loopx/blob/f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9/tests/control_plane/test_retired_todo_event_source.py#L52-L188)

**Document:** the separate experimental supervisor receipt log explicitly leaves
the crash interval between an external host effect and its receipt unresolved.
**Deduction from the inspected accounting code:** quota receipt repair only
reconstructs local accounting artifacts; it does not add fencing to that
external operation. If an external effect happened and the receipt is missing,
an automatic retry can duplicate the effect. Resolve it using that operation's
own identity/readback and authorization contract; do not infer success or safe
re-execution from a local lookup miss.

Local accounting idempotency, correct Goal admission and bounded next-action
selection establish neither external exactly-once execution nor a supplier-side
hard cost cap. The readset does not qualify provider backends, distributed
leases, all controller overlays, runtime integration, performance or agent
benefit. It introduces no executor, database, migration or automatic retry.
