---
name: audit-vllm-kv-lifetimes
description: Audit vLLM V1 asynchronous KV load/save completion, block retention, preemption, and receive-failure contracts when requests stall or blocks may be reused too early; requires a concrete connector trace.
---

# Audit vLLM KV lifetimes

## Trigger and boundary

Use for a request stuck in remote-KV waiting, suspected premature block reuse, or completion/failure inconsistency at the scheduler–connector boundary. Diagnose lifecycle ownership before attributing the symptom to a transport.

Pin: vllm-project/vllm `7f730b4cea9a66520a9200265928ebe016b48a39`. Evidence is limited to `vllm/distributed/kv_transfer/kv_connector/v1/base.py::{KVConnectorBase_V1,KVConnectorTransferResults,SupportsHMA}` and `vllm/v1/core/sched/scheduler.py::Scheduler`. Read [source-notes.md](references/source-notes.md). **F** means a pinned implementation fact or identified interface contract; **P** means a proposed procedure. The steps below are P; contracts are not proof a concrete connector obeys them. Empirical validation, including AREX/DisCo execution, is **not_run**. Cross-pin vllm-ascend/TorchNPU compatibility is unknown.

Status: candidate; empirical validation: **not_run**.

## Related capabilities

Use [diagnose-vllm-admission-pressure](../diagnose-vllm-admission-pressure/SKILL.md) for budget and admission branches. [kv-tier-management](../../lmcache/kv-tier-management/SKILL.md) addresses LMCache tier policy at a different pin; this skill addresses engine/connector ownership, not that backend's conformance or physical storage.

## Paper-derived state-placement decisions

[Elastic serving placement](../../../methods/evaluate-elastic-serving-placement/SKILL.md)
adds a separate decision about migrating request ownership or changing sequence
groups. It requires source/destination reservations, catch-up progress, commit/
abort ownership and class-specific SLO costs. The
[hypothetical migration case](../diagnose-vllm-admission-pressure/references/papers-20261015/cases/migration-is-not-free-memory.md)
is a decision example, not a reproduced bug. Neither the paper nor this connector
contract establishes current backend conformance, fault tolerance or free memory.

## Required evidence

Obtain exact engine/connector revisions and class, producer/consumer roles, KV-group count and block namespace, load-failure policy, concurrent-batch mode, graph mode, and the actual worker/model-runner call trace. For a bounded set of request IDs, correlate scheduler metadata, allocated block IDs, matched-token count, load/save start and completion, failed receives/invalid blocks, preemption, finished-request notification, and pool return. Record missing evidence rather than assuming an event occurred.

## Decision procedure

1. Reconstruct lookup → allocation → metadata → worker execution → completion → scheduler update. Match queries may repeat; `None` means undecided, zero cannot be asynchronous, and allocation callbacks may repeat for an async request. A nonempty block list does not authorize a load when `num_external_tokens == 0` (F1).
2. For a waiting receive, distinguish reserved/computed-token accounting from usable KV. The scheduler schedules zero new tokens during async admission and waits for `finished_recving` before promotion. Determine whether no completion was produced, it was not propagated, or promotion was blocked elsewhere (F2). Do not manually force the request to RUNNING.
3. Audit concrete worker ordering against F3: metadata binding, preemption handling before overwrite, required load readiness, save submission/synchronization, and cleanup. `wait_for_save` is contractually called even on empty steps with metadata still bound; async saves must retain their source blocks. Verify the real caller before declaring a violation. If layerwise asynchronous hooks are used, inspect the concrete graph-mode requirement (F7).
4. On request finish, identify which owner retains blocks. Connector delayed-free ownership ends at the reported send/save completion; scheduler in-flight-write fencing is a separate condition. Trace both instead of treating a finished response as proof that blocks are reusable (F4). For reliable delivery, check `requires_kv_delivery` and stale-output handling after preemption (F5).
5. For failures, verify failed async receives also reach `finished_recving`; otherwise the wait cannot be released. A block-level error must arrive no later than receive completion. At this pin, flat `invalid_block_ids` is rejected for multiple KV groups; investigate request-level `failed_recving` instead. Follow the existing recompute/fail policy, including valid-prefix handling, without silently changing it (F6).
6. Report the earliest evidenced broken obligation, its owner, affected requests/blocks, and the smallest missing observation. Label an untraced edge as unresolved. Keep transport, cache-tier, bandwidth, and host-copy conclusions outside this capability.

## Available actions, benefit, and resource cost

Read source/traces; produce an ownership/event ledger and a contract-conformance report; propose a targeted regression test or configuration review. No live state changes, reset, repair, transport selection, or policy mutation is implied. Intended benefit: distinguish delayed-but-safe retention from stuck completion or unsafe reuse. Costs: request-level tracing and focused test work; correct retention can temporarily reduce available device KV, synchronization can reduce overlap, and recovery can add recomputation. None is measured here.

## Counter-signals, verification, and escalation

Safe counter-signals include pending sends retaining blocks, unprocessed fence steps, undecided prefix lookup, and completed receives still waiting for ordinary admission. A best-effort cache miss differs from a required producer handoff; external-hit metadata proves no physical tier.

Verification idea, not run: focused tests using the real pinned scheduler and selected connector for delayed receive, repeated allocation callbacks with zero external tokens, failed-and-finished receive, multi-group request-level failure, finish-before-send-completion, and preempted in-flight output. Then inspect a concrete worker test for empty-step save/metadata ordering and graph replay. Preserve output correctness and block-lifetime checks before measuring performance.

Escalate absent concrete connector/caller evidence, ambiguous block namespaces, unsupported layouts, or revision drift. Stop before inferring a backend fix, freeing retained blocks, or claiming a reproduced bug. Candidate status remains until separately authorized validation.
