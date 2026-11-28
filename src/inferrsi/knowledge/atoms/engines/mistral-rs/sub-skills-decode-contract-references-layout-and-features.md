# Decode layout and feature contracts

## General cache shape

Q is rank 3 `[sequences, query_heads, head_dim]`. The inspected decode body
supports head dimensions 64, 80, 96, 112, 128, 192, 256 and 512; query heads
must divide into an integer number of query heads per KV head. The code checks
`query_heads % kv_heads == 0`; a reversed phrase in a source docstring does not
override that executable guard.

HND K is `[blocks, kv_heads, block_size, head_dim]`, with V matching it. Legacy
packed K is `[blocks, kv_heads, head_dim/x, block_size, x]`; V is
`[blocks, kv_heads, head_dim, block_size]`. The cache shape reader derives layout
from rank, checks equal K/V dtypes and matching dimensions. Sliding decode
requires HND. A reshape with the same number of elements does not transpose the
producer's bytes into the other contract.

At the engine allocation boundary `MISTRALRS_METAL_PAGED_LAYOUT` unset, `auto`
or `hnd` selects HND, `legacy` selects Standard, and other values fail. Direct
low-level tensors are still classified from their actual shapes, not this
environment label. Default block size is 32, but the helper deliberately only
screens that selected domain rather than inventing an exhaustive build matrix.

The engine's paged-attention guide lists decode kernel blocks 8/16/32. The
standalone prefill primitive and its block-seven test have a different contract;
their existence does not make arbitrary block sizes a supported loaded-model
configuration. Likewise, legacy layout retains paging/prefix sharing, while
`--paged-attn off` disables paging. The guide's `auto` enables paging only on
supported CUDA/Metal models and disables it on CPU; it is not a CPU paged-op path.

Query dtypes are F16/BF16/F32. Cache dtypes also permit F8E4M3. FP8 cache requires
both explicit K and V scales, each scalar F32; other cache dtypes must not
supply scales. The runtime also requires actual Metal storage/device for these
bindings. Scale metadata or nominal cache bits do not authenticate real tensor
bytes or numerical quantization quality.

## Specialized domain is narrower

`MetalPagedAttentionWorkspace.specialized_variant()` requires:

- query F16/BF16 and exactly matching cache dtype;
- no scales, ALiBi or sinks; `softcapping == 1.0` (the disabled value);
- block size 32 and either HND or packed `x=8`;
- integral GQA ratio 1 through 8;
- head size 64/96/128/192/256, or HND head 512 with GQA at most 4.

Passing this predicate is not evidence that the GPU executed it. The variant
policy then distinguishes short, fixed-split and grouped launches. Packed and
HND policies differ; HND can use an exact trailing window, and one specific
head-512 single-request/no-window range selects FP32 fixed-split partials.
Other profiles are measured source policy, not portable performance gates.

The native HND grouped consumer uses block-table IDs, slot and head strides,
per-sequence lengths and window bounds. Query/KV sharing is tied to GQA group,
not an interchangeable token/batch flattening. Threadgroup staging, SIMD-local
probabilities and reductions require their corresponding synchronization;
do not remove a barrier merely because source-level arithmetic looks equal.

## Evidence pointers

[Shape and scale reader](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/mod.rs),
[decode guards and consumer calls](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_attention.rs#L140-L670),
[allocator layout parser](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-core/src/paged_attention/cache_engine.rs#L13-L27),
[variant policy](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/kernels/mod.rs#L1011-L1237),
and [MSL HND consumer](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/kernels/paged_decode_hnd.metal#L1-L285).
The [versioned paging guide](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/docs/src/content/docs/guides/perf/paged-attention.mdx#L1-L200)
supplies the engine-versus-primitive configuration boundary, not local execution evidence.
These links preserve immutable provenance, not a dependency on a source checkout.
