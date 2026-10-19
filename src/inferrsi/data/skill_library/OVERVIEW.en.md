# Five inference repositories as bilingual skills

The package turns five pinned official source snapshots into **operating knowledge**: where to look, what can be changed, which choices interact, what can invalidate correctness, and how to verify a proposed optimization. It includes full English and Chinese editions, not just translated titles.

The main design lesson is to organize knowledge by **work unit, state ownership, scheduling, memory, communication and validation**, then map it to each engine. vLLM and SGLang provide deep examples of token execution and serving; the two Omni repositories add model-specific stage composition and heterogeneous output lifecycles. Strata adds heterogeneous MoE placement, expert memory and speculative execution. The boundaries overlap, and supported paths must be verified at a specific revision.

## Start here

| Repository | Knowledge emphasized | English | 中文 |
|---|---|---|---|
| Strata | Heterogeneous MoE, CPU/GPU placement, memory and speculation | [Skill](en/strata/SKILL.md) | [Skill](zh-CN/strata/SKILL.md) |
| vLLM | Token/admission/input budgets, KV ownership and prefix reuse, scheduler/runner/attention, parallel serving | [Skill](en/vllm/SKILL.md) | [Skill](zh-CN/vllm/SKILL.md) |
| SGLang | Scheduler and cache reuse, Radix/HiCache, prefill/decode and parallelism, extension and tuning | [Skill](en/sglang/SKILL.md) | [Skill](zh-CN/sglang/SKILL.md) |
| SGLang-Omni | Pipeline/stage runtime, scheduler IO boundary, stream/backpressure/transport, model integration | [Skill](en/sglang-omni/SKILL.md) | [Skill](zh-CN/sglang-omni/SKILL.md) |
| vLLM-Omni | Fixed topology vs deploy resources, stage affinity/connectors, AR/diffusion modes, output/state contracts | [Skill](en/vllm-omni/SKILL.md) | [Skill](zh-CN/vllm-omni/SKILL.md) |
| Collection router | Cross-engine reasoning and a unified constrained search workflow | [Skill](en/inference-engine-research/SKILL.md) | [Skill](zh-CN/inference-engine-research/SKILL.md) |

## What to learn across repositories

| Design question | Transferable knowledge | Important boundary |
|---|---|---|
| What is scheduled? | Requests, prefill chunks, decode tokens, speculative work, media chunks or diffusion steps | A bigger batch flag does not establish model support for that schedule unit |
| Who owns state? | Request lifecycle, KV blocks, prefix references, RNG, intermediate tensors and stage/replica affinity | Abort, preemption, reuse and streaming cannot discard or replay arbitrary state |
| What is the memory budget? | Weights + KV/model state + activations + workspace + transfer buffers + graph pools | Device utilization percentages alone do not prove feasibility; include host memory and lifetimes |
| Where is the bottleneck? | Admission/queue, CPU preprocessing, kernels, collectives, cross-stage transfer and output encoding | A local kernel improvement may worsen service p95 or shift the bottleneck |
| What parallelism is legal? | TP/PP/DP/EP and stage replicas; additional model-specific diffusion groups | Names and meanings differ by repository; group/layout and topology constraints matter |
| What is being reused? | Prefix/KV state, embeddings, weights or approximate diffusion intermediate results | Exact reuse and approximation need different validity keys and quality gates |
| How does streaming change execution? | Overlap, chunk size, context windows, readiness, backpressure and completion | First text token is not first usable audio/video; chunk throughput can hide gaps |
| How is improvement proved? | Matched baseline, fixed corpus/output contract, repeated measurements, quality gate and failure record | CPU/mocks cannot certify accelerator or native transport behavior |

## AI engine generation: three search levels

1. **Existing configuration**: search settings exposed and supported by the selected model/backend. First remove infeasible combinations, then profile and tune the measured bottleneck.
2. **Implementation changes**: modify a scheduler, cache policy, kernel/backend choice, runner, transfer path or stage boundary while preserving model semantics. Test state, numerical and concurrency contracts before timing.
3. **Research extensions**: introduce new scheduling/transport/decomposition or approximate computation. State new assumptions, comparison baseline and quality budget explicitly.

Use a constraint system before an optimizer. A candidate is feasible only if it respects hardware memory, communication, supported layouts, model semantics, termination/abort behavior and task quality. Among feasible candidates, compare latency percentiles, throughput, memory and cost. Keep a Pareto frontier where objectives conflict; there is no universal best setting in these artifacts.

## Snapshot and reuse caveats

The five HEADs were captured independently. **They are knowledge snapshots, not a tested compatible dependency stack.** In particular, Omni repositories pin/use specific base-engine releases; do not substitute the separately captured base-engine HEAD merely because it is in the same package.

| Snapshot | Pinned commit |
|---|---|
| strata | [`296b59d2f73c`](https://github.com/Niko1221/Strata/tree/296b59d2f73c8f04a805df29c2fa97655adace78) |
| vllm | [`2521446ac8c9`](https://github.com/vllm-project/vllm/tree/2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5) |
| sglang | [`16176278d018`](https://github.com/sgl-project/sglang/tree/16176278d0180f1a1a578e53e6eef432577876c2) |
| sglang-omni | [`2cfb3b67becb`](https://github.com/sgl-project/sglang-omni/tree/2cfb3b67becb437b70751defe37e63d3af4eedb0) |
| vllm-omni | [`52194f24fa42`](https://github.com/vllm-project/vllm-omni/tree/52194f24fa42e14d1c5e096f4bea4dc7f95cffa1) |

Existing AREX skills were inspected as prior work and refreshed against source rather than treated as current truth. Examples of drift: vLLM Python requirements and scheduler budgets; SGLang benchmark/cache paths and DP flag meanings; vLLM-Omni's 0.26-to-0.31 quickstart alignment. SGLang-Omni's queue implementation also required checking code beyond a descriptive module title. Exact source evidence and refresh boundaries are in the per-repository references.

## How this used AREX

Construction follows AREX-Skill `distill-ml-knowledge`: **scope → ground → construct → verify**, using its direct construction strategy, provenance/routing patterns, operating metadata and review criteria. This is a portable candidate preview. The DisCo managed CLI/importer, full environment preparation and GPU acceptance were not executed. See [construction record](IMPORT.md) and [verification](IMPORT.md).

Each repository is independently readable, with an entry point and progressively loaded references/sub-skills. The optional collection router refers to its five sibling roots; retain all six when using that router. Both languages share canonical skill IDs, so choose one language for any one installation. No global skill was installed or overwritten.

## Try it

```text
Read en/inference-engine-research/SKILL.md. For a new inference engine, derive a constrained search space from these repositories. Separate existing settings, implementation changes and research extensions. For each dimension give a source anchor, compatibility constraints, correctness tests and measurements. Hardware: [fill in]; model/revision: [fill in]; workload and SLO: [fill in].
```

For one repository, read its SKILL.md directly. The source code and model weights are excluded from the library; immutable source URLs and verification recipes are retained. GPU correctness, native distributed behavior and performance still require the target environment.
