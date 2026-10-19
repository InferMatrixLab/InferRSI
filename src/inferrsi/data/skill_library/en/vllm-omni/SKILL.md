---
name: vllm-omni
description: "Explain, tune and extend vLLM-Omni multi-stage AR, diffusion and media-output inference with source-grounded search spaces and validation."
license: Apache-2.0
metadata:
  disco-role: operating
---

# vLLM-Omni engine knowledge

Use this skill to explain, configure, tune or extend **vLLM-Omni** stage-based autoregressive, generation and diffusion execution. Multimodal input alone does not select this skill; its distinguishing boundary is heterogeneous output and model-owned execution pipelines.

This is a source-grounded portable candidate at `52194f24fa42e14d1c5e096f4bea4dc7f95cffa1`. It is not a GPU certification or a complete model catalogue. Read [provenance](references/repo-provenance.md) when the checkout or installed packages differ.

## Route by decision

| Need | Load |
|---|---|
| Explain data/control flow, derive a constrained engine search space | [Architecture and search](sub-skills/omni-architecture/SKILL.md) |
| Choose deployment, stage placement, streaming and performance experiments | [Serving and tuning](sub-skills/omni-serving/SKILL.md) |
| Add/change a pipeline, runner or connector; verify correctness | [Extension and validation](sub-skills/omni-validation/SKILL.md) |

Read only the relevant branch. Source links in [evidence](references/evidence.md) resolve to the pinned revision; instructions and decision criteria are bundled here. Native test commands require a matching engine checkout and environment.

## Shared procedure

1. Identify exact model revision, task/output modality, reference implementation, GPU topology, software revisions, input/output shapes, concurrency and latency/quality contract. State unknowns; do not invent an optimal configuration.
2. Trace `PipelineConfig` → deploy resolution → orchestrator → stage pool/client → scheduler/runner → connector/output processor. Keep topology ownership separate from placement and resource knobs.
3. Label each proposal **existing setting**, **implementation change**, or **research extension**. A dataclass field is not proof that every model/backend supports it.
4. Establish a real-model baseline with the smallest supported concurrency. Preserve model, sampling, generated duration/resolution, seeds and quality target while tuning execution.
5. Compare correctness before latency, then report queue time, stage time, transfer time, peak memory and modality-specific end-to-end metrics. Preserve rejected trials and fallback paths.

## Constraints that change decisions

- `PipelineConfig` and `StagePipelineConfig` own fixed model semantics and stage topology. Changing those requires a registered model variant and new validation; deploy YAML does not define arbitrary new model stages.
- A replica is not a model stage or a tensor-parallel rank. Stateful chunks must retain request/replica affinity until completion, cancellation or explicit failure handling.
- Async chunk transfer, AR continuous batching, diffusion request batching, diffusion step scheduling and streamed final media are different capabilities.
- Do not apply a Thinker quantization recipe to Talker/codec/VAE components without a compatible implementation and quality evidence.
- Successful YAML parsing, imports, CPU probes or mock tests do not establish GPU execution, media quality or throughput.

Return a decision with source evidence, feasible alternatives, assumptions, validation gates and recovery steps. No speedup is established by this skill alone.
