---
name: reason-hopper-kernels
description: Reason about Hopper SM90 CUDA GEMM kernels using TMA and mbarrier lifetimes, WGMMA warpgroup participation, register and pipeline budgets, layouts, software scheduling and FP8 scaling. Use for an H100/H200-family kernel diagnosis or a Blackwell-to-Hopper applicability check; source-derived candidate guidance with no local GPU validation.
metadata:
  inferrsi: |
    {
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "license": "UNKNOWN",
      "tags": [
        "cuda",
        "Hopper",
        "SM90",
        "SM90a",
        "H100",
        "H200",
        "TMA",
        "mbarrier",
        "WGMMA",
        "warp-specialization",
        "registers",
        "pipeline",
        "swizzle",
        "persistent-kernels",
        "FP8",
        "DeepGEMM",
        "CUTLASS",
        "KernelWiki",
        "KDA"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/NVlabs/kda",
          "commit": "acdd79343c5e9d0c7cb96289f26fd3f1051ce785",
          "paths": [
            ".gitmodules",
            "THIRD_PARTY_NOTICES.md",
            "LICENSE",
            "third_party_licenses/MIT-hanlab.txt",
            "skills/KernelWiki"
          ],
          "readset": "references/sources.md",
          "identity": "references/source-inventory.json",
          "scope": "KDA-to-KernelWiki gitlink and licensing provenance only; first-party runtime code not mined."
        },
        {
          "type": "git",
          "url": "https://github.com/mit-han-lab/KernelWiki",
          "commit": "76d27b56f804e7e7295d4c570e1e5d7eef4b0a75",
          "paths": [
            "README.md",
            "SKILL.md",
            "artifacts/kernels/deepgemm/full/PROVENANCE.yaml",
            "artifacts/prs/cutlass/PR-2139/PROVENANCE.yaml",
            "artifacts/prs/cutlass/PR-2750/key-files/examples/python/CuTeDSL/blackwell/tutorial_gemm/fp16_gemm_1.py",
            "artifacts/prs/cutlass/PR-3091/PROVENANCE.yaml",
            "artifacts/prs/cutlass/PR-3091/key-files/examples/python/CuTeDSL/hopper/grouped_gemm.py",
            "artifacts/prs/cutlass/PR-3091/key-files/python/CuTeDSL/cutlass/utils/tensormap_manager.py",
            "data/refresh-cutoff.yaml",
            "data/tool-versions.yaml",
            "sources/blogs/deepgemm.md",
            "sources/prs/cutlass/PR-2139.md",
            "sources/prs/cutlass/PR-2965.md",
            "sources/prs/sglang/PR-16014.md",
            "sources/prs/sglang/PR-19794.md",
            "sources/prs/sglang/PR-9559.md",
            "sources/prs/vllm/PR-20396.md",
            "sources/prs/vllm/PR-23666.md",
            "sources/prs/vllm/PR-33285.md",
            "wiki/hardware/mbarrier.md",
            "wiki/hardware/tma.md",
            "wiki/kernels/deepgemm.md",
            "wiki/kernels/fp8-block-scale-gemm.md",
            "wiki/kernels/grouped-gemm.md",
            "wiki/languages/cuda-cpp.md",
            "wiki/migration/register-to-tmem.md",
            "wiki/migration/wgmma-to-tcgen05.md",
            "wiki/patterns/compute-bound.md",
            "wiki/patterns/low-sm-utilization.md",
            "wiki/patterns/memory-bound.md",
            "wiki/patterns/pipeline-stalls.md",
            "wiki/patterns/register-pressure.md",
            "wiki/patterns/tail-effect.md",
            "wiki/techniques/cache-policy.md",
            "wiki/techniques/double-buffering.md",
            "wiki/techniques/fine-grained-quantization.md",
            "wiki/techniques/persistent-kernels.md",
            "wiki/techniques/ping-pong-scheduling.md",
            "wiki/techniques/pipeline-stages.md",
            "wiki/techniques/register-budgeting.md",
            "wiki/techniques/swizzling.md",
            "wiki/techniques/tile-scheduling.md",
            "wiki/techniques/vectorized-loads.md",
            "wiki/techniques/warp-specialization.md"
          ],
          "readset": "references/sources.md",
          "identity": "references/source-inventory.json",
          "license": "UNKNOWN",
          "scope": "All synthesis and source frontmatters screened; selected Hopper bodies mined with explicit qualifications. MIT assertion inherited from KDA; no root LICENSE at this pin."
        },
        {
          "type": "git",
          "url": "https://github.com/deepseek-ai/DeepGEMM",
          "commit": "891d57b4db1071624b5c8fa0d1e51cb317fa709f",
          "paths": [
            "LICENSE",
            "deep_gemm/include/deep_gemm/impls/sm90_fp8_gemm_1d1d.cuh",
            "deep_gemm/include/deep_gemm/mma/sm90.cuh",
            "deep_gemm/include/deep_gemm/ptx/wgmma.cuh",
            "deep_gemm/include/deep_gemm/scheduler/gemm.cuh"
          ],
          "readset": "references/sources.md",
          "identity": "references/source-inventory.json",
          "license": "MIT",
          "scope": "Selected code sections directly inspected; original bytes compared with KernelWiki where recorded; no native build or execution."
        },
        {
          "type": "git",
          "url": "https://github.com/NVIDIA/cutlass",
          "commit": "ca4fdbea708ad940c905359788372b8add9f85e0",
          "paths": [
            "LICENSE.txt",
            "examples/67_hopper_fp8_warp_specialized_gemm_with_blockwise_scaling/67_hopper_fp8_warp_specialized_gemm_with_blockwise_scaling.cu",
            "include/cutlass/gemm/collective/sm90_mma_tma_gmma_ss_warpspecialized_fp8_blockwise_scaling.hpp",
            "include/cutlass/gemm/kernel/sm90_gemm_array_tma_warpspecialized_pingpong.hpp"
          ],
          "readset": "references/sources.md",
          "identity": "references/source-inventory.json",
          "license": "BSD-3-Clause",
          "scope": "Selected code sections directly inspected; original bytes compared with KernelWiki where recorded; no native build or execution."
        },
        {
          "type": "document",
          "url": "https://docs.nvidia.com/cuda/archive/12.8.0/hopper-tuning-guide/index.html",
          "version": "CUDA 12.8.0",
          "content_sha256": "0fb0a5dd532f43e04c41112aa07bb3fddfab03fc8e68392509f0bec2c03ca418",
          "readset": "references/source-inventory.json",
          "scope": "Selected architecture/ISA sections directly inspected; source HTML not packaged."
        },
        {
          "type": "document",
          "url": "https://docs.nvidia.com/cuda/archive/12.8.0/parallel-thread-execution/index.html",
          "version": "CUDA 12.8.0 / PTX ISA 8.7",
          "content_sha256": "48849aa7851b9ff8893efc750f1a0db46e6023852cb76d001d68d57ffa49fa06",
          "readset": "references/source-inventory.json",
          "scope": "Selected architecture/ISA sections directly inspected; source HTML not packaged."
        }
      ],
      "applicability": {
        "scope": "Source-derived Hopper SM90/SM90a kernel reasoning for TMA/mbarrier, WGMMA, resource/layout/pipeline/software scheduling and selected FP8 GEMM. CUDA categorization does not certify other GPU architectures, library dispatch, or a combined tested stack.",
        "architectures": [
          "sm90",
          "sm90a"
        ],
        "excluded_mechanisms": [
          "tcgen05",
          "TMEM",
          "CLC",
          "two-SM MMA",
          "native NVFP4/block-scaled tcgen05 MMA"
        ],
        "input_contract": "Device/compute capability, compiler target and selected implementation, kernel/library revisions, shapes/strides/alignment, numeric and grouping/epilogue semantics, correctness criterion and measurement boundary.",
        "produced_artifact": "A source-qualified, reviewable hypothesis with one bounded change, resource/accuracy exchange, counter-signal, stop condition and next verification step.",
        "failure_modes": "SM90 tags or import/dispatch guards can hide an unbuilt or unselected SM90a instruction path; extra stages or register caps can increase spills or lower residency."
      },
      "limitations": [
        "Native compilation, GPU correctness, numerical accuracy, profiling, performance, model/service behavior and skill efficacy were not run.",
        "KernelWiki is Blackwell-first; frontmatter tags, verified labels and snippet claims are not Hopper compatibility proofs.",
        "Only selected code sections and nine source summary bodies were mined; remaining source headers and synthesis dispositions are explicit in the inventory.",
        "Source numerical claims, fixed tuning defaults and unsafe teaching snippets are not imported as local evidence or recipes.",
        "Pinned KernelWiki has no root LICENSE; KDA MIT assertion and its sanitized-distribution discrepancy are retained, with third-party terms kept separate."
      ],
      "provenance_readsets": [
        "references/sources.md",
        "references/source-inventory.json",
        "references/notices.md"
      ],
      "references": [
        "../diagnose-attention-bottlenecks/SKILL.md",
        "../../../../playbooks/optimization/kernel-writing-guide/SKILL.md"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "For WGMMA advice, confirm the compiled and selected SM90a path; do not transplant Blackwell-only instruction or memory mechanisms.",
        "Resolve producer/consumer ownership and completion before tuning stage depth; budget live accumulators, padded shared memory, scales and epilogue storage together.",
        "For later validation, check tails, short K, stage wraparound and grouped offsets against the frozen reference, inspect actual PTX/SASS resources, and include setup/conversion/reduction costs."
      ]
    }
---

# Reason about Hopper kernels

Use this procedure to turn an observed Hopper kernel bottleneck into one bounded
change and a correctness-first verification proposal. It does not implement a
kernel or establish installed library support. All operational steps are
**proposed**; the references distinguish inspected source facts, upstream reports
and unresolved claims. Empirical validation is **not_run**.

Read [source qualification and coverage](references/sources.md) first when using
KernelWiki material: its SM90 tags do not establish Hopper compatibility. The
[inventory](references/source-inventory.json) accounts for every synthesis page
and every source-page header advertising SM90 at the pinned snapshot. Read the
[retained notices](references/notices.md) before reusing source material.

## Establish the actual contract

Record device and compute capability, compiler/toolkit and target flags, kernel
and library revisions, selected implementation, shape/strides/alignment, operand,
scale, accumulation and output types, grouping/masking, epilogue and correctness
criterion. Distinguish kernel steady state from quantization, layout conversion,
JIT/descriptor setup, launch overhead and whole-request time.

Confirm the actual instruction path. Hopper WGMMA needs an architecture-specific
SM90a compilation path; a device-family label, a package import or a generic
SM90 dispatch guard does not prove that path was built or selected. Do not map
Blackwell tcgen05, TMEM, hardware block-scaled MMA, CLC or two-SM MMA recipes to
Hopper. Hopper thread-block clusters and TMA multicast are separate capabilities.

## Choose the next discriminating check

| Signal | Inspect and reason about | Small candidate and counter-signal |
| --- | --- | --- |
| TMA/barrier stalls, stale data, hang or size-sensitive failure | [Synchronization](references/synchronization.md): full/empty stages, transaction bytes, phase on reuse, WGMMA completion and epilogue-store lifetime | Repair the ownership protocol before tuning depth. A wait can be a correct dependency, not evidence of insufficient stages. |
| High registers, spills or low resident work | [Resource/layout/scheduling tradeoffs](references/resources-and-scheduling.md): all live accumulators, role budgets, padded SMEM and scale/epilogue storage | Reduce a live range, tile or unroll factor; compare against extra IO or lost instruction parallelism. A register cap can add spills. |
| Load/compute gaps with a long independent K-loop | Same reference: producer/consumer specialization and stage cost | Consider one extra input stage or a role change only after proving independence. Short K or lower residency can make it slower. |
| Low device utilization, thin/grouped GEMM or a long last wave | Same reference: useful tile count, actual residency, software schedule, locality and reduction cost | Compare tile/raster/grouping choices. Persistence cannot create missing work; split-K adds reduction and numerical obligations. |
| FP8 error or scaling/preprocessing cost | [FP8](references/fp8.md): scale meaning/layout, reduction-chunk boundary, partial-sum lifetime and output contract | Change one scale/layout/promotion choice; recheck error and the full conversion-plus-GEMM boundary. A software E8M0 representation is not native block-scaled WGMMA. |

For attention, start with
[diagnose-attention-bottlenecks](../diagnose-attention-bottlenecks/SKILL.md) for
online-softmax, mask, forward/backward and quality obligations; use this owner's
references only for the selected Hopper mechanism. General kernel lifecycle and
measurement remain with
[kernel-writing-guide](../../../../playbooks/optimization/kernel-writing-guide/SKILL.md).

## Return a reviewable hypothesis

State the source path/revision and evidence class; observed signal and missing
observations; semantic and architecture prerequisites; one proposed change; the
resource or accuracy exchange; a counter-signal and stop condition; and the next
check. Retain a rejected direction with its changed-condition requirement.

For later authorized validation, first check tails, zero/short K, repeated stage
wraparound, multiple work tiles, grouped offsets and output/scale layout against
the frozen reference. Inspect generated PTX/SASS and compiler resources on the
actual stack. Then compare the same workload and boundary, accounting for setup,
conversion, reduction, synchronization and epilogue costs. A source report or CPU
packaging check establishes no GPU correctness, performance or service gain.
