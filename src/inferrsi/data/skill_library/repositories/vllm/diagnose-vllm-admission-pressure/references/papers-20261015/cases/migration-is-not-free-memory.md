# Candidate case: enough cluster memory, no instance admits the waiting prompt

Status: candidate. Empirical validation: not_run. **P:** Hypothetical decision case, not an observed incident or performed validation.

## Trigger

A long prompt waits while several model replicas have spare KV blocks. A proposed change treats all cluster free memory as directly usable and assumes migrating an active request costs only 20 ms.

## Expected reasoning

- Distinguish per-device allocator waste from cross-instance fragmentation and head-of-line prompt demand. Physical blocks on several replicas cannot necessarily be summed into one admissible request.
- Verify compatible resident models and accessible receiving capacity. Llumnix's virtual demand/headroom changes the placement signal; it does not allocate extra physical memory.
- Compare moving a selected shorter/lower-priority running request, waiting, and supported recomputation. Measure temporary duplicate KV and both source/destination headroom, not just final residency.
- Separate full KV copy from final pause. Llumnix's 20–30-ms downtime is a two-stage microbenchmark result on its A10/64-Gb/s setting, not universal migration latency or a bandwidth budget.
- Treat migration as conditionally helpful when slack exists elsewhere. If every replica is full, relocation cannot create capacity. Do not declare a new overload rejection policy from these papers.
- If priority isolation is proposed, report normal-class costs and request approval for the actual policy change. Per-class FCFS and a faster high-priority mean do not establish fairness.

## Reviewable result and stop rule

A good output names the memory boundary, state/transport costs, compatibility and reservation checks, cohorts affected and the smallest next evidence gate. It cites [Llumnix L1–L3](../notes/llumnix.md). Stop before mutation and withhold a numerical benefit when destination fit/copy convergence is unverified. A source-completion/preemption or allocation-failure path must preserve ownership and progress, but the candidate must not claim evaluated fault-tolerance coverage absent from the paper.
