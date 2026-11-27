# InferRSI skill library

The main InferRSI agent selects one of the [seven primary inference skills](tasks/)
by the requested outcome, runs `inferrsi skills enter <task-id>` and reads
the returned procedure before the first supporting evidence search. Use the actual model, device, engine version, script, gates
and diagnosis to decide which supporting skill to load next. The
[compatibility router](tasks/inference-task-router/SKILL.md) retains older route
resource paths. The library has 90 registered bundles and 153 English
`SKILL.md` documents, including nested and unregistered entries.

| Question | Directory | Choose a second-level category |
| --- | --- | --- |
| Which procedure owns the inference task? | [Tasks](tasks/) | Day-0, performance, debug, accuracy, version alignment, derived engine or independent engine |
| How does this implementation work? | [Systems](systems/) | [Platforms](systems/platforms/README.md), [frameworks](systems/frameworks/) or [engines](systems/engines/) |
| How should I perform this engineering task? | [Playbooks](playbooks/) | [Measurement](playbooks/measurement/), [planning](playbooks/planning/) or [optimization](playbooks/optimization/) |
| How do several steps fit together? | [Workflows](workflows/) | [Research](workflows/research/), [governance](workflows/governance/) or [knowledge maintenance](workflows/maintenance/) |
| What happened the last time this was tried? | [Casebooks](casebooks/) | [Inference experiments](casebooks/inference/) or [Ascend-specific cases](casebooks/ascend/) |

For example, an Ascend capture/replay procedure belongs in `systems/platforms/ascend/`.
Prior NPU optimization outcomes belong in `casebooks/ascend/`. Cross-platform
benchmark design belongs in `playbooks/measurement/`. Put a bundle in one
canonical location; link to it from other categories by its registered ID.

The library also owns authored findings under `records/`, search configuration
under `config/` and generated build inputs under `_compiled/`. Supporting material belongs to its owner's `references/`, `cases/` or
existing resource directory.

## Read registered skills

[`skill-index.json`](skill-index.json) maps 90 stable skill IDs to their canonical
paths and backend scopes. Install the optional `skills` extra for these commands:

```bash
inferrsi skills list --json
inferrsi skills show ascend-graph-mode
inferrsi skills resource inference-optimization-casebook cases/qwen-ascend-rejected-directions.md
```

The runtime catalog links each
registered procedure through `skill_documents.original`. Core catalog reads do
not require the optional YAML parser:

```bash
inferrsi knowledge list --repo-type inferrsi --backend ascend
inferrsi read inferrsi.ascend.skills.ascend_graph_mode --material
```

An explicit `inferrsi skills --root <path>` selects a custom flat tree or a
categorized library with `skill-index.json`. Backend scope does not certify
device compatibility; readers do not execute helpers or promote candidates.

For Goal-state authority, ordered next-action decisions and local quota receipt
recovery, start with the existing [RSI evidence owner](workflows/governance/rsi-evidence/SKILL.md#goal-authority-and-accounting-decisions)
and its [LoopX source reference](workflows/governance/rsi-evidence/references/loopx-goal-governance/README.md).
The [search-policy route](playbooks/planning/optimization-search-policy/SKILL.md#goal-admission-and-accounting-source-knowledge)
reuses that owner. These are source-derived candidate additions, with runtime
and agent efficacy unmeasured; no new skill or registry ID is added.

## vLLM-Ascend version and responsibility routing

Choose by the question and the retained source version. These existing candidates have adjacent graph-startup topics and different primary responsibilities; neither entry replaces or validates the other.

| Existing owner | Retained source version | Use for | Existing evidence inventory | Original semantic inspection date |
| --- | --- | --- | --- | --- |
| [ascend-model-adaptation](systems/platforms/ascend/ascend-model-adaptation/SKILL.md) | Historical `bc8115ed` documentation pin | Checkpoint onboarding, FP8 loading, KV-head replication and multimodal validation order | The entry cites `.agents/skills/vllm-ascend-model-adapter/references/` lessons, including `fp8-on-npu-lessons.md` and `multimodal-ep-aclgraph-lessons.md`; no bundled owner readset | Not individually recorded in the retained entry; the commit date is not an inspection date |
| [ascend-aclgraph-capture-replay](systems/platforms/ascend/ascend-aclgraph-capture-replay/SKILL.md) | `8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf` runtime pin | Wrapper dispatch, caller-owned stable inputs, replay/update ordering and capture-resource diagnosis | Existing [source notes](systems/platforms/ascend/ascend-aclgraph-capture-replay/references/source-notes.md): wrapper, graph-mode guide and selected test cases | 2026-10-15 supplier inspection, carried unchanged; local consolidation does not repeat it |

The historical short pin resolves to [`bc8115ed7fdc7e500320b5de70742ef049b4c1a2`](https://github.com/vllm-project/vllm-ascend/commit/bc8115ed7fdc7e500320b5de70742ef049b4c1a2). That resolves Git identity only; it does not add a semantic reread or an inspection date. Both entries keep their candidate / empirical validation not_run state and separate compatibility limits.

The [Reference Matrix](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/reference-matrix.md) retains the older `bc8115ed` Dockerfile/thread-env shipping-default scope under [os-process-placement](systems/platforms/host/os-process-placement/SKILL.md). ACLGraph capture/replay supplies no new OS-control evidence; see the [OS/System row](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/searchspace-matrix.md#5--os--system).

## Focused llama.cpp runtime audit

The registered [audit-llama-runtime-state](systems/engines/llama-cpp/audit-llama-runtime-state/SKILL.md)
candidate separates partial decode progress, frontend graph reuse, backend input readiness
and server task/slot cancellation. Its pinned source contracts are untested natively;
[loading](playbooks/optimization/weight-loading-optimization/SKILL.md) and
[host placement](systems/platforms/host/os-process-placement/SKILL.md) remain with their
existing owners. The [scope and source map](systems/engines/llama-cpp/audit-llama-runtime-state/SKILL.md#choose-the-scope)
links all three responsibilities and their separate source snapshots.

## PyTorch compiler and checkpoint scope routing

The [PyTorch operating graph](systems/frameworks/pytorch/pytorch/SKILL.md) routes eight
workflows across installation/build, tensor/autograd, training/data,
compiler/export, memory/streams/graphs, distributed/checkpoint, profiling and
custom operators. The [TorchNPU operating graph](systems/frameworks/torch-npu/torch-npu/SKILL.md)
routes eight Ascend adapter workflows, including PrivateUse1 dispatch,
operator development, HCCL, precision and explicit compiler selection.
Both are source-derived candidates; installed CPU observations do not qualify
the pinned source build or the required accelerator and distributed backends.

Their registered IDs are `pytorch` and `torch-npu`. Nested SKILL.md files carry their own procedure and metadata and are packaged resources of those roots:

```bash
inferrsi skills resource pytorch sub-skills/compiler-and-export/SKILL.md
inferrsi skills resource torch-npu sub-skills/distributed-and-hccl/SKILL.md
inferrsi read inferrsi.common.skills.pytorch --material
inferrsi read inferrsi.ascend.skills.torch_npu --material
```

Choose by the affected responsibility within `pytorch/pytorch`. The compiler
dependency card and DCP procedure retain different source snapshots and
completion contracts; their shared repository name does not make a tested stack.

| Need | Existing entry | Retained evidence | Completion / applicability boundary |
| --- | --- | --- | --- |
| Inductor guards, capture shapes, replay addresses or live outputs | [Compiler dependency card](records/pytorch.cuda.compiler.cudagraph_shapes_and_lifetimes.json) | Technical documents at `f15b476814ebc5eade36fb40512e379ebf79dd60`, accessed 2026-10-15; upstream-reported, imported/unverified | Compile/recompile guards, graph recording/replay and output lifetime are independent constraints; this is CUDA/compiler guidance |
| Training-visible save pauses, snapshot buffers and cleanup | [DCP async-save procedure](systems/frameworks/pytorch/dcp-async-save-performance/SKILL.md) and [source ledger](systems/frameworks/pytorch/dcp-async-save-performance/references/sources.md) | Implementation at `7d239835e773c91689eb298692097f4a3340491f`, inspected 2026-10-15; candidate / empirical validation `not_run` | Preserve caller capture, staging, upload, cached-buffer reuse and caller-owned cleanup boundaries; writer completion is separate from backend durability and distributed recovery |
| Tutorial examples and API/version differences | [DCP documentation/implementation reconciliation](systems/frameworks/pytorch/dcp-async-save-performance/references/sources.md#documentation-matched-against-implementation) | Live async recipe retrieved 2026-10-15, with its own retained HTML hash and page metadata | The recipe's 2.4+ / 2.9+ labels do not identify the inspected main commit or establish a matching wheel; source notices and recipe attribution remain in the ledger |

Known mutation and storage lifetimes are a shared diagnostic prerequisite,
with different checks: the compiler card calls for retaining outputs across
later calls and exercising input mutation; DCP locates the next mutation of checkpointed state
and follows its [completion/lifetime contract](systems/frameworks/pytorch/dcp-async-save-performance/SKILL.md#completion-and-lifetime-contract).
Neither owner's completion event establishes the other's safe reuse or eligibility.

Keep timing boundaries separate too: compiler checks distinguish cold cost,
recompilation, capture and steady-state replay; DCP measures
[caller, staging, upload and step time](systems/frameworks/pytorch/dcp-async-save-performance/SKILL.md#evidence-to-request-in-a-separately-authorized-measurement),
including first-use versus reused buffers. These are owner-specific checks,
not a combined compiler/checkpoint calling protocol or compatibility result.

## TensorRT-LLM source and responsibility routing

TensorRT-LLM's retained methodology row covers **skill documents**, not an
engine-runtime audit. It records prefix `f33e0e5fd`; procedures keep
`f33e0e5f`, while the [ceiling skill metadata](playbooks/measurement/performance-ceiling-analysis/SKILL.md)
retains the longer **prefix** `f33e0e5fd55b`. An original inspection date for
that methodology extraction is not individually recorded. These are partial
source identities, not a verified common runtime version.

The separate [PD/KV-transfer peer card](records/tensorrt_llm.cuda.llm.prefill_decode_disaggregation.json)
records `c9b18eefa731dc59b0091bdfff6d890aa9d1e98e`, accessed 2026-10-15.
Its upstream-reported technique remains imported/unverified. The methods below
remain candidate / empirical validation `not_run`, with their other sources
and source notices retained. This cross-reading assesses when to combine the
guidance; it establishes no cross-pin implementation compatibility.

| Decision / resource | Existing entry | Shared prerequisite or accounting judgment | Keep separate |
| --- | --- | --- | --- |
| Evidence and measurement | [Evidence levels](playbooks/measurement/dense-performance-evidence/SKILL.md#claim-evidence-matching), [headroom inputs](playbooks/measurement/performance-ceiling-analysis/SKILL.md#evidence-to-inspect-first) and [case reuse](casebooks/inference/inference-optimization-casebook/SKILL.md#adapt-do-not-copy) | Apply the peer card's fixed input/output-length and arrival distributions, same total device budget and SLO workload; report TTFT, TPOT, tail latency, goodput and total GPU/network resources | Analytical/component evidence and a precedent do not establish service gain; re-derive model/hardware-specific values |
| Accelerator | [Kernel verification](playbooks/optimization/kernel-writing-guide/SKILL.md#workflow-verify-before-benchmark) | A kernel change still needs reference parity over target shapes/dtypes and critical-path profiling | Kernel correctness does not establish reduced prefill/decode interference or end-to-end PD benefit |
| RAM / Host | [Serving-trace prerequisites](systems/platforms/cuda/host-overhead-profiling/SKILL.md#prerequisites) and [confirmed host bottleneck](systems/platforms/host/host-overhead-optimization/SKILL.md#confirming-the-bottleneck) | Establish exposed host work from serving traces before attributing a PD regression to CPU preparation | A line profiler locates CPU time; it does not establish that CPU is limiting or measure the KV interconnect |
| SSD / Storage | [Startup accounting](playbooks/optimization/weight-loading-optimization/SKILL.md#2-account-startup-fixed-overhead-separately) | Loading/warmup is once per process; request KV delivery needs its own per-request bytes and timing | Do not combine those denominators; disk-loading mechanics retain their separately attributed sources |
| Communication / Network | [Disaggregation peer card](records/tensorrt_llm.cuda.llm.prefill_decode_disaggregation.json) | Consider PD with measured prefill/decode interference, compatible KV layouts and qualified NVIDIA GPU transport; include transfer, layout-conversion and queue costs, and verify backpressure, cancellation and failed-worker recovery | Host/device loading overlap and local H2D do not establish this interconnect path; diffusion-stage splitting does not inherit the autoregressive PD cost model |
| OS / System | [Placement discipline](systems/platforms/host/os-process-placement/SKILL.md#1-cpu-affinity-check-then-pin-then-keep-constant) | Record and control affinity, environment and device contention across matched pool comparisons | Placement methodology controls an experiment; it does not implement PD routing or OS-priority scheduling |

## vLLM version and responsibility routing

The existing [vLLM responsibility map](systems/engines/vllm/SKILL.md#choose-the-source-and-responsibility)
separates the broad engine guide at `2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5`
(inspection 2026-10-14) from the focused
[admission](systems/engines/vllm/diagnose-vllm-admission-pressure/SKILL.md) and
[KV lifetime](systems/engines/vllm/audit-vllm-kv-lifetimes/SKILL.md) procedures at
`7f730b4cea9a66520a9200265928ebe016b48a39` (supplier inspection 2026-10-15).
Their original readsets, source notices and candidate/unverified states remain;
this routing adds no semantic reread or compatible-stack result. Paper-era
scheduling/placement proposals remain separate from both implementation pins.

## Engine knowledge

Five repository entry skills, 15 focused sub-skills and one research router
provide source-grounded procedures. These 21 documents are available through
the links and catalog records below, separately from the 90-ID registry.
The registered ComfyUI and stable-diffusion.cpp audits are listed alongside
these imports and use generated abstracts rather than runtime repository packs.

| Repository | Focus | Entry | Catalog |
| --- | --- | --- | --- |
| Lithos Metal source guide | Task compiler/fusion, GPU-resident generation/DSpark state and exact serving/cache ownership; candidate | [Skill](systems/engines/lithos-metal/SKILL.md) | `inferrsi.common.skills.lithos_metal` |
| ComfyUI source audit | Workflow-output cache validity and model-weight residency; source-derived candidate | [Skill](systems/engines/comfy-ui/SKILL.md) | `inferrsi.common.skills.comfy_ui` |
| stable-diffusion.cpp source audit | Native image weight/runtime capacity and protected segment prefetch; source-derived candidate | [Skill](systems/engines/stable-diffusion-cpp/audit-sd-cpp-residency/SKILL.md) | `inferrsi.common.skills.audit_sd_cpp_residency` |
| h3.c / MiniMax-H3 source audit | Conditioning, AdaLN precompute, phased/cached residency, precision and BF16 SSD streaming; source-derived candidate | [Skill](systems/engines/h3-c/audit-h3-runtime-residency/SKILL.md) | `inferrsi.common.skills.audit_h3_runtime_residency` |
| h3-metal / FastH3 semantic audit | Effective parameters and ambient overrides, tensor/schedule transformations, VSA prefix/partial tiles and fallback; source-derived candidate | [Skill](systems/engines/h3-metal/audit-h3-metal-fasth3-semantics/SKILL.md) | `inferrsi.common.skills.audit_h3_metal_fasth3_semantics` |
| AFD plugin P2pNccl audit | CUDA eager dense-FFN rank namespaces and per-stage/per-peer payload ownership; source-derived candidate | [Skill](systems/engines/afd-plugin/audit-afd-p2p-exchanges/SKILL.md) | `inferrsi.cuda.skills.audit_afd_p2p_exchanges` |
| vLLM-RLT source audit | Synchronous early-exit KV propagation, later deeper attention and normal storage retirement; source-derived candidate | [Skill](systems/engines/vllm-rlt/audit-recurrent-kv-finalization/SKILL.md) | `inferrsi.common.skills.audit_recurrent_kv_finalization` |
| Strata | Heterogeneous MoE, placement, memory and speculative execution | [Skill](systems/engines/strata/SKILL.md) | [Records](records/README.md) |
| vLLM | Token scheduling, KV ownership and parallel execution | [Skill](systems/engines/vllm/SKILL.md) | [Records](records/README.md) |
| SGLang | Radix/HiCache, prefill/decode, extensions and a separately pinned [diffusion lifetime candidate](systems/engines/sglang/audit-sglang-diffusion-lifetimes/SKILL.md) | [Skill](systems/engines/sglang/SKILL.md) | [Records](records/README.md) |
| SGLang-Omni | Stage pipelines, streaming and transport | [Skill](systems/engines/sglang-omni/SKILL.md) | [Records](records/README.md) |
| vLLM-Omni | Model/deploy separation, AR/diffusion and output contracts | [Skill](systems/engines/vllm-omni/SKILL.md) | [Records](records/README.md) |
| Research router | Constrained engine design and validation | [Skill](workflows/research/inference-engine-research/SKILL.md) | — |

For vLLM-Omni, the
[source and responsibility map](systems/engines/vllm-omni/SKILL.md#source-and-responsibility-map)
routes broad stage/model/output decisions and the separate
[abort validation](systems/engines/vllm-omni/sub-skills/omni-validation/SKILL.md)
with their original inspection dates and source pins.

See the [collection overview](workflows/research/inference-engine-research/references/overview.md),
[import boundaries](workflows/research/inference-engine-research/references/import.md) and
[Strata design-space analysis](systems/engines/strata/references/design-space-analysis.md).
Catalog records link detailed procedures through `skill_documents.en`;
`knowledge show` and `context` retain these package-relative pointers.

```bash
inferrsi find Radix --repo-type sglang
inferrsi context --repo-type vllm --backend cuda --scenario llm.serving
```

For an installed wheel, locate a document without assuming a checkout path:

```python
from importlib.resources import files
library = files("inferrsi").joinpath("knowledge", "data", "skill_library")
router = library.joinpath("workflows", "inference-engine-research", "SKILL.md")
print(router.read_text(encoding="utf-8"))
```

Load one repository or follow the router progressively. When copying material,
retain its owner layout and referenced dependency bundles. Document and CPU
checks do not establish GPU correctness, model quality or performance gains.

## Maintain

Edit the canonical owner directory. Keep the library in English, preserve source
notices, negative results, candidate states and unknown-license declarations.
For registered skills, update `skill-index.json` when paths or backends change
and regenerate abstracts with `tools/build_skill_index.py`.

For engine knowledge, update the procedure and catalog abstract together and
retain source revisions and licenses in the
[source manifest](workflows/research/inference-engine-research/references/source-manifest.json).
Source snapshots are research provenance, not campaign defaults. Check local
links, dependencies, catalog reads and noneditable installed-package access;
retain `locally_verified=false` until a separate qualified campaign exists.

## MLX framework guidance

[Diagnose MLX evaluation and lifetimes](systems/frameworks/mlx/lazy-evaluation-stream-lifetimes/SKILL.md)
separates graph construction, cross-stream ordering, backend buffer retention and
result availability. It is source-derived candidate guidance; CPU, Metal and CUDA
runtime behavior and performance remain unverified. MLX-LM request/cache policy and
MLX platform discovery belong to their separate owners.

## MLX-LM application guidance

[Trace MLX-LM generation and cache lifecycle](systems/engines/mlx-lm/generation-cache-lifecycle/SKILL.md)
links prefill/decode boundaries, three-stage batch-row ownership, prefix-cache
identity and cooperative stopping. It is a source-derived candidate with no
installed API, model, native-backend or service validation. MLX framework execution
and MLX platform discovery remain separate responsibilities.

## Diffusers invocation guidance

[Trace Diffusers invocation state](systems/frameworks/diffusers/diffusers-invocation-state/SKILL.md)
separates pipeline-wrapper fields, reused component identities, scheduler progress
and cooperative interruption. The candidate is scoped to FluxPipeline and
FlowMatchEulerDiscreteScheduler at its source pin. Runtime/model/backend behavior
and performance remain unverified; the existing offload card keeps its own pin.

For host-memory/transfer questions, read the separate CUDA dependency record
`diffusers.cuda.diffusion.group_offload_transfer_overlap`. The
[version and responsibility comparison](systems/frameworks/diffusers/diffusers-invocation-state/SKILL.md#offload-or-invocation-state)
keeps its earlier documentation pin/access date separate from the invocation
candidate; neither supplies a combined-stack or backend qualification.

## SGLang versioned guidance

The [SGLang entry comparison](systems/engines/sglang/SKILL.md#choose-among-source-pins)
separates the LLM engine graph, CUDA HiCache peer card and multimodal_gen diffusion
candidate. Read external HiCache material by its stable catalog ID; the versioned
routes retain their original dates and validation limits. Shared navigation does
not establish cross-pin/backend compatibility or new Network coverage.

## Hopper kernel reasoning

The CUDA-owned [reason-hopper-kernels](systems/platforms/cuda/reason-hopper-kernels/SKILL.md)
candidate distills the pinned KDA → KernelWiki lineage into TMA/mbarrier/WGMMA
lifetime reasoning, register/pipeline/layout/software-scheduling tradeoffs and
selected FP8 GEMM contracts. Its [coverage inventory](systems/platforms/cuda/reason-hopper-kernels/references/source-inventory.json)
separates mined mechanisms, unmined source headers and Blackwell-only recipes;
[source/license qualifications](systems/platforms/cuda/reason-hopper-kernels/references/sources.md)
retain contradictions and distribution discrepancies. GPU execution and efficacy
remain not_run.

## DwarfStar portable AREX candidate

[DwarfStar](systems/engines/dwarfstar/SKILL.md) routes memory/SSD, serving-state and
qualification questions to one source-pinned operating graph. The portable AREX
create/verify workflow was adapted to native C with the user-approved partial
backend boundary. CPU checks do not qualify accelerated/model/service execution;
required backend gaps remain explicit. Its generated catalog ID is
`inferrsi.common.skills.dwarfstar`.
## Splash portable AREX candidate

[Splash](systems/engines/splash/SKILL.md) links source-pinned format/memory planning,
serving/cache identity and DFlash2/Metal/ANE qualification guidance. The portable
AREX workflow uses the user-approved native/source-module adaptation. CPU logic
checks do not clear required native backend blocks. Catalog ID:
`inferrsi.common.skills.splash`.
## Lily portable AREX candidate

[Lily](systems/engines/lily/SKILL.md) owns exact architecture/MLX-affine-Q4 runtime,
strict text API/token-prefix state and native/benchmark qualification guidance.
Its compiler/Metal/model gaps remain blocked; offline Python helpers are not
Rust execution. Catalog ID: `inferrsi.common.skills.lily`.
## Husky document-only research candidate

[Husky](systems/engines/husky/SKILL.md) separates an attributed official-page report
from implementation, reproduction and original research proposals. Repository,
revision, source license and raw receipts remain unknown; its offline helper
screens supplied metadata only. This is not complete repo-to-skill or native
verification. Catalog ID: `inferrsi.common.skills.husky`.

## Project Maya portable AREX candidate

[Project Maya](systems/engines/project-maya/SKILL.md) owns model-family dispatch and
physical residency planning, API versus native state, and speculation/calibration
qualification. Selected direct-compiler CPU policies and safe offline helpers do
not clear CUDA/HIP/model/state/quality/service gaps. New Qwen coverage is shallow
routing/format/guard evidence, not deep kernel qualification. Catalog ID:
`inferrsi.common.skills.project_maya`.

## vLLM Metal source and CPU candidate

The [vllm-metal graph](systems/engines/vllm-metal/SKILL.md) routes platform/native ABI, KV/offload lifetime and speculative/deferred/dispatch evidence. Three bundled offline helpers support bounded syntax, dense-pool arithmetic and accounting. Required Apple Metal/MPS/model/service/quality verification remains blocked; CPU source tests do not promote it.

## mistral.rs native paged-attention source candidate

The [mistral-rs graph](systems/engines/mistral-rs/SKILL.md) owns selected Metal decode layout/scales/workspace, prefill coordinates/masks/workspace and actual-model prewarm/evidence. Three offline metadata/formula/inventory helpers add no GPU simulation or execution proof. Rust compilation and Apple native/model/quality/service evidence remain not_run / blocked.

## MLX Swift LM ownership and recurrent Metal source candidate

The [mlx-swift-lm graph](systems/engines/mlx-swift-lm/SKILL.md) adds selected Swift exclusive-access/cancellation/task-settlement and actual GatedDelta native/ops contracts. Two bounded evidence/metadata helpers authenticate neither observations nor dispatch. Swift compilation and required Apple native/model/quality/service evidence remain not_run / blocked; source-only masked-output parity gap is retained.

## MLC LLM compiled Metal source contracts

The [mlc-llm candidate](systems/engines/mlc-llm/SKILL.md) covers opt-in artifact/schema/resource declarations, Apple target and pinned TVM module/storage/stream consumers, and compiled/runtime KV limits. Helpers authenticate no binary/weights/dispatch or memory fit; required native/model/quality/service evidence remains not_run.

## Local Dream Android diffusion source contracts

The [local-dream candidate](systems/engines/local-dream/SKILL.md) separates desired
and serving process state, grace/restart/readiness and unauthenticated LAN
exposure, MNN/QNN/Anima/DiT dispatch, shared cancellation/cache lifetimes and
CPU-library versus DSP-skels/ABI packaging. One offline declaration screen is
not native evidence. Android/Qualcomm/model/quality/fit/performance remain
blocked/not_run. Source CC BY-NC 4.0 restrictions remain distinct from API
`NOASSERTION`. Catalog ID: `inferrsi.common.skills.local_dream`.
