---
name: optimization-search-policy
description: 'Policy for how an optimization agent should select, order, and stop optimization experiments. Covers candidate generation, exploration vs exploitation, diversity, negative experiment memory, budget allocation, and stopping criteria. Drawn from vllm-evolve (phase-locked optimization round), TRT-LLM casebook (prior-art matching), and SkillOpt (bounded edit + gate). Use when deciding what to try next and when to stop.

  '
---

# Optimization Search Policy

Status: candidate. Source-grounded from vllm-evolve @ 43cc82c,
TensorRT-LLM @ f33e0e5f, SkillOpt @ 343db229.

## Core problem

An optimization agent without a search policy tends to:
- Re-explore the same configuration families (familiar solution bias)
- Escalate experiment cost prematurely (running E2E benchmarks when profiling
  would answer the question)
- Fail to record negative results (causing the same dead ends to be re-entered)
- Commit to a direction before checking prior art

This skill addresses all four.

## Phase-locked optimization round

An effective optimization round has locked phases that cannot be reordered.
Source: vllm-evolve `ar` CLI + PreToolUse hook (enforces phase order at the
tool call level).

```
Phase 1 — Read context
  Inspect: profiling data, existing config, prior experiment records,
  casebook of known wins and failures.
  Do not skip this because you think you know what to try.

Phase 2 — Design a change
  Propose one candidate change. State the hypothesis explicitly:
  "If I change X, metric Y should improve because Z."
  State the evidence that motivates this hypothesis.

Phase 3 — Edit (or configure)
  Apply the change. Bounded: do not change the evaluation protocol,
  measurement setup, or baseline at the same time.

Phase 4 — Verify (correctness)
  Run correctness check before performance measurement.
  A change that breaks correctness is discarded immediately.
  Do not spend benchmarking budget on a broken candidate.

Phase 5 — Evaluate (performance)
  Run the benchmark at the appropriate evidence level
  (see dense-performance-evidence skill).

Phase 6 — Compare (verdict)
  Verdict: better / worse / inconclusive.
  Record the result unconditionally, including negative results.

Phase 7 — Keep or discard
  On "better": integrate and record the win.
  On "worse" or "inconclusive": discard the change, record the failure.
```

After Phase 7, return to Phase 1 with the updated context.

## Candidate generation

Before generating a new candidate, consult:
1. **Prior art (casebook)**: does a known successful optimization apply to the
   current bottleneck class, model, and hardware? If yes, adapt it rather than
   inventing a new approach. The casebook search is recall-complete via
   free-text grep over the full case file bodies — do not limit by structured
   fields before searching.
   Source: TRT-LLM perf-optimization-casebook @ f33e0e5f.

2. **Negative record**: has this specific candidate class been tried and failed
   in this configuration? If yes, the burden of justification is higher —
   something about the conditions must have changed to try again.

   InferRSI's source-linked options are the [Qwen B300 rejection case](../inference-optimization-casebook/cases/qwen-b300-rejected-directions.md),
   [Ascend reported rejection case](../inference-optimization-casebook/cases/qwen-ascend-rejected-directions.md)
   and [Drama3 diagnostic case](../inference-optimization-casebook/cases/drama3-rejected-directions.md).
   First distinguish quality rejection, no demonstrated gain, resource failure,
   confounded control, unintegrated lead and analytical rejection. Match the
   source revision, workload, device and evidence level before drawing a lesson.
   Record the changed condition or unresolved question and the cheapest check
   that can distinguish it. A matching keyword is a lead, not a causal diagnosis
   or an automatic veto; do not exclude a different solution family because one
   implementation failed. The original campaign verdict and pause remain intact.

3. **Stage fraction**: is the target stage actually a significant fraction of
   E2E time? A 20% speedup on a stage that is 5% of E2E yields 1% overall.
   Compute the Amdahl contribution before committing to expensive work.
   Source: performance-ceiling-analysis skill.

## Exploration vs exploitation

**Use prior art as a hypothesis, not a predetermined winner.** Retain a bounded
shortlist of distinct mechanisms with assumptions, uncertainty, expected impact
and evaluation cost. A relevant known recipe may be the cheapest first contrast;
its prior success does not establish superiority in the current workload.

**Diversify mechanisms as well as bottleneck targets.** If local variants fail,
check whether ownership, work elimination, residency, algorithm or configuration
changes address the same measured bottleneck. Re-profile when the limiting stage
moves; do not keep sampling one family solely because budget remains.

**Exploration budget:** reserve a fraction of the experiment budget for
low-cost exploratory runs (single-seed, Tier A, quick profiling) before
committing to full benchmarks. vllm-evolve's architecture uses a "simulation
backend" (not yet implemented at time of writing) for this purpose.
Source: vllm-evolve README @ 43cc82c.

## Negative experiment memory

Every experiment that produces a "worse" or "inconclusive" verdict must be
recorded with:
- The hypothesis that was tested.
- The specific metric that did not improve.
- The hardware/software/workload context.
- The evidence level at which the test was run.
- Whether the failure was due to correctness, no improvement, or high variance.

Do not discard negative results. An optimization that "might work with more
tuning" with no evidence is not a reason to defer recording it as negative.
Source: SkillOpt blog/gating-reflection-safe-updates @ 343db229.

**Negative result → search constraint:** when a hypothesis fails, derive a
constraint from it. Example: "KV cache compression at this sequence length did
not reduce memory traffic (measured: mte2_ratio unchanged at concurrency=4)."
That constraint narrows the remaining search space.

## Cost-aware candidate selection

Not all experiments cost the same. Order candidates by cost-adjusted expected
value:

| Experiment type | Relative cost | When to use |
|-----------------|--------------|-------------|
| Static analysis / config change | Low | To verify correctness, not performance |
| Single-kernel microbench | Low | When the hypothesis is about a specific isolated op |
| Component profiler run | Medium | To identify or confirm a bottleneck class |
| Scenario benchmark (concurrency=1) | Medium | To confirm a win in the simplest case |
| Multi-regime benchmark | High | After a scenario benchmark win, before committing |
| Full production replay | Very high | Only after multi-regime benchmark |

Escalate upward only when a lower cost level returns a positive result that
warrants confirmation at the next level.

## Stopping criteria

Stop local tuning and switch strategy when any of the following is true:

1. **Current-mechanism headroom exhausted:** compare potential removable time
   against the target and locally measured uncertainty. Roofline proximity only
   constrains the stated work/traffic/operation mix; it does not exclude a better
   algorithm. No universal utilization threshold is a stopping rule.

2. **Amdahl ceiling reached:** the Amdahl-estimated maximum E2E speedup from
   all remaining stages together is below the target. Local tuning cannot reach
   the goal; the target itself or the approach must change.

3. **Repeated inconclusive results:** if the last N experiments on the same
   hypothesis all return inconclusive due to measurement variance, either the
   effect is below the noise floor or the measurement protocol is wrong. Fix
   the protocol or move to a different hypothesis. N = 3 is a reasonable
   default.

4. **Negative record saturated:** every plausible candidate from prior art and
   novel generation has been tried and recorded as failed. This is a signal to
   escalate the abstraction level (e.g., change parallelism strategy rather
   than tuning an individual op).

## Budget allocation and final-artifact integrity

Freeze the useful work, quality contract, allowed approximations, timing boundary
and resource budget before search. Preserve a complete restartable incumbent:
code/config identity, launcher, dependencies, cache/initialization state and
correctness evidence. Count distinct measured configurations separately from
restarts, failed probes and repeated recovery attempts.

Prefer controlled contrasts; label coupled changes at candidate level and test
important interactions explicitly. Quality checks and timing-path integrity are
independent: inspect work counts, event boundaries and the actual delivered
artifact. A shortcut outside the authorized semantics is not an optimization.

Reserve finalization time using observed restart, warmup and full-validation
cost, not a paper's fixed percentage. Restore and verify the best fully valid
incumbent through its canonical launcher. Report best-seen and delivered outcomes
separately; a successful probe does not qualify a broken final state.

The [experiment-governance procedure](../performance-ceiling-analysis/references/papers-20261015/govern-optimization-experiments/procedure.md)
and [decision cases](../performance-ceiling-analysis/references/papers-20261015/cases/decision-cases.md)
retain the reviewed A-pack mechanism, costs and limits. InferenceBench's
within-vLLM matched two-hour comparison is separate from its grid of independent
per-engine two-hour searches. None is an InferRSI measurement.

---

## Prior art from related systems

### RRSI — bounded harness proposals and acceptance

Use [RRSI v3 source evidence](references/papers-20261015/references/source-notes.md#f1--rrsi)
for the proposal-cardinality, critic, calibrated noise-floor, token-cost and
structural-novelty mechanisms. These are paper-specific choices, not mandatory
thresholds. Its grouped ablations do not establish each component's causal
benefit. A rejected bundle is not proof that every included mechanism failed.

Name the smallest adaptation unit supported by feedback: case, memory item,
skill, search policy, harness or improver. Preserve hypothesis, diff, outcome,
score distribution and total cost. Distinguish execution failure, valid regression,
noisy tie and loss of selection. A code reviewer can detect explicit leakage but
cannot certify absence of overfitting. Keep a best-ever reference and independent
validation evidence; contextual failures do not create permanent global bans.

[Dream-RSI, AIDE² and JitRL interface records](references/papers-20261015/knowledge/adaptation-interfaces.md)
qualify three other targets. Replay requires a legal action interface, observed
prefix and recorded support; unseen branches need fresh evidence. Action
reranking requires accessible candidate scoring and a trustworthy reward model;
a Markdown procedure supplies neither. Task-solving quality and improver quality
need separate comparisons; AIDE²'s improver experiment remains inconclusive.

The [mechanism comparison](references/papers-20261015/MECHANISMS.md) retains
per-paper benefits, costs and counter-signals. These methodology amendments
implement no controller, evaluator repair, logit interface or autonomous loop.

### CRISP (Critical Step Perception)
Source: https://arxiv.org/pdf/2608.01867
Mechanism: Agent learns to classify each step in an experiment as either "critical" (evidence-gathering that informs the next decision) or "redundant" (confirmatory or exploratory without decision impact). During candidate evaluation, the agent prioritizes critical steps and can defer or skip redundant steps, reducing total experiment cost by 15-33% while maintaining accuracy. The mechanism uses a learned model to identify which measurement or profiling steps actually change the verdict; once a critical step has a clear result, subsequent steps are skipped.
Answers question: (3) How should experiment cost affect candidate selection?
InferRSI adaptation: prioritize the least expensive discriminating regimes for screening. Screening may reject a candidate early; it cannot skip the frozen acceptance regimes or substitute for required service-level evidence. The historical CRISP summary is carried, not re-extracted in this wave; its numerical claim is not a local result or a default budget target.

### Stopping follows the current evidence contract

Use conditional headroom, measurement uncertainty, negative evidence and the
authorized budget together. Preserve no-change when candidates cannot be
separated. Reading these procedures authorizes no execution, framework change,
new resource spending or publication.

### Goal admission and accounting source knowledge

When budget/stop reasoning depends on a Goal's current authority or a repeated
settlement, follow the existing
[RSI evidence owner's LoopX reference](../../workflows/rsi-evidence/references/loopx-goal-governance/README.md).
Use its source/decision/receipt distinctions before selecting another experiment.
That owner retains the mechanism and counterexamples; this search policy does
not duplicate its accounting rules or turn a local quota into a provider cost
cap. Runtime and agent-effect validation remain `not_run`.
