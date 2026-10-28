---
name: qualification
description: "Qualify mistral.rs actual-model Metal prewarm coverage, executed paged-attention routes, native numerical and cache-state evidence, and cold versus warm measurement boundaries without treating source inspection or CPU checks as GPU qualification."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Actual-model Metal prewarm and evidence

Use this route when a loaded model reports Metal kernels prepared, a request
still compiles a pipeline, or someone proposes a correctness/performance claim
from an eligible attention shape. This is a source-derived **candidate**. Its
offline helper does not execute Metal, load a model or certify dispatch.

## Freeze the claim and identity

1. Record source/dependency revisions, build features and metallib artifacts,
   OS/SDK/device, process lifetime, actual model/tokenizer assets, query/cache
   dtype, per-layer geometry/device mapping, cache layout/block size, execution
   limits and request features. Distinguish pipeline preparation, actual
   dispatch, primitive parity, model quality and service performance.
2. Read [prewarm and evidence](references/prewarm-and-evidence.md). Trace the
   actual model's warmup input, not a representative model name. Unsupported,
   nonpaged, MLA and non-Metal layers do not acquire paged preparation coverage
   merely because the final log appears.
3. Compare request specializations with what was prepared. The inspected model
   path prepares causal attention with zero multimodal ranges, no right window
   and no attention chunk size. It preserves the layer's sliding window and
   selected ALiBi/sink/softcap features. It is not every possible request.
4. For decode pipeline-boundary planning only, run the bundled inventory below.
   Follow [its schema and limits](references/warmup-inventory.md). Its Cartesian
   shape list is neither a dispatch selector nor a native test result.
5. Trace an actual request to its pipeline and reduction path using authorized
   native evidence. Do not invent a public last-dispatch getter; no such API is
   established here. Preserve geometry, constants, buffers, tails and cache
   state alongside the trace. Use [decode contract](../decode-contract/SKILL.md)
   and [prefill contract](../prefill-contract/SKILL.md) for route semantics.
6. After integrating the whole skill graph, select and inspect the bounded
   native candidates in the reference. Execute them only with an authorized,
   prepared Apple Metal environment and finite resource limits. A compiled or
   skipped test is not an executed assertion. Missing backend evidence remains
   `BLOCKED_REQUIRED_BACKEND`, with no CPU substitution for Metal dispatch.
7. Separate compilation/prewarm, first real request and steady state. New
   `Kernels` values share process-wide caches. Freeze model/service acceptance
   gates before measurement; retain failures and slower trials. A primitive
   reference comparison proves neither model quality nor serving speed.

## Offline boundary inventory

From this sub-skill directory:

```bash
python scripts/warmup_shape_inventory.py --example
printf '%s\n' '{"schema_version":1,"max_batch":32,"max_context":32768}' \
  | python scripts/warmup_shape_inventory.py -
```

The example yields 7 batch boundaries, 17 context boundaries and 119 shape
pairs. These are source enumeration facts, not timing samples or new numeric
acceptance bars. The helper is standard-library-only, bounded and offline; it
does not import the engine or inspect the host GPU.

## Return a scoped conclusion

Report separately: source-supported preparation coverage; actual native
dispatch and numerical/cache-state evidence; model/quality/service evidence.
For each missing part, retain the exact blocked prerequisite and next safe
check. Use [troubleshooting](references/troubleshooting.md) for cache lifetime,
metallib failures and misleading CI/test outcomes. Scaffold CI and synthetic
helper checks never remove the required-native gap.
