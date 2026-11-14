---
name: dense-performance-evidence
description: 'Taxonomy of performance evidence an optimization agent needs, ordered by collection cost and diagnostic power. Maps evidence types to the questions they answer and the claims they can support. Use to decide which evidence to collect next, avoid over-claiming from cheap evidence, and structure a measurement campaign.

  '
---

# Dense Performance Evidence Taxonomy

Status: candidate. Source-grounded from TensorRT-LLM @ f33e0e5f and MindIE-SD
@ 8481d39b.

An optimization agent must not conflate different evidence levels. This skill
defines what each level proves and what it cannot prove.

## Evidence hierarchy

Listed from cheapest to most expensive to collect.

### Level 0 — Correctness

**What it is:** Output matches expected (test pass, md5 match, output schema valid).

**What it proves:** The change does not break the declared output contract.

**What it does NOT prove:** Any performance claim. A change can pass all tests
and be slower. An md5 match does not mean the output is semantically correct
(it could match a wrong baseline).

**When to collect:** Always, before any performance measurement.

**Key discipline:** md5 ≠ correct output. Verify the content of the output,
not just its hash.
Source: `perf-gate/SKILL.md` @ 8481d39b (§md5-blind-spot).

### Level 1 — Microbenchmark

**What it is:** Single-kernel or single-operation timing with controlled inputs,
warmup, and repetitions. Examples: CUDA event timing, torch.utils.benchmark,
CANN single-op timing.

**What it proves:** Whether a specific low-level operation is faster in isolation.

**What it does NOT prove:** E2E inference throughput. A kernel that is 20% faster
in isolation may have no E2E impact if it was not on the critical path, or may
be masked by a different bottleneck.

**Required for a valid claim:** pinned input shape/dtype, warmup excluded,
≥10 repetitions, hardware synchronized before timing, reported as median ± IQR.

**Common mistake:** reporting microbench improvement as inference throughput gain.
Source: TRT-LLM AGENTS.md ("Microbench ≠ service/E2E gain").

### Level 2 — Component profile

**What it is:** Profiler output over a representative workload. nsys timeline
(system-level), ncu (kernel-level), CANN msprof/torch_npu.profiler. Shows:
- Per-kernel time distribution
- SOL% (speed-of-light %) or AI Core utilization ratio
- Memory bandwidth utilization
- Communication time and overlap

**What it proves:** Which kernel or stage is the bottleneck, and whether it is
compute-bound vs memory-bound.

**What it does NOT prove:** E2E serving throughput under real load patterns
(batching, queueing, request mix, concurrent users).

**Metrics that are reliable:**
- Kernel call counts (reproducible across runs)
- Aggregate time fractions (reproducible within a session)
- SOL% or utilization ratios (reproducible within a session)

**Metrics that are NOT reliable across devices or sessions:**
- Absolute kernel duration in ms (may vary ±10% device-to-device)
- Single collective communication latency (may vary ~2× device-to-device)
Source: `profiling-analyze/SKILL.md` @ 8481d39b (§reproducibility).

### Level 3 — Isolated scenario benchmark

**What it is:** End-to-end benchmark on a fixed workload (single prompt, fixed
concurrency, fixed sequence length). Produces: throughput tokens/s or frames/s,
TTFA, latency percentiles.

**What it proves:** That the optimized system is faster on this specific workload
under these specific conditions.

**What it does NOT prove:** Performance under production traffic (variable
concurrency, mixed request sizes, burstiness). A win at concurrency=1 may
reverse at concurrency=8 if the optimization creates a new bottleneck under load.

**Required for a valid claim:** same hardware, same software stack, same model
revision, same input distribution, ≥3 repetitions, alternating A/B/A order to
detect drift.

### Level 4 — Multi-regime serving benchmark

**What it is:** Benchmark across multiple workload regimes: throughput-saturating
load, low-concurrency latency-sensitive load, and replay of real trace.

**What it proves:** That the optimization improves goodput (requests that complete
within SLO) across realistic conditions without regressions in any regime.

**What it does NOT prove:** Production behavior (hardware differences, actual
traffic distributions, long-run stability).

Source: `vllm-evolve/README.md` @ 43cc82c (§candidate-scoring: goodput across
throughput/latency/replay regimes, `high_variance_inconclusive` if too noisy).

### Level 5 — A/B production experiment

**What it is:** Controlled experiment in a live serving system, comparing a
baseline and candidate on real traffic.

**What it proves:** Actual production impact, including all second-order effects
not captured in benchmarks.

**Collection cost:** Very high. Requires production infrastructure, traffic
splitting, and statistical power.

## Claim-evidence matching

| Claim | Minimum evidence required |
|-------|--------------------------|
| "Kernel X is memory-bound" | Level 2 (SOL%, AI ratio) |
| "Op Y is the bottleneck" | Level 2 (kernel time fraction) |
| "Change Z improves microbench by N%" | Level 1 (microbench with controls) |
| "Optimization improves throughput at concurrency=1" | Level 3 |
| "Optimization improves throughput under production load" | Level 4 |
| "Optimization is safe to deploy" | Level 3 (no regression) + Level 0 |
| "Optimization improves production KPIs" | Level 5 |

An optimization agent should always state which evidence level supports each
claim and avoid upgrading a lower-level result to a higher-level claim.

## Methodology cost and evidence boundaries

For skill/search methods, keep source fidelity, static usability, execution
correctness, behavioral efficacy and transfer as separate checks. Record build,
selection, deployment-context and downstream-task cost separately. State whether
reported changes are absolute points, relative gains, geometric means or rates
with conditional denominators. Preserve worse metrics and per-task regressions;
a shared task budget alone does not prove equal total cost. An unresolved source
protocol/denominator mismatch stays unresolved.

[Paper-method comparison](../../workflows/npu-skill-factory/references/papers-20261015/COMPARISON.md)
and [protocol details](../../workflows/npu-skill-factory/references/papers-20261015/references/protocol-details.md)
provide the reviewed evidence; neither upstream scores nor local packaging checks
promote an InferRSI candidate. For performance predictions, distinguish physical
bounds, observed envelopes, simulator predictions and measured application results
as in [ceiling analysis](../performance-ceiling-analysis/SKILL.md).

## Collection escalation rule

Collect Level 0 before anything. Then:
- Start with Level 2 (profiler) to identify the bottleneck before implementing.
- Only escalate to Level 3 after a promising Level 2 result.
- Only escalate to Level 4 if Level 3 shows a win worth validating across regimes.
- Do not collect Level 1 unless the question is specifically about an isolated
  kernel and Level 2 has already confirmed it is the critical path.

## Evidence for negative results

Negative results (changes that do not help) are as valuable as positive ones.
Record them with:
- The hypothesis that was tested.
- The evidence level collected.
- The specific metric that did not improve (or regressed).
- The hardware/software/workload context.
- The reason the hypothesis was wrong (if known).

Do not discard negative evidence. It prevents re-exploring the same path and
bounds the search space for future candidates.
Source: SkillOpt blog/gating-reflection-safe-updates @ 343db229 (negative
evidence preservation in rejected edit records).

## Scoped internal experience

Read the single authoritative [admission/drain occupancy case](../inference-optimization-casebook/cases/admission-drain-occupancy.md) when interpreting finite service cohorts. It separates recorded observation, action and interpretation; phase-selected occupancy is not end-to-end gain. The original frozen evidence remains linked, not copied. This shared reference is included in the packaged skill library; standalone folder export is not supported.
