---
name: pytorch-inference-operating-graph
description: "Route a PyTorch inference question to the v2.15.0 dispatcher, SDPA, device-allocator, profiler or AOTInductor owner, or to an older host-copy, CUDA-graph or DCP owner. Use before treating those pins as one stack."
---

# PyTorch inference operating graph

Status: candidate. Empirical validation: **not_run**. Reading this skill authorizes no command, install or benchmark.

This is the router for a bounded repo-to-skill distillation of `pytorch/pytorch` at `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` (tag `v2.15.0`). It follows the AREX scope, ground, construct and verify sequence as an InferRSI document. The DisCo CLI was not executed, so this is not an AREX-verified graph.

## Choose an owner

| Question | Owner | Pin |
| --- | --- | --- |
| Which dispatch key or custom-op contract applies | [pytorch-dispatcher-and-custom-ops](../pytorch-dispatcher-and-custom-ops/SKILL.md) | `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` |
| Which SDPA backend or flash impl is selected | [pytorch-sdpa-backend-selection](../pytorch-sdpa-backend-selection/SKILL.md) | `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` |
| Device caching allocator, private pools or CUDA stream pools | [pytorch-caching-allocator-and-streams](../pytorch-caching-allocator-and-streams/SKILL.md) | `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` |
| Profiler schedule, activities or shape-tracing overhead | [pytorch-inference-profiler](../pytorch-inference-profiler/SKILL.md) | `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` |
| Export plus AOTInductor packaging | [pytorch-aot-inductor-inference](../pytorch-aot-inductor-inference/SKILL.md) | `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` |
| Compile guards, CUDA-graph shapes and output lifetime | [cudagraph-shapes-and-lifetimes](../../../../knowledge_packs/dependency/pytorch/cuda/compiler/cudagraph-shapes-and-lifetimes.json) | `f15b476814ebc5eade36fb40512e379ebf79dd60` |
| Pinned host copy ordering and host allocator reuse | [host-memory-management](../../../hardware/host/host-memory-management/SKILL.md) | `ba56102387ef21a3b04b357e5b183d48f0afefc7` (v2.8.0) |
| DCP async save staging and upload | [dcp-async-save-performance](../dcp-async-save-performance/SKILL.md) | `7d239835e773c91689eb298692097f4a3340491f` |
| NPU behavior | [torchnpu-inference-operating-graph](../../../hardware/ascend/torchnpu-inference-operating-graph/SKILL.md) | separate TorchNPU pin |

F: the v2.15 copy of `docs/source/user_guide/torch_compiler/torch.compiler_cudagraph_trees.md` has SHA-256 `0dbfcef13ad6baea52c6e989eaf6561440c02a26a6ef667da850439d3a88c6a5`, the same digest as the existing compiler card's source. That is document-byte identity for one file, not proof that Inductor or CUDA-graph runtime code is unchanged, and not a reason to merge the pins.

## Do not collapse the pins

P: record the installed wheel commit separately from these source pins. A v2.15 reading does not update the v2.8 host-copy ledger or the DCP ledger. TorchNPU is not a backend of this checkout.

## Limits

Collectives, Inductor codegen, Dynamo guard implementation, quantization, autograd, MPS, XPU and ATen kernels are listed in [unread inventory](references/unread-inventory.md). No performance result is claimed.
