# Chunk budget controls interference and overhead

ID: `case.sarathi-chunk-budget`. Owner: `optimization-search-policy`.
Axes: scheduling, pipelining. Resource: Accelerator compute/HBM.
Source-derived candidate; local validation not_run. No local campaign evidence.

## Source observation

Agrawal et al., [Sarathi-Serve, OSDI 2024](https://www.usenix.org/system/files/osdi24-agrawal.pdf),
§§4.1–4.3, 5.3–5.4: schedule decodes before fitting prefill chunks into a token
budget. More uniform batch work reduces pipeline imbalance. Figure 14 reports
extra prefill time from smaller chunks for Yi-34B TP2. Table 4's two-A100,
128-request ablation separates chunking-only, hybrid-batching-only and combined
scheduling: chunking alone worsens TTFT relative to the combined configuration;
hybrid batching alone worsens P99 TBT. This is author-reported evidence, not a
universal chunk size or an InferRSI measurement.

## Proposed decision

Signal: decode stalls coincide with long prefills in a measured timeline.
Prerequisites: supported chunking, known token budget and request-phase accounting.
Candidate: vary only the chunk budget while preserving model, workload and resources.
Invariants: token order, complete prompts, cancellation, KV ownership and fair admission.
Metrics: TTFT, inter-token tails, queue time by class, chunk overhead, bubbles and
goodput. Counter-indication: prefill-only or low-load traffic may pay chunk overhead
without enough interference to remove. Rollback: restore the frozen scheduler and
budget, drain task-owned in-flight work safely and recheck the original workload.

Attribution and source version are retained in [the case record](sarathi-chunk-budget.json).
