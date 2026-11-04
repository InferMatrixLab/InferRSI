# HF Qwen3.5 binding and state cases

These representative source-reasoning cases use the
[HF binding contract](../references/hf-qwen35-gdn-binding.md) and
[source ledger](../references/hf-qwen35-gdn-source.json).
State: candidate. Native execution `not_run`; agent efficacy `not_evaluated`.
They are not reproduced runtime failures or performance results.

## 1. Replace a chunk function after constructing layers

**Request:** A worker changes the modeling module's chunk function after
loading Qwen3.5 and claims every existing layer now uses it. Assess both releases.

**Expected reasoning:** Identify the linear-attention class and trace its
constructor/forward. In 5.10.2 the instance already saved its chunk callable;
changing only the global does not replace that field. In 5.17.0 Python forward
reads `torch_chunk_gated_delta_rule`, but Hub or worker method replacement can
supersede that path. A `torch_` name may already wrap FLA. Resolve method and
callable before choosing an authorized binding seam.

**Failure signals:** Use the same patch name/timing for both releases; confuse
module/instance identity; infer dispatch from a package import or marker.

## 2. First one-token prompt versus continuation

**Request:** Classify first one-token input, resumed one-token input, resumed
multi-token input and cache-free classification.

**Expected reasoning:** Without previous state, the first token uses full conv
and chunk GDN. No cache means no initial/final recurrent state. A cached first
call stores history and final state; resumed one-token work uses recurrent
GDN, while a resumed segment uses chunk GDN with initial state. Preserve old
conv context and output trimming. In 5.17.0, `record_past` disables in-place
single-token conv, but recurrence still takes its one-token route. A supplied
cache is not erased by `use_cache=False`.

**Failure signals:** Classify from token count alone; discard generation state;
zero-pad a resumed segment; assume conv and GDN phase predicates are identical.

## 3. Missing package and misleading availability

**Request:** A startup warning says a fast path is unavailable. Does that prove
conv and recurrence both execute PyTorch? Compare the two releases.

**Expected reasoning:** In 5.10.2 inspect each availability helper and saved
fallback separately. The aggregate flag only warns and was computed at import.
In 5.17.0 the decorator captures an importable original-package callable or
the reference body; requested Hub replacement is another boundary. Distinguish
decoration-time failure from selected-kernel invocation failure. Check export
and keyword filtering before reusing a signature.

**Failure signals:** Infer callables from a warning, global name, package list
or GPU name; assume an invocation exception silently retries on PyTorch.

## 4. Reuse a cache-free adapter for generation or grouped heads

**Request:** An adapter rejects initial/final state. Can it replace all GDN
calls or independently remove the repeated Q/K heads?

**Expected reasoning:** Limit it to proven cache-free classification-prefill:
actual `cache_params=None`, `initial_state=None`, `output_final_state=False`.
Decode/continuation needs a different state contract. Preserve gates,
normalization and output. Stock HF repeats Q/K to value-head count; removing
the repeat requires a selected grouped-head implementation and an explicit
caller/layout change. The bounded PPLX method override must be read as its
own path. Conv selection remains separate.

**Failure signals:** Infer whole worker behavior from the HF class; treat no
final state as generation-compatible; claim GVA, parity or gain from shapes.

## 5. Cross-engine state and request reset

**Request:** Substitute vLLM operators using HF batch position as a cache-row
ID, leave matrix orientation unchanged and reuse state for the next request.

**Expected reasoning:** Distinguish conv `[B,C,W]`, local recurrent
`[B,Hv,Dk,Dv]` and attention KV. vLLM's row mapping and recurrent orientation
differ; require an adapter and state/numerical checks. Resolve version-specific
cache dtype, reset and reorder. Reset zeroes initialized values and clears
prior-state flags without releasing allocation. Ownership, concurrency and
request isolation remain outside the readset. Conv record-past is not recurrent
rollback. Packed kwargs need the resolved implementation; local reference
bodies do not consume those boundaries.

**Failure signals:** Substitute state semantics by name; preserve stale state
for independent requests; equate zeroing with free; claim rollback, packing or
binary compatibility from source alone.

## Verification boundary

Each case gives a source-supported decision and counterexample. Resource reads
do not measure agent outcomes. Dependency build/load, executed dispatch,
target shapes/strides, output/state parity, checkpoint code, quality, device
compatibility and matched performance remain independently unverified.
