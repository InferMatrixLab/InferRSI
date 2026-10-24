# Prospective acceptance freeze — owner review draft

Status: INCONCLUSIVE / NOT ACTIVATED. Governing acceptance Issue #67.
Prepared 2026-10-23. Nothing here changes a historical result or authorizes
performance search. The owner-approved diagnostic cap is separately recorded
in diagnostics/fp8-graph-takeover.md.

## Existing accepted requirements

Same physical allocated H20-family GPU, same official FP8 model/tokenizer,
vLLM 0.32.0 default optimizations, the pinned official streaming client,
concurrency one, no prefix reuse. Exact input lengths 8192/65536/131072,
ten distinct fixed inputs each, exactly 2048 generated tokens, three paired
repetitions with alternating arm order. Every length must satisfy both
candidate/baseline TTFT and TPOT <= 1.03. No averaging across lengths.
Final task-quality datasets and one-percentage-point score floor remain as
specified in #67. No W8A16 substitution, truncation or reduced-work acceptance.

## Proposed statistical rule — requires owner confirmation

- Pair each input and repetition across arms (30 pairs per length).
- Primary statistic for each metric/length: median of the 30 paired ratios.
  Publish all raw measurements, arm medians, paired ratios and p10/p90.
- Resample the ten input IDs as clusters, retaining all three repetitions
  within each chosen ID: 10,000 bootstrap samples, seed 670032, percentile
  quantiles with linear interpolation. Retain the 95th percentile as a
  one-sided upper uncertainty bound. This is a proposed handling of sampling
  variation, not a claim that ten inputs establish general production behavior.
- Complete valid results: primary ratio > 1.03 means FAIL for that metric.
  Primary ratio <= 1.03 but upper bound > 1.03 means INCONCLUSIVE; both
  <= 1.03 permit the scoped metric gate to pass. Missing/error/timeout requests,
  changed environment or an unqualified correctness path mean INCONCLUSIVE,
  never a performance PASS. Predeclared correctness failures remain FAIL.
- Freeze exact commands, source hashes, order, warmup and restart policy
  before baseline measurement. Do not add repeats or remove outliers after
  seeing results. Startup/JIT/warmup are separately recorded and excluded;
  timed requests use the same warmup policy in both arms.

## Proposed retrieval construction — baseline then owner confirmation

- Ten fixed synthetic inputs at each required length; four distinct key/value
  targets near 10/35/65/90 percent of actual token positions, with decoys.
- Authenticate exact token lengths, positions, identities and expected strings
  before baseline. Ask for all four values; freeze extraction before scoring.
- Report both complete-case accuracy (all four exact) and per-position counts.
- Proposal: the baseline must solve at least 9/10 complete cases per length;
  otherwise the set is not qualified. Candidate complete-case counts and each
  position count must be no lower than the matched baseline at that length.
- Baseline qualification and owner approval precede candidate search. Do not
  silently regenerate hard cases or alter extraction after observing outputs.

## Prior-art-first implementation queue

Each item is a separate model-plane hypothesis, after correctness and freeze:

1. Adopt the vLLM 0.32.0 FP8 dispatch design: FlashInfer small-M blockscaled
   GEMM, DeepGEMM large-M branch, with exact dtype/scale-layout checks and
   logged actual selected callables. Preserve official W8A8 semantics.
2. Replace quadratic materialized attention with an upstream fused attention
   implementation supporting actual sequence lengths and graph capture.
   This is also required for meaningful 64K/128K feasibility on one GPU.
3. Adapt vLLM's GDN prefill / recurrent decode / causal convolution fusion and
   state ownership. Preserve FP32 recurrent state and checkpoint semantics.
4. Consider projection and normalization fusion only after measuring remaining
   service bottlenecks. BF16-only historical fusion is not an FP8 result.

Every attempted/rejected/inconclusive variant retains source, environment,
raw outcomes, cost and a candidate knowledge record. No automatic promotion.

## Proposed allocated GPU budget — hard caps, not a completion promise

| Stage | Proposed cap | Work and stop rule |
| --- | ---: | --- |
| Readiness and baseline qualification | 2 GPU-hours | Correctness follow-up, bounded long-context feasibility, source/client/model checks and measured runtime estimation. Stop on unsupported lengths or invalid timing. |
| Frozen baseline measurements | 4 GPU-hours | Performance matrix, full matched task-quality baseline and retrieval. Reuse outputs only under identical declared identities. |
| Candidate search | 8 GPU-hours | Prior-art-first operator/model screening and small service contrasts; include failed jobs and JIT. No final-set tuning. |
| Finalization reserve | 30 GPU-hours | Clean delivered restart, full performance/quality/retrieval gates, raw accounting and cleanup. Do not spend this reserve on search. |
| Total new authorization requested | **44 GPU-hours** | Sequential single-GPU jobs by default; allocation count times elapsed time, including idle allocated time. |

The earlier DSH estimates are not adopted as approvals. For scale only, its
566,000-token quality estimate at the observed 9.1 tokens/s is approximately
17.3 hours of generation, before loading/prefill/scoring. The full performance
matrix generates 184,320 tokens per arm; an 88 ms TPOT corresponds to about
4.5 hours of decode for one arm, excluding prefill. These measurements used
different paths and are cost scenarios, not matched performance results.

The maximum quality workload is 2,483 * 2,048 = 5,085,184 generated tokens per
arm. At 9.1 tokens/s that alone would take approximately 155.2 hours. Therefore
44 GPU-hours cannot guarantee completion if outputs approach the cap or current
slow paths persist. Recompute stage costs after readiness using actual lengths
and launch/prefill measurements. If a stage cannot finish within its cap, stop
and present the revised itemization before allocating more; preserve every
partial result as INCONCLUSIVE. Do not reduce workload or relax gates to fit.

Owner decision, 2026-10-23: **44 GPU-hours approved as a phased total cap**, with
the four stage caps above. This is prospective authority; the prior 147-second
diagnosis was separately approved and remains recorded. Budget approval does
not approve the proposed statistical/retrieval gates or activate a freeze.
Candidate search remains blocked until baseline qualification,
retrieval/statistical approval, identity binding and validator/freeze activation
are all complete. Re-budgeting a stage or exhausting the total requires a new
owner decision; finalization reserve is not available to candidate search.
