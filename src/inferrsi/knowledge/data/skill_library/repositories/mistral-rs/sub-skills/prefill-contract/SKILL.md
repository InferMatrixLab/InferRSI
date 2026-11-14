---
name: prefill-contract
description: "Investigate mistral.rs Metal paged-prefill shape, bounded workspace, packed metadata, absolute-position masking and strided cache consumption while keeping declared arithmetic separate from actual tensor and GPU validation."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Paged-prefill contracts

Use this source-derived **candidate** when a cached prefix, ragged batch,
multimodal range, mask or workspace estimate behaves unexpectedly on the Metal
paged-prefill path. This route owns prefill, not generic model support or all
attention implementations. Read the [host and kernel contract](references/prefill-and-metadata.md)
before proposing a layout change. Native and compiler checks remain **not_run**;
unavailable Apple Metal evidence remains **BLOCKED_REQUIRED_BACKEND**.

## Route by the broken assumption

| Question | Start here |
| --- | --- |
| Does workspace grow with the cached prefix? | Separate output/metadata reservation from KV, masks, writes and copies |
| Can `shape.supports()` establish eligibility? | Apply actual request/tensor guards as a separate layer |
| Packed queries read the wrong mask columns | Reconcile concatenated Q origin, packed/local K origin and explicit offsets |
| A multimodal range seems to bypass every restriction | Check absolute half-open bounds and attention-chunk restriction first |
| Unequal K/V dimensions or noncontiguous tensors fail | Trace this prefill parser and actual strides, not a neighboring decode shape |
| FP8 cache passes shape screening but fails startup | Check explicit scalar F32 K/V scale tensors and common Metal device |

## Procedure

1. Record the exact mistral.rs/Candle/native build and device, query/cache
   dtypes, K/V layout and dimensions, actual tensor strides/start offsets,
   physical block table and each sequence's lengths and absolute origins.
   Requested dimensions and a release name are not inspected tensor facts.
2. Separate three checks: the shape's shallow `supports` predicate, the host
   request's full structural/binding checks, and actual kernel execution with a
   numerical reference. Success at one layer cannot substitute for the next.
3. Reconcile packed versus padded query storage. Packed Q uses batch one and
   the sum of query lengths; padded Q uses sequence count and maximum query
   length. Query packing and additive-mask packing are separate flags. Do not
   assume one determines the other in a real request.
4. For declared arithmetic and selected metadata checks, use the bundled
   [screen_prefill_metadata.py](scripts/screen_prefill_metadata.py) with its
   [complete schema and limits](references/helper-contract.md):

   ```bash
   python scripts/screen_prefill_metadata.py --example
   python scripts/screen_prefill_metadata.py --example | python scripts/screen_prefill_metadata.py -
   ```

   Run from this sub-skill directory, or resolve the script as an installed
   resource. It uses only the Python standard library and performs no tensor,
   model, compiler or device operations. Exit zero means selected caller
   declarations are internally consistent, never that a GPU route is eligible.
5. Count output and metadata allocations independently: each is the next power
   of two with a 16 KiB floor. The primary workspace formula excludes KV cache,
   caller masks, cache writes and separate query/output-copy reservations.
   Cached context can enlarge KV/tables/masks and execution work even when this
   workspace formula stays unchanged.
6. Preserve the coordinate systems. Causal/window/chunk tests and multimodal
   ranges use absolute token positions. Packed query mask rows stay concatenated;
   explicit key offsets replace the ordinary local/packed mask K origin. Range
   ends are exclusive. A range does not override the attention-chunk boundary.
7. Before accepting tensor support, verify actual device/storage, query shape,
   K/V geometry/dtypes, table batch/columns, scale tensors, head-feature shapes,
   mask dtype/rank/broadcast extents, finite scalars and position arithmetic.
   Strided views retain their real element strides and byte start offsets.
8. For numerical evidence, select discriminating real native cases: ragged
   packed/padded batches, metadata inline/buffer transition, historical ranges,
   strict windows/chunks, noncontiguous cache/masks, fully masked rows, FP8
   scales, unequal K/V dimensions and large absolute ALiBi origins. These are
   described in the reference, not executed by this helper.
9. A warmup pipeline cache or estimated workspace is not evidence of actual
   dispatch, parity, memory fit, model quality or serving gain. Coordinate decode
   and shared cache assumptions with [decode-contract](../decode-contract/SKILL.md)
   and route experiments/claims to [qualification](../qualification/SKILL.md).

## Return a falsifiable conclusion

Use [troubleshooting](references/troubleshooting.md) to name the first conflicting
invariant and smallest authorized check. Report declarations versus inspected
bytes versus executed results separately, preserve exact native not-run reasons,
and retain unverified/INCONCLUSIVE scope. Do not install toolchains, download
weights, launch a service or erase caches merely because a source example does
so. Reading this route does not grant those permissions.
