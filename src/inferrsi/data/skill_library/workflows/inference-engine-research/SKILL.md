---
name: inference-engine-research
description: "Prepare model-aware inference-engine research: broaden knowledge discovery, select source references, inventory full-pipeline weights and screen target feasibility before engine design. Route relevant Strata, vLLM, SGLang and Omni knowledge."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Inference engine research router

Use this collection to prepare a dedicated engine, compare architectures or design a constrained search. Start from the model's actual task and component graph, then discover both model-specific and transferable knowledge. A model name and a preferred framework alone are insufficient. Keep the library's `repositories/` and `workflows/` layout so links reach their owners; repository skills can also be distributed independently.

| Question | Route |
|---|---|
| Prepare a new model/hardware pair: discovery, reference selection, full weights and feasibility | [Model-aware preparation](references/model-aware-preparation.md); [MiniMax-H3 on Apple Silicon example](references/minimax-h3-apple.md) when applicable |
| Compare graph, cache, lifetime, stop and completion contracts across source slices | [Cross-repository mechanisms](references/cross-repository-mechanisms.md) and [source scope](references/repository-source-scope.md) |
| Strata heterogeneous MoE, CPU/GPU expert placement, memory and speculative execution | [strata](../../repositories/strata/SKILL.md) |
| vLLM token scheduling, KV/prefix reuse, execution/parallelism or model integration | [vllm](../../repositories/vllm/SKILL.md) |
| SGLang scheduling, Radix/HiCache, prefill/decode, parallel runtime or extensions | [sglang](../../repositories/sglang/SKILL.md) |
| SGLang-Omni pipelines, stage/scheduler ownership, streaming and transport | [sglang-omni](../../repositories/sglang-omni/SKILL.md) |
| vLLM-Omni model/deploy separation, AR/diffusion execution, stage transport and heterogeneous outputs | [vllm-omni](../../repositories/vllm-omni/SKILL.md) |

## Comparison procedure

1. Fix the model/checkpoint/tokenizer, tasks/modalities, component graph, target hardware/memory, software and quality contract. Ask only for missing facts that alter a decision; otherwise state reversible assumptions. Do not infer architecture from a family name.
2. Search model, framework, task, modality and mechanism dimensions independently and union the results. Use `inferrsi knowledge research <model> --framework <framework>` with explicit `--task`, `--modality` or `--mechanism` additions as needed; known profiles supply grounded terms, unknown models require source inspection. Exact `knowledge search` still ANDs all tokens. Retain hard filters and record empty dimensions; broaden an over-restrictive scope only explicitly.
3. Compare eligible native implementations at pinned revisions. If the user requests the most-starred reference, record the candidate set, eligibility, observation date and counts; choose the largest count within that set, then check license and compatibility. Read that source directly or distill its relevant paths with an available repo-to-skill workflow before engine generation. Popularity is a reference-selection input, not a quality or hardware guarantee.
4. Inventory every selected encoder, denoiser, VAE/decoder, adapter and auxiliary asset. Reconcile tensor shapes, dtypes, quantization metadata, files and actual execution paths. Separate full checkpoint weights, required subsets, phase peaks, activations/workspace, unified/host memory and storage. Do not count alternative task checkpoints twice or equate a DiT-only quant with a complete pipeline. Follow the [preparation procedure](references/model-aware-preparation.md) before deciding target feasibility.
5. Load the smallest relevant repository branches. Trace work units, state ownership, scheduling, memory, communication, output and cleanup. Produce supported settings, semantics-preserving implementation changes and research extensions as separate candidate classes, with explicit approximation budgets.
6. Screen supported model/backend/format pairs, residency, partition/layout, numerical/quality contracts, abort/termination and queue stability before benchmarking. Mark unsupported and unverified paths separately; preparation alone does not establish target feasibility.
7. Freeze the workload and validators before candidate experiments. Measure matched real workloads, separating CPU/static, mocked contract, accelerator/native transport, real-model quality and service evidence. Rank only valid runs and report conflicting objectives without claiming a universal winner.

## Transfer rules

DP/EP/TP labels, batch size, prefix cache, async execution and streaming can mean different things across engines. Translate the ownership and capability contract before transferring a knob or optimization. Do not assume an Omni repository accepts the independently captured base-engine HEAD: these snapshots do not constitute a compatibility matrix.

Measure text TTFT/TPOT separately from media first-packet latency, chunk gaps, end-to-end completion, RTF, image/video throughput and quality. Reduced steps, resolution or output length change the workload/quality contract and must be disclosed.

The repository and framework owners retain their pinned provenance and source evidence. The collection is a portable candidate; actual GPU, native distributed and quality validation requires the target environment. No new engine or measured speedup is included.
