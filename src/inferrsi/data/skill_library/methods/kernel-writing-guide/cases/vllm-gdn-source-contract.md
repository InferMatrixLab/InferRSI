# vLLM GDN source-contract cases

These four representative scenarios qualify source reasoning for the
[Qwen3-Next GDN contract](../references/vllm-gdn-causal-conv-contract.md).
Source: vLLM `537a79f0fc5ba564d2bef43d54915b2f80f9f77d`. State: candidate.
Native execution is `not_run`; agent efficacy is `not_evaluated`.
These cases do not report a reproduced failure or a performance result.

## 1. Mixed phases and one-token initialization

**Request:** A Qwen3-Next batch contains a resumed one-token request and a
first one-token prefill with `is_prefilling=True`. Explain which convolution
and recurrent paths the pinned vLLM source selects. Treat a following mixed
batch with a longer prefill separately. Do not run the model.

**Expected reasoning:**

- Name Qwen3NextDecoderLayer's `linear_attention` caller and interleaved layout.
- Use prior-state/prefill metadata as well as query length; a first one-token
  chunk can require the prefill route to mask recycled state.
- If any non-speculative prefill rows exist, identify the varlen forward
  convolution over the non-speculative portion.
- In a mixed non-speculative batch, identify decode-first recurrent update,
  rebased prefill cumulative lengths, prefill-row state slicing and output stitch.
- Distinguish this from speculative-row reclassification.

**Failure signals:** Treat every one-token row as decode; select a decode-only
conv for the entire mixed batch; pass unre-based offsets to the prefill
recurrence; claim model execution from source classification.

## 2. Requested backend versus actual branch

**Request:** An operator proposal says that selecting FlashInfer for GDN
prefill also replaces Qwen3-Next's decode convolution, and that an installed
fused CUDA MTP symbol proves it will run. Audit that statement from the pinned
caller without certifying any GPU.

**Expected reasoning:**

- Separate requested from effective prefill selection and retain source predicates.
- Separate convolution from recurrence dispatch and explain the packed decode guard.
- Follow Qwen3-Next's `gqa_interleaved_layout=True` into fused-MTP rejection;
  distinguish implicit fallback from explicitly requesting the rejected CUDA mode.
- State that XPU SYCL is an adjacent fused whole-layer exception whose behavior
  cannot be imposed on the chosen CUDA-facing path.
- Require actual dispatch evidence before claiming a backend ran.

**Failure signals:** Infer selection from package presence, default flags or
symbol names; generalize a separate-conv rule to every model/backend; turn a
source predicate into hardware compatibility or speedup.

## 3. Reordered state rows and speculative progress

**Request:** A worker wants to reuse the vLLM conv update while reordering
requests. It proposes using batch positions as cache-row IDs and a persistent
`cache_seqlens` ring cursor. Describe the compatible state contract and the
evidence still needed.

**Expected reasoning:**

- Separate convolution history, GDN recurrent matrix and attention KV.
- Derive row IDs from the engine mapping; preserve mapping across reorderings.
- State the per-rank history and recurrent shapes and account for SD/DS orientation.
- Explain initial-state masks, first-chunk zero history, recurrent-state clearing,
  null padding and request-count versus token-count metadata.
- Identify `num_accepted_tokens-1` as the inspected speculative read offset;
  packed cumulative lengths are batch offsets, not a persistent cursor.
- Retain in-place history writes and distinguish converted-input aliasing from
  unconditional original-input mutation.
- Keep physical row allocation/release/recycling outside the inspected boundary.

**Failure signals:** Copy standalone-package cursor semantics into this API;
equate batch index with cache row; preserve stale first-chunk state; assume
convolution and recurrent state are attention KV or ignore state writes.

## 4. Proving a binding with an unidentified HF caller

**Request:** A model label is given, with no HF implementation revision.
Can the worker bind vLLM's named causal-conv functions directly and claim GDN
acceleration? Return a source-backed readiness decision and the missing evidence.

**Expected reasoning:**

- Identify the vLLM in-tree import and registered core call chain.
- Keep the concrete HF implementation and its calling schema unknown.
- Request only the source needed to establish the HF caller, projection/layout,
  state ownership, phase guards, output and mutation contract.
- Do not infer equivalence with the standalone Dao package, external FlashInfer
  or vendored FLA implementations from an import or a shared symbol name.
- Separate source compatibility, installed/built operator, actual dispatch,
  numerical/state correctness and measured performance.
- Propose independent first/resumed, mixed, reordered, padded and speculative
  checks only where the eventual bound implementation supports them.

**Failure signals:** Invent a model-to-HF implementation mapping; prescribe an
unverified installation; assert numeric correctness, hardware support or speedup.

## Rubric and uncovered work

| Capability | Previous owner material | Added representative rubric | Evaluation |
|---|---|---|---|
| Phase classification | Generic verify-before-benchmark guidance | Concrete first/resumed, mixed and speculative branch checks | Source-supported; not_evaluated |
| Effective operator selection | General framework choice | Requested/effective recurrence, separate conv and fused-path exclusions | Source-supported; not_evaluated |
| State lifecycle at the call boundary | General correctness rules | Row mapping, initialization, history mutation and accepted-token offset | Source-supported; not_evaluated |
| Binding readiness | General reference/numeric validation | Concrete import/registration plus explicit unidentified-HF boundary | Source-supported; not_evaluated |

The upstream metadata and convolution tests express relevant intent, but were
not run for these cases. Native backend execution, independent numeric/state
comparison, concrete HF binding, physical allocator lifecycle, backend builds,
performance and agent outcome comparisons remain uncovered.
