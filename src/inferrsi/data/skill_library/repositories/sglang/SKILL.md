---
name: sglang
description: "Understand, tune, or extend SGLang's inference runtime with versioned source evidence: scheduling, KV/HiCache, parallel execution, kernels, and controlled validation."
license: Apache-2.0
metadata:
  disco-role: operating
---

# SGLang inference engineering

Use this graph for SGLang engine reasoning, bounded tuning, and implementation reviews. Before relying on it, compare the checkout with [provenance](references/repo-provenance.md). The original LLM routes retain that snapshot; the diffusion supplement has its own pinned source notes and validation limits. These are portable candidates, not claims that a GPU configuration has passed.

Choose one main route; compose a second when its boundary is involved:

| Task | Read |
|---|---|
| Trace a request; diagnose admission, prefix reuse, KV pressure, chunking, or speculation | [Runtime and memory](sub-skills/sglang-runtime-memory/SKILL.md) |
| Choose TP/DP/EP/PD topology; add a model, attention backend, or kernel | [Parallelism and extension](sub-skills/sglang-parallel-extension/SKILL.md) |
| Design a limited experiment, correctness gate, or benchmark comparison | [Tuning and validation](sub-skills/sglang-tuning-validation/SKILL.md) |
| Diagnose multimodal_gen diffusion stage state, component retention or request timeout/deletion | [Diffusion lifetimes](audit-sglang-diffusion-lifetimes/SKILL.md), a separate source-derived candidate |

Record model/tokenizer revision, hardware and interconnect, SGLang commit, dependency versions, workload shape, and the requested outcome. Separate **existing configuration**, **implementation change**, and **research extension** before proposing work. Existing flags do not establish that their combinations are supported.

For the LLM routes, keep the request path explicit: HTTP/Engine → TokenizerManager → Scheduler/ScheduleBatch → TpModelWorker/ForwardBatch → ModelRunner/backend → results → DetokenizerManager → caller. Overlap scheduling and distributed roles change timing and ownership; the [architecture reference](references/architecture-and-memory.md) locates those boundaries.

Prefer the smallest causal hypothesis and its observable check. Keep cache identities, request lifetime, allocation ownership, and collective participation intact. Verify output correctness before accepting a performance gain; report unmeasured effects as hypotheses. If a check fails, preserve the reproducer and return to a known baseline before adding another optimization.

The [native candidate map](references/native-candidates.md) points to specialized repository skills when code changes need them. It does not import or execute those skills automatically. [Source map](references/source-map.md) holds checked, commit-pinned evidence; [routing metadata](references/repo-routing-metadata.json) records AREX classification.

Scope excludes SGLang frontend language tutorials, diffusion paths beyond the bounded supplement, full deployment automation, and untested combinations across every accelerator. The supplement concerns this repository's multimodal_gen runtime, not SGLang-Omni. Load the relevant native implementation when extending beyond the evidenced paths.
