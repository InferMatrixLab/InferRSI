# InferRSI skill library

The English-only library contains **96 skill documents**: 66 registered roots,
21 separately indexed engine/router documents and 9 AREX graph sub-skills.
Complete procedures, metadata, references, cases and source notices ship with the package.

## Browse by owner

| Directory | Content |
| --- | --- |
| [Hardware](hardware/) | Ascend (14 registered skills), CUDA (3) and host resource guidance (5) |
| [Frameworks](frameworks/) | Framework-owned procedures, PyTorch distributed checkpointing and MLX evaluation/lifetimes |
| [Repositories](repositories/) | Engine entry skills, focused procedures, references and cases |
| [Methods](methods/) | Optimization, benchmarking, analysis, search and casebooks |
| [Workflows](workflows/) | Research, acceptance, evidence, source checking and skill lifecycle |

Only this README and [`skill-index.json`](skill-index.json) live at the library
root. Supporting material belongs to its owner's `references/`, `cases/` or
existing resource directory.

## Read registered skills

[`skill-index.json`](skill-index.json) maps 66 stable skill IDs to their canonical
paths and backend scopes. Install the optional `skills` extra for these commands:

```bash
inferrsi skills list --json
inferrsi skills show ascend-graph-mode
inferrsi skills resource inference-optimization-casebook cases/qwen-ascend-rejected-directions.md
```

The [generated catalog](../repo_packs/inferrsi/knowledge/README.md) links each
registered procedure through `skill_documents.original`. Core catalog reads do
not require the optional YAML parser:

```bash
inferrsi knowledge search --repo-type inferrsi --backend ascend
inferrsi read inferrsi.ascend.skills.ascend_graph_mode --material
```

An explicit `inferrsi skills --root <path>` selects a custom flat tree or a
categorized library with `skill-index.json`. Backend scope does not certify
device compatibility; readers do not execute helpers or promote candidates.

For Goal-state authority, ordered next-action decisions and local quota receipt
recovery, start with the existing [RSI evidence owner](workflows/rsi-evidence/SKILL.md#goal-authority-and-accounting-decisions)
and its [LoopX source reference](workflows/rsi-evidence/references/loopx-goal-governance/README.md).
The [search-policy route](methods/optimization-search-policy/SKILL.md#goal-admission-and-accounting-source-knowledge)
reuses that owner. These are source-derived candidate additions, with runtime
and agent efficacy unmeasured; no new skill or registry ID is added.

## vLLM-Ascend version and responsibility routing

Choose by the question and the retained source version. These existing candidates have adjacent graph-startup topics and different primary responsibilities; neither entry replaces or validates the other.

| Existing owner | Retained source version | Use for | Existing evidence inventory | Original semantic inspection date |
| --- | --- | --- | --- | --- |
| [ascend-model-adaptation](hardware/ascend/ascend-model-adaptation/SKILL.md) | Historical `bc8115ed` documentation pin | Checkpoint onboarding, FP8 loading, KV-head replication and multimodal validation order | The entry cites `.agents/skills/vllm-ascend-model-adapter/references/` lessons, including `fp8-on-npu-lessons.md` and `multimodal-ep-aclgraph-lessons.md`; no bundled owner readset | Not individually recorded in the retained entry; the commit date is not an inspection date |
| [ascend-aclgraph-capture-replay](hardware/ascend/ascend-aclgraph-capture-replay/SKILL.md) | `8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf` runtime pin | Wrapper dispatch, caller-owned stable inputs, replay/update ordering and capture-resource diagnosis | Existing [source notes](hardware/ascend/ascend-aclgraph-capture-replay/references/source-notes.md): wrapper, graph-mode guide and selected test cases | 2026-10-15 supplier inspection, carried unchanged; local consolidation does not repeat it |

The historical short pin resolves to [`bc8115ed7fdc7e500320b5de70742ef049b4c1a2`](https://github.com/vllm-project/vllm-ascend/commit/bc8115ed7fdc7e500320b5de70742ef049b4c1a2). That resolves Git identity only; it does not add a semantic reread or an inspection date. Both entries keep their candidate / empirical validation not_run state and separate compatibility limits.

The [Reference Matrix](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/reference-matrix.md) retains the older `bc8115ed` Dockerfile/thread-env shipping-default scope under [os-process-placement](hardware/host/os-process-placement/SKILL.md). ACLGraph capture/replay supplies no new OS-control evidence; see the [OS/System row](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/searchspace-matrix.md#5--os--system).

## Focused llama.cpp runtime audit

The registered [audit-llama-runtime-state](repositories/llama-cpp/audit-llama-runtime-state/SKILL.md)
candidate separates partial decode progress, frontend graph reuse, backend input readiness
and server task/slot cancellation. Its pinned source contracts are untested natively;
[loading](methods/weight-loading-optimization/SKILL.md) and
[host placement](hardware/host/os-process-placement/SKILL.md) remain with their
existing owners. The [scope and source map](repositories/llama-cpp/audit-llama-runtime-state/SKILL.md#choose-the-scope)
links all three responsibilities and their separate source snapshots.

## PyTorch compiler and checkpoint scope routing

Choose by the affected responsibility within `pytorch/pytorch`. The compiler
dependency card and DCP procedure retain different source snapshots and
completion contracts; their shared repository name does not make a tested stack.

| Need | Existing entry | Retained evidence | Completion / applicability boundary |
| --- | --- | --- | --- |
| Inductor guards, capture shapes, replay addresses or live outputs | [Compiler dependency card](../knowledge_packs/dependency/pytorch/cuda/compiler/cudagraph-shapes-and-lifetimes.json) | Technical documents at `f15b476814ebc5eade36fb40512e379ebf79dd60`, accessed 2026-10-15; upstream-reported, imported/unverified | Compile/recompile guards, graph recording/replay and output lifetime are independent constraints; this is CUDA/compiler guidance |
| Training-visible save pauses, snapshot buffers and cleanup | [DCP async-save procedure](frameworks/pytorch/dcp-async-save-performance/SKILL.md) and [source ledger](frameworks/pytorch/dcp-async-save-performance/references/sources.md) | Implementation at `7d239835e773c91689eb298692097f4a3340491f`, inspected 2026-10-15; candidate / empirical validation `not_run` | Preserve caller capture, staging, upload, cached-buffer reuse and caller-owned cleanup boundaries; writer completion is separate from backend durability and distributed recovery |
| Tutorial examples and API/version differences | [DCP documentation/implementation reconciliation](frameworks/pytorch/dcp-async-save-performance/references/sources.md#documentation-matched-against-implementation) | Live async recipe retrieved 2026-10-15, with its own retained HTML hash and page metadata | The recipe's 2.4+ / 2.9+ labels do not identify the inspected main commit or establish a matching wheel; source notices and recipe attribution remain in the ledger |

Known mutation and storage lifetimes are a shared diagnostic prerequisite,
with different checks: the compiler card calls for retaining outputs across
later calls and exercising input mutation; DCP locates the next mutation of checkpointed state
and follows its [completion/lifetime contract](frameworks/pytorch/dcp-async-save-performance/SKILL.md#completion-and-lifetime-contract).
Neither owner's completion event establishes the other's safe reuse or eligibility.

Keep timing boundaries separate too: compiler checks distinguish cold cost,
recompilation, capture and steady-state replay; DCP measures
[caller, staging, upload and step time](frameworks/pytorch/dcp-async-save-performance/SKILL.md#evidence-to-request-in-a-separately-authorized-measurement),
including first-use versus reused buffers. These are owner-specific checks,
not a combined compiler/checkpoint calling protocol or compatibility result.

## TensorRT-LLM source and responsibility routing

TensorRT-LLM's retained methodology row covers **skill documents**, not an
engine-runtime audit. It records prefix `f33e0e5fd`; procedures keep
`f33e0e5f`, while the [ceiling sidecar](methods/performance-ceiling-analysis/metadata.json)
retains the longer **prefix** `f33e0e5fd55b`. An original inspection date for
that methodology extraction is not individually recorded. These are partial
source identities, not a verified common runtime version.

The separate [PD/KV-transfer peer card](../knowledge_packs/peer/tensorrt_llm/cuda/llm/prefill-decode-disaggregation.json)
records `c9b18eefa731dc59b0091bdfff6d890aa9d1e98e`, accessed 2026-10-15.
Its upstream-reported technique remains imported/unverified. The methods below
remain candidate / empirical validation `not_run`, with their other sources
and source notices retained. This cross-reading assesses when to combine the
guidance; it establishes no cross-pin implementation compatibility.

| Decision / resource | Existing entry | Shared prerequisite or accounting judgment | Keep separate |
| --- | --- | --- | --- |
| Evidence and measurement | [Evidence levels](methods/dense-performance-evidence/SKILL.md#claim-evidence-matching), [headroom inputs](methods/performance-ceiling-analysis/SKILL.md#evidence-to-inspect-first) and [case reuse](methods/inference-optimization-casebook/SKILL.md#adapt-do-not-copy) | Apply the peer card's fixed input/output-length and arrival distributions, same total device budget and SLO workload; report TTFT, TPOT, tail latency, goodput and total GPU/network resources | Analytical/component evidence and a precedent do not establish service gain; re-derive model/hardware-specific values |
| Accelerator | [Kernel verification](methods/kernel-writing-guide/SKILL.md#workflow-verify-before-benchmark) | A kernel change still needs reference parity over target shapes/dtypes and critical-path profiling | Kernel correctness does not establish reduced prefill/decode interference or end-to-end PD benefit |
| RAM / Host | [Serving-trace prerequisites](hardware/cuda/host-overhead-profiling/SKILL.md#prerequisites) and [confirmed host bottleneck](hardware/host/host-overhead-optimization/SKILL.md#confirming-the-bottleneck) | Establish exposed host work from serving traces before attributing a PD regression to CPU preparation | A line profiler locates CPU time; it does not establish that CPU is limiting or measure the KV interconnect |
| SSD / Storage | [Startup accounting](methods/weight-loading-optimization/SKILL.md#2-account-startup-fixed-overhead-separately) | Loading/warmup is once per process; request KV delivery needs its own per-request bytes and timing | Do not combine those denominators; disk-loading mechanics retain their separately attributed sources |
| Communication / Network | [Disaggregation peer card](../knowledge_packs/peer/tensorrt_llm/cuda/llm/prefill-decode-disaggregation.json) | Consider PD with measured prefill/decode interference, compatible KV layouts and qualified NVIDIA GPU transport; include transfer, layout-conversion and queue costs, and verify backpressure, cancellation and failed-worker recovery | Host/device loading overlap and local H2D do not establish this interconnect path; diffusion-stage splitting does not inherit the autoregressive PD cost model |
| OS / System | [Placement discipline](hardware/host/os-process-placement/SKILL.md#1-cpu-affinity-check-then-pin-then-keep-constant) | Record and control affinity, environment and device contention across matched pool comparisons | Placement methodology controls an experiment; it does not implement PD routing or OS-priority scheduling |

## vLLM version and responsibility routing

The existing [vLLM responsibility map](repositories/vllm/SKILL.md#choose-the-source-and-responsibility)
separates the broad engine guide at `2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5`
(inspection 2026-10-14) from the focused
[admission](repositories/vllm/diagnose-vllm-admission-pressure/SKILL.md) and
[KV lifetime](repositories/vllm/audit-vllm-kv-lifetimes/SKILL.md) procedures at
`7f730b4cea9a66520a9200265928ebe016b48a39` (supplier inspection 2026-10-15).
Their original readsets, source notices and candidate/unverified states remain;
this routing adds no semantic reread or compatible-stack result. Paper-era
scheduling/placement proposals remain separate from both implementation pins.

## Engine knowledge

Five repository entry skills, 15 focused sub-skills and one research router
provide source-grounded procedures. These 21 documents are available through
the links and catalog records below, separately from the 66-ID registry.
The registered ComfyUI and stable-diffusion.cpp audits are listed alongside
these imports and use generated abstracts rather than runtime repository packs.

| Repository | Focus | Entry | Catalog |
| --- | --- | --- | --- |
| ComfyUI source audit | Workflow-output cache validity and model-weight residency; source-derived candidate | [Skill](repositories/comfy-ui/SKILL.md) | [Record](../repo_packs/inferrsi/knowledge/common/skills/comfy-ui.json) |
| stable-diffusion.cpp source audit | Native image weight/runtime capacity and protected segment prefetch; source-derived candidate | [Skill](repositories/stable-diffusion-cpp/audit-sd-cpp-residency/SKILL.md) | [Record](../repo_packs/inferrsi/knowledge/common/skills/audit-sd-cpp-residency.json) |
| h3.c / MiniMax-H3 source audit | Conditioning, AdaLN precompute, phased/cached residency, precision and BF16 SSD streaming; source-derived candidate | [Skill](repositories/h3-c/audit-h3-runtime-residency/SKILL.md) | [Record](../repo_packs/inferrsi/knowledge/common/skills/audit-h3-runtime-residency.json) |
| AFD plugin P2pNccl audit | CUDA eager dense-FFN rank namespaces and per-stage/per-peer payload ownership; source-derived candidate | [Skill](repositories/afd-plugin/audit-afd-p2p-exchanges/SKILL.md) | `inferrsi.cuda.skills.audit_afd_p2p_exchanges` |
| vLLM-RLT source audit | Synchronous early-exit KV propagation, later deeper attention and normal storage retirement; source-derived candidate | [Skill](repositories/vllm-rlt/audit-recurrent-kv-finalization/SKILL.md) | [Record](../repo_packs/inferrsi/knowledge/common/skills/audit-recurrent-kv-finalization.json) |
| Strata | Heterogeneous MoE, placement, memory and speculative execution | [Skill](repositories/strata/SKILL.md) | [Records](../repo_packs/strata/knowledge/README.md) |
| vLLM | Token scheduling, KV ownership and parallel execution | [Skill](repositories/vllm/SKILL.md) | [Records](../repo_packs/vllm/knowledge/README.md) |
| SGLang | Radix/HiCache, prefill/decode, extensions and a separately pinned [diffusion lifetime candidate](repositories/sglang/audit-sglang-diffusion-lifetimes/SKILL.md) | [Skill](repositories/sglang/SKILL.md) | [Records](../repo_packs/sglang/knowledge/README.md) |
| SGLang-Omni | Stage pipelines, streaming and transport | [Skill](repositories/sglang-omni/SKILL.md) | [Records](../repo_packs/sglang_omni/knowledge/README.md) |
| vLLM-Omni | Model/deploy separation, AR/diffusion and output contracts | [Skill](repositories/vllm-omni/SKILL.md) | [Records](../repo_packs/vllm_omni/knowledge/README.md) |
| Research router | Constrained engine design and validation | [Skill](workflows/inference-engine-research/SKILL.md) | — |

For vLLM-Omni, the
[source and responsibility map](repositories/vllm-omni/SKILL.md#source-and-responsibility-map)
routes broad stage/model/output decisions and the separate
[abort validation](repositories/vllm-omni/sub-skills/omni-validation/SKILL.md)
with their original inspection dates and source pins.

See the [collection overview](workflows/inference-engine-research/references/overview.md),
[import boundaries](workflows/inference-engine-research/references/import.md) and
[Strata design-space analysis](repositories/strata/references/design-space-analysis.md).
Catalog records link detailed procedures through `skill_documents.en`;
`knowledge show` and `context` retain these package-relative pointers.

```bash
inferrsi knowledge search Radix --repo-type sglang
inferrsi context --repo-type vllm --backend cuda --scenario llm.serving
```

For an installed wheel, locate a document without assuming a checkout path:

```python
from importlib.resources import files
library = files("inferrsi").joinpath("data", "skill_library")
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
[source manifest](workflows/inference-engine-research/references/source-manifest.json).
Source snapshots are research provenance, not campaign defaults. Check local
links, dependencies, catalog reads and noneditable installed-package access;
retain `locally_verified=false` until a separate qualified campaign exists.

## MLX framework guidance

[Diagnose MLX evaluation and lifetimes](frameworks/mlx/lazy-evaluation-stream-lifetimes/SKILL.md)
separates graph construction, cross-stream ordering, backend buffer retention and
result availability. It is source-derived candidate guidance; CPU, Metal and CUDA
runtime behavior and performance remain unverified. MLX-LM request/cache policy and
MLX platform discovery belong to their separate owners.

## MLX-LM application guidance

[Trace MLX-LM generation and cache lifecycle](repositories/mlx-lm/generation-cache-lifecycle/SKILL.md)
links prefill/decode boundaries, three-stage batch-row ownership, prefix-cache
identity and cooperative stopping. It is a source-derived candidate with no
installed API, model, native-backend or service validation. MLX framework execution
and MLX platform discovery remain separate responsibilities.

## Diffusers invocation guidance

[Trace Diffusers invocation state](frameworks/diffusers/diffusers-invocation-state/SKILL.md)
separates pipeline-wrapper fields, reused component identities, scheduler progress
and cooperative interruption. The candidate is scoped to FluxPipeline and
FlowMatchEulerDiscreteScheduler at its source pin. Runtime/model/backend behavior
and performance remain unverified; the existing offload card keeps its own pin.

For host-memory/transfer questions, read the separate CUDA dependency record
`diffusers.cuda.diffusion.group_offload_transfer_overlap`. The
[version and responsibility comparison](frameworks/diffusers/diffusers-invocation-state/SKILL.md#offload-or-invocation-state)
keeps its earlier documentation pin/access date separate from the invocation
candidate; neither supplies a combined-stack or backend qualification.

## SGLang versioned guidance

The [SGLang entry comparison](repositories/sglang/SKILL.md#choose-among-source-pins)
separates the LLM engine graph, CUDA HiCache peer card and multimodal_gen diffusion
candidate. Read external HiCache material by its stable catalog ID; the versioned
routes retain their original dates and validation limits. Shared navigation does
not establish cross-pin/backend compatibility or new Network coverage.

## Hopper kernel reasoning

The CUDA-owned [reason-hopper-kernels](hardware/cuda/reason-hopper-kernels/SKILL.md)
candidate distills the pinned KDA → KernelWiki lineage into TMA/mbarrier/WGMMA
lifetime reasoning, register/pipeline/layout/software-scheduling tradeoffs and
selected FP8 GEMM contracts. Its [coverage inventory](hardware/cuda/reason-hopper-kernels/references/source-inventory.json)
separates mined mechanisms, unmined source headers and Blackwell-only recipes;
[source/license qualifications](hardware/cuda/reason-hopper-kernels/references/sources.md)
retain contradictions and distribution discrepancies. GPU execution and efficacy
remain not_run.

## DwarfStar portable AREX candidate

[DwarfStar](repositories/dwarfstar/SKILL.md) routes memory/SSD, serving-state and
qualification questions to one source-pinned operating graph. The portable AREX
create/verify workflow was adapted to native C with the user-approved partial
backend boundary. CPU checks do not qualify accelerated/model/service execution;
required backend gaps remain explicit. Its generated catalog ID is
`inferrsi.common.skills.dwarfstar`.
## Splash portable AREX candidate

[Splash](repositories/splash/SKILL.md) links source-pinned format/memory planning,
serving/cache identity and DFlash2/Metal/ANE qualification guidance. The portable
AREX workflow uses the user-approved native/source-module adaptation. CPU logic
checks do not clear required native backend blocks. Catalog ID:
`inferrsi.common.skills.splash`.
## Lily portable AREX candidate

[Lily](repositories/lily/SKILL.md) owns exact architecture/MLX-affine-Q4 runtime,
strict text API/token-prefix state and native/benchmark qualification guidance.
Its compiler/Metal/model gaps remain blocked; offline Python helpers are not
Rust execution. Catalog ID: `inferrsi.common.skills.lily`.
## Husky document-only research candidate

[Husky](repositories/husky/SKILL.md) separates an attributed official-page report
from implementation, reproduction and original research proposals. Repository,
revision, source license and raw receipts remain unknown; its offline helper
screens supplied metadata only. This is not complete repo-to-skill or native
verification. Catalog ID: `inferrsi.common.skills.husky`.
