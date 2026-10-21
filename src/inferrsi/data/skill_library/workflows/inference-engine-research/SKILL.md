---
name: inference-engine-research
description: "Route inference-engine research across Strata, vLLM, SGLang and their Omni repositories; derive source-grounded, correctness-constrained search and validation plans."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Inference engine research router

Use this collection to compare architectures or design a constrained search for an inference engine. If the user names one repository, load its entry directly. Keep the library's `repositories/` and `workflows/` layout when using this router so its links reach the repository and framework owners; the repository skills can also be distributed independently.

| Question | Route |
|---|---|
| Compare graph, cache, lifetime, stop and completion contracts across source slices | [Cross-repository mechanisms](references/cross-repository-mechanisms.md) and [source scope](references/repository-source-scope.md) |
| Strata heterogeneous MoE, CPU/GPU expert placement, memory and speculative execution | [strata](../../repositories/strata/SKILL.md) |
| vLLM token scheduling, KV/prefix reuse, execution/parallelism or model integration | [vllm](../../repositories/vllm/SKILL.md) |
| SGLang scheduling, Radix/HiCache, prefill/decode, parallel runtime or extensions | [sglang](../../repositories/sglang/SKILL.md) |
| SGLang-Omni pipelines, stage/scheduler ownership, streaming and transport | [sglang-omni](../../repositories/sglang-omni/SKILL.md) |
| vLLM-Omni model/deploy separation, AR/diffusion execution, stage transport and heterogeneous outputs | [vllm-omni](../../repositories/vllm-omni/SKILL.md) |

## Comparison procedure

1. Fix the model/checkpoint/tokenizer, modalities, hardware/interconnect, software versions, input/output distributions, arrival/concurrency pattern, latency SLO and quality contract. Ask only for missing facts that alter a decision; otherwise state reversible assumptions.
2. Load the smallest relevant repository branches. Trace work units, state ownership, scheduling, memory, communication, output and cleanup before comparing feature names.
3. Produce three separate candidate classes: supported existing settings; implementation changes preserving semantics; research extensions with explicit new assumptions or approximation budgets.
4. Screen constraints before benchmarking: supported model/backend combinations, memory/lifetime, partition/layout, numerical/quality contract, abort/termination and queue stability.
5. Measure matched real workloads. Separate CPU/static, mocked contract, accelerator/native transport, real-model quality and service performance evidence. Do not promote a weaker layer into a stronger claim.
6. Return a source-backed table of candidates, interactions, tests, expected observations and recovery. Rank only valid runs, reporting conflicting objectives as a Pareto frontier rather than claiming a universal winner.

## Transfer rules

DP/EP/TP labels, batch size, prefix cache, async execution and streaming can mean different things across engines. Translate the ownership and capability contract before transferring a knob or optimization. Do not assume an Omni repository accepts the independently captured base-engine HEAD: these snapshots do not constitute a compatibility matrix.

Measure text TTFT/TPOT separately from media first-packet latency, chunk gaps, end-to-end completion, RTF, image/video throughput and quality. Reduced steps, resolution or output length change the workload/quality contract and must be disclosed.

The repository and framework owners retain their pinned provenance and source evidence. The collection is a portable candidate; actual GPU, native distributed and quality validation requires the target environment. No new engine or measured speedup is included.
