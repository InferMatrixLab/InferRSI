# Nine-repository source scope

This is a finite source-scope snapshot for nine bounded slices inspected on
2026-10-21 and 2026-10-22. Use the linked owners for their complete procedures
and detailed readsets. The Reference Matrix owns maintained provenance and
extraction coverage; the SearchSpace Matrix owns maintained resource × stage
coverage. This snapshot does not track live integration or validation progress.

## Pinned sources

| Repository | Distillation source revision | Preserved independent sources / boundary |
|---|---|---|
| DeepInfer | [`8b16149741a4935e1dec8cea27853f273b374c5b`](https://github.com/deepseek-ai/DeepInfer/tree/8b16149741a4935e1dec8cea27853f273b374c5b) | Apache-2.0 parent; six vendor pins/licenses and unexpanded nested gitlinks remain separate. The reading archive omits nine media assets and leaves ten nested gitlinks unexpanded; this is not a complete whole-tree audit. |
| ComfyUI | [`b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c`](https://github.com/Comfy-Org/ComfyUI/tree/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c) | GPL v3; old AREX `comfy-ui` snapshot is reference input, not equivalent source evidence. |
| llama.cpp | [`707616feb5f379e99ff7442680a55b4a1704c7c9`](https://github.com/ggml-org/llama.cpp/tree/707616feb5f379e99ff7442680a55b4a1704c7c9) | MIT; older loading/host source `3e390af18de1131dda27913c00511725b4274c8a` retains its own scope. |
| MLX | [`bff10220c742907f0c68e55ff174aaea56f74e3d`](https://github.com/ml-explore/mlx/tree/bff10220c742907f0c68e55ff174aaea56f74e3d) | MIT / Apple attribution; framework source is independent of MLX-LM application source. CPU/Metal/CUDA implementations are distinct. |
| MLX-LM | [`ab7f7048dc341ced2d84b1887eeb17d60b0d1b02`](https://github.com/ml-explore/mlx-lm/tree/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02) | MIT / Apple attribution; compatibility with the independently captured MLX pin is unverified. Model-specific caches are not one universal KV type. |
| Diffusers | [`aea7b70be0f594bcdc15a6f2677ee2ca85e49e8e`](https://github.com/huggingface/diffusers/tree/aea7b70be0f594bcdc15a6f2677ee2ca85e49e8e) | Apache-2.0 attribution; existing CUDA group-offload guidance stays at `efe46a5b177af67c64b3666da8ddddac7ee12163`. The selected slice is invocation state. |
| stable-diffusion.cpp | [`b13a48219d5cdf408edcb93da6cd69b612ed03d3`](https://github.com/leejet/stable-diffusion.cpp/tree/b13a48219d5cdf408edcb93da6cd69b612ed03d3) | MIT / leejet; 18 bounded readset paths plus one separately identity-checked README, totaling 19 blobs matched to pinned Git tree IDs and sizes. model_manager.h was limited to selected owner/state fields and symbols. The README is not an implementation read; complete archive/submodule bytes are not authenticated. Matching GGML/private headers remain required. |
| SGLang | [`df13d5dce31abfeff0e701a62e8c39a136758e6c`](https://github.com/sgl-project/sglang/tree/df13d5dce31abfeff0e701a62e8c39a136758e6c) | Apache-2.0 plus retained FastVideo/Diffusers origins; this is `multimodal_gen`, not SGLang-Omni. Old LLM owner `16176278d0180f1a1a578e53e6eef432577876c2` and HiCache peer `f7ad4345b86d147a1c3095a3cebabca9a33ebaa1` remain independent. |
| vLLM-Omni | [`18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e`](https://github.com/vllm-project/vllm-omni/tree/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e) | Apache-2.0 / vLLM-Omni and vLLM attribution; original engine guide at `52194f24fa42e14d1c5e096f4bea4dc7f95cffa1` is preserved rather than silently repinned. |

For the four supplemental sources, a manifest-selected blob check is not a
whole-tree byte check. Diffusers, SGLang and vLLM-Omni retain that explicit
selected-file limitation. stable-diffusion.cpp additionally carries its separate
19-blob identity check, including the separately checked README. Those checks
do not certify unexpanded dependencies.

## Per-repository scope and owner

Each link names a canonical packaged owner. Similar terminology does not make
their work units, state or completion contracts interchangeable. Existing
loading, host-placement and offload references retain their independent pins.

| Repository | Canonical owner | Selected mechanism | Deferred or excluded |
|---|---|---|---|
| DeepInfer | [DeepInfer owner](../../../repositories/deepinfer/bound-windowed-attention-replay/SKILL.md) and [verification budget](../../../repositories/deepinfer/budget-speculative-verification/SKILL.md) | Dependency-closed bounded query replay with separately preserved full state; gated ring margins; verification-row budgeting, draft/verify cost separation and CPU/GPU confidence-round ownership | No native equivalence or sampling-correctness run; model-specific dimensions, vendor/kernel bodies, in-flight preemption safety and backend parity. |
| ComfyUI | [ComfyUI owner](../../../repositories/comfy-ui/SKILL.md) | Dependency-complete output identity versus object identity/retention; lazy consumers and external fingerprints; wrapper/patch identity versus partial/full weight release | Full executor/cache suites, third-party custom nodes, provider storage, native dynamic allocator, model families, device/quality/performance. No LLM KV or storage-tuning claim. |
| llama.cpp | [llama.cpp owner](../../../repositories/llama-cpp/audit-llama-runtime-state/SKILL.md) | Partial ubatch progress and memory-specific rollback; frontend graph compatibility plus fresh inputs/readiness; task/slot/prompt retention and cancellation boundary | Native context/server replay tests; recurrent/hybrid generalization; backend capture/kernel behavior; loading, quantization, full stream sessions and model quality. |
| MLX | [MLX owner](../../../frameworks/mlx/lazy-evaluation-stream-lifetimes/SKILL.md) | Graph construction/evaluation/availability; stream fence/event dependencies; backend buffer retention after graph detach | MLX execution on any backend; allocator internals, compile/fusion, numerical operator coverage, distributed execution and model/service qualification. Does not own LLM request/cache policy. |
| MLX-LM | [MLX-LM owner](../../../repositories/mlx-lm/generation-cache-lifecycle/SKILL.md) | Prefill/decode lookahead boundaries; pending/prompt/generation UID and aligned rows; model/token prefix identity, copy/trim/retention; cooperative stop | Native/model/HTTP tests; model-specific cache families, full speculation/VLM/distributed semantics and combined MLX compatibility. No paged/radix allocator inference. |
| Diffusers | [Diffusers owner](../../../frameworks/diffusers/diffusers-invocation-state/SKILL.md) | Flux wrapper/component identity and `from_pipe` sharing; selected FlowMatchEuler scheduler reset/index progression; interruption and normal output tail | Real scheduler/pipeline test, serving caller serialization, other pipeline/scheduler classes, exception cleanup, offload implementation and image quality. No framework-wide thread-safety verdict. |
| stable-diffusion.cpp | [stable-diffusion.cpp owner](../../../repositories/stable-diffusion-cpp/audit-sd-cpp-residency/SKILL.md) | Native image entry path; managed weights/runtime budget versus device headroom; protected segment pin/preparation, optional prefetch and synchronized activation/cleanup | Matching unexpanded GGML/private headers, model-specific numerical runner chain, device memory/async behavior, graph-cut algorithm, complete loader I/O, video/audio/server. CPU bypasses decisive accelerator gates. |
| SGLang | [SGLang owner](../../../repositories/sglang/audit-sglang-diffusion-lifetimes/SKILL.md) | Default ParallelExecutor and entry/cleanup intervals; component retention and request-tail prefetch; mutable numerical scheduler aliases/dedup copies; timeout/job deletion versus device completion | Concrete offload strategies, pool/disaggregation, realtime/rollout, complete CUDA IPC exception lifetime, model kernels and native quality/performance. Existing LLM/Radix/HiCache is not repinned. |
| vLLM-Omni | [Existing validation owner](../../../repositories/vllm-omni/sub-skills/omni-validation/SKILL.md) and [abort scope](../../../repositories/vllm-omni/sub-skills/omni-validation/references/abort-acknowledgment.md) | Abort submission versus correlated logical receipt versus queued per-replica transfer reclamation; partial AR output/processor commit; waiter/late-result ownership; post-submit wait timeout excludes blocking submission | Native abort guarantee, connector internals, every serving wrapper, full duplex/session lifecycle, all-device reclaim, model/media semantics and service/performance. |

## DeepInfer state and sampling boundary

The [comparison](cross-repository-mechanisms.md#deepinfer-contracts-that-constrain-transfer)
separates compact query rows from preserved full-layout hidden state and
historical main/index KV. Ring margins depend on the outer extra-state flag
and the inner truncation gate. The verification-row floor is an allocation
contract, not an accepted-draft-token guarantee. CPU total-budget selection,
per-request allocation and GPU worker correction consume different available
confidence rounds.

The verification owner retains distinct validation gates: V3 checks exact
cumulative products of conditional per-position inputs, preserving inputs
already expressed cumulatively; G5 measures the complete emitted next-token
distribution, including rejection/residual sampling; G7 uses accepted tokens
over total elapsed time including draft work. Multiplying estimates establishes
neither statistical independence nor calibration. Source guards and release
ordering constrain reachable paths; a missing runtime experiment does not
establish a preemption race or a known defect.

## Validation boundary

For the newly distilled mechanisms, N = native engine/framework/backend
behavior, M = real-model correctness or quality, S = service behavior, and
P = performance or efficacy.

| Slice | N | M | S | P | Separate bounded evidence |
|---|---|---|---|---|---|
| DeepInfer | not_run | not_run | not_run | not_run | Source and unexecuted test assertions |
| ComfyUI | not_run | not_run | not_run | not_run | Seven checks passed on the unchanged complete pure-Python graph_utils module; see the [owner boundary](../../../repositories/comfy-ui/references/validation-boundaries.md). This does not cover executor, cache-signature, model or allocator behavior. |
| llama.cpp | not_run | not_run | not_run | not_run | Source and unexecuted test assertions |
| MLX | not_run | not_run | not_run | not_run | CPU, Metal and CUDA execution remain separately unqualified |
| MLX-LM | not_run | not_run | not_run | not_run | Selected test classes load external model fixtures |
| Diffusers | not_run | not_run | not_run | not_run | Source observations; a real CPU scheduler cycle is a proposed check |
| stable-diffusion.cpp | not_run | not_run | not_run | not_run | Selected source-identity/static checks; CPU bypasses decisive accelerator gates |
| SGLang | not_run | not_run | not_run | not_run | Source and unexecuted test assertions; mocked assertions do not qualify native paths |
| vLLM-Omni | not_run | not_run | not_run | not_run | Source and unexecuted test assertions; synthetic clients do not qualify backend reclamation |

Catalog/resource/package checks establish knowledge delivery, not engine
correctness, model quality, service behavior or speed. Source presence, a
candidate procedure, native correctness and service performance are distinct
claims. Applying a transfer hypothesis requires the matching implementation,
fixtures and relevant backend; no comparable cross-repository benchmark or
compatibility result is established by this snapshot.
