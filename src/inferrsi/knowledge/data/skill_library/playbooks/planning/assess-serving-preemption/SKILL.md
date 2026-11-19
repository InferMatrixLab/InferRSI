---
name: assess-serving-preemption
description: Assess whether LLM serving queue delays justify token-boundary priority preemption, accounting for suspended KV, host swapping or recomputation, and long-request service guarantees. Use for admission-versus-service-order diagnosis, not current scheduler implementation or tenant-fairness certification.
---

# Assess serving preemption

Every procedure below is **P: a proposed operational rule**. This candidate produces a read-only decision and a future verification plan, not a validated configuration. Do not install, benchmark, change scheduling/admission, migrate state, edit a repository, or run a reproduction without a separate authorized task.

Read the self-contained [source notes](references/source-notes.md): the Orca branch covers iteration eligibility/reservation/FCFS; the FastServe branch covers priority preemption and state residency. Their exact readsets are included there. Consult them before quoting a metric or comparing a baseline. Historical CUDA/GPU evidence does not establish current vLLM semantics, framework support, or NPU compatibility.

## Distinguish the failed boundary

Establish what is late: first token, individual token gap, request completion, or a stated cohort's service. Obtain the exact percentile/attainment target and denominator. Then separate:
- Waiting for the current whole batch to end
- Inability to admit because reserved or live KV is full
- Long first-iteration/prefill interference
- Long accepted requests occupying service while short jobs queue
- Waiting for state recovery or host/device transfer

Iteration-level batching can address the first without solving the others. Short-job preemption addresses service ordering but can worsen the total unfinished-state footprint. If prefill interference is the binding problem, the optional earlier `choose-prefill-decode-schedule` candidate addresses that separate question; `diagnose-kv-block-efficiency` addresses physical allocation/slack. Neither is required to consume this skill: if unavailable, report the diagnosed boundary and the missing current evidence rather than substituting a preemption recipe.

## Evidence required for a candidate

Record model/KV format, actual engine revision, safe interruption boundary, request batch limit, input/output/context distributions, arrival bursts, device live/reserved/allocated bytes, active and suspended requests, host budget, transfer path, recovery time, and queue/phase/service timings. Keep per-tenant or priority-class obligations distinct from aggregate latency. Mark unavailable evidence explicitly.

Do not infer that an ordinary iteration boundary permits interrupting a prefill halfway through. Do not treat unknown output length as known from the prompt. Do not treat a high-priority label as permission to change an existing service contract.

## Decision gates

1. **Admit:** Determine whether the request can progress under the current memory policy. Orca's maximum-total-token reservation prevents future KV exhaustion within its bound, while demand allocation needs an explicit supported recovery or overload path. Preserve that distinction; do not remove reservations solely because some capacity is not live.
2. **Batch:** Determine whether the engine can change membership at the intended boundary and batch the mixed phases without violating the declared token-latency target. A larger request-count limit is not a token-cost budget.
3. **Preempt:** Propose a size/attained-service-aware candidate only when measured queue delay and length heterogeneity plausibly justify it. State the priority initialization inputs, quantum calibration, demotion boundary, promotion rule and service contract. Skip-join's profiled first iteration is a useful candidate, not SRPT optimality or a universal doubling/300-ms recipe.
4. **Retain/recover:** Count KV for every started unfinished request, not only the running batch. Compare keeping state on device, host swap, and recomputation using measured bytes, latency and opportunity cost. Require both host capacity and device space for the next restored job. Prioritize state by supported next-service estimates, including imminent promotions, rather than priority labels alone.
5. **Protect progress:** Identify what happens when new bursts consume headroom, predictions are wrong, a long job is promoted, or two jobs repeatedly displace each other. Do not propose recompute-based eviction without a progress invariant. Do not label all recompute policies defective based on FastServe's strawman.
6. **Separate paths:** Charge H2D/D2H to Accelerator/RAM and same-host IPC to its actual local resource. Only cross-node transport is Network. Distributed TP/PP coordination is not itself evidence of live KV migration or changing parallel degrees.

## Decision output

Return the observed failure boundary, the smallest candidate that addresses it, unchanged assumptions, missing evidence, resource cost, affected cohorts, counter-signal, and the next authorized gate. Withhold a preemption recommendation if the apparent gain can be explained by different kernels, unmatched parallelism, or an incomparable latency metric.

FastServe's same-engine FCFS comparison is stronger scheduler evidence than its historical-vLLM headline. Its P95 aggregate improvement is not a formal starvation or tenant-fairness guarantee. The ENST printed index convention and pseudocode details are ambiguous; do not turn them into implementation instructions.

## Verification proposal and stop conditions

For a later authorized test, preserve model/precision, engine, device count, TP/PP, batching, arrivals and the admission rule. First isolate service ordering, then state recovery; evaluate interactions only after both are understood. Measure TTFT, token-gap tails, normalized completion latency, maximum wait/cohort tails, attained service, device/host occupancy, bytes, exposed copy wait, futile prefetch and recomputation. Include low load, burst load, long inputs, long outputs and promotion under pressure.

Reject a candidate that loses forward progress, exceeds host/device budgets, shifts unacceptable delay to protected requests, or improves only an aggregate while missing the stated SLO. Unknown safe boundaries, unsupported state recovery, uncalibrated timing or unclear service obligations are blockers. Empirical validation: not_run.
