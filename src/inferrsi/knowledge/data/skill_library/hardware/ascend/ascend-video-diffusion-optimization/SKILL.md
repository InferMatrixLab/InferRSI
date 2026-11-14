---
name: ascend-video-diffusion-optimization
description: 'Run and verify goal-driven Ascend video diffusion optimization. Specializes the backend-agnostic video-diffusion-optimization skeleton with Ascend NPU operator, layout and profiler references. Use when the user asks for latency, RTF, throughput, or HBM targets across VLM, DiT, MoE, attention, or VAE on Ascend NPU. Not for text-only LLMs.'
---

# Ascend Video Diffusion Optimization

Status: candidate workflow guidance, Ascend-specific. The procedure is first-hand and has not been independently validated beyond the [field notes](references/field-notes-video-diffusion.md). Keep model identifiers, campaign revisions, and numeric gates out of this file; they belong to an acceptance issue and its frozen evidence.

This skill is the Ascend specialization of the backend-agnostic [video diffusion optimization skeleton](../../../methods/video-diffusion-optimization/SKILL.md). Follow that skeleton for the goal contract, baseline discipline, optimization loop, candidate-selection strategy, correctness protection, final acceptance, and final report. This file adds the Ascend-specific operator, layout, and profiler references; it does not repeat the full procedure.

Own the performance objective through implementation and final verification. Do not stop after profiling, proposing changes, or showing a faster microbenchmark. Continue the measure-change-verify loop until the target is met, the authorized budget is exhausted, or an external blocker prevents execution.

Read the field notes only for prior failures and starting hypotheses. Treat every observation there as untraceable and non-reproducible. Derive thresholds, chunk sizes, precision policy, and sparsity from the target model's own measurements.

Verify every stage against the packaged [benchmark design](../../../methods/inference-benchmark-design/SKILL.md) and [evidence discipline](../../../workflows/rsi-evidence/SKILL.md). A microbenchmark or operator parity check is not end-to-end evidence.

## Ascend-Specific Layout And Profiler References

Where the common skeleton says "operator names, memory layouts, and profiler references are backend-specific", apply these Ascend facts:

- `FRACTAL_NZ` is the Ascend packed weight layout. Materialize contiguous weights before converting to `FRACTAL_NZ` when source strides can differ from physical order; a physical-layout mismatch corrupts output.
- `TransData` performs layout conversion between formats. Attribute `TransData` and layout-copy cost before designing fusion or format-preserving wrappers.
- Profiling and stream instrumentation follow `CANN` conventions. Establish producer-consumer events, record tensor lifetimes on side streams, and join streams before their first common consumer.
- Sparse-attention and quantization candidate selection remain backend-agnostic decisions; only the kernel names, packed-layout materialization, and profiler attributions are Ascend-specific.

For the candidate-selection guidance (condition/scheduling, DiT/MoE/quantization, attention, VAE/long-video), follow the common skeleton and read the [field notes](references/field-notes-video-diffusion.md) for the Ascend-specific failures to avoid.

The common skeleton's `scripts/evaluate_target.py` and `assets/campaign.template.json` are shared and backend-agnostic; use them as documented there.
