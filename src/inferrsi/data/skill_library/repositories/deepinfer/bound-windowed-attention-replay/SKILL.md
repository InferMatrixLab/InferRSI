---
name: bound-windowed-attention-replay
description: Bound replay or prefill query rows across a producer/consumer boundary whose retained inputs and separately preserved historical state satisfy the full dependency closure. Use when a model has shared hidden state or preserved-compressed KV and the retained region must be derived rather than assumed. Derives the retain rule from window plus rollback depth, separates query-row compaction from dropping historical keys, and names what becomes unrecoverable.
---

# Bound a windowed-attention replay

## Trigger and boundary

Use when all of the following hold:

- The architecture has an explicit boundary: layers before it run over the full prefix, while layers after it compute a bounded suffix of query rows. Historical keys or other full-layout state may remain preserved separately. A YoCo-style split, a shared-hidden design, or a preserved-compressed-KV design can qualify after deriving its dependencies.
- That boundary is where replay cost concentrates, so shortening the post-boundary query is what saves the work.
- You control metadata construction, not only the attention kernel.

Do **not** use when:

- A retained query needs a value unavailable from retained producer outputs or explicitly preserved historical state, and that value cannot be reconstructed. Reading a historical key outside the retained query suffix is allowed when that key is preserved. Derive the dependency first (step 1) and stop if you cannot establish it.
- The request needs per-token outputs for the clipped region, such as prompt logprobs.
- The system relies on bit-identical results across preemption, because recompute moves the retained rectangle's anchor.

**Model dependency.** The retain arithmetic `keep = window + rollback` is a small, transferable identity. What does not transfer is everything that makes it *safe*: which layers are producers, which are consumers, where the boundary sits, whether the consumer's KV is compressed or shared across layers, and the per-model window and ring sizes. Treat this procedure as a template for deriving those answers, not as a formula to apply.

## Status and source

Status: **candidate**. Empirical validation: **not_run**.

Source: `deepseek-ai/DeepInfer` @ `8b16149741a4935e1dec8cea27853f273b374c5b` (Apache-2.0), read statically; no equivalence run was performed here. **F** is a fact observed in the pinned source; **P** is proposed procedure.

Read [source-notes.md](references/source-notes.md) for the evidence ledger and [validation.md](references/validation.md) for the unrun checks.

## Required inputs

1. **The producer/consumer split.** Which layers run over the full prefix and write the persistent cache; which layers run compact query rows and which historical state they still read. Read the layer construction, not the config comment.
2. **The dependency closure.** For each consumer, what it reads and where that was produced. Follow it transitively: a consumer reading a shared hidden that was itself computed from a compressed KV needs both accounted for.
3. The window and rollback depth that apply at the boundary.
4. The boundary layer index, or a rule that identifies it.
5. Whether consumer KV is compressed, shared across layers, or per-layer, and whether the historical keys are preserved in full.

## Procedure

1. **Derive the dependency closure before touching any window arithmetic.** Enumerate, per consumer layer, every producer it reads: previous-layer hidden state, a shared hidden captured at the boundary, a compressed KV written by an earlier layer, a top-k index pool. For each retained query, establish whether its inputs are available from retained producer outputs or explicitly preserved historical state. Stop if a required value was discarded and cannot be reconstructed. One layer's finite window does not establish the whole stack's dependency horizon; dependencies can extend across layers.

2. **Confirm the boundary hosts a full-length write.** The architecture has to preserve, at the boundary, the state the consumer needs at full length. In the reference this is the captured full hidden plus the main/index KV stored at full length during the compact query's forward (`F`: `deepinfer/model_executor/models/v4_modules/attn.py:672-719`, `decoder_layer.py:134-141`). If no such full-length write exists, shortening the query changes the cache and the procedure does not apply.

3. **Compute the retain length.** `keep = window + max_rollback`. Enforce a floor on `max_rollback` equal to the speculation width plus one, so a full-width rollback after a full-width draft still leaves `window` tokens (`F`: `deepinfer/environ.py:132`, `max(value, USE_NEXTN_DECODE + 1)`).

4. **Enforce `keep` at every entry.** The value can arrive through an environment variable, so a single check is not enough. In the reference it is checked at model-metadata construction (`F`: `deepinfer/model_executor/model_metadata_utils.py:91-92`), at worker setup (`F`: `deepinfer/worker/model_runner.py:107-114`) and in the C++ metadata builder (`F`: `csrc/engine/input_metadata/prepare_tensor_input_v4.cpp:350-357`).

5. **Define the visible region explicitly.** For a query at absolute position `p`, visible keys are `[max(p − window + 1, rect_lo, valid_start), p]`, where `rect_lo = data_len − keep_tokens` is the retained rectangle's lower bound and `valid_start` guards against attending to zeroed state after a recompute. Clamp and assert bounds; an out-of-range start slot is a silent correctness bug (`F`: `prepare_tensor_input_v4.cpp:155-166`).

6. **Separate query-row compaction from historical-key retention.** These are two independent decisions and the reference makes only the first:
   - **Query-row compaction** removes query rows whose visible region is empty. That is where the compute saving comes from.
   - **Historical-key retention** is a separate question. A consumer may legitimately keep full-layout keys in a compressed or shared index while computing over fewer query rows. Compact queries are not evidence that historical keys were dropped.

   Do not state or assume that whole-context compressed attention is incompatible with this procedure. A retained query may read keys outside the retained query region when the required historical state is preserved. Preserving keys alone does not establish that every other hidden-state dependency is available; step 1 must still account for those inputs.

7. **Decide the mode, and keep both.** Provide a diagnostic mode that keeps all rows and only narrows visibility, and a saving mode that drops the clipped rows. In the reference these are `mask` and `compact` (`F`: `deepinfer/environ.py:188`). Make the diagnostic one the target of the equivalence test, because it is compute-neutral and isolates the visibility math from the gather.

8. **Preserve the full layout while building the compact copy.** At the boundary, compute the full-length representation the consumer needs before or alongside producing the compact copy. In the reference the boundary helper returns both the compact inputs and the original full hidden/residual, and the caller stores the full hidden into the cross-layer runtime before continuing with the compact values (`F`: `deepinfer/model_executor/models/v4_modules/yoco.py:93-122`, `deepinfer/model_executor/models/decoder_layer.py:134-141`). Note the shape of this requirement: it is "the full-layout value must exist and be stored", not a global ordering that KV writes precede a gather.

9. **Handle a fully clipped chunk.** If a chunk lies entirely before the rectangle, keep one row so a sampling position always exists. The reference does this in the clip computation itself, by clamping the clip prefix to `q_len − 1` rather than `q_len` (`F`: `prepare_tensor_input_v4.cpp:225`).

10. **Disable what becomes invalid.** Prompt logprobs cannot be reconstructed from a clipped region. The reference forces them off with a warning rather than rejecting the request (`F`: `deepinfer/engine/llm_engine.py:529-537`). Note the actual behaviour: the request proceeds with `prompt_logprobs = False`. If your engine must reject instead, that is a policy change, not a description of this source.

11. **State the anchor.** Define the rectangle relative to `prompt + generated` length, and document that preemption-and-recompute moves it.

## Expected outputs

- A dependency closure listing, per consumer, what it reads and where that was produced.
- A retain length, with every point that enforces it.
- Per-request compact metadata: query count, position ids, store slots and visible-range indices.
- A statement of whether historical keys are preserved, compacted, or compressed, kept separate from the query-compaction decision.
- A diagnostic mode usable as the equivalence reference.

## Evidence to collect

- **Metadata equivalence**, using a matching built extension without model weights: visible-key sets, store slots and compressed-key ranges between diagnostic and saving modes at chunk boundaries. Runtime is not measured here.
- **End-to-end equivalence** on a fixed teacher-forcing trajectory: logprobs and top-k compared element-wise.
- **Prompt-logprob handling**: confirm the actual behaviour — forced off with a warning, or rejected — rather than assuming either.
- **Preemption count during the comparison run**: must be zero, or the results are not comparable.

## Preconditions and caveats

- **The dependency closure is the real gate.** A stack of windowed layers is not automatically safe to shorten; only a demonstrated boundary dependency is.
- **The retain rule is not a suggestion.** Below `window + rollback`, the decoder sees fewer than `window` tokens after a rollback. The failure can be loud (an assert) or numerical (diagnostic mode), depending on the mode.
- **Diagnostic mode is compute-neutral.** Do not report it as an optimization.
- **Recomputed SWA state before the valid rectangle is unavailable.** Cache reuse and prefill-to-decode transfer must respect that validity boundary. This does not invalidate the separately preserved full-layout main/index KV.
- **Ring sizing has nested gates.** The inference ring is `window + rollback` per sequence when `window > 0`, otherwise zero (`F`: `deepinfer/worker/cache_engine.py:88-95`). The *prefill/kvstore* ring adds margins only when `DEEPINFER_PREFILL_STORE_EXTRA_STATE` is set: that branch adds the store-granularity margin, plus the truncation keep margin when truncation mode is not `off` (`F`: `cache_engine.py:97-110`). The keep margin therefore requires both gates. Do not describe the larger ring as unconditional.
- **Chunk boundaries do not align with store boundaries.** Prefill chunks do not land on store boundaries, so a longer ring is required to reassemble a complete window at a store point.
- **Intermediate chunk samples are discarded.** Only the last prompt chunk's last row produces the token.
- **Config may not be authoritative.** If the window comes from a config the parser did not read, the check compares against a wrong value.

## Stop conditions

- Stop if the dependency closure shows any consumer reading state produced outside the retained region and no full-length copy of that state is preserved.
- Stop if you cannot capture the full-layout representation at the boundary.
- Stop if the comparison run preempts; the anchor moved and the result is not evidence.

## Configuration in the reference source

| Variable | Default | Effect |
|---|---|---|
| `DEEPINFER_YOCO_PREFILL_TRUNCATION_MODE` | `off` | `off` / `mask` (diagnostic, compute-neutral) / `compact` (removes clipped query rows) |
| `DEEPINFER_YOCO_PREFILL_KEEP_TOKENS` | `0` (must be set when truncation is on) | Retained trailing query count. The `> 0` and `>= window + rollback` checks apply only when the mode is not `off`; with `off` the value is unused. |
| `DEEPINFER_MAX_BACKTRACKING_TOKENS` | `max(value, nextn + 1)` | Rollback depth folded into the retain rule |
| `DEEPINFER_PREFILL_STORE_EXTRA_STATE` | unset → false | Gates both kvstore-ring margins; the keep margin also requires truncation mode not `off` |

Truncation is **off by default** in the reference. Enabling it without setting the keep length fails an assertion rather than silently clipping.
