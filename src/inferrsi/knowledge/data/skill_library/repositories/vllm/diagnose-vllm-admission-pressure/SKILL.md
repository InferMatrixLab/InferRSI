---
name: diagnose-vllm-admission-pressure
description: Diagnose vLLM V1 admission stalls and KV-pressure preemption by separating token, input, active-request, cache-allocation, and connector-wait constraints at a pinned scheduler revision.
---

# Diagnose vLLM admission pressure

## Trigger and boundary

Use when queued requests, low scheduled-token counts, or repeated preemption need explanation in vLLM V1. The capability is branch-grounded diagnosis and bounded configuration hypotheses, not a throughput optimizer or transport diagnostic.

Source boundary: vllm-project/vllm at `7f730b4cea9a66520a9200265928ebe016b48a39`, chiefly `vllm/v1/core/sched/scheduler.py::Scheduler`. Read [source-notes.md](references/source-notes.md) for evidence IDs and exact anchors. **F** denotes pinned source facts; **P** denotes this candidate's proposed procedure. All operational steps below are P. No runtime, AREX, or DisCo validation has occurred. Re-establish the branch correspondence for another revision; do not infer compatibility with vllm-ascend or TorchNPU pins.

Status: candidate; empirical validation: **not_run**.

## Related capabilities

For broad engine, configuration, topology or extension guidance, use the
[version and responsibility map](../SKILL.md#choose-the-source-and-responsibility).
That engine graph retains `2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5`
(inspection 2026-10-14); this focused procedure retains
`7f730b4cea9a66520a9200265928ebe016b48a39` (supplier inspection 2026-10-15).
Neither navigation nor shared terminology proves cross-pin compatibility or
concrete worker/connector conformance.

Use [audit-vllm-kv-lifetimes](../audit-vllm-kv-lifetimes/SKILL.md) when the blocking branch involves receive completion or retained blocks. [optimization-search-policy](../../../methods/optimization-search-policy/SKILL.md) governs experiment selection, not scheduler admission. [kv-tier-management](../../lmcache/kv-tier-management/SKILL.md) covers LMCache tier policy at an independent pin; it does not establish this scheduler's behavior.

## Paper-derived scheduling alternatives

[Serving preemption](../../../methods/assess-serving-preemption/SKILL.md) distinguishes iteration
eligibility, service ordering and suspended-KV residency.
[Elastic placement](../../../methods/evaluate-elastic-serving-placement/SKILL.md) distinguishes
replica migration from changing a sequence-parallel group. The
[boundary comparison](references/papers-20261015/knowledge/scheduling-state-boundaries.md)
and [hypothetical pressure case](references/papers-20261015/cases/preemption-under-kv-pressure.md)
retain admission, fairness and state-recovery costs. These paper-era proposals
do not describe implementation at the vLLM pin above. Establish current engine
support and service-class obligations before recommending a policy change.

## Required evidence

Collect the deployed revision, scheduler class, effective scheduler/cache configuration, connector class and role, KV-group layout, scheduling policy, speculative/encoder features, and concurrent-batch mode. Obtain a bounded request/step trace: queue/status, actual scheduled tokens, both remaining budgets, allocation result, preemption victim, pending-transfer/free state, and request timing. Separate unavailable observations from zero values. `Scheduler.make_stats` is gated by `log_stats`; its queue/KV fields are useful context but do not expose every branch reason (F7).

## Decision procedure

1. Establish the effective caps: running slots derive from `max_num_seqs`; admission uses `max_num_active_seqs` or its fallback; scheduling-token and input budgets are separate (F1). Record both, including draft-slot charges. Never treat a nonempty queue as proof of memory exhaustion.
2. Trace the first blocking/skip branch for representative requests. Running requests are considered first. Token availability, context bounds, cadence, encoder constraints, and alignment can prevent work before KV allocation (F2). Distinguish a skipped request from a loop-ending failure.
3. For a long prefill, check whether more than one request is eligible before attributing a cap to `long_prefill_token_threshold`; the singleton case disables it and the adaptive option can raise the cap (F2). Do not copy a default or prescribe a universal threshold.
4. If `allocate_slots` returns `None`, inspect `has_pending_block_frees` and `_request_blocks_can_be_freed` before blaming victim selection. The source can stop allocation without preempting. Otherwise identify the actual priority/FCFS victim and, for an already-scheduled priority victim, restored token/input/encoder accounting (F3, F6).
5. Reconstruct waiting admission separately: preemption earlier in the same step, pause state, KV-holding queue precedence, active-request cap, blocked status, and LoRA limit precede useful work (F4). For external-prefix lookup, distinguish unknown matches, zero matches, and positive asynchronous matches. Async admission reserves blocks while scheduling zero new tokens; its computed-token counter is not evidence of load completion (F5).
6. Classify the observed limiting branch and one competing explanation. Produce one conditional hypothesis: adjust a documented cap only after checking the deployed configuration schema, or investigate connector progress instead. Predict which branch/metric should change and what latency, capacity, or recomputation trade-off could worsen. Do not change settings under this skill.

## Available actions and costs

Read source and existing traces; build a per-step accounting ledger; identify missing instrumentation; propose a focused test or one-variable configuration comparison. Intended benefit: avoid mistaking transfer waits or token limits for device-memory pressure, and avoid wasteful preemption tuning. Costs: trace collection/analysis and later test time; larger concurrency/budgets may retain more device KV, while smaller caps may reduce throughput or increase waiting. Benefits and costs require measurement.

## Counter-signals, verification, and escalation

Counter-signals include unused budgets without allocation failure, disabled stats, pause/cadence/grammar/streaming gates, encoder scarcity, model-specific alignment, and pending deferred frees. High KV usage alone does not establish the cause.

Verification idea, not run: construct small pinned scheduler fixtures for token versus input exhaustion, singleton versus competing long prefills, priority-victim budget restoration, pending-transfer suppression of preemption, and async-load admission/resume. Check accounting and status transitions against source, then use an authorized workload comparison with correctness, queue latency, throughput, and preemption/recomputation measures.

If required state is missing, label the diagnosis unresolved and request the smallest trace. Escalate model-specific allocation arithmetic or concrete connector behavior beyond this read set. Stop before live mutation or performance claims; preserve the candidate/not-run status.
