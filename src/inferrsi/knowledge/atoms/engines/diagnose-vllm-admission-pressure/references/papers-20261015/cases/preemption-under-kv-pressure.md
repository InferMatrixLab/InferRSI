# Candidate case: short-request queueing with a growing suspended-state set

Status: candidate. Empirical validation: not_run. This is **P: a hypothetical decision case**, not a captured incident or executed test.

## Trigger and supplied evidence

A serving owner reports good token execution time but long request-completion tails. The engine already changes batch membership each iteration. Long requests occupy most service; new short jobs wait. Live device KV is high. Someone proposes adopting FastServe and quotes its 31.4× headline.

## Expected reasoning

1. Check whether the measured queueing is caused by service order or inability to allocate state. Orca's iteration eligibility and its FCFS/memory-admission policy are separate mechanisms. Existing continuous batching does not rule out head-of-line waiting.
2. Ask for exact model/revision, admission/recovery semantics, request/context distribution, and phase/cohort metrics. Do not treat end-to-end/output-token latency as TBT. Do not accept the headline as current engine evidence; the v3 baseline is vLLM 0.1.7 with implementation and 175B parallelism differences.
3. Propose a matched-engine service-order candidate only if the data supports it. Budget the KV of running **and suspended** jobs, restore headroom and host capacity. Increasing preemption can increase state occupancy even with PagedAttention.
4. Compare measured swap and recompute costs. At low pressure neither may matter; under bursts, prefetch can be mistimed and reserved slots consume capacity. Include promotion in the next-use estimate.
5. Protect long-request and tenant obligations. A lower average/P95 is insufficient proof of a bound on maximum wait, per-tenant fair share, or token streaming gaps.

## Withhold or escalate

Withhold a preemption change if no safe token boundary, host capacity, recovery semantics or service contract is established. If the actual failure is long-prefill interference, route to the prior chunked-prefill/disaggregation candidate instead. If it is reservation slack, route to the prior KV-efficiency candidate without dropping forward-progress protection.

## Reviewable output and evidence

A good output separates diagnosis, candidate, benefits/costs, affected cohorts and missing evidence; it proposes no unapproved live action. It cites [Orca O1/O3](../notes/orca.md) and [FastServe F1–F3](../notes/fastserve.md), uses the same-engine ablation cautiously, and labels all prospective conclusions P. The smallest next gate is a current-implementation/telemetry review; any later experiment needs its own authorization and resource/abort bounds.
