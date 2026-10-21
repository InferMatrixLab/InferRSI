# InferRSI skill library

The English-only library contains **72 skill documents**: 51 registered skills
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

[`skill-index.json`](skill-index.json) maps 51 stable skill IDs to their canonical
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

## Engine knowledge

Five repository entry skills, 15 focused sub-skills and one research router
provide source-grounded procedures. These 21 documents are available through
the links and catalog records below, separately from the 51-ID registry.
The registered ComfyUI audit is listed alongside these imports and uses its
generated skill abstract rather than a separate runtime repository pack.

| Repository | Focus | Entry | Catalog |
| --- | --- | --- | --- |
| ComfyUI source audit | Workflow-output cache validity and model-weight residency; source-derived candidate | [Skill](repositories/comfy-ui/SKILL.md) | [Record](../repo_packs/inferrsi/knowledge/common/skills/comfy-ui.json) |
| Strata | Heterogeneous MoE, placement, memory and speculative execution | [Skill](repositories/strata/SKILL.md) | [Records](../repo_packs/strata/knowledge/README.md) |
| vLLM | Token scheduling, KV ownership and parallel execution | [Skill](repositories/vllm/SKILL.md) | [Records](../repo_packs/vllm/knowledge/README.md) |
| SGLang | Radix/HiCache, prefill/decode and extensions | [Skill](repositories/sglang/SKILL.md) | [Records](../repo_packs/sglang/knowledge/README.md) |
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
