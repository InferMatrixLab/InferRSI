---
name: evaluate-elastic-serving-placement
description: Compare migrating an LLM request between model replicas with changing its sequence-parallel execution group, including state-copy, reservation, recomputation, interruption, and priority costs. Use for cross-instance memory imbalance or highly variable long-context serving, not connector wiring or live scaling.
---

# Evaluate elastic serving placement

All instructions are **P: proposed decision support**, not empirically validated deployment rules. Read the relevant Llumnix or LoongServe branch and its exact readset in the self-contained [source notes](references/source-notes.md). Produce an evidence-based recommendation and a future verification plan only. Do not move state, alter admission/priority, scale replicas, change parallelism, run experiments, or edit frameworks without separate authorization.

## Choose the actual decision

- **Relocate a request between compatible model replicas:** Llumnix changes which instance owns running state; it retains the existing model partitioning. Consider it for imbalanced memory pressure, blocked head-of-line prompts, priority isolation, or drain/fill transitions.
- **Change the request's sequence-parallel group:** LoongServe changes which workers share a long context and how they perform prefill/decode. Consider it when workload/phase-dependent computation and KV distribution make a fixed group inefficient.
- **Reuse an existing prefix or separate phase pools:** The earlier `evaluate-kv-cache-transfer-gates` and `choose-prefill-decode-schedule` candidates optionally cover those questions; they are not dependencies of this skill. If unavailable, identify the different decision and missing evidence rather than forcing it through the migration/ESP procedure. Prefix reuse, replica migration and ESP are different state-placement decisions; none proves the others beneficial.

Do not treat model-weight repartitioning, pipeline configuration, instance migration, and sequence sharding as interchangeable uses of “parallelism.” No paper establishes compatibility with a present framework revision or NPU.

## Common evidence gates

Record exact model/cache identity and format; weight residency; request phase, context and generated length; source/destination KV bytes; physical free/reserved memory; virtual accounting; batch state; current parallel group; queue/service times; and the actual topology/transport. Require the target SLO statistic and affected priority/tenant cohorts.

Name each path independently: device-local storage/access, intra-node GPU link, H2D/D2H, same-host IPC, and inter-node transport. Only the last is Network. A source-to-destination transfer can include multiple paths; neither copy duration nor final interruption is a substitute for total bytes/resource cost.

## Replica-migration branch

1. Demonstrate useful destination slack. Aggregate free bytes do not imply that a single blocked request can fit; internal KV-block slack and cross-instance fragmentation are different.
2. Require an already-resident compatible model and an allocation/commit/abort protocol. During pre-copy, source and destination may both hold state. Reserve destination physical blocks as well as accounting for virtual scheduling headroom.
3. Estimate whether pre-copy can catch up: use effective copy progress versus newly appended KV, concurrency and congestion. Compare total migration cost and final pause with queueing/recompute avoided. Do not substitute Llumnix's 20–30-ms measured downtime for all transfer time.
4. Preserve progress if allocation fails or the request completes/is preempted mid-copy. Do not infer tested fault tolerance from the separately described release; the evaluated v1 artifact has an explicit limitation.
5. For priority headroom, state which normal requests may be moved/delayed and set class-specific acceptable regressions. Virtual headroom is an accounting technique, not extra memory or a tenant-fairness guarantee.
6. For draining/filling, account for migration traffic, active replica-time and receiving capacity. Scaling is a proposed operational action, not part of this read-only procedure. Average active instances do not automatically equal billed cost.

## Elastic-sequence-parallel branch

1. Check that the engine can actually distribute attention/KV across the proposed workers and preserve sequence identity when the group changes. ESP is an architectural capability; a static TP/PP knob is not a substitute.
2. Separate prefill expansion, prefill-to-decode contraction, decode scale-up and decode scale-down. List which KV is retained, copied, left in place or newly appended for each transition. A “zero-overhead” transition label does not mean every group change is free.
3. Evaluate the profiled batch/group candidates against computation, communication, HBM capacity, extra weight replicas and interfering requests. Preserve length-sensitive attention work; a token sum alone can hide long-context cost.
4. Charge ongoing distributed-attention communication even when existing KV does not migrate. Charge explicit KV transfer when contraction requires it. Measure any uncovered pause and displaced useful work, including effects on requests that do not change groups.
5. Keep batching/order constraints and starvation protections visible. A throughput-improving group allocation is not an admission/rejection policy or a proof of per-tenant fairness.

## Decision and verification proposal

Return the smallest justified branch, missing capability/evidence, expected saved work/wait, added state/traffic/replica cost, exact affected SLO/cohorts, counter-signals and proposed next gate. Withhold the candidate when every destination is full, catch-up is unproven, model/cache compatibility is unknown, or the measured work saved does not exceed exposed costs.

A later authorized comparison should hold model, trace, arrivals, resource count and acceptance policy fixed. Measure TTFT, request-average decode and token-gap tails separately; total completion/goodput, normal/high-priority outcomes, source/destination peaks, migration bytes/time/downtime, recomputation, and replica/group occupancy. Include short and long contexts, mixed phases, bursts, scarce slack, slow/congested links and repeated resize/migration. Compare both local and cross-node paths when actually relevant.

Reject correctness mismatches, unbounded waits, failed reservations, nonconverging copies, or protected-SLO regressions. Keep a feasible static/no-migration baseline. Current-code review and target-system tests are a later authorization gate; this candidate has not executed them.
