# vLLM knowledge

Named JSON records are retrieval abstracts with source attribution, conditions,
validation plans and explicit verification state. The complete bilingual skills
provide the detailed procedures and evidence maps; they are not per-entry
Markdown copies of the catalog records.

Full library: [English](../../../skill_library/repositories/vllm/SKILL.md) |
[中文](../../../skill_library/repositories/vllm/translations/zh-CN/SKILL.md).

All entries are imported guidance with `locally_verified=false`. `common` means
backend-independent guidance within this repository, not verified backend
support. The pack uses caller-supplied external commands and supplies no model
launcher. GPU/NPU execution, model quality and performance need separate
target-environment evidence.

## Entries

| Component | Record |
| --- | --- |
| llm | [vLLM V1 scheduling, token budgets and KV ownership](common/llm/runtime-and-kv-ownership.json) |
| llm | [vLLM bounded serving experiments and workload controls](common/llm/bounded-serving-measurement.json) |
| llm | [vLLM extension boundaries and correctness gates](common/llm/extension-correctness-gates.json) |

## Maintenance

Keep IDs stable and add a navigation row for every record. Retain pinned source
attribution and limitations; omit PR links. Keep detailed procedures in the
linked full skills, and update abstracts when their source contracts change.
Catalog or CPU tests do not promote imported guidance to validated runtime
evidence. Follow the shared [knowledge maintenance contract](../../vllm_omni/knowledge/README.md#maintaining-the-pack).
