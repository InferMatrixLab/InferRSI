# Scheduling choices alter state lifetime, placement, or execution scope

Status: candidate. Empirical validation: not_run. This is an incremental knowledge brief, **not a third matrix**. **F** facts below point to the four new paper notes or the previously completed notes. **P** denotes the new operational synthesis. No runtime behavior or accelerator portability is inferred from historical paper descriptions.

## Six distinct questions

1. **Admit a request:** Can accepted work progress with the chosen memory/SLO contract? **F:** [Orca O3](../notes/orca.md) reserves maximum total tokens; [LoongServe G3](../notes/loongserve.md) checks possible future KV before dispatch. The prior Mooncake synthesis (`notes/kv.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`) instead describes early rejection based on projected downstream load. **P:** Local dispatch delay, reservation, overload rejection and a contractual acceptance guarantee must not be collapsed into one “admission” knob.
2. **Batch ready work:** Which tokens/requests execute together? **F:** Orca makes membership adjustable at iteration boundaries, with request-local attention; the prior Sarathi synthesis (`notes/scheduling.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`) adds a token budget and prefill chunks to bound same-iteration interference. **P:** Request-count limits and token-work budgets constrain different quantities.
3. **Preempt accepted work:** Who gets the next service opportunity? **F:** [FastServe F1–F3](../notes/fastserve.md) uses skip-join MLFQ/promotion and therefore retains more started-but-unfinished state. **P:** Priority preemption and memory-pressure eviction are different causes; the recovery/state-retention policy must match the cause and service contract.
4. **Migrate ownership:** Which replica runs the request? **F:** [Llumnix L1–L2](../notes/llumnix.md) copies append-only KV between compatible model instances and commits after a short final pause. **P:** Migration relocates capacity pressure; it creates no physical memory and may require temporary duplication. Final downtime, total copy time and copied bytes are three different quantities.
5. **Change execution group:** How many instances share this context's work? **F:** [LoongServe G1–G5](../notes/loongserve.md) keeps fixed model parallelism inside each replica but elastically changes sequence-parallel groups. Post-prefill retention and decode expansion can avoid extra whole-cache migration; optional decode contraction pays for KV movement. **P:** “No extra migration” is not “no communication,” and “elastic parallelism” does not imply live model-weight repartitioning.
6. **Recover discarded or displaced state:** Recompute, swap, or continue using remote shards? **F:** The prior PagedAttention synthesis (`notes/kv.md` in prior archive `omnirsi-paper-intelligence-2026-10-15.zip`) compares device-block recovery; FastServe adds next-service-aware host residency; Llumnix copies state to another replica; LoongServe can consume old shards in place. **P:** Choose the state-use model before estimating transfer/recompute cost. A single bytes/bandwidth quotient cannot describe all four paths.

## State accounting proposal

**P:** Keep separate counters for model weights, live running KV, suspended KV, reserved-but-not-live capacity, migration source/destination duplicates, prefetched KV, per-layer transient buffers, and retained reusable prefixes. Virtual priority headroom is a scheduling signal rather than an additional physical category. Do not add logical ownership totals as though they were unique physical bytes.

**F:** Orca's forced-to-maximum evaluation does not measure early-EOS reservation waste. FastServe's Fig. 8 demonstrates the extra unfinished-state footprint of preemption. Llumnix's pre-copy needs receiving blocks before each stage. LoongServe's per-layer buffer improvement does not shrink the persistent complete-model KV to one layer. These facts support the accounting decomposition but do not validate a universal memory estimator.

**P:** Keep path accounting equally explicit: HBM/local device, intra-node GPU link, host/device copy, IPC, and inter-node network. Some migration implementations stage through RAM before a network transfer. H2D and IPC are not Network. An OS scheduling analogy is not an OS tuning result.

## Fairness is not one metric

**F:** Orca preserves an iteration-count FCFS property. FastServe mitigates starvation through promotion and reports global P95 outcomes. Llumnix differentiates priorities and reports measured normal-class regressions. LoongServe combines FCFS candidate selection with length-based resource batching and normalized-latency heuristics. None supplies a general per-tenant fair-share guarantee for the combination.

**P:** Require the owner to distinguish arrival-order constraints, minimum service, maximum wait, tenant shares, priority differentiation and user-visible token gaps. Measure the promised property directly; an improved mean or aggregate tail can hide affected long/normal-priority cohorts. The only new unread paper lead is VTC/fair serving, listed in the FastServe/Llumnix readsets; it was not extracted.

## Keep metric identities intact

- **F Orca:** Median of request completion latency/output tokens; homogeneous-case median unnormalized completion; separate engine whole-batch microbenchmarks. No joint TTFT/TBT goodput.
- **F FastServe:** Mean/P95 of completion latency/output tokens at a 0.3-s/token target; a separate OPT-13B figure uses 95% joint phase attainment with 5×/10×/20× light-load phase targets. Some phase-statistic details are not specified there.
- **F Llumnix:** Mean/P99 request, prefill and **request-average decode** latency; migration downtime and average active-instance count are separate axes.
- **F LoongServe:** Mean completion latency/total sequence length, prefill/input tokens and decode/output tokens; maximum rates under a stated 25× inference-latency SLO; separate P90-goodput ablations.
- **F prior work, from existing notes only:** Sarathi's P99 per-token TBT capacity, DistServe's joint TTFT/request-average-TPOT per-GPU goodput, PagedAttention's mean completion/output latency and Mooncake's workload-specific completed-SLO yield each have different definitions.

**P:** No cross-paper league table or multiplication of headline speedups is warranted. Normalize model/workload/resource counts, metric boundaries, baseline revision/capabilities, allowed admission/rejection and load construction first. If these cannot be matched, present a mechanism comparison rather than a numerical winner.

## Source confidence and promotion boundary

**F:** All four papers are author-reported historical GPU systems. Versions, actual readsets, exact locators, metric denominators, measured counter-signals and unreported gaps are in [Orca](../references/orca-readset.md), [FastServe](../references/fastserve-readset.md), [Llumnix](../references/llumnix-readset.md) and [LoongServe](../references/loongserve-readset.md).

**P:** The two candidate skills and three hypothetical cases add reusable decisions rather than new implementation facts. A current-code capability audit, target-topology model calibration, correctness/progress checks and explicitly authorized bounded experiments are future gates. No installations, system changes, reproduction runs, heavy A/B tests, or InferRSI edits occurred in this pack.
