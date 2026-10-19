---
name: calibrate-serving-simulation
description: Build an evidence-gated serving-configuration shortlist from a profiled simulator while separating empirical predictions from physical bounds and near-capacity queueing risk.
---

# Calibrate a serving-simulation shortlist

Use when simulation or a cost model is proposed to reduce deployment experiments. This candidate extends existing `performance-ceiling-analysis`, `optimization-search-policy` and `inference-benchmark-design`; it does not replace their ceilings or measurement contract. Reading this skill does not authorize execution; follow the current task's scope.

## Inputs and prerequisites

Require model/shape/dtype, actual kernel/runtime revision, graph mode, GPU/host/topology, request length and arrival distribution, total resources/cost basis, memory limits, latency definitions and percentile SLOs. Read [Vidur evidence](references/source-notes.md) and [evidence types](references/source-notes.md). If any essential identity is missing, mark that dimension unknown rather than borrowing a paper default.

## Procedure (P)

1. Classify each estimate: physical feasibility bound, measured attainable envelope, Amdahl-style conditional impact, or empirical prediction. Never label learned runtime output a bound.
2. Build operator dependency signatures: current tokens; phase and context-length distribution; KV bytes; communication payload plus topology. Keep prefill and decode separate. Record how sharding and memory planning enter the model.
3. Record calibration domain and held-out coverage. Preserve skewed attention cases, small-model host overhead and tile/shape transitions. If the predictor relies on summed KV volume, challenge batches with equal volume but unequal context distributions.
4. Validate plans must distinguish operator/iteration errors from static normalized execution time and dynamic E2E/queue delay. Include the intended load regime and capacity boundary; do not substitute a low-load check for an SLO claim. No checks are run under this skill without separate execution authorization.
5. Enumerate feasible configuration families under total resource cost and memory budgets. If using capacity binary search, verify the empirical monotonic/stationary premise and define its scheduling-delay threshold. Treat overloaded samples explicitly.
6. Filter on all latency/quality constraints together. Retain nondominated alternatives and uncertainty bands, including differing mechanisms, rather than one predicted winner. If uncertainty exceeds rank separation, label the ordering unresolved.
7. Produce a small future-measurement shortlist whose trials discriminate among competing explanations. Recalibration triggers include workload drift, kernel/graph/runtime changes, new hardware/topology and mismatched residuals.

## Output

A bounded decision memo: input identities; model assumptions; evidence type; exact metrics/denominators; unsupported dimensions; candidates and predicted ranges; joint constraint checks; next discriminating trial; rollback/finalization requirements. Prediction and measurement columns must not be conflated.

## Failure / stop conditions

Stop predictive certification if profiles are missing, topology is substituted, error grows near capacity, or host overhead is omitted. Do not assert universal error below9%: Vidur AppendixA has12.65% maximum error in a specified near-capacity case. Do not claim current vLLM, asynchronous PP or NPU support from this historical simulator paper.

## Resource contract

This folder and its local `references/source-notes.md` are sufficient for selective consumption. Optional comparison notes and cases are linked through the owning ceiling skill; the local source notes retain the calibration procedure's evidence and limits. Existing InferRSI skill names above are reconciliation targets, not runtime dependencies.
