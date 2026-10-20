# InferRSI skill library / 技能知识库

This is the canonical home for InferRSI's complete skill content: **48 registered
skills and 42 bilingual engine skill documents**, grouped by their owner or
scope. Procedures, metadata, references, cases, helpers and source notices ship
with the package. Their IDs and verification state are unchanged.

## Directory layout / 目录结构

| Owner or scope | Content |
| --- | --- |
| [Hardware](hardware/) | Ascend (13 registered skills), CUDA (2) and host resource guidance (5) |
| [Frameworks](frameworks/) | Framework-owned procedures, currently PyTorch distributed checkpointing |
| [Repositories](repositories/) | Repository entry skills, focused procedures, references and cases for Strata, vLLM, SGLang, SGLang-Omni, vLLM-Omni and LMCache |
| [Methods](methods/) | General optimization, benchmarking, analysis, search and casebooks |
| [Workflows](workflows/) | Cross-repository research, acceptance, evidence, source checking and skill lifecycle |

Language is a property of an owner's bundle, not a top-level category. The five
engine bundles and cross-repository research workflow have an English entry
directly under their owner, with the complete Chinese edition under
`translations/zh-CN/`. Repository editions retain their `sub-skills/` and
`references/`.
For example:

```text
skill_library/
  README.md
  skill-index.json
  hardware/{ascend,cuda,host}/<skill>/
  frameworks/<framework>/<skill>/
  repositories/
    vllm/
      SKILL.md
      sub-skills/
      references/
      translations/zh-CN/
        SKILL.md
        sub-skills/
        references/
      audit-vllm-kv-lifetimes/
      diagnose-vllm-admission-pressure/
    strata/
      references/design-space-analysis.md
      translations/zh-CN/references/design-space-analysis.md
  methods/<skill>/
  workflows/
    inference-engine-research/
      SKILL.md
      references/
        overview.md
        import.md
        source-manifest.json
      translations/zh-CN/
        SKILL.md
        references/overview.md
    <other-workflow>/
```

Only this navigation README and [`skill-index.json`](skill-index.json) live at
the library root. Collection overviews, import notes and source inventory belong
to the research workflow; the Strata design-space analysis belongs to Strata.
Classification follows substantive procedure: Nsight host profiling and
FlashAttention GPU mechanisms belong to CUDA; the general NPU-named skill factory
belongs to workflows. Host resource guidance is independent of accelerator HBM.

本目录统一按硬件、框架、仓库、方法和工作流组织完整内容，不再把语言目录与这些
分类并列。引擎技能的英文正文直接放在所属仓库目录，中文完整版本放在该目录的
`translations/zh-CN/` 中；总入口归属 `workflows/inference-engine-research/`。
总览、导入记录、来源清单和分析文档随所属技能进入 `references/`。所有原始内容、
候选状态、验证结论和未知许可证声明均保留。

## Read registered skills / 读取已注册技能

[`skill-index.json`](skill-index.json) maps the 48 stable registered skill IDs to
their canonical relative paths and backend scopes.

Install the optional `skills` extra to inspect registered skills directly:

```bash
inferrsi skills list --json
inferrsi skills show ascend-graph-mode
inferrsi skills resource inference-optimization-casebook cases/qwen-ascend-rejected-directions.md
# Optional custom flat tree or registry-based library:
inferrsi skills --root src/inferrsi/data/skill_library list
```

The default is the installed library's 48-ID registry. Bilingual engine documents
are available through the navigation and catalog records below; their editions
do not add duplicate IDs to the registry. Core catalog operations do not
require the optional YAML parser:

```bash
inferrsi knowledge search --repo-type inferrsi --backend ascend
inferrsi knowledge show inferrsi.ascend.skills.ascend_graph_mode
inferrsi read inferrsi.ascend.skills.ascend_graph_mode --material
```

[Generated catalog records](../repo_packs/inferrsi/knowledge/README.md) link each
migrated procedure through `skill_documents.original`. Normalized package reads
retain library dependency resources, including cross-skill references. The
registry's `backend` classifies scope; it does not certify device compatibility.
Original candidate states, provenance and `UNKNOWN` licenses remain unchanged.
No reader executes helpers or promotes skills.

## Five-engine knowledge / 推理引擎知识

Source-grounded English and Chinese knowledge for five repositories, distilled
with the [AREX direct workflow](https://github.com/VectorSpaceLab/AREX-Skill/tree/ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6).
Each repository has an entry skill and three focused sub-skills. The collection
router connects all five: **21 skill nodes per language, 42 in total**.

[English overview](workflows/inference-engine-research/references/overview.md) ·
[中文总览](workflows/inference-engine-research/translations/zh-CN/references/overview.md) ·
[Import and verification boundaries / 导入与验证边界](workflows/inference-engine-research/references/import.md)

| Repository | Focus / 重点 | English | 中文 | CLI catalog |
| --- | --- | --- | --- | --- |
| Strata | Heterogeneous MoE, placement, memory and speculative execution / 异构执行与搜索空间 | [Skill](repositories/strata/SKILL.md) | [Skill](repositories/strata/translations/zh-CN/SKILL.md) | [Records](../repo_packs/strata/knowledge/README.md) |
| vLLM | Token scheduling, KV ownership and parallel execution / 调度、缓存与并行 | [Skill](repositories/vllm/SKILL.md) | [Skill](repositories/vllm/translations/zh-CN/SKILL.md) | [Records](../repo_packs/vllm/knowledge/README.md) |
| SGLang | Radix/HiCache, prefill/decode and extensions / 缓存、运行时与扩展 | [Skill](repositories/sglang/SKILL.md) | [Skill](repositories/sglang/translations/zh-CN/SKILL.md) | [Records](../repo_packs/sglang/knowledge/README.md) |
| SGLang-Omni | Stage pipelines, streaming and transport / 阶段流水线、流式与传输 | [Skill](repositories/sglang-omni/SKILL.md) | [Skill](repositories/sglang-omni/translations/zh-CN/SKILL.md) | [Records](../repo_packs/sglang_omni/knowledge/README.md) |
| vLLM-Omni | Model/deploy separation, AR/diffusion and output contracts / 编排、扩散与输出契约 | [Skill](repositories/vllm-omni/SKILL.md) | [Skill](repositories/vllm-omni/translations/zh-CN/SKILL.md) | [Records](../repo_packs/vllm_omni/knowledge/README.md) |
| Cross-repository router / 总入口 | Constrained engine design and validation / 受约束的设计与验证 | [Skill](workflows/inference-engine-research/SKILL.md) | [Skill](workflows/inference-engine-research/translations/zh-CN/SKILL.md) | — |

The original Strata design-space analysis is also included in
[English](repositories/strata/references/design-space-analysis.md) and [中文](repositories/strata/translations/zh-CN/references/design-space-analysis.md).

### Use the bilingual engine knowledge

```bash
inferrsi knowledge search --repo-type strata
inferrsi knowledge search Radix --repo-type sglang
inferrsi context --repo-type vllm --backend cuda --scenario llm.serving
inferrsi context --repo-type sglang_omni --backend cuda
inferrsi context --repo-type vllm_omni --backend cuda
```

Named JSON records in `repo_packs/` are the canonical searchable abstracts,
conditions and validation plans. Their `skill_documents` fields point to the
detailed bilingual procedures in this library; they are package-relative paths,
not network downloads. `knowledge show <id>` returns the complete record and
`context` retains these document pointers. There are no per-record Markdown
summary copies. Existing backend-scoped experiences keep their original IDs.

For an installed wheel, locate the library without assuming a checkout path:

```python
from importlib.resources import files
library = files("inferrsi").joinpath("data", "skill_library")
router = library.joinpath(
    "workflows", "inference-engine-research", "translations", "zh-CN", "SKILL.md"
)
print(router.read_text(encoding="utf-8"))
```

Load a single repository or follow the router progressively. When copying
material, preserve this owner layout and the referenced dependency bundles,
including translations and resources; the router links into `repositories/`.
Choose one language edition as the agent entry point because both editions use
the same skill IDs. InferRSI ships the documents and reads catalog JSON; it does
not automatically install skills, execute their instructions, download models
or launch an inference engine.

中文使用方式：先通过 CLI 查找相关知识，再读取 `skill_documents` 指向的完整中文
Skill。固定源码版本、模型、硬件和负载后再开展实验；文档或 CPU 检查不能证明
GPU 正确性、模型质量或性能收益。`common` 只表示仓库内通用方法，不代表任意
后端已经验证。

## Maintain

Edit the canonical owner directory and preserve its metadata and source notices.
Keep supporting Markdown and JSON in the owner's `references/`, `cases/` or other
existing resource directory; only library navigation and the registry belong at
the library root.

For the 48 registered skills, update `skill-index.json` if a canonical path or
backend changes, regenerate catalog records with `tools/build_skill_index.py`,
and verify local links, cross-skill dependencies and noneditable installed reads.
Do not duplicate skill content or hand-edit generated cards.

For the bilingual engine collection, keep source revisions and licenses in
[source-manifest.json](workflows/inference-engine-research/references/source-manifest.json)
and each repository's provenance references. These are research-source snapshots,
not campaign baseline/candidate defaults. For an update, check changed source
contracts, update the English owner bundle, its `translations/zh-CN/` edition
and the catalog abstract together, then run catalog, local-link and
installed-package checks. Preserve negative
results and `locally_verified=false` until a separate qualified campaign exists.
