# Infera serving-search provenance

Status: source-derived candidate; empirical validation `not_run`.

Use this reference when an Infera serving-tuner result supplies a configuration
shortlist. The [source record](source-record.json) owns the fixed revision,
selected readset, source hashes, rights and evidence limits. This is an
implementation example for the existing calibration and search procedures;
it supplies no local ranking, model-quality or service result.

## What the selected source establishes

### Follow fidelity through the actual command

The inference branch has a deterministic seed stage followed by an optional LLM
continuation. It constructs its own evaluator; the training branch's
`--profiling-mode` selection is not forwarded by that inference entry.
Within the serving evaluator, `dry` synthesizes metrics and returns before the
real-projector path. Other modes may use the analytical model, a cached/forced
benchmark artifact, or a requested live benchmark. Inspect the actual emitted
command and artifacts: the result is initialized with `source="inference"`
before those branches, so that label does not identify its fidelity.
([CLI](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/cli.py#L122-L220),
[evaluator](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/evaluator.py#L954-L1067))

| Retained input or dispatch | Evidence it supplies | Limit |
|---|---|---|
| Dry evaluator | Synthetic loop-exercise metrics | Neither prediction fidelity nor measurement |
| Analytical projector | Modeled target metrics | No measured attainable result |
| Measured anchor consumed by the projector | An observed calibration input plus a transported target prediction | The target configuration is still projected; record measured and target shapes separately |
| Fresh benchmark artifact | Measurement of the artifact's recorded execution conditions | Subsequent projected metrics and analytical memory are separate evidence |

The anchor documentation explicitly keeps memory analytical and distinguishes
anchor-defining execution regimes from transported dimensions. Preserve model,
engine/kernel, dtype, graph/speculation settings, hardware/topology, calibration
shape and target shape. Do not infer compatibility or a target measurement from
an artifact filename, cache hit or benchmark counter.
([Anchor contract](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/manual/simulation/anchors.md#L55-L109),
[command selection](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/evaluator.py#L698-L715))

### Separate the deterministic comparator from its continuation

`--seed-only` / `--no-agent` runs the deterministic initial configuration sweep.
The LLM stage continues with the same history and evaluator unless skipped or
unavailable. This seed sweep is a configuration-search stage; repeated random
seeds for measurement are a different control. A run that only produces seed
results has not demonstrated an LLM contribution.
([Stage dispatch](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/cli.py#L160-L220),
[seed construction](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/inference_tuning.py#L776-L855))

### Keep evaluated rejections with the selected result

Both seed and agent paths append returned evaluation results before selecting
the best legal score. The JSONL stores configuration, result, source, timestamp
and notes; results carry rejection reason and, after a projector call, command,
return code, duration and an output tail. The final best-summary JSON is a
selection view, not the full trial record. Loading appends valid rows, records their configuration signatures and skips
malformed/incomplete lines. The signature set lets later seed/agent calls skip
configurations already evaluated; it does not remove duplicate stored rows. Retention therefore covers the evaluated
results written by these paths, not every proposed or prefiltered candidate.
([History](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/history.py#L16-L92),
[seed retention and selection](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/cli.py#L173-L263),
[agent retention](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/inference_agent.py#L328-L366))

### Check which metrics actually reach ranking

The tuner parses scalar performance labels and scores a named objective with
its direction. The launcher prints those labels before an optional
discrete-event simulation (DES), which prints a separate mean/p50/p90/p99 table.
The inspected tuner parser does not read that percentile table. This source-flow
observation means that forwarding a workload-file or length-spread option does
not establish that the tuner objective or SLO gate uses trace-tail metrics.
([Parser](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/inference_tuning.py#L1394-L1519),
[scalar print and DES entry](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/core/projection/inference_projection/launcher.py#L989-L1043),
[percentile format](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/core/projection/inference_projection/launcher.py#L463-L511))

The SLO helper checks recognized, present scalar values. Missing metrics and
unknown SLO keys produce no violation, as its source tests explicitly document.
Thus `legal=true` is insufficient evidence that every intended constraint was
evaluated. It also cannot establish a tail-latency or service guarantee.
([SLO helper](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/evaluator.py#L1360-L1385),
[unexecuted test definitions](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/tests/unit/projection/test_tuning_slo.py#L55-L61))

## Proposed audit and ranking-calibration plan

These are checks for a later authorized study, not checks executed by this
reference or a supplied runner.

1. Freeze the source/runtime/model, hardware and serving regime; retain workload
   and anchor content identities. Record whether each reported quantity is
   synthetic, analytical, anchor-assisted or measured, using actual dispatch and
   artifact evidence. Preserve original results rather than relabeling them.
2. Freeze useful work and quality controls before comparing seed-only with an
   LLM continuation. Match objective/direction, latency definitions, constraints,
   starting history, evaluation fidelity and available evaluation cost. Account
   for seed work, repeats, rejected trials and LLM time/tokens/cost separately;
   equal proposal counts do not establish equal total cost.
3. Retain the full trial JSONL, relevant workload overlays, full available logs
   and anchor references alongside the best summary. Count evaluated results,
   skipped duplicates, prefiltered proposals and unreadable rows separately.
   Distinguish execution failure, modeled infeasibility, missing data and a
   valid measured regression; the search's `legal` flag is not a campaign verdict.
4. Bind ranking validation to a fixed trace or workload distribution. Preserve
   arrivals, input/output lengths, concurrency, prefix semantics, measurement
   window and metric numerator/denominator. A length/arrival file lacks the block
   hashes that drive content-addressed cache reuse; an analytical hit-rate
   assumption is not observed trace reuse. Total-token and decode-only
   throughput, fleet totals and per-GPU rates are different objectives.
   ([Workload semantics](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/manual/simulation/workloads.md#L11-L123),
   [metric denominators](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/agents/tuning_agent/inference_tuning.py#L1423-L1518))
5. Compare a bounded predicted shortlist with independent observations of the
   same candidates and required quality/SLO metrics. Keep predicted ranks,
   observed ranks, constraint coverage, rank reversals, unresolved ties and
   calibration-domain gaps visible. Select numeric gates in that study before
   search; this source reference supplies none. Withhold a calibrated ranking
   or agent-benefit conclusion when comparable observations are missing.

## Source conflict and remaining limits

The pinned boundaries manual says disaggregation has no independent event
queues. The same revision's `simulate_disaggregated` has separate prefill/decode
queues and clocks and is selected by `run_des` for an enabled split. Do not carry
the stale negative capability claim into a decision. This static countercheck
does not validate those queues' fidelity or any P/D deployment.
([Stale text](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/manual/simulation/boundaries.md#L53-L55),
[split state](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/core/projection/inference_projection/des.py#L2355-L2365),
[split dispatch](https://github.com/AMD-AGI/Infera/blob/ff1136e4a51998eba2933ed63cfb9c10120f86ea/infera/projection/core/projection/inference_projection/des.py#L3073-L3145))

No upstream code or tests, model/device/service run, ranking calibration or
agent comparison was executed for this reference. Precision and speculation
choices still need independent quality controls. Source rights cover the
selected original repository material; dependencies, models, traces and other
assets have separate rights. The source record retains that boundary.
