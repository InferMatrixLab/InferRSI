# Source qualification, readset and architecture boundary

Inspected 2026-10-23. This is a manual, bounded distillation from KernelWiki,
with selected underlying code and versioned NVIDIA documentation checked
separately. It imports no runnable kernel, external artifact tree, benchmark
result or GPU qualification. The operational procedure is proposed guidance.

## Source identities

| ID | Source and immutable/release identity | Direct inspection versus inherited evidence |
| --- | --- | --- |
| KDA | [NVlabs/kda snapshot](https://github.com/NVlabs/kda/tree/acdd79343c5e9d0c7cb96289f26fd3f1051ce785) | `.gitmodules`, the `skills/KernelWiki` Git tree entry, `THIRD_PARTY_NOTICES.md`, license notices. The actual gitlink is KW below. No KDA agent/runtime code was mined. |
| KW | [mit-han-lab/KernelWiki snapshot](https://github.com/mit-han-lab/KernelWiki/tree/76d27b56f804e7e7295d4c570e1e5d7eef4b0a75) | README/SKILL and cutoff metadata; all 48 synthesis frontmatters; all 2,217 source-page frontmatters screened for SM90/SM90a. Selected bodies and code locations are enumerated in the inventory. |
| DG | [DeepGEMM snapshot](https://github.com/deepseek-ai/DeepGEMM/tree/891d57b4db1071624b5c8fa0d1e51cb317fa709f) | Directly fetched `impls/sm90_fp8_gemm_1d1d.cuh`, SM90 atom/helper headers, selected scheduler sections and LICENSE. The mainloop bytes match KW's artifact and declared SHA-256. No JIT/API dispatch, other variants or full integration was inspected. |
| C2139 | [CUTLASS snapshot](https://github.com/NVIDIA/cutlass/tree/ca4fdbea708ad940c905359788372b8add9f85e0) | KW's PR-2139 provenance carries `ca4fdbea`; the GitHub commit API resolved that prefix to the full identity here. Three underlying files were directly fetched and compared with KW's copies: example 67, the SM90 SS block-scaled collective and SM90 array ping-pong kernel. Selected sections were inspected, not every branch or dependency. |
| PTX87 | [PTX ISA 8.7 in CUDA 12.8.0 archive](https://docs.nvidia.com/cuda/archive/12.8.0/parallel-thread-execution/index.html) | Direct section inspection: mbarrier phase/transaction semantics; asynchronous proxies; WGMMA operands/fence/commit/wait and target notes; shared descriptor layouts; ordinary load vector forms; setmaxnreg. Versioned URL plus observed HTML digest is retained, not a fabricated Git SHA. |
| HTG128 | [Hopper Tuning Guide, CUDA 12.8.0](https://docs.nvidia.com/cuda/archive/12.8.0/hopper-tuning-guide/index.html) | Direct sections 1.4.1.1–1.4.1.3 (occupancy, TMA, clusters). Hardware limits are source facts, not launch defaults or measured occupancy. |

[The inventory](source-inventory.json) retains byte counts, Git blob identities
where available, SHA-256, inspection scopes and underlying URLs. Hashing a file
identifies the inspected snapshot; it does not mean every line was semantically
reviewed. External original bytes are not retained in this package and remain
external dependencies. Selected license notices are retained separately.

Useful underlying anchors:

- [DG mainloop](https://github.com/deepseek-ai/DeepGEMM/blob/891d57b4db1071624b5c8fa0d1e51cb317fa709f/deep_gemm/include/deep_gemm/impls/sm90_fp8_gemm_1d1d.cuh),
  [SM90 atoms](https://github.com/deepseek-ai/DeepGEMM/blob/891d57b4db1071624b5c8fa0d1e51cb317fa709f/deep_gemm/include/deep_gemm/mma/sm90.cuh),
  [WGMMA helpers](https://github.com/deepseek-ai/DeepGEMM/blob/891d57b4db1071624b5c8fa0d1e51cb317fa709f/deep_gemm/include/deep_gemm/ptx/wgmma.cuh),
  [software scheduler](https://github.com/deepseek-ai/DeepGEMM/blob/891d57b4db1071624b5c8fa0d1e51cb317fa709f/deep_gemm/include/deep_gemm/scheduler/gemm.cuh).
- [C2139 SS collective](https://github.com/NVIDIA/cutlass/blob/ca4fdbea708ad940c905359788372b8add9f85e0/include/cutlass/gemm/collective/sm90_mma_tma_gmma_ss_warpspecialized_fp8_blockwise_scaling.hpp),
  [example 67](https://github.com/NVIDIA/cutlass/blob/ca4fdbea708ad940c905359788372b8add9f85e0/examples/67_hopper_fp8_warp_specialized_gemm_with_blockwise_scaling/67_hopper_fp8_warp_specialized_gemm_with_blockwise_scaling.cu),
  [SM90 ping-pong kernel](https://github.com/NVIDIA/cutlass/blob/ca4fdbea708ad940c905359788372b8add9f85e0/include/cutlass/gemm/kernel/sm90_gemm_array_tma_warpspecialized_pingpong.hpp).

The source IDs do not assert a compatible combined runtime stack. KW declares a
**2026-04-27** knowledge cutoff and tool snapshots including Triton 3.6.0 and
CUTLASS 4.5.0. These are inherited corpus dates/version claims; this work does not
refresh or certify current library support. DG/C2139/PTX87 are independently
identified anchors, not a stack tested together.

## Inventory and selection coverage

The inventory screens all 48 `wiki/**/*.md` synthesis headers, including
architecture-less problem pages and SM90→SM100 migrations, rather than selecting
only literal SM90 tags. It also screens every source-page header: 2,179 PRs,
20 blogs, 11 docs and 7 contest pages. It retains the 171 source paths advertising
SM90/SM90a as a bounded follow-up set; the other source bodies and candidate
ledgers were not mined. Header classification can miss relevant untagged source
content; it is not an exhaustive upstream Hopper survey.

| Topic group | Extraction / disposition | Reuse boundary |
| --- | --- | --- |
| TMA, mbarrier, WGMMA migration contrast | Mined with code/ISA qualification → [synchronization](synchronization.md) | Descriptor/copy/barrier and register/completion contracts retained; SM100 snippets and unsupported property generalizations excluded. |
| Warp specialization, stages, buffering, registers, swizzle | Mined with qualifications → [resources](resources-and-scheduling.md) | Mechanisms and resource exchanges retained; fixed role counts, stage counts, occupancy estimates, universal swizzle and register caps excluded. |
| Persistent/tile scheduling, utilization, tail and memory/compute patterns | Mined conditionally → same reference | Hopper software schedule and workload diagnostics retained; CLC and guaranteed tail elimination excluded. |
| DeepGEMM / FP8 / fine-grained scaling | Mined for selected SM90 path → [FP8](fp8.md) | 1d1d mainloop versus general block-scale narrative explicitly separated; no library-wide layout, accuracy or throughput claim. |
| Ping-pong and register→TMEM | Boundary/counter-signal only | SM100/FA4 teaching sequence excluded; C2139 supplies a distinct SM90 counterexample to blanket overlap exclusions. |
| PDL/GDC | Located, not mined | Hopper availability is not rejected. Primary/secondary signal semantics, launch/compiler flags and correct consumer waits need their own primary-code readset; no automatic-overlap recipe imported. |
| FlashMLA, NSA/sparse MLA, GDN, fused MoE, gated dual GEMM, chunk parallelism and fusion/epilogue topics | Located, not mined (except grouped scheduling concepts and explicit boundary comparison) | Separate algorithm, state, precision and framework dispatch contracts; use existing attention owner where applicable. No support inferred from tags. |
| tcgen05, TMEM, CLC, native NVFP4, two-SM MMA, software-exp, SM100 language recipes and contest winners | Excluded from Hopper recipes | Some high-level principles may transfer; instruction, accumulator, format and scheduling implementation does not. No contest speedups or snippet copied. |

Each synthesis path and each SM90 source path has an explicit disposition and
inspection level in the JSON inventory. Selected PR **summary bodies** supply
counter-signals (C2139/2965; SGLang 9559/16014/19794; vLLM 20396/23666/33285).
Except C2139's three matched files, their underlying PR diffs/code/tests were
**not** independently inspected or reproduced. Some summaries are truncated;
retain them as leads, not verified fixes or default policies. Original PR URLs
and historical merge prefixes are inherited citations, kept distinct from the
full KW snapshot identity.

## Evidence classes and limits

- **Inspected-source fact:** the identified code or versioned documentation
  contains the stated mechanism/constraint. This is static evidence.
- **Source-reported:** a KW synthesis/summary or cited source reports behavior,
  rationale or results; it is not promoted by KW's `verified`/`snippet` labels.
- **Proposed:** an InferRSI operational inference or future discriminating check,
  including all tuning choices in the skill.
- **Locally unverified:** native compilation/execution, correctness, precision,
  profiling, performance, model quality, service behavior and skill efficacy.

Important contradictions are retained where they affect decisions:
[synchronization hazards](synchronization.md#retained-upstream-contradictions),
[resource/scheduling overgeneralizations](resources-and-scheduling.md#upstream-claims-deliberately-not-inherited),
and [FP8 units/variant scope](fp8.md#preserve-unresolved-source-claims).
Missing GPU evidence stays missing; CPU package/link checks do not turn it into
campaign PASS or establish hardware, host RAM, storage, network or OS coverage.
