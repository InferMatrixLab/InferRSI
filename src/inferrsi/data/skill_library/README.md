# InferRSI skill library

The English-only library contains **80 skill documents**: 59 registered skills
and 21 engine and research-router skills. Complete procedures, metadata,
references, cases and source notices ship with the package.

## Browse by owner

| Directory | Content |
| --- | --- |
| [Hardware](hardware/) | Ascend (13 registered skills), CUDA (2) and host resource guidance (5) |
| [Frameworks](frameworks/) | Framework-owned procedures, PyTorch distributed checkpointing and MLX evaluation/lifetimes |
| [Repositories](repositories/) | Engine entry skills, focused procedures, references and cases |
| [Methods](methods/) | Optimization, benchmarking, analysis, search and casebooks |
| [Workflows](workflows/) | Research, acceptance, evidence, source checking and skill lifecycle |

Only this README and [`skill-index.json`](skill-index.json) live at the library
root. Supporting material belongs to its owner's `references/`, `cases/` or
existing resource directory.

## Read registered skills

[`skill-index.json`](skill-index.json) maps 59 stable skill IDs to their canonical
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

## Engine knowledge

Five repository entry skills, 15 focused sub-skills and one research router
provide source-grounded procedures. These 21 documents are available through
the links and catalog records below, separately from the 59-ID registry.
The registered ComfyUI and stable-diffusion.cpp audits are listed alongside
these imports and use generated abstracts rather than runtime repository packs.

| Repository | Focus | Entry | Catalog |
| --- | --- | --- | --- |
| ComfyUI source audit | Workflow-output cache validity and model-weight residency; source-derived candidate | [Skill](repositories/comfy-ui/SKILL.md) | [Record](../repo_packs/inferrsi/knowledge/common/skills/comfy-ui.json) |
| stable-diffusion.cpp source audit | Native image weight/runtime capacity and protected segment prefetch; source-derived candidate | [Skill](repositories/stable-diffusion-cpp/audit-sd-cpp-residency/SKILL.md) | [Record](../repo_packs/inferrsi/knowledge/common/skills/audit-sd-cpp-residency.json) |
| h3.c / MiniMax-H3 source audit | Conditioning, AdaLN precompute, phased/cached residency, precision and BF16 SSD streaming; source-derived candidate | [Skill](repositories/h3-c/audit-h3-runtime-residency/SKILL.md) | [Record](../repo_packs/inferrsi/knowledge/common/skills/audit-h3-runtime-residency.json) |
| AFD plugin P2pNccl audit | CUDA eager dense-FFN rank namespaces and per-stage/per-peer payload ownership; source-derived candidate | [Skill](repositories/afd-plugin/audit-afd-p2p-exchanges/SKILL.md) | `inferrsi.cuda.skills.audit_afd_p2p_exchanges` |
| Strata | Heterogeneous MoE, placement, memory and speculative execution | [Skill](repositories/strata/SKILL.md) | [Records](../repo_packs/strata/knowledge/README.md) |
| vLLM | Token scheduling, KV ownership and parallel execution | [Skill](repositories/vllm/SKILL.md) | [Records](../repo_packs/vllm/knowledge/README.md) |
| SGLang | Radix/HiCache, prefill/decode, extensions and a separately pinned [diffusion lifetime candidate](repositories/sglang/audit-sglang-diffusion-lifetimes/SKILL.md) | [Skill](repositories/sglang/SKILL.md) | [Records](../repo_packs/sglang/knowledge/README.md) |
| SGLang-Omni | Stage pipelines, streaming and transport | [Skill](repositories/sglang-omni/SKILL.md) | [Records](../repo_packs/sglang_omni/knowledge/README.md) |
| vLLM-Omni | Model/deploy separation, AR/diffusion and output contracts | [Skill](repositories/vllm-omni/SKILL.md) | [Records](../repo_packs/vllm_omni/knowledge/README.md) |
| Research router | Constrained engine design and validation | [Skill](workflows/inference-engine-research/SKILL.md) | — |

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
