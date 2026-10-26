# Phase separation must pay for state transfer

ID: `case.distserve-phase-placement`. Owner: `optimization-search-policy`.
Axes: parallelism, pipelining. Resources: Accelerator compute/HBM, accelerator
links and Network only for actual inter-node traffic.
Source-derived candidate; local validation not_run. No local campaign evidence.

## Source observation

Zhong et al., [DistServe, OSDI 2024](https://www.usenix.org/system/files/osdi24-zhong-yinmin.pdf),
§§3–4, 6.1, 6.3–6.4: separate prefill/decode resource and parallelism choices,
with bandwidth-aware KV placement. Real-system tests use A100 nodes with limited
cross-node bandwidth; corresponding stages can transfer locally. Figure 11's
parallelism/placement ablation is simulated. It reports no improvement from
searching vLLM parallelism in its OPT-66B/ShareGPT setting, where the reference
choice already wins. The simulation is not another measured multi-node result.

## Proposed decision

Signal: measured phase interference and distinct phase service demands.
Prerequisites: supported KV handoff, compatible layouts, topology/bandwidth and
per-rank memory feasibility. Candidate: compare a phase split to the incumbent
at equal total accelerator/resource cost. Invariants: handoff completion, token
ordering, cancellation, collective order and bounded destination queues.
Metrics: joint TTFT/TPOT attainment, per-class tails, transfer bytes/time,
stage idle time, peak memory and per-resource goodput. Hypothetical counterexample:
exposed KV transfer and duplicate residency outweigh removed interference on a
constrained link. Low load may not amortize separation. Rollback: drain owned
handoffs, restore colocated placement and verify complete request outputs.

Attribution and source version: [case record](distserve-phase-placement.json).
