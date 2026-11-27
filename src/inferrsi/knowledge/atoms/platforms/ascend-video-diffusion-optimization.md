---
name: ascend-video-diffusion-optimization
description: 'Run and verify goal-driven Ascend video diffusion optimization. Specializes the backend-agnostic video-diffusion-optimization skeleton with Ascend NPU operator, layout and profiler references. Use when the user asks for latency, RTF, throughput, or HBM targets across VLM, DiT, MoE, attention, or VAE on Ascend NPU. Not for text-only LLMs.'
metadata:
  inferrsi: |
    {
      "schema_version": 1,
      "profile": "local-skill-v1",
      "kind": "skill",
      "status": "candidate",
      "origin": [
        "first-party"
      ],
      "tags": [
        "ascend",
        "npu",
        "video-diffusion",
        "dit",
        "moe",
        "attention",
        "vae",
        "performance",
        "profiling"
      ],
      "empirical_validation": "not_run",
      "verification": {
        "locally_verified": false,
        "evidence_level": "guidance",
        "note": "Procedure is first-hand workflow guidance. The linked field notes are not reproducible as published. No acceptance campaign under this repository's evidence contract backs this skill, and no public performance claim is made."
      },
      "applicability": {
        "scope": "Ascend NPU video diffusion inference and serving optimization",
        "hardware": "Ascend NPU; the measure-change-verify workflow skeleton is backend-agnostic and lives in playbooks/optimization/video-diffusion-optimization, while the operator, layout and profiler references here are Ascend-specific",
        "prerequisites": "A reproducible benchmark, a frozen quality check, and numeric gates defined in the governing acceptance issue",
        "input_contract": "Issue-scoped performance and quality gates, timing boundary, representative and held-out workloads, frozen model/runtime/input settings and an authorized optimization budget.",
        "produced_artifact": "An experiment ledger and final report of the frozen goal, baseline/final samples, quality/resource checks, accepted or reverted changes and remaining gap; verdicts require the acceptance issue evidence.",
        "failure_modes": "Packed-layout conversion from noncontiguous weights can corrupt outputs; missing side-stream lifetime/order handling or omitted layout-copy costs can invalidate an optimization comparison."
      },
      "limitations": [
        "Ascend specialization of the backend-agnostic playbooks/optimization/video-diffusion-optimization skeleton; every operator, layout and profiler reference (TransData, FRACTAL_NZ, CANN) is Ascend-specific and must be re-derived per backend.",
        "Candidate workflow guidance; not independently validated beyond the field notes.",
        "Field notes are non-reproducible as published and must not be cited as evidence.",
        "Model identifiers, campaign revisions, and numeric gates are intentionally excluded and remain issue-scoped.",
        "Remaining figures are order-of-magnitude recollections."
      ],
      "provenance_readsets": [
        "references/field-notes-video-diffusion.md"
      ],
      "references": [
        "../../../../playbooks/optimization/video-diffusion-optimization/SKILL.md",
        "../../../../playbooks/optimization/video-diffusion-optimization/scripts/evaluate_target.py",
        "../../../../playbooks/optimization/video-diffusion-optimization/assets/campaign.template.json"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Follow the common goal-contract and measure-change-verify loop, including final restarted-artifact acceptance; an operator win does not establish end-to-end improvement.",
        "Materialize contiguous weights before FRACTAL_NZ conversion when strides differ from physical order, and attribute TransData/copy costs before proposing fusion.",
        "Use field notes only to form hypotheses; derive thresholds, chunking, precision and sparsity from the target model measurements, and preserve stream dependencies and tensor lifetimes."
      ]
    }
---

# Ascend Video Diffusion Optimization

Status: candidate workflow guidance, Ascend-specific. The procedure is first-hand and has not been independently validated beyond the [field notes](references/field-notes-video-diffusion.md). Keep model identifiers, campaign revisions, and numeric gates out of this file; they belong to an acceptance issue and its frozen evidence.

This skill is the Ascend specialization of the backend-agnostic [video diffusion optimization skeleton](../../../../playbooks/optimization/video-diffusion-optimization/SKILL.md). Follow that skeleton for the goal contract, baseline discipline, optimization loop, candidate-selection strategy, correctness protection, final acceptance, and final report. This file adds the Ascend-specific operator, layout, and profiler references; it does not repeat the full procedure.

Own the performance objective through implementation and final verification. Do not stop after profiling, proposing changes, or showing a faster microbenchmark. Continue the measure-change-verify loop until the target is met, the authorized budget is exhausted, or an external blocker prevents execution.

Read the field notes only for prior failures and starting hypotheses. Treat every observation there as untraceable and non-reproducible. Derive thresholds, chunk sizes, precision policy, and sparsity from the target model's own measurements.

Verify every stage against the packaged [benchmark design](../../../../playbooks/measurement/inference-benchmark-design/SKILL.md) and [evidence discipline](../../../../workflows/governance/rsi-evidence/SKILL.md). A microbenchmark or operator parity check is not end-to-end evidence.

## Ascend-Specific Layout And Profiler References

Where the common skeleton says "operator names, memory layouts, and profiler references are backend-specific", apply these Ascend facts:

- `FRACTAL_NZ` is the Ascend packed weight layout. Materialize contiguous weights before converting to `FRACTAL_NZ` when source strides can differ from physical order; a physical-layout mismatch corrupts output.
- `TransData` performs layout conversion between formats. Attribute `TransData` and layout-copy cost before designing fusion or format-preserving wrappers.
- Profiling and stream instrumentation follow `CANN` conventions. Establish producer-consumer events, record tensor lifetimes on side streams, and join streams before their first common consumer.
- Sparse-attention and quantization candidate selection remain backend-agnostic decisions; only the kernel names, packed-layout materialization, and profiler attributions are Ascend-specific.

For the candidate-selection guidance (condition/scheduling, DiT/MoE/quantization, attention, VAE/long-video), follow the common skeleton and read the [field notes](references/field-notes-video-diffusion.md) for the Ascend-specific failures to avoid.

The common skeleton's `scripts/evaluate_target.py` and `assets/campaign.template.json` are shared and backend-agnostic; use them as documented there.
