# Foundational mechanism decisions

Status: candidate; empirical validation: **not_run**. This guide consolidates
existing packaged evidence for [issue #131](https://github.com/InferMatrixLab/InferRSI/issues/131).
It adds no primary-source inspection, selector, experiment result or permission
to change a system. Resource layers locate a bottleneck; scheduling, caching/reuse
and parallelism/pipelining describe possible interventions. They are not an
exhaustive taxonomy or a ranking of solutions.

## Use the measured boundary

Start with the fixed workload, useful work and quality/SLO contract, measured
limiting stage, resource budget, software revision and allowed changes. If these
are missing, defer the optimization choice and name the missing observation.
Use [performance-ceiling-analysis](../../performance-ceiling-analysis/SKILL.md)
for headroom and the parent search policy for experiment ordering and stopping.
A keyword or available recipe does not identify a cause.

| Axis | Question before a candidate change | Preserve |
| --- | --- | --- |
| Scheduling | Who becomes eligible, in which order, at which boundary? | Progress, service order, fairness/backpressure and unfinished state |
| Caching / reuse | Which repeated work is avoided, with which identity and lifetime? | Validity, ownership, readiness, invalidation and eviction obligations |
| Parallelism / pipelining | Which independent work can occupy which stage or resource? | Dependencies, tensor/request identity, in-flight memory and completion |

The cases below are **golden expectations for a human or agent to assess**, not
implemented dispatch rules. Collect matches identity/metadata/entrypoint text; it
does not diagnose bottlenecks or make semantic selection/abstention judgments.
CPU checks can validate retrieval, references and revision refusal, not that an
agent chose the appropriate method.

## Scheduling

### S1 — Admission gates before preemption

- **Signal and prerequisite:** Waiting work coexists with low scheduled-token use
  or allocation pressure. Identify which gate blocked the request before proposing
  a larger batch, different ordering or preemption.
- **Source boundary:** The carried vLLM
  [admission ledger F1–F5](../../../repositories/vllm/diagnose-vllm-admission-pressure/references/source-notes.md#f1--separate-budgets-and-admission-caps-implementation)
  pins `7f730b4cea9a66520a9200265928ebe016b48a39`, supplied 2026-10-15.
  Running/active caps, token/input budgets, readiness and allocation are separate.
  Pending connector frees can stop allocation retries without immediate preemption;
  counted remote-prefix tokens are not load readiness.
- **Candidate and invariants:** Route to
  [diagnose-vllm-admission-pressure](../../../repositories/vllm/diagnose-vllm-admission-pressure/SKILL.md).
  Change only the implicated gate while preserving token/state accounting,
  blocked-request handling and the service contract. This readset does not
  establish safe CLI values or behavior of a concrete connector.
- **Counter-signal:** No runnable work, an earlier gate, input/encoder waits or
  pending frees can explain unused capacity. A queue alone does not identify a
  policy bottleneck.
- **Next verification / rollback:** First trace the blocking branch and request
  state at the current revision. For a later authorized contrast, match useful
  work and measure queue/token latency and completion. Restore the prior
  configuration if progress, protected-request latency or quality regresses.

### S2 — Preemption must retain a recovery path

- **Signal and prerequisite:** Heterogeneous jobs wait behind service while
  unfinished requests retain KV. Establish supported resume, recompute or transfer
  and count all started, unfinished state, not just running jobs.
- **Source boundary:** The carried
  [Orca O1/O3 and FastServe F1–F3 notes](../../assess-serving-preemption/references/source-notes.md)
  use Orca OSDI 2022 proceedings (§4.2/Algorithm 1) and FastServe
  `2305.05920v3` (§§4.1–4.2), read 2026-10-15. Iteration eligibility and
  conservative reservations differ from priority/promotion and suspended-state
  residency. Historical paper mechanisms are not current vLLM APIs.
- **Candidate and invariants:** Use
  [assess-serving-preemption](../../assess-serving-preemption/SKILL.md) to separate
  admission, eligibility, service order and recovery. Less conservative admission
  or changed order must preserve progress, state identity, recoverability,
  backpressure and the declared fairness contract.
- **Counter-signal:** Long uninterruptible prefill, dominant engine time or exposed
  copy/recompute can outweigh scheduling benefits. Aggregate tail improvement is
  not per-tenant fairness; asynchronous copies do not establish useful overlap.
- **Next verification / rollback:** First inventory running and suspended KV and
  recovery ownership. A later authorized contrast must retain cohort tails and
  exposed recovery cost alongside throughput. Restore prior ordering/residency
  if recovery stalls or protected classes regress. Do not adopt a paper threshold
  as a tuning default.

## Caching and reuse

### C1 — Available KV is different from tier capacity

- **Signal and prerequisite:** A reported hit/computed-token count coexists with
  a blocked request, or retained/prefetched data pressures a lower tier. Identify
  a validity/readiness/lifetime problem versus a capacity/retention problem.
- **Source boundary:** The carried
  [vLLM KV ledger F1–F4/F6](../../../repositories/vllm/audit-vllm-kv-lifetimes/references/source-notes.md)
  pins `7f730b4cea9a66520a9200265928ebe016b48a39`, supplied 2026-10-15.
  Async counted tokens precede receive completion; connector retention and
  scheduler in-flight-write fencing differ. Base-class obligations do not qualify
  a concrete backend. Separately,
  [LMCache MP tier management](../../../repositories/lmcache/kv-tier-management/SKILL.md)
  retains historical prefix `c3b875a` (inspection date unrecorded here).
  Its retention, staging and prefetch-pressure policy has a separate pin/scope.
- **Candidate and invariants:** First use
  [audit-vllm-kv-lifetimes](../../../repositories/vllm/audit-vllm-kv-lifetimes/SKILL.md)
  for hit identity, completion, failure and release ownership. Use the tier owner
  only for an identified supported MP stack and measured retention/pressure
  question. Preserve prefix validity and source/destination lifetime through
  required completion; spare capacity does not satisfy a dependency.
- **Counter-signal:** Adding capacity does not repair a failed receive, stale
  identity or held source block. Extra retention/prefetch can increase RAM
  pressure; hit rate alone does not show lower request latency. vLLM lifecycle
  evidence does not prove LMCache tier availability or a compatible dependency tuple.
- **Next verification / rollback:** Trace allocation, receive completion/failure
  and deferred release at the selected implementation. A later authorized tier
  contrast should measure useful contiguous-prefix reuse, resident/in-flight
  bytes and request latency. Restore prior retention/prefetch if pressure or
  protected latency worsens; never bypass readiness or free live buffers.

### C2 — Graph reuse can lose to replay and copy cost

- **Signal and prerequisite:** Repeated launch/setup work suggests graph or
  compiled-artifact reuse. Establish stable capture boundaries, shapes, buffer
  identity/lifetime, useful work and equivalent output.
- **Historical observation:** The
  [Qwen B300 rejection case](../../inference-optimization-casebook/cases/qwen-b300-rejected-directions.md)
  and [identity record](../../inference-optimization-casebook/cases/qwen-b300-rejected-directions.json)
  retain InferRSI source `d51c941dc57807c1e16ea698cd9291f414110c45`,
  issue #3. H6/H7 graph projection/norm/RoPE or post-attention trials were removed
  for no material end-to-end gain; H7 separately records replay/copy costs. These
  are carried historical observations in that Qwen/BF16/native-step/four-B300
  context, not experiments rerun here or a newly established common cause.
- **Candidate and invariants:** Revisit with a stated changed condition, such as
  a supported capture boundary or buffer lifetime. Preserve work, graph-input
  identity, numerical/image quality and valid buffer ownership.
- **Counter-signal:** Faster enqueue or a reusable artifact can coexist with no
  full-request gain after capture, replay and copies. This record does not ban
  graph reuse; the campaign's final PASS does not qualify H6/H7.
- **Next verification / rollback:** Inspect the rejection scope first. A later
  authorized contrast must include capture amortization, replay/copies and
  full-request cost under matched quality control. Restore the complete prior
  launcher/configuration/artifact if quality fails or benefit is absent; retain
  the new verdict separately from the historical result.

## Parallelism and pipelining

### P1 — Balance stages against communication and in-flight memory

**Training only: this is not an inference-serving placement recipe.**

- **Signal and prerequisite:** Stages have unequal work/memory and idle intervals.
  Fix global batch, microbatch count, shapes, precision/optimizer state and topology
  before changing stage boundaries, meshes or shardings.
- **Source boundary:** The packaged
  [Alpa AL1–AL2 ledger](../../choose-parallel-training-plan/references/source-notes.md#al-alpa)
  pins `2201.12023v3`, especially §§4–7, with the original readset/PDF digest.
  This consolidation does not reread the paper or invent an inspection date.
  Its objective omits inter-stage transfer, takes microbatch count externally and
  does not optimize compute/communication overlap; the model is static training.
- **Candidate and invariants:** Route to
  [choose-parallel-training-plan](../../choose-parallel-training-plan/SKILL.md).
  Compare against a simple equal-stage incumbent using actual transfer and
  per-rank peak memory, including in-flight activations/staging. Preserve training
  semantics, batch/work and tensor partition identity.
- **Counter-signal:** Balanced modeled compute can expose communication or exhaust
  activation memory. Equal-layer partitioning already matches the reported plan
  on the tested homogeneous GPT case. Solver output is not a measured optimum.
- **Next verification / rollback:** First account for omitted transfer, topology
  and memory feasibility. Later authorized training checks must establish
  correctness, full-step benefit and planning amortization. Restore the prior
  partition/launcher if quality, capacity or full-step cost regresses. Historical
  evidence does not qualify a current GPU/NPU stack.

### P2 — Preserve peer rows before seeking pipeline overlap

- **Signal and prerequisite:** Attention/FFN separation creates an exchange
  boundary. Establish role/native/communication ranks, layer/stage identity,
  per-peer row lengths and receive-buffer ownership for the selected eager path.
- **Source boundary:** The
  [AFD F1–F4 ledger](../../../repositories/afd-plugin/audit-afd-p2p-exchanges/references/source-notes.md#f1--derive-role-rank-then-communication-namespaces)
  pins `df8d6a0c403c3ca1b4ed9cf1687e7204908bebec`, inspected 2026-10-23:
  CUDA P2pNccl eager dense FFN with `compute_gate_on_attention=false`.
  Control destination and data fan-in can differ; matching a total token count
  does not preserve each peer's rows.
- **Candidate and invariants:** Use
  [audit-afd-p2p-exchanges](../../../repositories/afd-plugin/audit-afd-p2p-exchanges/SKILL.md)
  before proposing placement/overlap. Preserve per-peer lengths through
  concatenation, FFN and return splitting, receive context and buffer lifetime.
  Python return is not device/communication completion.
- **Counter-signal:** An even split, valid total shape or more in-flight work can
  conceal ownership errors or extra staging. Source synchronization calls do not
  prove overlap, successful rendezvous or a performance gain.
- **Next verification / rollback:** Trace producer-to-consumer rank/stage/row
  ownership first. Native/model/transport checks need separate authorization and
  a pinned dependency tuple; communicator internals and multi-host behavior remain
  unqualified. Restore the prior supported topology and stage/buffer policy if
  identity, completion or capacity cannot be established. Exclude MoE, graph/DBO
  and NPU paths.

## Evidence and authorization limits

All six cases reuse canonical material packaged before this contribution.
Source notes retain attribution, license scope, versions and original inspection
dates; abbreviated historical pins remain prefixes. New primary inspection,
backend correctness, quality, performance and agent efficacy are **not_run**.
Missing Sarathi, PagedAttention or DistServe archives are not silently replaced
with a proposal bibliography.

Keep each domain owner as the substantive procedure. These short cases provide a
reason to inspect it, reject/defer a candidate and choose a bounded next check.
They do not promote candidates or authorize execution, resource changes,
publication or integration. Preserve the last qualified incumbent and record
better/worse/inconclusive outcomes under the existing search policy.
