---
name: sglang
description: "Understand, tune, or extend SGLang's inference runtime with versioned source evidence: scheduling, KV/HiCache, parallel execution, kernels, and controlled validation."
license: Apache-2.0
metadata:
  disco-role: operating
---

# SGLang inference engineering

Use this graph for SGLang engine reasoning, bounded tuning, and implementation reviews. Before relying on it, compare the checkout with [provenance](references/repo-provenance.md). The original LLM routes retain that snapshot; the diffusion supplement has its own pinned source notes and validation limits. These are portable candidates, not claims that a GPU configuration has passed.

## Choose among source pins

Use the question and the retained source scope to select an entry. These pins
are independent; each row's inspection date applies only to its stated scope.

| Question | Existing entry | Fixed evidence / original date | Limit |
| --- | --- | --- | --- |
| LLM admission, Radix/KV ownership, topology or controlled engine tuning | This engine graph; [runtime and memory](sub-skills/sglang-runtime-memory/SKILL.md) and [source map](references/source-map.md) | `16176278d0180f1a1a578e53e6eef432577876c2`; contribution records accessed 2026-10-14, with separate [snapshot provenance](references/repo-provenance.md) | LLM routes retain this snapshot; engine navigation is not a tested combination of all routes/backends |
| Qwen3.5/Qwen3-Next GDN versus convolution dispatch, phase metadata or one-shot prefill transfer | [Kernel caller/backend contract](../../methods/kernel-writing-guide/references/sglang-gdn-causal-conv-contract.md) and [source cases](../../methods/kernel-writing-guide/cases/sglang-gdn-source-contract.md) | Same `16176278d0180f1a1a578e53e6eef432577876c2`; bounded source inspection 2026-10-29 | Candidate/not_run; per-runner GDN choices, conv stride/alias branches and state-row contracts; no HF binding, native hardware, model-quality or performance qualification |
| Reusable LLM prefix KV across device, host and optional storage tiers | Separate catalog ID `sglang.cuda.llm.hierarchical_prefix_cache` ([canonical peer record](https://github.com/InferMatrixLab/InferRSI/blob/8233a2ba795a22af9b8f17c8793da0a936a38857/src/inferrsi/data/knowledge_packs/peer/sglang/cuda/llm/hierarchical-prefix-cache.json)) | `f7ad4345b86d147a1c3095a3cebabca9a33ebaa1`; HiCache documentation accessed 2026-10-15 | CUDA/LLM peer card; imported, locally_verified=false; prefix identity, sharing scope and transfer/recompute cost require matching evidence |
| multimodal_gen stage state, component-use intervals or timeout/job finalization | [Diffusion lifetimes](audit-sglang-diffusion-lifetimes/SKILL.md) and its [source notes](audit-sglang-diffusion-lifetimes/references/source-notes.md) | `df13d5dce31abfeff0e701a62e8c39a136758e6c`; supplied archive inspected 2026-10-22 | Candidate, empirical validation not_run; bounded monolithic path, separate from LLM srt and SGLang-Omni |

Read the HiCache peer separately through its stable ID, for example
`inferrsi knowledge show sglang.cuda.llm.hierarchical_prefix_cache`.
The record link identifies retained provenance, not an implicit dependency of a
diffusion bundle.

LLM prefix KV tiers do not define diffusion scheduler-instance, component or
job-finalizer lifetimes. Common indexing and an engine entry do not qualify
CUDA/NPU execution or cross-pin compatibility. Process transport/IPC alone
does not establish Network capability.

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
