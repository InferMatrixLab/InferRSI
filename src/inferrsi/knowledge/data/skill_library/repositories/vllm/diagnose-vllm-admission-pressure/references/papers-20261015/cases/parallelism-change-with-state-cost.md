# Candidate case: a long prefill needs a larger group than its decode

Status: candidate. Empirical validation: not_run. **P:** Hypothetical decision case, not an incident record or executed experiment.

## Trigger

A workload combines very long prompts with short requests and comparatively small decode batches. A proposal says elastic parallelism has zero movement cost and should replace the fixed phase/parallel plan everywhere.

## Expected reasoning

1. Verify that the actual engine supports sequence-sharded KV and attention. Changing a configured TP/PP degree is not the same operation as LoongServe's ESP.
2. State separately what happens on prefill expansion, prefill-to-decode contraction, decode expansion and decode contraction. Distinguish retaining KV that is already present, leaving old shards where they are, and explicit transfer to release workers.
3. Use length-sensitive profiled costs and actual group topology. Saved compute may be offset by small-batch communication, source/destination peaks, extra weight replicas and work displaced from other requests.
4. Preserve metric definitions and baseline/resource counts. LoongServe's maximum request rate meeting its normalized-latency SLO is not automatically rate under a joint TTFT/token-tail SLO; its P90 ablations are a separately defined comparison. Do not combine LoongServe's ratios with DistServe or Sarathi ratios using different targets.
5. Keep service order and protected short-request latency explicit. No dynamic-group throughput result alone proves tenant fairness or an overload admission policy.

## Reviewable result and stop rule

A good output identifies which transition plausibly helps and which state cost remains, cites the exact [LoongServe mechanism/evidence](../notes/loongserve.md), and gives a gated proposal instead of a universal default. Keep the feasible static baseline if current support, transfer/copy path, model-cost calibration or protected latency evidence is missing. Do not implement ESP, migrate state or run a benchmark in this paper-extraction task.
