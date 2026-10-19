# Inference-engine knowledge / 推理引擎知识库

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

## Use from InferRSI

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

Keep source revisions and licenses in [source-manifest.json](source-manifest.json)
and each repository's provenance references. These are research-source snapshots,
not campaign baseline/candidate defaults. For an update, check changed source
contracts, update the affected language pair and its catalog abstract together,
then run catalog, local-link and installed-package checks. Preserve negative
results and `locally_verified=false` until a separate qualified campaign exists.
