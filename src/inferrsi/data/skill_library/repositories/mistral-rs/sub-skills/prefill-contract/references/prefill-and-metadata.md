# Host shape, metadata and kernel consumer

Source provenance is the inspected
[Rust prefill backend](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_prefill.rs),
[shared cache/scale guards](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/mod.rs)
and selected
[Metal consumer](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/kernels/paged_prefill.metal#L91-L310).
These are source-derived contracts; native compilation and execution were not
performed. Source presence is not Metal/device/model qualification.

## Shape screening is not the full request contract

`MetalPagedPrefillShape::supports` checks nonzero sequence/head/KV-head/query/
context/block dimensions, query heads divisible by KV heads, total query tokens
at least maximum query length, head dimensions in 1–4096, floating F16/BF16/F32
queries and F16/BF16/F32/F8E4M3 cache. It does not inspect actual tensors, cache
contents, table IDs, devices, strides, positions, masks, FP8 scale tensors or
finite scalar settings. A manually constructed shape need not encode a real
request. The helper derives a narrower consistent shape from complete declared
length vectors; it does not authenticate the declarations.

The actual request expects four-dimensional query `[query_batch, heads,
query_axis, key_dim]`. Packed query storage requires `query_batch=1` and
`query_axis=sum(query_lens)`; padded storage requires `query_batch=num_seqs` and
`query_axis=max(query_lens)`. Sequence vectors must agree in length, and query/
context lengths must be nonzero. Position-plus-length, mask extents and query
count use checked arithmetic.

Key/value layouts in this prefill parser:

| Key cache | Value cache | Meaning |
| --- | --- | --- |
| `[blocks, kv_heads, block_size, key_dim]` | `[blocks, kv_heads, block_size, value_dim]` | HND-style path |
| `[blocks, kv_heads, key_dim/x, block_size, x]` | `[blocks, kv_heads, value_dim, block_size]` | Packed legacy key path; actual K dimension is inner dimension times `x` |

Blocks, KV heads, block size and K/V dtype must agree; key dimension must match
Q. Prefill allows an independently resolved `value_dim`; do not impose the
neighboring `CacheShape::new` equal-head-size expectation on this parser, or
assume that prefill's unequal dimensions make every decode path compatible.

The block table must be rank two, U32 or I32, with one row per sequence and at
least `ceil(max_context_len/block_size)` columns; cache block count must be
nonzero. This is not validation of every physical table value or actual page
contents. The inspected vector kernel skips physical IDs outside cache blocks;
do not mistake that consumer guard for proof that supplied IDs are valid.

Each bound tensor must live in Metal storage on the same device as Q. Binding
retains byte offset `layout.start_offset * dtype_size`; element strides are
copied into kernel parameters. Replacing a narrowed/transposed view with assumed
contiguous addressing can read different bytes even when dimensions match.
Non-power-of-two blocks use division/remainder rather than power-of-two shifts.

FP8 cache requires **both** explicit K/V tensors, each F32 with one element;
non-FP8 cache rejects supplied K/V scales. Head features (ALiBi/sinks) must be
floating vectors of length query heads, with their actual stride retained.
Sliding/window-right/chunk options reject zero; attention scale must be finite,
and softcap must be finite and positive when present. See
[request/binding guards](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_prefill.rs#L392-L664)
and [scale guards](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/mod.rs#L45-L69).

## The bounded workspace formula

For `rows = total_query_tokens` when packed, otherwise `num_seqs*max_query_len`:

- Raw output = `rows * num_heads * value_head_dim * sizeof(query_dtype)`.
- Raw metadata = `(num_seqs*9 + num_multimodal_ranges*2) * sizeof(u64)`.
- Each allocation reservation = `max(next_power_of_two(raw_bytes), 16384)`.
- `workspace_bytes = rounded_output + rounded_metadata`.

This is not rounding the **sum** once and not rounding to the next multiple of
16 KiB. `query_copy_workspace_bytes` separately rounds
`rows*heads*key_dim*sizeof(query_dtype)`; `output_copy_workspace_bytes` separately
rounds the output formula. Add those only for the caller route that actually
needs those copies. KV cache, caller additive-mask storage, cache writes and
other model work are excluded. Checked multiplication/rounding/addition may fail
on overflow. Context length does not appear in these output/metadata formulas,
but it still changes table capacity, cache state, mask extents and computation.
See [workspace methods](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_prefill.rs#L275-L349)
and [rounding](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_prefill.rs#L378-L390).

The runtime sends metadata inline when raw bytes are at most 4096. Above that
it allocates backing and copies metadata in 256-u64-word chunks. The workspace
method conservatively reserves rounded metadata even when the runtime binding
is inline. Do not interpret that reservation as measured resident memory.

## Nine words per sequence plus half-open ranges

Each row contains, in order: query length, context length, absolute query start,
absolute key start, concatenated query offset, concatenated context offset,
range-data offset **in u64 words**, range count and mask K offset. Range pairs
are appended after row data; each has `end > start` and denotes `[start,end)` in
absolute positions. Historical ranges need not intersect the current query.

The kernel computes `qp=query_start+local_q` and `kp=key_start+local_k`. Its
attention-chunk check occurs first: Q and K must have equal absolute-position
chunk indices. Causality admits `kp<=qp`; a left window admits past positions
with `qp-kp<window_left`; a right window admits future positions with
`kp-qp<window_right`. The equality boundary is excluded for positive windows.
After those gates, a range containing both positions can override causal/window
rejection, but **cannot** override the earlier attention-chunk rejection.
Query/key bounds still apply. Coarse key bounds are narrowed by windows and
expanded for intersecting ranges, followed by per-key permission tests. See
[permission and bounds consumer](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/kernels/paged_prefill.metal#L118-L223).

ALiBi computes the signed difference of integer absolute positions before
converting that distance to float, preserving small distances at large common
origins. Softcap applies to scaled QK before ALiBi/additive-mask terms. A shape
helper does not validate these numerical operations or accumulation precision.

## Additive mask coordinates are independent of Q packing

Mask rank must be 2, 3 or 4 with floating F16/BF16/F32 dtype. Left-pad its shape
with ones to four axes. Non-unit batch/head/Q axes must equal expected sizes;
the K axis may be unit (broadcast) or **at least** the required extent.

| Mask mode | Expected four-axis extents |
| --- | --- |
| Not packed | `[num_seqs, heads, max_q, max(context_len + explicit_offset_or_zero)]` |
| Packed, no explicit K offsets | `[1, heads, total_q, sum(context_lens)]` |
| Packed, explicit K offsets | `[1, heads, total_q, max(context_len + explicit_offset)]` |

At consumption, packed mask Q is `local_q + concatenated_q_offset`; unpacked
mask Q is local. Mask K is `local_k + row.mask_k_offset`. Without explicit
offsets, that origin is concatenated context offset for packed masks, zero for
local masks. An explicit vector replaces that origin, **not** the concatenated
packed Q origin. Broadcast axes use index zero, and actual mask strides/start
offset survive binding. See [host extents](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_prefill.rs#L480-L641)
and [mask load](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/kernels/paged_prefill.metal#L141-L178).

## Native discriminators, not local successes

The [source test module](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/tests/metal_prefill.rs#L1-L17)
is compiled only with feature `metal` on macOS. Even its
[pure workspace assertion](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/tests/metal_prefill.rs#L705-L735)
is inside that file-level gate; a Linux zero-test result is not a successful
workspace test. No Rust/compiler/native test was executed for this candidate.

The inspected test body compares actual native outputs to a separately formed
F64 reference with dtype-specific source tolerances, verifies finite values and
output shape, and synchronizes the device. Those source tolerances are not
portable campaign gates. Selected cases cover geometry/layouts, 56/57-sequence
metadata transition, windows/ranges/FP8, historical ranges, noncausal/chunked
attention and query tiles. Large-origin ALiBi, strided/broadcast/packed masks,
fully masked rows and block size seven are further discriminators. Explicit
mask-key-offset semantics are source-consumer evidence here, not a claimed
executed native case in that test module. Native numerical, memory and service
claims require their own compatible runtime, inputs and actual results.
