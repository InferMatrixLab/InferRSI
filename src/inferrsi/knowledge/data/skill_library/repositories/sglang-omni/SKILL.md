---
name: sglang-omni
description: "Operate, explain, tune and extend sgl-project/sglang-omni multi-stage omni, speech and TTS inference with source-grounded topology, transport and quality checks."
license: Apache-2.0
metadata:
  disco-role: operating
  repository: sgl-project/sglang-omni
  source-commit: 2cfb3b67becb437b70751defe37e63d3af4eedb0
  language: en
  skill-root: sglang-omni
---

# SGLang-Omni

Operate and extend the multi-stage runtime in `sgl-project/sglang-omni`. It owns pipeline topology, process/stage lifecycle, transport, model adapters and serving; compatible autoregressive stages compose with upstream SGLang. This is a separate repository from `sgl-project/sglang`. Do not transfer SGLang text-server or `multimodal_gen` flags into this runtime without tracing their consumer.

Before making a recommendation, establish the model/checkpoint revision, input and output modalities, endpoint, platform/dependency stack, GPU topology and memory, concurrency, and latency/quality objective. If only inspecting code, record unavailable runtime facts instead of fabricating a deployment.

| Work | Load |
|---|---|
| Explain a DAG, locate state ownership, reason about schedulers/transport, choose a supported optimization surface | [Architecture and search space](sub-skills/sglang-omni-architecture/SKILL.md) |
| Resolve configuration, serve a model, tune latency/throughput with a quality floor, diagnose overload | [Serving and tuning](sub-skills/sglang-omni-serving/SKILL.md) |
| Add a stage/model, change a runtime contract, select regression tests | [Extension and validation](sub-skills/sglang-omni-extension/SKILL.md) |

Use [snapshot and dependencies](references/snapshot.md) before installation or version-sensitive advice, and [provenance](references/repo-provenance.md) to check drift. Read only the route needed for the task.

Work from one baseline: record the resolved config and source revision, change one bounded factor, then check the affected contract and the end-to-end objective. Return the exact change, evidence, remaining uncertainty, and rollback configuration. A CPU config test does not establish GPU serving, numerical quality, or performance. This graph is a portable candidate, not evidence of AREX runtime import acceptance or hardware benchmarking.
