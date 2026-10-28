# Skill coverage view

Generated from the registry, the skill sidecars and the two maintained
matrices. **Do not edit by hand**; regenerate after any registry, skill,
matrix or frozen-plan change.

- Input digest: `sha256:20625ca481a285ea88cff5a2e7cdccecd0b2a28a09eb1a43243d97d84731c444`
- Regenerate: `python tools/build_skill_coverage.py`
- Verify without writing: `python tools/build_skill_coverage.py --check`

The digest covers every source file this view reads. It changes when an
input changes and stays fixed across commits that touch neither the view
nor its sources, so `--check` reports real drift only.

This view answers, from the skill outward: which task it addresses, which
SearchSpace resource layers and lifecycle stages it is recorded against,
which source it is pinned to, what its declared state is, whether a frozen
plan ever selected it, and what is missing. It adds no third authoritative
matrix: every field is copied from an owner that already maintains it.

| Field | Owner of the fact |
|---|---|
| Skill id, canonical path, backend | [`skill-index.json`](../src/inferrsi/data/skill_library/skill-index.json) |
| Declared task, status, validation state, provenance readsets | the skill's `SKILL.md` frontmatter and `metadata.json` sidecar |
| Resource layer, lifecycle stage | [SearchSpace Matrix](searchspace-matrix.md) |
| Source identity and inspected scope | [Reference Matrix](reference-matrix.md) |
| Evaluation selection | frozen `evidence/<campaign>/plan/protocol-*.json` |
| Delivery PR and issue | not derived here; see [issue #91](https://github.com/InferMatrixLab/InferRSI/issues/91) and `docs/reviews/issue91-*.md` |

## Snapshot

| Measure | Value |
|---|---|
| Registered skill ids | 74 |
| By category | frameworks 3, hardware 22, methods 19, repositories 24, workflows 6 |
| By backend | ascend 14, common 55, cuda 5 |
| Recorded on a numbered SearchSpace resource layer | 48 |
| Recorded only in a supplementary guidance table (†) | 12 |
| Recorded on two or more resource layers | 24 |
| Recorded in the Reference Matrix | 67 |
| With a `metadata.json` sidecar | 69 |
| Selected by a frozen evaluation plan | 2 |
| `SKILL.md` documents in the library | 118 |
| Unregistered documents (excluded from every count above) | 44 |

A complete inventory is not a coverage claim. Every registered row below
has an entry; that says the listing is exhaustive, not that inference
optimization is fully covered or that any procedure has measured benefit.

## Registered: Hardware and platform (22)

| Skill | Backend | Declared task | SearchSpace layer / stage | Reference Matrix | State | Gaps |
|---|---|---|---|---|---|---|
| [ascend-aclgraph-capture-replay](../src/inferrsi/data/skill_library/hardware/ascend/ascend-aclgraph-capture-replay/SKILL.md) | ascend | Diagnose vLLM-Ascend ACLGraph capture/replay eligibility, stable-input and ordering contracts, and capture-resource ... | 1 Accelerator · Diagnose / Configure / Optimize / Verify | 1 · Systems sources (vllm-project/vllm-ascend @ `8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf` ...) | candidate · not_run · 1 readset(s) | no-eval |
| [ascend-device-health](../src/inferrsi/data/skill_library/hardware/ascend/ascend-device-health/SKILL.md) | ascend | Pre-run health checks and recovery procedures for Ascend NPU devices on shared machines: card-group topology ... | 4 Network · Diagnose<br>5 OS · Observe / Profile / Diagnose / Configure / Verify | 1 · Systems sources (Ascend/MindIE-SD @ 8481d39) | candidate · not_run · 0 readset(s) | no-eval |
| [ascend-distributed-parallel](../src/inferrsi/data/skill_library/hardware/ascend/ascend-distributed-parallel/SKILL.md) | ascend | Select and validate distributed parallelism strategy on Ascend NPU: topology-aware card-group selection, USP/CP/TP/PP ... | 1 Accelerator · Configure<br>4 Network · Diagnose / Configure / Optimize / Verify / Observe | 1 · Systems sources (Ascend/MindIE-SD @ 8481d39)<br>1 · Systems sources (ascend-ai-coding/awesome-ascend-skills @ 75ec89c) | candidate · not_run · 1 readset(s) | no-eval |
| [ascend-graph-mode](../src/inferrsi/data/skill_library/hardware/ascend/ascend-graph-mode/SKILL.md) | ascend | How to configure, debug, and optimize Ascend NPU graph mode (npugraph_ex / aclgraph): capture-and-replay mechanics, FX ... | 1 Accelerator · Configure<br>3 SSD · Diagnose | 1 · Systems sources (ascend-ai-coding/awesome-ascend-skills @ 75ec89c) | candidate · not_run · 0 readset(s) | no-eval |
| [ascend-model-adaptation](../src/inferrsi/data/skill_library/hardware/ascend/ascend-model-adaptation/SKILL.md) | ascend | Patterns for porting LLM/VLM model adapters to Ascend NPU: FP8 checkpoint handling, KV replication with TP, multimodal ... | 1 Accelerator · Configure<br>3 SSD · Diagnose / Configure | 1 · Systems sources (vllm-project/vllm-ascend @ bc8115ed) | candidate · not_run · 0 readset(s) | no-eval |
| [ascend-operator-profiling](../src/inferrsi/data/skill_library/hardware/ascend/ascend-operator-profiling/SKILL.md) | ascend | Benchmark a single Ascend NPU operator using msprof op: build, collect with warmup, read the 8 CSV metrics files ... | 1 Accelerator · Observe / Profile<br>5 OS · Observe / Profile | 1 · Systems sources (ascend-ai-coding/awesome-ascend-skills @ 75ec89c) | candidate · not_run · 0 readset(s) | no-eval |
| [ascend-operator-tuning](../src/inferrsi/data/skill_library/hardware/ascend/ascend-operator-tuning/SKILL.md) | ascend | Run a staged, accuracy-gated tuning campaign on a single Ascend NPU operator: set a numeric target up front, block ... | 1 Accelerator · Optimize | 1 · Systems sources (ascend-ai-coding/awesome-ascend-skills @ 75ec89c) | candidate · not_run · 0 readset(s) | no-eval |
| [ascend-optimization-casebook](../src/inferrsi/data/skill_library/hardware/ascend/ascend-optimization-casebook/SKILL.md) | ascend | Casebook of NPU optimization cases for Ascend inference systems: symptom → diagnosis → action → evidence records for ... | 1 Accelerator · Optimize / Verify | 1 · Systems sources (Ascend/MindIE-SD @ 8481d39) | candidate · not_run · 0 readset(s) | no-eval |
| [ascend-performance-analysis](../src/inferrsi/data/skill_library/hardware/ascend/ascend-performance-analysis/SKILL.md) | ascend | Diagnose performance bottlenecks on Ascend NPU systems using CANN profiling data. Maps GPU profiling concepts (nsys ... | 1 Accelerator · Observe / Profile / Diagnose / Verify<br>4 Network · Observe / Profile / Diagnose / Verify<br>5 OS · Diagnose | 1 · Systems sources (Ascend/MindIE-SD @ 8481d39)<br>1 · Systems sources (cann/cannbot @ `c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110` (selected ...) | candidate · not_run · 1 readset(s) | no-eval |
| [ascend-video-diffusion-optimization](../src/inferrsi/data/skill_library/hardware/ascend/ascend-video-diffusion-optimization/SKILL.md) | ascend | Run and verify goal-driven Ascend video diffusion optimization. Use when the user asks for latency, RTF, throughput, or ... | — | — | candidate · not_run · 1 readset(s) | no-SearchSpace-layer, no-Reference-Matrix-row, no-eval |
| [ascendc-tiling-design](../src/inferrsi/data/skill_library/hardware/ascend/ascendc-tiling-design/SKILL.md) | ascend | Design tiling for a custom AscendC operator: normalize the shape first (axis-collapse or flatten), answer the ... | 1 Accelerator · Optimize | 1 · Systems sources (ascend-ai-coding/awesome-ascend-skills @ 75ec89c) | candidate · not_run · 0 readset(s) | no-eval |
| [cann-attribution-overlap](../src/inferrsi/data/skill_library/hardware/ascend/cann-attribution-overlap/SKILL.md) | ascend | Attribute NPU trace kernels to model source and plan bounded multistream overlap: select a representative step, map ... | 1 Accelerator · Observe / Profile / Diagnose / Optimize / Verify<br>4 Network · Diagnose / Optimize / Verify | 1 · Systems sources (cann/oam-tools @ `8440935f` (!302 import; later master `f3cf4115` ...) | candidate · not_run · 0 readset(s) | no-eval |
| [cgroup-resource-controls](../src/inferrsi/data/skill_library/hardware/host/cgroup-resource-controls/SKILL.md) | common | Diagnose and configure cgroup v2 resource controls for serving/training workloads: distinguish quota stalls from ... | 2 RAM/Host · Observe / Profile / Configure / Verify<br>5 OS · Observe / Profile / Diagnose / Configure / Optimize / Verify | 1 · Systems sources (Linux cgroup v2 docs — kernel.org live 2026-10-15 (revision ...) | candidate · not_run · 0 readset(s) | no-eval |
| [diagnose-attention-bottlenecks](../src/inferrsi/data/skill_library/hardware/cuda/diagnose-attention-bottlenecks/SKILL.md) | cuda | Diagnose the next attention-kernel bottleneck after IO reduction using evidence about HBM traffic, work ownership ... | 1 Accelerator · Diagnose / Optimize / Verify | 1 · Systems sources (FlashAttention — [2205.14135v2](https://arxiv.org/abs/2205.14135v2)) | candidate · not_run · 9 readset(s) | no-eval |
| [host-memory-management](../src/inferrsi/data/skill_library/hardware/host/host-memory-management/SKILL.md) | common | Configure host memory for inference serving: pinned memory for fast H2D transfers, async transfer streams, Python GIL ... | 2 RAM/Host · Configure | 1 · Systems sources (vllm-project/vllm-ascend @ `8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf` ...) | candidate · not_run · 2 readset(s) | no-eval |
| [host-overhead-optimization](../src/inferrsi/data/skill_library/hardware/host/host-overhead-optimization/SKILL.md) | common | Profile and reduce CPU/host overhead in inference serving using line_profiler. Iterative ... | 2 RAM/Host · Optimize / Diagnose / Verify | 1 · Systems sources (NVIDIA/TensorRT-LLM @ f33e0e5fd) | candidate · not_run · 0 readset(s) | no-eval |
| [host-overhead-profiling](../src/inferrsi/data/skill_library/hardware/cuda/host-overhead-profiling/SKILL.md) | cuda | Detect and diagnose CPU/host overhead in inference serving from nsys traces. Answers: is host overhead the bottleneck? ... | 2 RAM/Host · Observe / Profile / Diagnose | 1 · Systems sources (NVIDIA/TensorRT-LLM @ f33e0e5fd) | candidate · not_run · 0 readset(s) | no-eval |
| [os-process-placement](../src/inferrsi/data/skill_library/hardware/host/os-process-placement/SKILL.md) | common | Place and configure inference/training processes at the OS level before measuring or optimizing: check then pin CPU ... | 5 OS · Optimize | 1 · Systems sources (NVIDIA/TensorRT-LLM @ f33e0e5fd)<br>1 · Systems sources (ascend-ai-coding/awesome-ascend-skills @ 75ec89c)<br>1 · Systems sources (ggml-org/llama.cpp @ `3e390af18de1131dda27913c00511725b4274c8a` (MIT ...)<br>1 · Systems sources (vllm-project/vllm-ascend @ bc8115ed) | candidate · not_run · 1 readset(s) | no-eval |
| [reason-hopper-kernels](../src/inferrsi/data/skill_library/hardware/cuda/reason-hopper-kernels/SKILL.md) | cuda | Reason about Hopper SM90 CUDA GEMM kernels using TMA and mbarrier lifetimes, WGMMA warpgroup participation, register ... | 1 Accelerator † guidance: Hopper kernel reasoning (source-derived) | 1 · Systems sources (NVlabs/kda @ `acdd79343c5e9d0c7cb96289f26fd3f1051ce785` → ...) | candidate · not_run · 3 readset(s) | no-eval |
| [storage-io-measurement](../src/inferrsi/data/skill_library/hardware/host/storage-io-measurement/SKILL.md) | common | Measure storage I/O for LLM/diffusion serving without conflating device metrics with application outcomes: match the ... | 3 SSD · Observe / Profile / Diagnose / Verify | 1 · Systems sources (axboe/fio @ acb7a302)<br>1 · Systems sources (sysstat/sysstat @ efd0c445) | candidate · not_run · 0 readset(s) | no-eval |
| [torchnpu-device-memory-lifecycle](../src/inferrsi/data/skill_library/hardware/ascend/torchnpu-device-memory-lifecycle/SKILL.md) | ascend | Diagnose TorchNPU device-HBM reuse, cross-stream lifetimes, cache retention and fragmentation, then propose ... | 1 Accelerator · Diagnose / Configure / Optimize / Verify | 1 · Systems sources (Ascend/pytorch (TorchNPU) @ `67511c53cd4c88014f6123de7097677e60e85faa` ...) | candidate · not_run · 1 readset(s) | no-eval |
| [torchnpu-pinned-host-memory-lifecycle](../src/inferrsi/data/skill_library/hardware/ascend/torchnpu-pinned-host-memory-lifecycle/SKILL.md) | ascend | Diagnose TorchNPU pinned-host RAM allocation, asynchronous-copy lifetime, reuse and cache controls, then propose ... | 2 RAM/Host · Diagnose / Configure / Optimize / Verify | 1 · Systems sources (Ascend/pytorch (TorchNPU) @ `67511c53cd4c88014f6123de7097677e60e85faa` ...) | candidate · not_run · 1 readset(s) | no-eval |

## Registered: Frameworks (3)

| Skill | Backend | Declared task | SearchSpace layer / stage | Reference Matrix | State | Gaps |
|---|---|---|---|---|---|---|
| [dcp-async-save-performance](../src/inferrsi/data/skill_library/frameworks/pytorch/dcp-async-save-performance/SKILL.md) | common | Diagnose training-visible checkpoint pauses using PyTorch Distributed Checkpoint asynchronous saving and staging ... | 1 Accelerator · Diagnose / Configure / Optimize<br>2 RAM/Host · Observe / Profile / Configure / Optimize / Verify<br>3 SSD · Observe / Profile / Configure / Optimize / Verify | 1 · Systems sources (C1 / DCP async-save-only approval — pytorch/pytorch @ ...) | candidate · not_run · 1 readset(s) | no-eval |
| [diffusers-invocation-state](../src/inferrsi/data/skill_library/frameworks/diffusers/diffusers-invocation-state/SKILL.md) | common | Trace Diffusers pipeline-wrapper and scheduler invocation state when repeated calls, from_pipe reuse or interruption ... | 2 RAM/Host † guidance: Diffusers invocation guidance (source-derived) | Diffusers invocation source extraction (huggingface/diffusers @ `aea7b70be0f594bcdc15a6f2677ee2ca85e49e8e` ...) | candidate · not_run · 1 readset(s) | no-eval |
| [lazy-evaluation-stream-lifetimes](../src/inferrsi/data/skill_library/frameworks/mlx/lazy-evaluation-stream-lifetimes/SKILL.md) | common | Diagnose MLX lazy evaluation, cross-stream ordering and array-buffer lifetimes when timing, memory use or asynchronous ... | 1 Accelerator † guidance: MLX framework guidance (source-derived) | MLX framework source extraction (ml-explore/mlx @ `bff10220c742907f0c68e55ff174aaea56f74e3d` (MIT)) | candidate · not_run · 1 readset(s) | no-eval |

## Registered: Repositories (24)

| Skill | Backend | Declared task | SearchSpace layer / stage | Reference Matrix | State | Gaps |
|---|---|---|---|---|---|---|
| [audit-afd-p2p-exchanges](../src/inferrsi/data/skill_library/repositories/afd-plugin/audit-afd-p2p-exchanges/SKILL.md) | cuda | Audit CUDA P2pNccl Attention/FFN rank namespaces and per-stage, per-peer hidden-state ownership when uneven worker ... | 1 Accelerator · Diagnose / Configure / Verify | 1 · Systems sources (vllm-project/afd-plugin @ `df8d6a0c403c3ca1b4ed9cf1687e7204908bebec` ...) | candidate · not_run · 1 readset(s) | no-eval |
| [audit-flare-session-lifecycle](../src/inferrsi/data/skill_library/repositories/flare-local-inference/audit-flare-session-lifecycle/SKILL.md) | cuda | Audit Flare complete prefix/session restoration, inbound transfer tickets, publication/use/retirement fences and ... | 1 Accelerator † guidance: Flare preparation and complete-session source contracts<br>2 RAM/Host † guidance: Flare preparation and complete-session source contracts<br>3 SSD † guidance: Flare preparation and complete-session source contracts | Flare preparation and complete-session source knowledge (NVIDIA/flare-local-inference → [NVIDIA/local-inference](https://github ...) | candidate · not_run · 2 readset(s) | no-eval |
| [audit-h3-metal-fasth3-semantics](../src/inferrsi/data/skill_library/repositories/h3-metal/audit-h3-metal-fasth3-semantics/SKILL.md) | common | Audit h3-metal FastH3 effective configuration, checkpoint tensor and schedule semantics, partial VSA tiles, sparse ... | 1 Accelerator · Observe / Diagnose / Verify | 1 · Systems sources (zuiho-kai/h3-metal @ `4ba47a3eabdbebf801ac6664b31f8ec168bc57a8` ...) | candidate · not_run · 3 readset(s) | no-eval |
| [audit-h3-runtime-residency](../src/inferrsi/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/SKILL.md) | common | Audit MiniMax-H3 generation in h3.c on Apple Silicon by tracing conditioning, AdaLN precompute, DiT residency, Metal ... | 1 Accelerator · Observe / Diagnose / Verify<br>2 RAM/Host · Observe / Diagnose / Verify<br>3 SSD · Diagnose / Configure / Verify | 1 · Systems sources (antirez/h3.c @ `8974cc055ea9c02fcd14cc27dfda3e1027c05153` (MIT ...) | candidate · not_run · 3 readset(s) | no-eval |
| [audit-llama-runtime-state](../src/inferrsi/data/skill_library/repositories/llama-cpp/audit-llama-runtime-state/SKILL.md) | common | Audit llama.cpp context memory, partial decode progress, graph reuse and server cancellation when a retry, stale ... | 1 Accelerator · Diagnose / Verify<br>2 RAM/Host · Diagnose / Verify | 1 · Systems sources (ggml-org/llama.cpp @ `707616feb5f379e99ff7442680a55b4a1704c7c9` (MIT ...) | candidate · not_run · 1 readset(s) | no-eval |
| [audit-recurrent-kv-finalization](../src/inferrsi/data/skill_library/repositories/vllm-rlt/audit-recurrent-kv-finalization/SKILL.md) | common | Audit vLLM-RLT synchronous early-exit KV propagation, later depth-specific attention reads, and request storage ... | — | 1 · Systems sources (InferMatrixLab/vllm-rlt (legacy ThinkFlowLab/vllm-rlt) @ ...) | candidate · not_run · 2 readset(s) | no-SearchSpace-layer, no-eval |
| [audit-sd-cpp-residency](../src/inferrsi/data/skill_library/repositories/stable-diffusion-cpp/audit-sd-cpp-residency/SKILL.md) | common | Audit stable-diffusion.cpp image-generation memory pressure by separating catalog freshness and weight-byte delivery ... | 1 Accelerator · Observe / Diagnose / Verify<br>2 RAM/Host · Observe / Diagnose / Verify<br>3 SSD · Diagnose / Verify | 1 · Systems sources (leejet/stable-diffusion.cpp @ `b13a48219d5cdf408edcb93da6cd69b612ed03d ...) | candidate · not_run · 2 readset(s) | no-eval |
| [audit-sglang-diffusion-lifetimes](../src/inferrsi/data/skill_library/repositories/sglang/audit-sglang-diffusion-lifetimes/SKILL.md) | common | Diagnose SGLang multimodal_gen stage state, component residency and request timeout/deletion when grouped outputs ... | 1 Accelerator · Diagnose / Verify<br>2 RAM/Host · Diagnose / Verify | 1 · Systems sources (sgl-project/sglang @ `df13d5dce31abfeff0e701a62e8c39a136758e6c` ...) | candidate · not_run · 1 readset(s) | no-eval |
| [audit-vllm-kv-lifetimes](../src/inferrsi/data/skill_library/repositories/vllm/audit-vllm-kv-lifetimes/SKILL.md) | common | Audit vLLM V1 asynchronous KV load/save completion, block retention, preemption, and receive-failure contracts when ... | 1 Accelerator · Observe / Diagnose / Verify | 1 · Systems sources (vllm-project/vllm @ `7f730b4cea9a66520a9200265928ebe016b48a39` ...) | candidate · not_run · 1 readset(s) | no-eval |
| [bound-windowed-attention-replay](../src/inferrsi/data/skill_library/repositories/deepinfer/bound-windowed-attention-replay/SKILL.md) | common | Bound replay or prefill query rows across a producer/consumer boundary whose retained inputs and separately preserved ... | 1 Accelerator † guidance: DeepInfer bounded source guidance<br>2 RAM/Host † guidance: DeepInfer bounded source guidance | DeepInfer source extraction (deepseek-ai/DeepInfer @ `8b16149741a4935e1dec8cea27853f273b374c5b` ...) | candidate · not_run · 2 readset(s) | no-eval |
| [budget-speculative-verification](../src/inferrsi/data/skill_library/repositories/deepinfer/budget-speculative-verification/SKILL.md) | common | Decide how many draft tokens to verify per decode step when acceptance varies by request and position. Use when an ... | 1 Accelerator † guidance: DeepInfer bounded source guidance | DeepInfer source extraction (deepseek-ai/DeepInfer @ `8b16149741a4935e1dec8cea27853f273b374c5b` ...) | candidate · not_run · 2 readset(s) | no-eval |
| [comfy-ui](../src/inferrsi/data/skill_library/repositories/comfy-ui/SKILL.md) | common | Audit ComfyUI workflow-output cache validity, lazy dependencies and model-weight residency as separate state contracts ... | 1 Accelerator · Diagnose / Configure / Verify<br>2 RAM/Host · Diagnose / Configure / Verify | 1 · Systems sources (Comfy-Org/ComfyUI @ `b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c` (GNU ...) | candidate · not_run · 1 readset(s) | no-eval |
| [diagnose-vllm-admission-pressure](../src/inferrsi/data/skill_library/repositories/vllm/diagnose-vllm-admission-pressure/SKILL.md) | common | Diagnose vLLM V1 admission stalls and KV-pressure preemption by separating token, input, active-request ... | 1 Accelerator · Observe / Diagnose / Configure / Optimize / Verify | 1 · Systems sources (vllm-project/vllm @ `7f730b4cea9a66520a9200265928ebe016b48a39` ...) | candidate · not_run · 14 readset(s) | no-eval |
| [dwarfstar](../src/inferrsi/data/skill_library/repositories/dwarfstar/SKILL.md) | common | Investigate DwarfStar model fit, expert SSD streaming, session and vision cache correctness, speculative sampling and ... | — | DwarfStar portable AREX extraction (antirez/ds4 @ `ee7e8405232c8971000cc7ba2b945b00bf6d20d3`; AREX-Skill ...) | candidate · partial_cpu_only · 2 readset(s) | no-SearchSpace-layer, no-eval |
| [generation-cache-lifecycle](../src/inferrsi/data/skill_library/repositories/mlx-lm/generation-cache-lifecycle/SKILL.md) | common | Trace MLX-LM prefill, generation batching, prompt-cache reuse and cooperative stopping when request state, cache rows ... | 2 RAM/Host † guidance: MLX-LM application guidance (source-derived) | MLX-LM application source extraction (ml-explore/mlx-lm @ `ab7f7048dc341ced2d84b1887eeb17d60b0d1b02` (MIT)) | candidate · not_run · 1 readset(s) | no-eval |
| [husky](../src/inferrsi/data/skill_library/repositories/husky/SKILL.md) | common | Review Husky's official-document claims as research hypotheses, separating author reports, implementation evidence ... | — | Husky document-only research adaptation (Official https://husky.underdog.ai/; displayed2026-09-20 ...) | candidate · not_run · 2 readset(s) | no-SearchSpace-layer, no-eval |
| [kv-tier-management](../src/inferrsi/data/skill_library/repositories/lmcache/kv-tier-management/SKILL.md) | common | Manage runtime KV cache tiers (GPU → CPU RAM → local disk) for LLM serving: decide when KV is stored, retained ... | 2 RAM/Host · Configure / Optimize<br>3 SSD · Optimize | 1 · Systems sources (LMCache/LMCache @ c3b875a) | candidate · not_run · 0 readset(s) | no-eval |
| [lily](../src/inferrsi/data/skill_library/repositories/lily/SKILL.md) | common | Investigate Lily's exact Qwen3.6-35B-A3B MLX-affine-Q4 contract, Metal state and kernels, strict greedy text API ... | — | Lily portable AREX extraction (perplexityai/pplx-garden `lily/` @ `1ed972ed3f0bd5616c997c9507c25616c6 ...) | candidate · not_run · 2 readset(s) | no-SearchSpace-layer, no-eval |
| [mistral-rs](../src/inferrsi/data/skill_library/repositories/mistral-rs/SKILL.md) | common | Investigate mistral.rs Metal paged-attention decode layouts, prefill coordinates and workspace, actual-model prewarm ... | 1 Accelerator † guidance: mistral.rs Metal paged-attention source contracts<br>2 RAM/Host † guidance: mistral.rs Metal paged-attention source contracts | mistral.rs Metal paged-attention extraction (EricLBuehler/mistral.rs @ `9459891e7697238225885518119682ac8209a612` ...) | candidate · not_run · 2 readset(s) | no-eval |
| [mlc-llm](../src/inferrsi/data/skill_library/repositories/mlc-llm/SKILL.md) | common | Investigate MLC LLM compiled Metal artifact/schema, Apple target and pinned TVM module/storage/stream contracts, and ... | 1 Accelerator † guidance: MLC LLM artifact, target and runtime source contracts<br>2 RAM/Host † guidance: MLC LLM artifact, target and runtime source contracts | MLC LLM compiled Metal and runtime contracts (mlc-ai/mlc-llm @ `8978ea9aec626d64096aaa92fbc89bda2e3ea802`; TVM ...) | candidate · not_run · 2 readset(s) | no-eval |
| [mlx-swift-lm](../src/inferrsi/data/skill_library/repositories/mlx-swift-lm/SKILL.md) | common | Investigate MLX Swift LM generation ownership, cancellation and settled task completion, and recurrent GatedDelta Metal ... | 1 Accelerator † guidance: MLX Swift LM ownership and recurrent Metal source contracts<br>2 RAM/Host † guidance: MLX Swift LM ownership and recurrent Metal source contracts | MLX Swift LM lifecycle and recurrent Metal extraction (ml-explore/mlx-swift-lm @ `3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac` ...) | candidate · not_run · 2 readset(s) | no-eval |
| [project-maya](../src/inferrsi/data/skill_library/repositories/project-maya/SKILL.md) | common | Investigate Project Maya model-family dispatch, representation and memory tiers, API versus native state, speculative ... | 1 Accelerator † guidance: Project Maya model-specific source contracts<br>2 RAM/Host † guidance: Project Maya model-specific source contracts<br>3 SSD † guidance: Project Maya model-specific source contracts | Project Maya source and CPU-slice extraction (mw00/project-maya @ `249f9a87d1a9d72bec2b684d704b0aa9296b1c9c` ...) | candidate · partial_cpu_only · 2 readset(s) | no-eval |
| [splash](../src/inferrsi/data/skill_library/repositories/splash/SKILL.md) | common | Investigate Splash model-format compatibility, automatic memory planning, Metal and ANE execution, DFlash2 ... | — | Splash portable AREX extraction (incoai/splash @ `39a97385f8560cf8a93972cec9b0a963c9195250`; AREX ...) | candidate · partial_cpu_only · 2 readset(s) | no-SearchSpace-layer, no-eval |
| [vllm-metal](../src/inferrsi/data/skill_library/repositories/vllm-metal/SKILL.md) | common | Investigate vllm-metal Apple inference through platform and native-ABI selection, paged KV/offload ownership ... | 1 Accelerator † guidance: vLLM Metal selected source contracts<br>2 RAM/Host † guidance: vLLM Metal selected source contracts<br>3 SSD † guidance: vLLM Metal selected source contracts | vLLM Metal portable AREX source and CPU extraction (vllm-project/vllm-metal @ `e7df7a6ff215f99c7842552d230fdbc709835934` ...) | candidate · partial_cpu_only · 2 readset(s) | no-eval |

## Registered: Methods (19)

| Skill | Backend | Declared task | SearchSpace layer / stage | Reference Matrix | State | Gaps |
|---|---|---|---|---|---|---|
| [assess-serving-preemption](../src/inferrsi/data/skill_library/methods/assess-serving-preemption/SKILL.md) | common | Assess whether LLM serving queue delays justify token-boundary priority preemption, accounting for suspended KV, host ... | 1 Accelerator · Diagnose / Configure / Optimize / Verify<br>2 RAM/Host · Diagnose / Configure / Optimize / Verify | 1 · Systems sources (Orca — OSDI 2022 proceedings) | candidate · not_run · 1 readset(s) | no-eval |
| [assess-split-backward-schedule](../src/inferrsi/data/skill_library/methods/assess-split-backward-schedule/SKILL.md) | common | Evaluate memory-capped split-backward and V-shaped pipeline scheduling proposals, preserving synchronous update ... | 1 Accelerator · Diagnose / Configure / Optimize / Verify | 1 · Systems sources (Zero Bubble — [2401.10241v1](https://arxiv.org/abs/2401.10241v1)) | candidate · not_run · 1 readset(s) | no-eval |
| [audit-fixed-workload-claim](../src/inferrsi/data/skill_library/methods/audit-fixed-workload-claim/SKILL.md) | common | Audit a performance claim from supplied fixed-workload reports and an explicit measurement contract. Check aggregation ... | — | — | candidate · not_run · 0 readset(s) | no-SearchSpace-layer, no-Reference-Matrix-row, no-eval |
| [calibrate-serving-simulation](../src/inferrsi/data/skill_library/methods/calibrate-serving-simulation/SKILL.md) | common | Build an evidence-gated serving-configuration shortlist from a profiled simulator while separating empirical ... | 1 Accelerator · Diagnose / Verify | 1 · Systems sources (Vidur — [2405.05465v2](https://arxiv.org/abs/2405.05465v2)) | candidate · not_run · 1 readset(s) | no-eval |
| [checkpoint-recovery-consistency](../src/inferrsi/data/skill_library/methods/checkpoint-recovery-consistency/SKILL.md) | common | Assess distributed checkpoint recovery using DLRover memory agreement, persistence completion and replica transport ... | 2 RAM/Host · Configure / Verify<br>3 SSD · Configure / Verify<br>4 Network · Diagnose / Configure / Verify<br>5 OS · Diagnose / Configure | 1 · Systems sources (C3 / DLRover FlashCheckpoint @ `e35b1ad90e2928ca6bacf5d22117f71356 ...)<br>1 · Systems sources (C4 / NVIDIA Resiliency Extension @ ...) | candidate · not_run · 1 readset(s) | no-eval |
| [choose-parallel-training-plan](../src/inferrsi/data/skill_library/methods/choose-parallel-training-plan/SKILL.md) | common | Compare stage, device-mesh and operator-sharding candidates for static distributed training while accounting for ... | 1 Accelerator · Diagnose / Configure / Optimize / Verify<br>4 Network · Diagnose / Configure / Optimize / Verify | 1 · Systems sources (Alpa — [2201.12023v3](https://arxiv.org/abs/2201.12023v3)) | candidate · not_run · 1 readset(s) | no-eval |
| [dense-performance-evidence](../src/inferrsi/data/skill_library/methods/dense-performance-evidence/SKILL.md) | common | Taxonomy of performance evidence an optimization agent needs, ordered by collection cost and diagnostic power. Maps ... | 1 Accelerator · Observe / Profile / Verify<br>2 RAM/Host · Verify<br>4 Network · Verify | 1 · Systems sources (NVIDIA/TensorRT-LLM @ f33e0e5fd)<br>2 · Methodology and corpus references (JiusiServe/vllm-evolve @ 43cc82c)<br>2 · Methodology and corpus references (microsoft/SkillOpt @ 343db22) | candidate · not_run · 0 readset(s) | — |
| [evaluate-elastic-serving-placement](../src/inferrsi/data/skill_library/methods/evaluate-elastic-serving-placement/SKILL.md) | common | Compare migrating an LLM request between model replicas with changing its sequence-parallel execution group, including ... | 1 Accelerator · Diagnose / Configure / Optimize / Verify<br>2 RAM/Host · Diagnose / Configure / Optimize / Verify<br>4 Network · Diagnose / Configure / Optimize / Verify | 1 · Systems sources (Llumnix — [2406.03243v1](https://arxiv.org/abs/2406.03243v1)) | candidate · not_run · 1 readset(s) | no-eval |
| [inference-benchmark-design](../src/inferrsi/data/skill_library/methods/inference-benchmark-design/SKILL.md) | common | Select task quality gates, reference parity checks and performance workloads for text, agentic coding, work agents ... | — | 2 · Methodology and corpus references (JiusiServe/vllm-evolve @ 43cc82c)<br>Task-specific benchmark selection (issue #60) ([Issue #60 report](https://github.com/InferMatrixLab/InferRSI/issues/6 ...) | candidate · not_run · 2 readset(s) | no-SearchSpace-layer |
| [inference-optimization-casebook](../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/SKILL.md) | common | How to structure and use a casebook of past optimization decisions as a decision-support tool. Extracts the casebook ... | 1 Accelerator · Optimize | 1 · Systems sources (NVIDIA/TensorRT-LLM @ f33e0e5fd) | candidate · not_run · 0 readset(s) | no-eval |
| [kernel-writing-guide](../src/inferrsi/data/skill_library/methods/kernel-writing-guide/SKILL.md) | common | Decision guide for writing custom inference kernels: when to write one, which framework to choose (Triton, CuTe DSL ... | 1 Accelerator · Optimize / Diagnose / Configure / Verify | 1 · Systems sources (Dao-AILab/causal-conv1d @ `cd81f0413cad2fc1e6f17e785ac39f59aae690cd` ...)<br>1 · Systems sources (NVIDIA/TensorRT-LLM @ f33e0e5fd)<br>1 · Systems sources (mindspore-ai/akg @ `5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff` ...) | candidate · not_run · 2 readset(s) | no-eval |
| [optimization-search-policy](../src/inferrsi/data/skill_library/methods/optimization-search-policy/SKILL.md) | common | Policy for how an optimization agent should select, order, and stop optimization experiments. Covers candidate ... | 1 Accelerator · Optimize | 2 · Methodology and corpus references (JiusiServe/vllm-evolve @ 43cc82c)<br>2 · Methodology and corpus references (RRSI — arXiv 2609.24972v3)<br>2 · Methodology and corpus references (arXiv 2608.01867 (CRISP))<br>2 · Methodology and corpus references (microsoft/SkillOpt @ 343db22) | candidate · not_run · 6 readset(s) | no-eval |
| [performance-ceiling-analysis](../src/inferrsi/data/skill_library/methods/performance-ceiling-analysis/SKILL.md) | common | Estimate optimization headroom before modifying an inference system. Produces a three-level ceiling model (analytical ... | 1 Accelerator · Diagnose / Verify<br>5 OS · Configure | 1 · Systems sources (NVIDIA/TensorRT-LLM @ f33e0e5fd)<br>1 · Systems sources (ebugger/Empirical-Roofline-Toolkit @ 0771fa9)<br>1 · Systems sources (hahnyuan/LLM-Viewer @ 1893e4b) | candidate · not_run · 16 readset(s) | no-eval |
| [plan-activation-residency](../src/inferrsi/data/skill_library/methods/plan-activation-residency/SKILL.md) | common | Propose training activation and gradient memory reductions by distinguishing lifetime reordering, address packing and ... | 1 Accelerator · Diagnose / Optimize / Verify | 1 · Systems sources (Checkmate — [1910.02653v3](https://arxiv.org/abs/1910.02653v3)) | candidate · not_run · 1 readset(s) | no-eval |
| [repository-evolution-analysis](../src/inferrsi/data/skill_library/methods/repository-evolution-analysis/SKILL.md) | common | Analyze a repository's commit history to build a capability-evolution model: what the system can do, how it got there ... | — | 2 · Methodology and corpus references (LearningToCommit/LearningToCommit @ 7e5a1d7)<br>2 · Methodology and corpus references (yetone/magpie @ 77800032) | candidate · not_run · 0 readset(s) | no-SearchSpace-layer, no-eval |
| [skill-evolution-playbook](../src/inferrsi/data/skill_library/methods/skill-evolution-playbook/SKILL.md) | common | Practical design choices for evolving agent skills from execution traces: when one trajectory should update a skill ... | — | 2 · Methodology and corpus references (Qwen-Applications/Trace2Skill @ 3d0b52a)<br>2 · Methodology and corpus references (microsoft/SkillOpt @ 343db22) | candidate · not_run · 0 readset(s) | no-SearchSpace-layer, no-eval |
| [training-input-pipeline](../src/inferrsi/data/skill_library/methods/training-input-pipeline/SKILL.md) | common | Diagnose training input stalls and choose bounded queue, shard-cache and cache-ownership changes from DALI, Mosaic ... | 1 Accelerator · Observe / Configure / Optimize<br>2 RAM/Host · Observe / Diagnose / Configure / Optimize<br>3 SSD · Diagnose / Configure / Optimize<br>4 Network · Configure / Optimize<br>5 OS · Configure / Optimize | 1 · Systems sources (B1 / NVIDIA DALI @ `6fe47c48d3b0ca335f5e1afd3c77c750b2c7e041` ...)<br>1 · Systems sources (B2 / Mosaic Streaming @ `d99bf9c7cdf2dd4ed62a4960ed35270b93337a5f` ...)<br>1 · Systems sources (B3 / FFCV @ `3a12966b3afe3a81733a732e633317d747bfaac7` ...) | candidate · not_run · 1 readset(s) | no-eval |
| [training-resource-budget](../src/inferrsi/data/skill_library/methods/training-resource-budget/SKILL.md) | common | Choose training offload and resource-budget changes using pinned DeepSpeed configuration, attributed expert diagnosis ... | 1 Accelerator · Diagnose / Configure / Optimize<br>2 RAM/Host · Observe / Diagnose / Configure / Optimize / Verify<br>3 SSD · Configure / Optimize<br>4 Network · Observe / Diagnose / Verify<br>5 OS · Diagnose / Configure | 1 · Systems sources (CR1 / DeepSpeed ZeRO-Infinity @ `5f266e26d216a705d9c64cac88fb813ce ...)<br>1 · Systems sources (CR5 / Ascend MindSpeed adaptive memory — `core_r0.8.0`, page ...)<br>1 · Systems sources (ZeRO-Offload — [2101.06840v1](https://arxiv.org/abs/2101.06840v1))<br>2 · Methodology and corpus references (CR6 / Stas Bekman ML Engineering Open Book @ ...) | candidate · not_run · 8 readset(s) | no-eval |
| [weight-loading-optimization](../src/inferrsi/data/skill_library/methods/weight-loading-optimization/SKILL.md) | common | Optimize the serving-level weight load path from storage to device: judge the load path on four dimensions (source ... | 1 Accelerator † guidance: Flare preparation and complete-session source contracts<br>2 RAM/Host † guidance: Flare preparation and complete-session source contracts<br>3 SSD · Observe / Profile / Diagnose / Optimize / Verify † guidance: Flare preparation and complete-session source contracts<br>4 Network · Configure / Optimize / Verify | 1 · Systems sources (Ascend/MindIE-SD @ 8481d39)<br>1 · Systems sources (NVIDIA/TensorRT-LLM @ f33e0e5fd)<br>1 · Systems sources (ascend-ai-coding/awesome-ascend-skills @ 75ec89c)<br>1 · Systems sources (foundation-model-stack/fastsafetensors @ 219e256)<br>1 · Systems sources (ggml-org/llama.cpp @ `3e390af18de1131dda27913c00511725b4274c8a` (MIT ...)<br>1 · Systems sources (mindie-agent/mindie-agent @ 6a81b41) | candidate · not_run · 3 readset(s) | no-eval |

## Registered: Workflows (6)

| Skill | Backend | Declared task | SearchSpace layer / stage | Reference Matrix | State | Gaps |
|---|---|---|---|---|---|---|
| [cite-check-downstream-pr](../src/inferrsi/data/skill_library/workflows/cite-check-downstream-pr/SKILL.md) | common | Review a downstream PR description for correct acceptance issue links, SHA pins, and artifact citations. | — | — | unknown · unknown · 0 readset(s) | no-SearchSpace-layer, no-Reference-Matrix-row, no-sidecar, no-eval |
| [claim-contract](../src/inferrsi/data/skill_library/workflows/claim-contract/SKILL.md) | common | Enforce ThinkFlowLab claim contract wording and verdict rules without embedding campaign-specific revision pins. | 1 Accelerator · Verify | — | unknown · unknown · 0 readset(s) | no-Reference-Matrix-row, no-sidecar, no-eval |
| [competitor-scan](../src/inferrsi/data/skill_library/workflows/competitor-scan/SKILL.md) | common | Structure a lightweight competitive scan without inventing benchmark numbers or campaign verdicts. | — | — | unknown · unknown · 0 readset(s) | no-SearchSpace-layer, no-Reference-Matrix-row, no-sidecar, no-eval |
| [draft-acceptance-issue](../src/inferrsi/data/skill_library/workflows/draft-acceptance-issue/SKILL.md) | common | Draft a campaign acceptance issue with checklist, RunSpec, evidence paths, and placeholders for baseline/candidate SHAs. | — | — | unknown · unknown · 0 readset(s) | no-SearchSpace-layer, no-Reference-Matrix-row, no-sidecar, no-eval |
| [npu-skill-factory](../src/inferrsi/data/skill_library/workflows/npu-skill-factory/SKILL.md) | common | Design and operation of the InferRSI NPU skill factory: artifact lifecycle, skill evaluation contract, corpus ... | — | 2 · Methodology and corpus references (Dong1017/OmniRSI @ `codex/skill-eval-bootstrap` (82218b4))<br>2 · Methodology and corpus references (InferMatrixLab/InferRSI PR #9 @ 4ad551a9)<br>2 · Methodology and corpus references (VectorSpaceLab/AREX-Skill @ ac3fe1af)<br>2 · Methodology and corpus references (microsoft/SkillOpt @ 343db22) | candidate · not_run · 14 readset(s) | no-SearchSpace-layer, no-eval |
| [rsi-evidence](../src/inferrsi/data/skill_library/workflows/rsi-evidence/SKILL.md) | common | Guide agents to publish and cite RSI evidence using plan/results/patch/validator paths and PASS/FAIL/INCONCLUSIVE ... | 1 Accelerator · Verify | — | unknown · unknown · 0 readset(s) | no-Reference-Matrix-row, no-sidecar, no-eval |

## Documents outside the registry

44 `SKILL.md` documents are not registered, so they have
no stable id and no row above. They are engine entrypoints, their
sub-skills, and the research router. Counting them would inflate coverage:
an entrypoint routes to procedures below it rather than adding one.

| Directory | Kind |
|---|---|
| `repositories/dwarfstar/sub-skills/qualification` | sub-skill |
| `repositories/dwarfstar/sub-skills/runtime-memory` | sub-skill |
| `repositories/dwarfstar/sub-skills/serving-state` | sub-skill |
| `repositories/lily/sub-skills/model-runtime` | sub-skill |
| `repositories/lily/sub-skills/qualification` | sub-skill |
| `repositories/lily/sub-skills/serving-cache` | sub-skill |
| `repositories/mistral-rs/sub-skills/decode-contract` | sub-skill |
| `repositories/mistral-rs/sub-skills/prefill-contract` | sub-skill |
| `repositories/mistral-rs/sub-skills/qualification` | sub-skill |
| `repositories/mlc-llm/sub-skills/artifact-contract` | sub-skill |
| `repositories/mlc-llm/sub-skills/metal-build-runtime` | sub-skill |
| `repositories/mlc-llm/sub-skills/runtime-kv-limits` | sub-skill |
| `repositories/mlx-swift-lm/sub-skills/gated-delta-contract` | sub-skill |
| `repositories/mlx-swift-lm/sub-skills/generation-lifecycle` | sub-skill |
| `repositories/project-maya/sub-skills/model-runtime` | sub-skill |
| `repositories/project-maya/sub-skills/qualification` | sub-skill |
| `repositories/project-maya/sub-skills/serving-state` | sub-skill |
| `repositories/sglang` | engine entrypoint |
| `repositories/sglang-omni` | engine entrypoint |
| `repositories/sglang-omni/sub-skills/sglang-omni-architecture` | sub-skill |
| `repositories/sglang-omni/sub-skills/sglang-omni-extension` | sub-skill |
| `repositories/sglang-omni/sub-skills/sglang-omni-serving` | sub-skill |
| `repositories/sglang/sub-skills/sglang-parallel-extension` | sub-skill |
| `repositories/sglang/sub-skills/sglang-runtime-memory` | sub-skill |
| `repositories/sglang/sub-skills/sglang-tuning-validation` | sub-skill |
| `repositories/splash/sub-skills/qualification` | sub-skill |
| `repositories/splash/sub-skills/runtime-planning` | sub-skill |
| `repositories/splash/sub-skills/serving-cache` | sub-skill |
| `repositories/strata` | engine entrypoint |
| `repositories/strata/sub-skills/design-space` | sub-skill |
| `repositories/strata/sub-skills/tune-execution` | sub-skill |
| `repositories/strata/sub-skills/validate-engine` | sub-skill |
| `repositories/vllm` | engine entrypoint |
| `repositories/vllm-metal/sub-skills/cache-lifecycle` | sub-skill |
| `repositories/vllm-metal/sub-skills/platform-config` | sub-skill |
| `repositories/vllm-metal/sub-skills/qualification` | sub-skill |
| `repositories/vllm-omni` | engine entrypoint |
| `repositories/vllm-omni/sub-skills/omni-architecture` | sub-skill |
| `repositories/vllm-omni/sub-skills/omni-serving` | sub-skill |
| `repositories/vllm-omni/sub-skills/omni-validation` | sub-skill |
| `repositories/vllm/sub-skills/architecture-search-space` | sub-skill |
| `repositories/vllm/sub-skills/extend-validate` | sub-skill |
| `repositories/vllm/sub-skills/operation-performance` | sub-skill |
| `workflows/inference-engine-research` | router |

## Integrity checks

- Registered ids resolve to an existing `SKILL.md`: 74 of 74.
- Duplicate ids or paths: none; `skill_catalog` rejects them before this view is built.
- Skill links in the two matrices that do not resolve: 0.
- Registered skills without a `metadata.json` sidecar: 5.

## Recorded gaps

| Gap | Skills |
|---|---|
| `no-SearchSpace-layer` | 14: ascend-video-diffusion-optimization, audit-fixed-workload-claim, audit-recurrent-kv-finalization, cite-check-downstream-pr, competitor-scan, draft-acceptance-issue, dwarfstar, husky, inference-benchmark-design, lily, npu-skill-factory, repository-evolution-analysis, skill-evolution-playbook, splash |
| `no-Reference-Matrix-row` | 7: ascend-video-diffusion-optimization, audit-fixed-workload-claim, cite-check-downstream-pr, claim-contract, competitor-scan, draft-acceptance-issue, rsi-evidence |
| `no-sidecar` | 5: cite-check-downstream-pr, claim-contract, competitor-scan, draft-acceptance-issue, rsi-evidence |
| `no-eval` | 72: as listed in the Gaps column above |

These are inventory gaps, not defects. A workflow skill may legitimately
have no hardware resource layer; a candidate may legitimately be untested.
The view records the absence instead of inferring an answer.

## Evaluation linkage

A frozen plan selecting a skill proves that a case exists and that it was
defined before the run. It does not prove the run supported the skill:
read each campaign's own `README.md` for its verdict and limits.

| Skill | Frozen campaign |
|---|---|
| dense-performance-evidence | `skill-eval-v1-20261021` |
| inference-benchmark-design | `skill-eval-v1-20261021` |

## Not claimed here

- Coverage count is a registry inventory, not an inference-optimization
  coverage result.
- `candidate` and `not_run` are copied, never promoted. No row implies a
  measured gain, a working backend, or an accepted procedure.
- Unmerged work is absent by construction: this view reads the committed
  tree only.
- A provenance readset count is a file count, not a strength score, and an
  empty count does not mean the skill has no source.

## Drift and maintenance

The generator is the only writer of this file. After changing the registry,
a skill body, a sidecar, either matrix or a frozen plan, regenerate and
commit both files together. `--check` rebuilds in memory and diffs against
the committed file, exiting non-zero on any difference, so CI can detect a
view that drifted from its sources. Only the affected rows need review;
the diff names them.
