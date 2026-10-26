---
name: inference-benchmark-design
description: 'Select task quality gates, reference parity checks and performance workloads for text, agentic coding, work agents, TTS, full-duplex audio/video, image and video inference. Covers AIPerf AgentX/Exgentic replay, vLLM/SGLang benchmark boundaries, SLO-aware metrics and InferRSI integration.'
---

# Inference Benchmark Design

Status: candidate. Source-grounded from vllm-evolve @ 43cc82c and
InferRSI evidence framework @ 4c8e1285.

## Select the task and its evaluation contract

Read [task-specific benchmark selection](references/task-benchmark-selection.md)
when choosing quality evaluators, reference parity and a performance workload.
It covers text, agent replay, TTS, three full-duplex task families, images and
videos, with pinned provenance from InferRSI issue #60. Use the
[command templates](references/benchmark-commands.md) for entry points and a
bounded HTTP smoke. These references are candidate knowledge, not qualification
of every model or backend.

Freeze one primary objective, timing boundary, quality gates and sample/failure
accounting before optimization. Recorded agent task scores and replay completion
do not establish current task success; a VBench prompt workload does not compute
VBench quality. Missing coverage stays INCONCLUSIVE. Numeric gates and required
workload regimes are campaign choices, not repository-wide defaults.

## Core principle: goodput over throughput

Raw throughput (tokens/second, frames/second) is misleading because a system
can maximize throughput by accepting requests it then fails to serve within
the user's latency expectation. The meaningful metric is goodput: the rate of
requests that complete AND meet the declared SLO.

```
goodput = (requests completed within SLO) / time
```

A candidate that improves raw throughput by trading latency away cannot "win"
under a goodput metric if it causes SLO violations.
Source: vllm-evolve README @ 43cc82c.

## Workload regimes to select for the campaign

A single benchmark run at one concurrency level does not characterize serving
performance. These source-derived regimes answer different questions; choose
the required set from the deployment use case and freeze it before comparison:

| Regime | Load level | What it answers |
|--------|-----------|----------------|
| Throughput | Saturating load, with observed bottleneck and queue state | Max sustainable goodput at peak load |
| Latency | Low load | Responsiveness for latency-sensitive workloads |
| Replay | Real or representative trace | Behavior under actual production burstiness |

An optimization may improve one regime while degrading another. Report all
required regimes separately; do not aggregate into a single score without disclosing
how the aggregation was done.

For replay, standard trace sources (from vllm-evolve): BurstGPT, Azure,
ShareGPT, Mooncake. Use the trace that matches your actual deployment pattern.

## Verdict semantics

The upstream vllm-evolve comparison labels are:

| Verdict | Condition |
|---------|----------|
| better | Improvement in all required regimes, no regression in any |
| worse | Regression in any required regime |
| inconclusive | Too noisy to distinguish (see below) |

These labels are not InferRSI's verdict enum. InferRSI uses PASS / FAIL /
INCONCLUSIVE and the campaign's frozen gates. `high_variance_inconclusive`
is a useful diagnostic reason: it means the
measurement signal is not strong enough to support a claim in either direction.
Do not report an inconclusive result as a win. Record it as INCONCLUSIVE and
note the variance level.
Source: vllm-evolve README @ 43cc82c.

## Statistical requirements

Freeze repetition count, workload seeds and the decision rule in the campaign.
The upstream guidance recommends multiple seeds and median goodput with IQR or
range. State whether a repetition changes the workload seed or repeats identical
inputs. If using `max - min > threshold × median` as a noise gate, choose the
threshold in the acceptance plan; this skill defines no universal numeric bar.
InferRSI's built-in median/range summaries are descriptive, not a significance
test or automatic enforcement of that noise gate.

The decision of which regimes must improve and which must not regress is the
caller's policy, not the benchmark's. Encode it in a decision config file
(`decision.yaml` in vllm-evolve) so it is explicit, versioned, and auditable.

## Audit a supplied fixed-workload report

Preserve the request-to-trial grouping and every observation covered by the
contract. Late requests and outliers remain included unless the frozen protocol
explicitly excludes them; retain exclusion and failure counts. Apply aggregation
in the declared order: a median of per-trial request means uses every included
request to calculate each trial mean, then takes the median across trials. A
pooled request median is a different statistic, especially with unequal trial
sizes. If the report omits an aggregation rule that changes the verdict, expose
that ambiguity rather than choosing one after seeing the result.

For a lower-is-better metric with a positive baseline, calculate percentage
reduction as `100 * (baseline - candidate) / baseline` and compare it with the
declared threshold before rounding. Check workload equivalence, output quality
and completion evidence separately from this arithmetic. Report the computed
threshold result and any missing evidence under the frozen contract's verdict
semantics; an attractive aggregate alone does not establish an accepted gain.

## What must be pinned before comparing two runs

Every valid A/B comparison requires these to be identical:
- Hardware (exact device SKU, driver version, firmware).
- Software stack (framework version, model weights revision).
- Input distribution (same trace or same generation config and seed).
- Benchmark configuration (concurrency levels, SLO thresholds, timeout).
- Warmup (same warmup protocol, excluded from measurement).
- Measurement protocol (same window duration, same number of seeds).

If any of these differ between the baseline and candidate run, the comparison
is invalid. "Same hardware class" is not the same as "same device."

## Shared-machine measurement discipline

On shared infrastructure (multiple users, shared GPU/NPU allocation):

- Cross-window comparison is invalid. Run baseline and candidate within the
  same time window (interleaved or back-to-back in the same allocation).
- Record neighbor load state before each run. If it changes between runs,
  report the comparison as potentially confounded.
- Dedicate devices: do not share GPU devices between the baseline server and
  the candidate server in the same comparison run.

Source: MindIE-SD perf-gate skill @ 8481d39b (window discipline for NPU).

## What a benchmark cannot prove

- A benchmark win at one concurrency level does not imply a win at other
  concurrency levels.
- A benchmark win with synthetic traces does not imply a win under real
  production traffic.
- A benchmark win on one model does not transfer to other models without
  re-running.
- A benchmark win on one hardware SKU does not transfer to other SKUs.
- Microbenchmark improvement does not imply E2E benchmark improvement.

State these scope boundaries explicitly in any report that cites benchmark
results.

## Search integrity and final-state verification

Freeze workload hashes, output/work semantics, permitted approximations, quality
checks, timing events and developer-versus-held-out splits. Verify that measured
work actually occurs; a quality pass does not certify a truthful timing path.
Keep fast probes separate from full evaluation, and preserve invalid, failed and
inconclusive trials. A simulator shortlist requires calibrated load/capacity
coverage and does not replace measurements.

Compare search methods at matched total budgets. Separate search/API cost from
steady-state serving cost; independent per-engine searches are not one equal-budget
engine-selection run. Keep different SLOs, baselines, resources and aggregation
rules explicit. Before reporting, restart the final code/config artifact and
validate that exact state; report best-seen results separately from delivered ones.

[Reviewed experiment discipline](../performance-ceiling-analysis/references/papers-20261015/govern-optimization-experiments/procedure.md)
and [source audit](../performance-ceiling-analysis/references/papers-20261015/references/inferencebench.md)
retain author-reported evidence and counterexamples. No local experiment is
established by integrating these notes.

## Evidence trail requirements (InferRSI compatibility)

A benchmark campaign that claims PASS under InferRSI's evidence framework
must produce:
```
evidence/<campaign-id>/
  plan/
    hypothesis.md         # what is being tested and why
    runspec.json          # frozen RunSpec (repo × revision × backend × device × model × scenario)
    slo.yaml              # declared SLO and threshold
    decision.yaml         # which regimes must improve / must not regress
  results/
    regime-throughput/    # raw metrics, logs, per-seed records
    regime-latency/
    regime-replay/
    verdict.json          # PASS / FAIL / INCONCLUSIVE with reasons
  patch/
    candidate.patch       # the exact change being evaluated
  validator/
    validate.py           # frozen validator script
```

A run without a frozen RunSpec is INCONCLUSIVE regardless of the metric values.
A run whose validator was modified after the plan was frozen is INCONCLUSIVE.
Source: InferRSI AGENTS.md and rsi-evidence skill @ 4c8e1285.

## Scoped internal experience

Read the single authoritative [admission/drain occupancy case](../inference-optimization-casebook/cases/admission-drain-occupancy.md) when interpreting finite service cohorts. It separates recorded observation, action and interpretation; phase-selected occupancy is not end-to-end gain. The original frozen evidence remains linked, not copied. This shared reference is included in the packaged skill library; standalone folder export is not supported.
