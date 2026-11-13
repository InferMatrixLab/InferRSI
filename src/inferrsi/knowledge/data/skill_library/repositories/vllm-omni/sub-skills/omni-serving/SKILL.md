---
name: omni-serving
description: "Configure and benchmark supported vLLM-Omni deployments, streaming and stage placement."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Serving and tuning

Read the [serving cookbook](references/serving.md) for version alignment, launch templates, experiment order and failure recovery. Use the [architecture table](../omni-architecture/references/architecture.md) when deciding which variable to search.

Start with the selected model's supported default deployment. Record effective configuration after model, platform, YAML and CLI resolution. Confirm actual stage placement and active backend from logs. A config accepted by the parser may still select an unsupported runtime combination.

Measure a fixed short request before concurrency. Separate compilation/warmup, queueing, inference, transport and output encoding. For audio collect first media packet and chunk gaps; for image/video collect end-to-end latency, output size/duration and quality. Text token throughput is insufficient for these outputs.

Investigate the bottleneck before increasing TP, replicas, batch size or asynchronous buffering. If correctness changes, keep the failure evidence and return to the last valid baseline. Use [validation](../omni-validation/SKILL.md) for the affected state/transport/model gates.
