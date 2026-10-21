---
name: inference-optimization-casebook
description: 'How to structure and use a casebook of past optimization decisions as a decision-support tool. Extracts the casebook pattern from TensorRT-LLM''s perf-optimization-casebook skill. Use when building a record of optimization experiments or when deciding which optimization to try next based on prior art.

  '
---

# Inference Optimization Casebook Pattern

Status: candidate. Source-grounded from TensorRT-LLM @ f33e0e5f,
`perf-optimization-casebook/SKILL.md`.

## What a casebook is

A casebook is a queryable record of past optimization decisions: what worked,
what failed, under what conditions, at what cost, and with what evidence.
It is reference material, not a coordinator. It does not run profiling or
make decisions — it informs them.

The casebook pattern is valuable because:
- Optimization search is expensive; prior art prevents re-exploring dead ends.
- Successful patterns generalize across models and hardware generations.
- Failure modes generalize too: knowing that a technique fails under certain
  conditions is as valuable as knowing when it succeeds.

## Case structure

Each case record should contain:

```yaml
name: <short slug>
bottleneck_class: [compute | memory | launch | communication | sync | host]
signals:           # conditions that suggest this case applies
  - model_arch: <decoder LLM | diffusion | MoE | audio>
  - hardware: <GPU gen | NPU model>
  - symptom: <e.g., "high mte2_ratio, low mac_ratio">
  - config: <e.g., "TP>1, sequence length > 4096">
mechanism: |       # what the optimization does at the hardware/algorithm level
applies_when: |    # specific conditions required for the optimization to help
does_not_apply: |  # conditions where this case is known to fail or be neutral
how_to_apply: |    # step-by-step procedure to apply the optimization
expected_effect: |  # direction and rough magnitude of expected improvement
accuracy_risk:     # what quality/correctness guarantees may be affected
verification: |    # how to confirm the optimization worked
rollback: |        # how to undo the change safely
evidence:          # what real measurement evidence supports this case
  - run_id: <evidence campaign ID>
    verdict: [PASS | FAIL | INCONCLUSIVE]
    hardware: <exact SKU>
    model: <exact revision>
    workload: <benchmark config>
    result: <metric before → metric after>
```

Source: TRT-LLM casebook case-template.md @ f33e0e5f.

## Query protocol

**Always use free-text grep first.** The casebook search is recall-complete via
grep over the full case body text. Do not pre-translate the query into canonical
vocabulary before searching — that narrows recall. Search for natural terms:
model name, knob, mechanism word, deployment feature.

```bash
# Good: natural query, whole-body search
grep -ril "quantization" cases/
grep -ril "sequence parallel" cases/
grep -ril "vae decode" cases/

# Then rank by frontmatter signals if multiple hits
grep -ril "mte2_ratio" cases/ | xargs grep -l "memory-bound"
```

Structured fields (bottleneck_class, signals) are for ranking among hits,
not for bounding the search. A synonym or colloquial term in the body text
would be missed by a structured-field-only query.
Source: perf-optimization-casebook @ f33e0e5f, §how-to-use.

## Recorded diagnostic options

Current owner-local records retain rejected directions alongside their limits:

- [MiniCPM-o speaker extraction](cases/minicpm-speaker-cpu-reference.md): CPU
  graph optimizer semantics, short-input numerical rejection and component/service boundaries.

- [Qwen B300](cases/qwen-b300-rejected-directions.md): full-image rejection,
  graph/copy overhead, unintegrated leads and confounded trials.
- [Qwen Ascend](cases/qwen-ascend-rejected-directions.md): reported OOM,
  attention/cache alternatives and missing gain on one 910B1 cohort.
- [Drama3 B300](cases/drama3-rejected-directions.md): invalid controls,
  correct kernels without service gain, prefix reuse and analytical rejection.

Each `.json` sibling owns identity, origin, source pins and limitations; the
Markdown owns the observation and suggested revisit check. Read them as
diagnostic options, not a permanent blacklist. A discarded implementation does
not rule out another implementation of the same mechanism. A confounded run,
missing experiment and failed gate are different evidence states.

Before retrying, state which condition changed or which uncertainty a bounded
check will resolve. Preserve the original result, run an unchanged control and
choose the least expensive discriminating check. Only new complete evidence can
qualify a new scope; reading these records does not reopen a paused campaign.

## Adapt, do not copy

A case is a precedent, not a guaranteed config. The procedure and expected
direction are reusable; the specific values (batch size, tensor parallelism
degree, kernel parameters) must be re-derived for the current model and hardware.
Before applying: read the nearest checked-in config and the model's deployment
guide. After applying: measure. The precedent's expected direction of effect
does not substitute for measurement.

## When to add a new case

Add a case when:
- A change produced a verified win or a clear, reproducible failure.
- The mechanism generalizes to other models or hardware.
- The prior-art record would have prevented wasted work.

Do NOT add a case for:
- INCONCLUSIVE optimization-effect claims (not enough evidence to characterize
  the effect). Keep the original campaign verdict and do not manufacture a
  PASS; a scoped diagnostic observation may still be recorded with its
  INCONCLUSIVE verdict and stated configuration boundary.
- Results that only apply to one specific configuration with no plausible
  generalization, unless they are scoped diagnostic observations that state
  their configuration boundary.
- Results without a real measurement evidence trail.

## Maintaining the casebook

The casebook is only valuable if it stays accurate. When a case's conditions
no longer hold (hardware generation changed, the op was fused away, the
optimization was upstreamed), mark the case as deprecated with the reason.
Do not delete deprecated cases — they remain as negative evidence for future
searches.

## Starting a casebook for a new system

For a new inference system (e.g., a new NPU inference engine), bootstrap the
casebook from:
1. Existing profiling evidence in the repository (`evidence/` tree).
2. Known bottleneck patterns from vendor documentation.
3. Cross-system cases from TRT-LLM, vLLM, SGLang that have plausible NPU analogs
   (re-verify the mechanism holds on the target hardware before including).

Mark each bootstrapped case's evidence as `source_grounded` or `author_reported`
until a local measurement confirms or refutes it.
