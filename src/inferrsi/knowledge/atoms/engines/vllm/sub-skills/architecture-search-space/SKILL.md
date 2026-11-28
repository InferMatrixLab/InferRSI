---
name: architecture-search-space
description: "Trace vLLM V1 request execution and token/KV ownership; map scheduling, cache, backend, speculation and parallel controls to source before proposing an inference change."
license: Apache-2.0
metadata:
  disco-role: operating
---

# Architecture and search space

Start with the symptom or proposed mechanism, the pinned commit, and one request/iteration trace. Read [runtime and invariants](references/runtime-and-invariants.md) for the execution path and [capability boundaries](references/capability-boundaries.md) when deciding whether to tune or implement.

1. Trace frontend request → engine core → scheduler output → executor/runner → attention/model/sampler → scheduler update. Inspect abort and asynchronous overlap paths when the symptom involves stale output or completion.
2. Identify the scarce resource: scheduled token budget, runner input capacity, admitted sequences, KV blocks, encoder compute, device compute, memory bandwidth or communication. Several can bind together.
3. Match a supported control to that resource; explain its interactions and what observation would falsify the hypothesis. Resolve actual effective config, rather than assuming dataclass test defaults are serving defaults.
4. If a capability is absent, state the missing invariant/behavior and code boundary. Existing experimental hooks are starting points, not stability guarantees. Route changes to [extend and validate](../extend-validate/SKILL.md).

Check: the explanation identifies actual symbols, a pinned evidence link, workload dependence and correctness constraints. Recovery: if docs and implementation disagree, report the conflict, follow the pinned implementation for current behavior, and narrow the claim; do not infer support from a directory or registry entry alone.
