---
name: vllm
description: "Analyze and operate vLLM inference internals: V1 scheduling, KV and prefix reuse, parallel topology, speculation, backend selection, and measurable performance experiments; route source changes to focused validation."
license: Apache-2.0
metadata:
  disco-role: operating
---

# vLLM inference engine

Use this graph for explaining how vLLM executes requests, choosing existing inference controls, or locating a narrowly scoped engine change. This is a portable candidate grounded in one source snapshot, not a claim of complete repository or hardware coverage.

Read [source snapshot](references/repo-provenance.md) before relying on defaults or compatibility. A different commit requires checking the affected code and CLI again. Model revision, tokenizer/chat template, hardware/backend, traffic lengths and concurrency, and target latency/throughput determine the useful path; resolve missing facts only when they change the next action.

| Need | Read |
|---|---|
| Trace a token step, understand KV lifetime, distinguish existing controls from new mechanisms | [Architecture and search space](sub-skills/architecture-search-space/SKILL.md) |
| Diagnose OOM, queueing or latency; choose TP/PP/DP/EP, speculation, P/D, compilation or quantization experiments | [Operation and performance](sub-skills/operation-performance/SKILL.md) |
| Change scheduler, cache, connector, attention, quantization or compilation behavior and validate correctness | [Extend and validate](sub-skills/extend-validate/SKILL.md) |

Return an evidence-backed answer: current mechanism → bounded decision or change → expected observations → correctness and performance checks. Distinguish source-supported facts, hypotheses, and executed results. Never turn a help check, import, synthetic benchmark, or AST check into an inference/performance claim.

Preserve token accounting, request completion/abort behavior, KV ownership and semantic cache identity. Quantization changes need quality checks; speculation needs verification semantics; parallel or transfer changes need topology and lifecycle checks. Read only the relevant sub-skill and its references.

Use existing user authorization for model runs and infrastructure actions. Before resource-consuming work, identify the actual model, target resources and bounded run. Source/model plugins are executable code; inspect changes before running setup or enabling remote code. This graph includes no installation or mutation helper.

Machine contracts: [routing](references/repo-routing-metadata.json), [provenance](references/repo-provenance.json), [evidence map](references/evidence-map.json). Human references are bundled; a live AREX installation is not required. API payload details, comprehensive model onboarding, every accelerator, and exhaustive kernel coverage are outside this graph.
