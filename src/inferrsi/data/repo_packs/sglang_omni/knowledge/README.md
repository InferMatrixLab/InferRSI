# SGLang-Omni knowledge

Named JSON records are retrieval abstracts with source attribution, conditions,
validation plans and explicit verification state. The complete English skills
provide the detailed procedures and evidence maps; they are not per-entry
Markdown copies of the catalog records.

Full library: [English skill](../../../skill_library/repositories/sglang-omni/SKILL.md).

All entries are imported guidance with `locally_verified=false`. `common` means
backend-independent guidance within this repository, not verified backend
support. The pack uses caller-supplied external commands and supplies no model
launcher. GPU/NPU execution, model quality and performance need separate
target-environment evidence.

## Entries

| Component | Record |
| --- | --- |
| omni | [SGLang-Omni stage DAG, process replicas and transport lifetime](common/omni/pipeline-state-and-transport.json) |
| audio | [SGLang-Omni serving recipes and streaming audio measurements](common/audio/serving-and-streaming-quality.json) |
| omni | [SGLang-Omni extension ownership and lifecycle validation](common/omni/extension-lifecycle-validation.json) |

## Maintenance

Keep IDs stable and add a navigation row for every record. Retain pinned source
attribution and limitations; omit PR links. Keep detailed procedures in the
linked full skills, and update abstracts when their source contracts change.
Catalog or CPU tests do not promote imported guidance to validated runtime
evidence. Follow the shared [knowledge maintenance contract](../../vllm_omni/knowledge/README.md#maintaining-the-pack).
