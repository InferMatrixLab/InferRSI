# InferRSI skill library / 技能知识库

This is the canonical home for InferRSI's complete skill content: **48 categorized
skills migrated from root `skills/`, plus 42 existing bilingual engine skill
nodes**. Procedures, metadata, references, cases, helpers and source notices ship
with the package. The repository's root `skills/` directory is navigation only.

## Categorized skills / 分类技能

[`skill-index.json`](skill-index.json) maps the 48 stable skill IDs to their
canonical relative paths and backend scopes. Classification follows the skill's
substantive procedure, not its name alone: Nsight host profiling and
FlashAttention GPU mechanisms belong to CUDA; the general NPU-named skill factory
belongs to workflows. Host resource guidance is independent of accelerator HBM.

| Owner | Count | Content |
| --- | ---: | --- |
| [Hardware / Ascend](hardware/ascend/) | 13 | CANN, ACLGraph, Torch-NPU memory, operators, adaptation and device/distributed guidance |
| [Hardware / CUDA](hardware/cuda/) | 2 | Nsight host-overhead profiling and GPU attention bottleneck analysis |
| [Hardware / host](hardware/host/) | 5 | Host RAM, process placement, cgroups, storage I/O and host overhead |
| [Frameworks / PyTorch](frameworks/pytorch/) | 1 | Distributed checkpoint asynchronous-save performance |
| [Repositories / vLLM](repositories/vllm/) | 2 | KV lifetimes and admission pressure |
| [Repositories / LMCache](repositories/lmcache/) | 1 | KV tier management |
| [Methods](methods/) | 18 | Benchmarking, ceilings, search, training, serving, evidence and casebooks |
| [Workflows](workflows/) | 6 | Acceptance, claims, evidence, source checking, scans and skill lifecycle |

Install the optional `skills` extra to inspect registered skills directly:

```bash
inferrsi skills list --json
inferrsi skills show ascend-graph-mode
inferrsi skills resource inference-optimization-casebook cases/qwen-ascend-rejected-directions.md
# Optional custom flat tree or registry-based library:
inferrsi skills --root src/inferrsi/data/skill_library list
```

The default is the installed library, with those 48 IDs; the existing bilingual
editions below remain distinct document views. Core catalog operations do not
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

本目录统一维护完整技能正文、元数据、参考资料和案例。48 个原根目录技能按硬件、
框架、仓库、方法和工作流分类；平台相关内容归入对应 `hardware/` 子目录。已有的
42 个中英文引擎技能节点保持原结构。迁移不改变候选状态、验证结论或未知许可证，
读取技能也不会自动执行其中命令。

## Five-engine knowledge / 推理引擎知识

Source-grounded English and Chinese knowledge for five repositories, distilled
with the [AREX direct workflow](https://github.com/VectorSpaceLab/AREX-Skill/tree/ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6).
Each repository has an entry skill and three focused sub-skills. The collection
router connects all five: **21 skill nodes per language, 42 in total**.

[English overview](OVERVIEW.en.md) · [中文总览](OVERVIEW.zh-CN.md) ·
[Import and verification boundaries / 导入与验证边界](IMPORT.md)

| Repository | Focus / 重点 | English | 中文 | CLI catalog |
| --- | --- | --- | --- | --- |
| Strata | Heterogeneous MoE, placement, memory and speculative execution / 异构执行与搜索空间 | [Skill](en/strata/SKILL.md) | [Skill](zh-CN/strata/SKILL.md) | [Records](../repo_packs/strata/knowledge/README.md) |
| vLLM | Token scheduling, KV ownership and parallel execution / 调度、缓存与并行 | [Skill](en/vllm/SKILL.md) | [Skill](zh-CN/vllm/SKILL.md) | [Records](../repo_packs/vllm/knowledge/README.md) |
| SGLang | Radix/HiCache, prefill/decode and extensions / 缓存、运行时与扩展 | [Skill](en/sglang/SKILL.md) | [Skill](zh-CN/sglang/SKILL.md) | [Records](../repo_packs/sglang/knowledge/README.md) |
| SGLang-Omni | Stage pipelines, streaming and transport / 阶段流水线、流式与传输 | [Skill](en/sglang-omni/SKILL.md) | [Skill](zh-CN/sglang-omni/SKILL.md) | [Records](../repo_packs/sglang_omni/knowledge/README.md) |
| vLLM-Omni | Model/deploy separation, AR/diffusion and output contracts / 编排、扩散与输出契约 | [Skill](en/vllm-omni/SKILL.md) | [Skill](zh-CN/vllm-omni/SKILL.md) | [Records](../repo_packs/vllm_omni/knowledge/README.md) |
| Cross-repository router / 总入口 | Constrained engine design and validation / 受约束的设计与验证 | [Skill](en/inference-engine-research/SKILL.md) | [Skill](zh-CN/inference-engine-research/SKILL.md) | — |

The original Strata design-space analysis is also included in
[English](STRATA-ANALYSIS.en.md) and [中文](STRATA-ANALYSIS.zh-CN.md).

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
print(library.joinpath("zh-CN", "inference-engine-research", "SKILL.md").read_text(encoding="utf-8"))
```

Load a single repository or follow the router progressively. Copy one language
edition if installing these as agent skills: both editions use the same skill
IDs. Keep all six sibling directories for the collection router. InferRSI ships
the documents and reads catalog JSON; it does not automatically install skills,
execute their instructions, download models or launch an inference engine.

中文使用方式：先通过 CLI 查找相关知识，再读取 `skill_documents` 指向的完整中文
Skill。固定源码版本、模型、硬件和负载后再开展实验；文档或 CPU 检查不能证明
GPU 正确性、模型质量或性能收益。`common` 只表示仓库内通用方法，不代表任意
后端已经验证。

## Maintain

For the 48 categorized skills, edit the canonical owner directory and preserve its
metadata and source notices. Update `skill-index.json` if a canonical path or
backend changes, regenerate catalog records with `tools/build_skill_index.py`,
and verify local links, cross-skill dependencies and noneditable installed reads.
Do not maintain duplicate content in root `skills/` or hand-edit generated cards.

For the bilingual engine collection, keep source revisions and licenses in
[source-manifest.json](source-manifest.json)
and each repository's provenance references. These are research-source snapshots,
not campaign baseline/candidate defaults. For an update, check changed source
contracts, update the affected language pair and its catalog abstract together,
then run catalog, local-link and installed-package checks. Preserve negative
results and `locally_verified=false` until a separate qualified campaign exists.
