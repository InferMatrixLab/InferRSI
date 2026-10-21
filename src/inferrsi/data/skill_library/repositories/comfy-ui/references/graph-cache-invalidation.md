# Workflow-output cache validity

## State and execution path

**CODE.** `/prompt` validates before queuing
([`post_prompt`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/server.py#L1161-L1227)).
The queue worker owns a reusable `PromptExecutor`; its default is RAM-pressure
caching, with explicit classic/LRU/none branches
([`prompt_worker`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/main.py#L330-L377)).
Do not infer the same default from constructing CacheSet directly: its fallback
is classic
([`CacheSet`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/execution.py#L121-L154)).

For each prompt, `execute_async` creates a DynamicPrompt and IsChangedCache,
rebuilds cache keys, cleans policy-owned entries and creates an ExecutionList
([`execute_async`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/execution.py#L733-L800)).
A cached output returns before node invocation; on a miss, the node class is
instantiated or retrieved from the separate object cache
([`execute`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/execution.py#L439-L523)).
Completed results enter the output cache only after pending async/subgraph work
is resolved
([completion branches](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/execution.py#L547-L619)).

## Validity ledger

| State | Key or identity | Lifetime / invalidation |
|---|---|---|
| Node output + UI entry | Node and ordered ancestors: class, fingerprint, sorted constant inputs, link input name/ancestor position/output socket; conditional node ID | Survives prompts only while policy retains a matching signature |
| Node object instance | `(node_id, class_type)` | Separate hierarchy; changing a literal does not itself create a new object identity |
| Fingerprint result | Per-prompt node ID in IsChangedCache | Computed once per node in this prompt; no fingerprint method gives False |
| Runtime consumer references | ExecutionList cache links and listeners | Holds upstream entries for consumers and updates them when a producer completes |
| External provider entry | Canonical serialized signature hash in CacheContext | Provider-specific retention; unknown/unserializable or self-unequal keys are declined |

Identity sources:
[`CacheKeySetInputSignature`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/caching.py#L83-L148),
[`CacheKeySetID`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/caching.py#L68-L81),
[`IsChangedCache.get`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/execution.py#L72-L106),
[`ExecutionList.cache_link/get_cache/cache_update`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/graph.py#L230-L264),
[provider guards](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/caching.py#L238-L305).

`NOT_IDEMPOTENT` and hidden `UNIQUE_ID` add node identity to the signature.
They prevent equivalence across different node IDs; the implementation does not
make a fixed ID change on every execution. Do not translate either into a
blanket “always rerun” rule. Fingerprints receive constants, not cached linked
output tensors. Exceptions produce NaN; external lookup/store guards reject
self-unequal keys so deterministic serialization does not accidentally turn a
local non-hit into an external hit
([signature identity](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/caching.py#L110-L128),
[NaN guard](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/cache_provider.py#L88-L114)).

External files are not automatically tracked by their JSON filename. A concrete
built-in example explicitly reads image bytes in `LoadImage.IS_CHANGED`
([implementation](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/nodes.py#L1808-L1814)).
For a custom node, audit file contents/revision, mutable model state, random
state and hidden configuration separately. Whether these belong in its
fingerprint is a node-specific correctness decision, not a global cache flag.

## Scheduling and retention are separate

**CODE.** Declared lazy links are omitted from initial strong dependencies until
requested by the node's lazy-status method. The executor can add those links,
return PENDING and unstage the node. Dynamic expansions get parent-scoped
subcaches and new dependencies
([initial dependencies](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/graph.py#L145-L181),
[lazy branch](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/execution.py#L504-L523),
[expansion](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/execution.py#L581-L615)).
The signature ancestry traversal still follows declared input links; do not
replace it with “only nodes observed to execute.”

Classic cleanup keeps keys/subcaches used by the current prompt. LRU tracks
generations; its cleanup loop can stop at the current generation, so N is not
a hard process-memory bound. RAM-pressure cleanup and eviction depend on host
headroom and protected active entries, rather than a fixed number of bytes
per node
([classic](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/caching.py#L162-L198),
[LRU](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/caching.py#L440-L477),
[RAM pressure](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/caching.py#L523-L568)).

## Troubleshooting and falsification

| Symptom | Discriminating check | Boundary |
|---|---|---|
| Same JSON, stale result | Change external bytes while retaining the filename; inspect the node's fingerprint and downstream result | JSON equality alone does not prove cache validity |
| Unrelated nodes rerun | Change one literal and compare producer/consumer execution sets under a fixed mode | Separate ancestry invalidation from eviction and dynamic/lazy expansion |
| Low hit rate after mode change | Record effective caller defaults and entry eviction events | Do not remove a correctness key input to force reuse |
| Node executes but output unchanged | Compare signatures, not only final values | Signature equality is not computed by comparing output tensors |
| External hit conflicts with local non-hit | Check NaN/unknown types and provider key serialization | Provider storage/concurrency semantics remain provider-owned |

**TEST-SOURCE.** Upstream tests specify same-graph reuse, changed-input partial
reuse, custom fingerprint reruns and constant-only fingerprint inputs
([cache cases](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/tests/execution/test_execution.py#L617-L651),
[custom fingerprint](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/tests/execution/test_execution.py#L810-L831),
[constant-only case](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/tests/execution/test_execution.py#L915-L935)).
They are inspected assertions, not reported local passes. Avoid claiming a
latency improvement without matched end-to-end timing and the executed-node
evidence that explains it.
