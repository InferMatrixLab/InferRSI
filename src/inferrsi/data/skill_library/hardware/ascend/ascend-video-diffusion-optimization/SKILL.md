---
name: ascend-video-diffusion-optimization
description: Run and verify goal-driven Ascend video diffusion optimization. Use when the user asks for latency, RTF, throughput, or HBM targets across VLM, DiT, MoE, attention, or VAE. Not for text-only LLMs.
---

# Ascend Video Diffusion Optimization

Status: candidate workflow guidance. The procedure is first-hand and has not been independently validated beyond the [field notes](references/field-notes-video-diffusion.md). Keep model identifiers, campaign revisions, and numeric gates out of this file; they belong to an acceptance issue and its frozen evidence.

Own the performance objective through implementation and final verification. Do not stop after profiling, proposing changes, or showing a faster microbenchmark. Continue the measure-change-verify loop until the target is met, the authorized budget is exhausted, or an external blocker prevents execution.

Read the field notes only for prior failures and starting hypotheses. Treat every observation there as untraceable and non-reproducible. Derive thresholds, chunk sizes, precision policy, and sparsity from the target model's own measurements.

Verify every stage against the packaged [benchmark design](../../../methods/inference-benchmark-design/SKILL.md) and [evidence discipline](../../../workflows/rsi-evidence/SKILL.md). A microbenchmark or operator parity check is not end-to-end evidence.

## 1. Freeze The Goal Contract

Write the contract before editing code:

- Primary metric and direction, such as a latency, RTF, throughput, or peak-HBM bar.
- Exact timing boundary and RTF denominator.
- Required workload set: representative short input, production-shaped input, longest supported input, and held-out cases.
- Quality gates, such as tensor tolerance, image or video metrics, recognition success, prompt adherence, or human review.
- Resource gates: no OOM, maximum HBM, device count, and prohibited offload.
- Approximation policy: exact, numerically tolerant, perceptually gated, or task-quality gated.
- Warmup count, measured repetitions, aggregation rule, and maximum acceptable variance.
- Optimization budget: allowed code changes, lossy methods, experiment count, and wall time.

Numeric gates come from the governing acceptance issue. Do not invent them in this skill, in workflow defaults, or in reusable recipes.

If the user supplied a target, preserve it exactly. If no numeric target exists, establish one before claiming success. A vague request to "make it faster" permits exploration, not a `PASS`.

Freeze model and checkpoint revision, architecture mode, hardware SKU, device mapping, runtime and custom-op revisions, input, prompt, size, frames, FPS, steps, guidance, seed, dtype, scheduler, and output validator.

Align actual initial noise or latent across frameworks. Equal seed values are insufficient when RNG advancement differs.

## 2. Build A Reproducible Baseline

Start from a clean process. Exclude warmup from steady-state measurements and report cold start separately.

Measure synchronized wall time and peak HBM for:

1. Input decode and preprocessing.
2. Each condition encoder and vision path.
3. Source-video VAE encode when present.
4. DiT denoising, with attention, MoE or MLP, normalization, and residual attribution when needed.
5. VAE decode.
6. Postprocessing, layout conversion, device-to-host transfer, and encoding.

Collect at least three measured repetitions; use five or more for final acceptance. Preserve raw samples and report median plus range or IQR. On a shared machine, interleave baseline and candidate in the same allocation window.

Do not optimize while the baseline is unstable. Investigate device health, neighbor load, thermal or frequency state, compilation, cache state, and synchronization until variance is within the contract.

Compute an Amdahl ceiling from non-overlapping stage wall-time fractions. Use it to rank work and to expose when the requested target requires multiple stages or an algorithmic change.

## 3. Run The Optimization Loop

Maintain an experiment ledger. For every round record:

- Hypothesis and profiler evidence.
- Expected end-to-end gain and resource cost.
- Exact code or configuration delta.
- Quality and correctness result.
- Raw performance samples, aggregate, peak HBM, and variance.
- Verdict: keep, revert, or inconclusive.

Execute this loop:

1. Profile the current accepted state.
2. Select the largest removable exposed cost, not the largest summed kernel duration.
3. Make one bounded change, keeping one declared plane per step.
4. Run the fastest correctness gate that can reject it.
5. Run a short A/B probe with identical workload and synchronization.
6. Revert regressions and failed quality gates.
7. Keep a win only when it exceeds measurement noise and does not violate any gate.
8. Re-profile the accepted state because the bottleneck may move.
9. Evaluate the goal contract with `scripts/evaluate_target.py`.
10. Continue until final acceptance passes or the budget is exhausted.

Do not leave rejected experimental code enabled. Preserve only logs, evidence, and accepted production changes.

## 4. Choose Candidates From Evidence

### Condition And Scheduling

- Verify visual pixel, frame, and token budgets before changing kernels.
- Keep frequently reused condition encoders resident only when transfer or reload cost dominates and HBM headroom permits.
- Quantize large language-MLP weights selectively; keep attention, embeddings, normalization, routers, and vision paths in higher precision until separately validated.
- Treat condition/VAE overlap as a conditional candidate, never a default optimization. Draw the request-level dependency DAG before creating streams. Record each stage's inputs, outputs, mutable state, consumers, and earliest legal start.
- Permit overlap only when condition encoding does not consume VAE latents or metadata, VAE does not consume condition outputs, neither stage mutates shared buffers or module state, and both outputs are needed only at a later join.
- Prove runtime safety separately from logical independence. Verify every operator supports the selected streams, establish producer-consumer events, record tensor lifetimes on side streams, and join both streams before their first common consumer.
- Check resource compatibility before enabling overlap. Concurrent work must not cause OOM, allocator pressure, workspace collision, or enough compute and bandwidth contention to erase the wall-time gain.
- If only subgraphs are independent, overlap only those subgraphs. Keep the dependent prefix or suffix serial. If any dependency or lifetime is uncertain, preserve serial execution.
- Accept overlap only when the profiler timeline shows real concurrency and synchronized end-to-end A/B measurements improve beyond noise while quality and HBM gates pass. The maximum theoretical saving is bounded by the shorter exposed stage; configured streams alone are not evidence.
- Localize cold start around vision embeddings, patch merging, compilation, weight loading, and format conversion.

### DiT, MoE, And Quantization

- Prefer large linear projections and expert weights as initial quantization candidates.
- Instantiate final quantized modules directly to avoid simultaneous full-precision and quantized copies.
- Release loader references before format conversion and before loading the next component.
- Materialize contiguous weights before packed or `FRACTAL_NZ` conversion when source strides can differ from physical order.
- Measure intermediate cast and copy cost. Treat changed intermediate precision as approximate unless equivalence is proven.
- Validate attention and MoE independently before combining optimizations.

### Attention

- Establish a dense fused baseline first.
- Use sparse attention only when token geometry and sequence length amortize setup cost.
- Derive dense-prefix and sparse-grid regions from actual token packing.
- Require eligibility checks and a dense fallback.
- Tune activation step, skipped layers, and sparsity separately.
- Re-profile after a kernel win; VAE, MoE, casts, or synchronization may become dominant.

### VAE And Long Video

- Use no-tiling decode only when the measured shape has safe HBM headroom.
- Enable temporal or spatial chunking dynamically for larger shapes.
- Replace repeated growing `torch.cat` operations with list accumulation and one final concatenation.
- Attribute `TransData` and layout copies before designing fusion or format-preserving wrappers.
- Distinguish capacity failure, model temporal-quality failure, and algorithmic cost growth.
- Derive chunk length and overlap experimentally. For text or sharp structures, compare midpoint hard cuts against blending.
- Do not move VAE to CPU when RTF and numerical consistency are hard gates unless explicitly authorized.

## 5. Protect Correctness

When output diverges:

1. Verify checkpoint structure and architecture mode.
2. Align media preprocessing, frame sampling, resize, normalization, text cleanup, tokenization, masks, and padding.
3. Inject identical initial latents and compare one denoising step.
4. Compare scheduler coefficients, patch order, and unpatchify order.
5. Find the first divergent block, then inspect normalization, attention, routing, experts, residual, and projection.
6. For MoE, verify indices, routing weights, activation semantics, packed weight order, transpose rules, and accelerator layout.
7. Remove dumps, golden injection, and debug-only paths after verification.

Do not use output hash equality as the only quality proof. Do not label sparse attention, lower precision, or changed accumulation order as lossless without evidence.

## 6. Final Acceptance

After the target first appears met, restart from the final code and configuration. Do not validate a stale process or a best-seen intermediate state.

Run the full acceptance set:

- At least five interleaved baseline/candidate groups in the same measurement window.
- Representative short, production-shaped, longest supported, and held-out inputs.
- Cold-start and steady-state measurements when loading or compilation changed.
- Primary performance metric, stage breakdown, peak HBM, and raw samples.
- Every automatic quality gate plus required visual or task review.
- No OOM, corruption, fallback, hidden CPU offload, skipped work, or invalid output.

A local pre-check is available:

```bash
cp {skill_path}/assets/campaign.template.json campaign.json
# Replace every placeholder with measured samples and the issue-scoped gates.
python3 {skill_path}/scripts/evaluate_target.py campaign.json
```

The script checks target attainment, minimum improvement, variance, quality gates, and resource gates. It is an aid, not the verdict. The authoritative verdict comes from the acceptance issue's frozen gates and its `evidence/<campaign-id>/` tree, and it stays `INCONCLUSIVE` while any required level or artifact is missing.

Return `PASS` only when the final restarted artifact satisfies the frozen gates, with pinned baseline and candidate revisions and complete evidence. A microbenchmark win, one fast run, a profiler estimate, or an earlier best result is insufficient.

Return `FAIL` when complete enough evidence shows a gate was not met. Report the measured gap, accepted gains, rejected rounds, binding bottleneck, remaining ceiling, and the next change required.

Return `INCONCLUSIVE` when a freeze is missing, runs are partial, the environment does not qualify, or required levels were not executed. Report the exact missing prerequisite and preserve the completed evidence.

## 7. Final Report

Report:

- Final verdict: `PASS`, `FAIL`, or `INCONCLUSIVE`.
- Frozen goal and quality contract, with its acceptance issue.
- Baseline and final raw samples, aggregates, variance, RTF, and peak HBM.
- End-to-end improvement and whether it exceeds noise.
- Quality and longest-input results.
- Accepted and reverted changes.
- Final artifact revision and exact runtime configuration.
- Remaining gap and ceiling when the target is not met.
