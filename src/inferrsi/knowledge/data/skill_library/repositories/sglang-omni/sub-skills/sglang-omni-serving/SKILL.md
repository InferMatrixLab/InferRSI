---
name: sglang-omni-serving
description: "Resolve SGLang-Omni configs, select model-specific serving recipes and tune latency or throughput against explicit audio/video quality constraints."
license: Apache-2.0
metadata:
  disco-role: operating
  repository: sgl-project/sglang-omni
  source-commit: 2cfb3b67becb437b70751defe37e63d3af4eedb0
  language: en
  skill-root: sglang-omni
  parent: sglang-omni
---

# Serving and tuning

Use for an SGLang-Omni launch, model recipe, effective configuration, overload or measured optimization. Read [recipes and experiment contract](references/recipes-and-tuning.md) and the root [snapshot](../../references/snapshot.md).

1. Select the model-specific recipe and endpoint; preserve its platform package pins and reference-audio requirements. Match cached checkpoint and config class before starting workers.
2. Inspect `sgl-omni config resolve` and `config explain` with the same arguments as the proposed launch. Record config, diff and provenance. Resolution is not a no-dependency guarantee: model registry/config imports or model metadata lookup may need optional packages or cached/network metadata.
3. Start the minimum supported topology in an authorized target environment. Verify readiness, one request, output modality, sample rate, complete audio/text, and streaming errors before load testing.
4. Record a warm baseline and one changed factor using the same dataset, seed/sampling, duration distribution, quality scoring, hardware and dependency versions. Compare completed good requests, latency distribution, audio duration/RTF, failures and quality together.
5. Roll back on a quality, completion, memory or tail-latency regression; retain per-request artifacts and server logs. Increase concurrency only after locating the queue that saturates.

For startup failure, inspect the earliest missing-package/config/factory error before increasing memory. For OOM, distinguish weights, KV, graph capture, vocoder and communication pools; reserve memory across processes, and retest the same workload after a minimal change. For 503, inspect admission plus request-build and AR queues. For audio missing after HTTP 200, verify speech mode and inspect SSE error events and EOS. Return a reproducible command/config change and measured evidence; never promise an unmeasured speedup.
