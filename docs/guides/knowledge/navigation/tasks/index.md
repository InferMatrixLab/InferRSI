# Start with the primary task

- [task-accuracy](../../../../../src/inferrsi/knowledge/data/skill_library/tasks/task-accuracy/SKILL.md)
- [task-day-0](../../../../../src/inferrsi/knowledge/data/skill_library/tasks/task-day-0/SKILL.md)
- [task-debug](../../../../../src/inferrsi/knowledge/data/skill_library/tasks/task-debug/SKILL.md)
- [task-derived-engine](../../../../../src/inferrsi/knowledge/data/skill_library/tasks/task-derived-engine/SKILL.md)
- [task-independent-engine](../../../../../src/inferrsi/knowledge/data/skill_library/tasks/task-independent-engine/SKILL.md)
- [task-performance](../../../../../src/inferrsi/knowledge/data/skill_library/tasks/task-performance/SKILL.md)
- [task-version-alignment](../../../../../src/inferrsi/knowledge/data/skill_library/tasks/task-version-alignment/SKILL.md)

For task-accuracy compare the timing endpoint and complete output. For task-version-alignment verify the supported stack and replay boundary.

- [`package:vllm_omni.common.audio.streaming_serving_measurement`](../../../../../src/inferrsi/knowledge/data/skill_library/records/vllm_omni.common.audio.streaming_serving_measurement.json) — Which events define first audio and chunk continuity? The endpoint called first packet differs between engines or releases. Measurement method. Target release behavior requires a local event trace. Read `record.json` at `sha256:d88cae264916abce761108bed26ab471fe5cd4ed8ff964fe0ad17058dd3abd8a`.
- [`package:sglang_omni.common.audio.serving_and_streaming_quality`](../../../../../src/inferrsi/knowledge/data/skill_library/records/sglang_omni.common.audio.serving_and_streaming_quality.json) — How should streaming speech quality and completeness be checked? A successful HTTP request produced degraded or truncated audio. SGLang-Omni provides a method analogue. Validate the target codec and load. Read `record.json` at `sha256:8b256066de12d761cf6944b449a6234f1857c8fce6e5a94b6813b236d81371f9`.
- [`package:inferrsi.ascend.skills.ascend_aclgraph_capture_replay`](../../../../../src/inferrsi/knowledge/data/skill_library/systems/platforms/ascend/ascend-aclgraph-capture-replay/SKILL.md) — How do I isolate capture and replay failures? An Ascend or vLLM upgrade changed graph execution on identical inputs. Procedure only. Target stack compatibility stays unknown until replay. Read `data/skill_library/systems/platforms/ascend/ascend-aclgraph-capture-replay/SKILL.md` at `sha256:182c537e8bb8856b97009726ec0b49d3aed267c2a1c29a32bf3ef44accd0f708`.
- [`package:inferrsi.ascend.skills.vllm_ascend`](../../../../../src/inferrsi/knowledge/data/skill_library/systems/engines/vllm-ascend/SKILL.md) — Which stack and devices does the cited release declare? A graph configuration is being moved across vLLM-Ascend releases. The release declaration is tag-specific. Compare installed versions and SKU. Read `data/skill_library/systems/engines/vllm-ascend/SKILL.md` at `sha256:2b3427b1422c0c2a350d789c53ed1f830896bbb37059bc694687ad3ba5e09f56`.
