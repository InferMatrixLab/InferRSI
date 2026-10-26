# Foundational mechanism decisions

Owner: `optimization-search-policy`. Candidate guidance; local efficacy not_run.
Use during Phase 1 when optimization stalls or a successful change moves the
bottleneck. This supplements the existing search/evidence loop. Resource layers
answer **where** time or capacity is constrained; intervention axes answer **how**
to change it. They are neither new SearchSpace rows nor an exhaustive taxonomy.

## Re-derive the system before selecting a technique

1. Freeze useful work, latency/throughput or goodput objective, quality and
   fairness gates, timing boundary, topology, versions, resource cost and budget.
   Keep preparation, cold start, warmup, steady admission and drain distinct.
2. Map arrival → host preparation → admission → prefill → decode → output,
   including transfers, codecs and cleanup where applicable. Record dependencies,
   queue waits, stage times, bytes/FLOPs and live/reserved/in-flight state owners.
   Check utilization, saturation and errors per resource; utilization alone does
   not prove a bottleneck. Separate HBM, host RAM, storage, accelerator links and
   inter-node network. Missing measurements stay unknown.
3. Bound the opportunity with [performance-ceiling-analysis](../../performance-ceiling-analysis/SKILL.md).
   For a fixed work graph, elapsed time cannot beat its dependency critical path
   or work/resource-capacity bounds. Overlapping stage durations must not be
   added as if serial. Amdahl bounds apply to the measured removable fraction;
   changing the algorithm or removing work changes those premises. Ask what
   must execute, what can be reused, what must wait and what can overlap.
4. Compare a small set of mechanisms against the same constrained resource.
   For each, state the signal, expected removable cost, new work/state/traffic,
   prerequisites, counter-signal, correctness invariant and cheapest falsifying
   check. Include keeping the incumbent. Prefer a simpler intervention when it
   addresses the same cost; extra workers or cache tiers need their own rationale.
5. If no measured signal discriminates candidates, **abstain and request
   measurement**. For an unexplained plateau, first request a scoped timeline,
   workload/phase breakdown and uncertainty estimate, not a larger experiment.
   Never convert an unrelated keyword, unsupported backend or low utilization
   into a recommendation. No remaining budget means stop and report the gap.

## Card 1: admission versus preemption

**Question:** is waiting caused by eligibility/order, insufficient future KV
capacity, long prefill interference, or a finite cohort's drain?

| Evidence | Bounded candidate / owner | Counter-indication and invariant |
| --- | --- | --- |
| Whole-batch join/retire delay | Iteration eligibility; existing [Orca/preemption procedure](../../assess-serving-preemption/SKILL.md) | Does not fix a long individual prefill; preserve ordering, cancellation and cleanup |
| KV allocation failures or suspended requests | [vLLM admission pressure](../../../repositories/vllm/diagnose-vllm-admission-pressure/SKILL.md); distinguish admission from service-order preemption | Do not admit without forward-progress/recovery capacity; price recompute and restore costs |
| Prefill coincides with decode stalls | [Sarathi chunk budget](../cases/sarathi-chunk-budget.md) | Chunk overhead can hurt TTFT; check decode tails and per-class waiting as well as throughput |
| Low mean occupancy mostly during drain | Reuse [case.admission-drain-occupancy](../../inference-optimization-casebook/cases/admission-drain-occupancy.md) | Selected-interval occupancy is not whole-service goodput; retain every request in acceptance |

Measure queue time, TTFT, inter-token latency, preemptions/recomputation and
completed requests meeting the declared SLOs per second. Check starvation and
per-class tails; a cache-friendly or short-job priority is not a fairness proof.

## Card 2: allocation/reuse versus tiering

**Question:** is the cost wasted allocation, repeat computation or actual resident
capacity? Autoregressive KV state, cross-request prefix reuse and paged allocation
are distinct. Compiled artifacts and staging buffers need different validity rules.

| Evidence | Bounded candidate / owner | Counter-indication and invariant |
| --- | --- | --- |
| Reserved capacity exceeds live KV; duplication blocks admission | [Paged allocation/sharing](../cases/paged-kv-allocation.md) | Spare capacity with compute saturation may not help; retain block ownership and copy-on-write |
| Repeated exact prefixes consume prefill work | [Prefix reuse and locality](../cases/prefix-reuse-locality.md) | No reusable work or overloaded cache-local replicas; validate complete reuse identity |
| Useful state cannot remain resident; reload/recompute dominates | Existing [KV tier management](../../../repositories/lmcache/kv-tier-management/SKILL.md) | Compare retain/move/recompute including lookup, transfer, staging and eviction; no generic offload win |

Reuse identity must include all relevant model/weight, configuration, token/input,
position and adapter identities and trust boundaries; approximate/semantic reuse
changes the quality contract. Use [KV lifetime audit](../../../repositories/vllm/audit-vllm-kv-lifetimes/SKILL.md)
for in-flight ownership, invalidation and release. Measure cold and realistically
warm conditions, token-weighted reuse, avoided work, transfer/lookup time,
live/reserved memory and eviction churn. A hit rate is not an end-to-end benefit.

## Card 3: pipeline bubbles versus communication/memory pressure

**Question:** which independent work can run concurrently, and which dependent
stages can overlap across requests or chunks within the same resource budget?

| Evidence | Bounded candidate / owner | Counter-indication and invariant |
| --- | --- | --- |
| Unbalanced batches leave stages idle | Inspect stage balance and chunk granularity using the Sarathi case | More microbatches add overhead and live buffers; distinguish drain from steady bubbles |
| Prefill/decode interference and different phase needs | [DistServe phase placement](../cases/distserve-phase-placement.md) | KV transfer or duplicate model residency can erase benefit; require measured topology and memory feasibility |
| Exposed H2D/D2H transfer with independent chunks | [CUDA copy/compute overlap](../cases/cuda-copy-overlap.md) | An asynchronous API is not overlap; backend/hardware conditions must hold |
| Attention/FFN P2P exchange on the selected CUDA path | Existing [AFD exchange audit](../../../repositories/afd-plugin/audit-afd-p2p-exchanges/SKILL.md) | AFD exchanges hidden states, not DistServe's KV; preserve rank mapping and buffer ownership |

Preserve dependencies, collective order, buffer lifetimes, cancellation and
bounded queues/backpressure. Measure the critical path, stage utilization,
bubbles, exposed communication, peak memory and resource-normalized goodput.
Extra ranks may increase traffic/contention. Single-request latency and throughput
are separate objectives. [Parallel training plans](../../choose-parallel-training-plan/SKILL.md)
apply only to training; their optimizer/activation assumptions are not inference recipes.

## Reusable cases and existing inventory

The six case IDs below use the existing Case contract, not a new mechanism
catalog. New interpretations are proposals; imported observations remain locally
unverified. [Source inventory and notices](foundational-sources.md) identifies
the inspected versions and the prior extraction that is reused.

| Stable case ID | Axes / resource layer | Evidence and counterexample |
| --- | --- | --- |
| `case.admission-drain-occupancy` (existing owner) | scheduling / Accelerator, OS | Historical diagnostic; campaign INCONCLUSIVE, drain confounds mean occupancy |
| `case.sarathi-chunk-budget` | scheduling, pipelining / Accelerator | Paper ablation; smaller chunks add prefill overhead |
| `case.paged-kv-allocation` | caching / Accelerator HBM | Paper ablation; oversized blocks hurt short-sequence workloads |
| `case.prefix-reuse-locality` | caching, scheduling / Accelerator HBM, OS | Paper plus versioned identity rules; hot-replica unfairness is a hypothetical counterexample |
| `case.distserve-phase-placement` | parallelism, pipelining / Accelerator, Network when inter-node | System evaluation separate from simulated parallelism ablation; transfer-bound reversal is hypothetical |
| `case.cuda-copy-overlap` | pipelining / RAM, Accelerator link | Versioned documentation; overlap prerequisites, not an observed local speedup |

Orca's O1–O4 and FastServe's low-load no-advantage result already live in
[assess-serving-preemption source notes](../../assess-serving-preemption/references/source-notes.md).
Alpa and split-backward training material retain their own owners. No duplicate
Orca/Alpa records or new stable skill IDs are needed.

## Return to the existing evidence loop

Record one hypothesis and SIAS plane, candidate change, prerequisites, invariants,
counter-indications, metrics, rollback and scope. Point to issue-scoped frozen
baseline/candidate evidence in `plan/`, `results/`, `patch/`, `validator/`; never
put campaign pins or numeric gates in reusable cases. For these imported cases,
local experiment pointers are absent because no local experiment was run.
Use [benchmark design](../../inference-benchmark-design/SKILL.md) and
[performance evidence](../../dense-performance-evidence/SKILL.md) for verification.
Preserve negative/inconclusive results and re-profile after any accepted change.

If a later experiment is separately authorized, freeze repeated controlled runs,
low-load and saturation regimes, representative held-out traces, cold/warm state,
per-class tails, quality gates, resource budget and stop condition. Compare isolated
factors before selected interactions: locality versus fairness, KV capacity versus
batch latency, prefix reuse versus phase split, chunk size versus bubbles, and
replicas/disaggregation versus cache locality and transfer. Measure the original
baseline against the final combination directly; never add percentage gains.

CPU fixtures check reader/selection and package contracts only. The existing Skill
Eval performance-report-audit task does not grade this diagnostic task shape;
an adapter/grader change needs its own review. Neither fixture success nor Skill
Eval scores establish agent efficacy or engine performance. No controller,
experiment, automatic promotion or canonical-store mutation is introduced.
