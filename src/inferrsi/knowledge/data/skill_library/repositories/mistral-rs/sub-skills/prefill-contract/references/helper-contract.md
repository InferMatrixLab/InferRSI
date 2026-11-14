# Declared metadata/workspace helper

[screen_prefill_metadata.py](../scripts/screen_prefill_metadata.py) adapts selected
source shape, metadata and mask-extent checks plus the
[workspace formula](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_prefill.rs#L275-L349).
It is newly authored Python support, **not** a Rust binding, complete native
request validator, GPU emulator, dispatch selector or numerical reference.

Use `--example` to print a complete synthetic input. Give a JSON file or `-` /
stdin to screen it. No engine/model/compiler/device is imported or executed; no
files are written. Inputs are limited to 1 MiB, 4096 sequences and 16384 range
pairs for this bounded helper, not because the source advertises those limits.
Duplicate/unknown/missing keys fail. All documented keys are mandatory:

| Fields | Declaration contract |
| --- | --- |
| `schema_version` | Integer `1`, not boolean |
| `num_heads`, `num_kv_heads` | Positive integers with query heads divisible by KV heads |
| `key_head_dim`, `value_head_dim` | Positive integers at most 4096 |
| `block_size` | Positive integer; non-power-of-two values are not rejected |
| `query_dtype` | `f16`, `bf16` or `f32` |
| `cache_dtype` | Same set plus `f8e4m3`; this does not validate actual FP8 scale tensors |
| `packed_queries`, `packed_mask` | Independent booleans |
| `query_lens`, `context_lens` | Nonempty, same-count lists of positive lengths |
| `query_start_positions`, `key_start_positions` | Same-count lists of nonnegative absolute origins |
| `multimodal_ranges` | One list per sequence, each containing `[start,exclusive_end]` pairs with `end>start`; use empty rows when absent |
| `mask_key_offsets` | `null` or same-count nonnegative K offsets |
| `additive_mask_shape` | `null` or positive rank-2/3/4 dimensions, screened against source broadcast extents |
| `sliding_window`, `window_right`, `attention_chunk_size` | `null` or positive integers |

Booleans are never accepted as integer dimensions. Declared sizes/positions use
checked unsigned 64-bit bounds, matching the intended 64-bit Apple target
arithmetic, not arbitrary Rust target widths. Allocation next-power-of-two or
sum overflow is rejected. Positions/lengths, explicit mask extents and their sum
are screened, but no mask values or permitted attention pairs are calculated.

Callable API: `screen(plan) -> dict`; invalid declarations raise `ValueError`.
`example() -> dict` returns the synthetic fixture. CLI exit `0` means these
selected declarations pass; exit `2` means invalid input, with a fixed diagnostic
that does not echo file paths or input contents. The helper cannot distinguish a
lie about tensor dimensions from an accurate declaration.

Outputs include expected query shape, storage rows, raw output/metadata bytes,
separately rounded output/metadata reservation, their `workspace_formula_bytes`,
additional query/output-copy estimates, inline versus buffered metadata binding,
expected mask extents and minimum block-table columns. The source reserves
rounded metadata even on its inline binding path; this is not measured memory.
Extra-copy estimates are **not included** in primary workspace. KV cache,
caller-owned masks, cache writes, model state and other workspaces are excluded.

Every result says `runtime_eligibility=not_verified`,
`numerical_correctness=not_verified`, `native_verification=not_run` and
`compiler_check=not_run`. Real query/cache/table shapes, data/physical IDs,
devices/storage, strides/start offsets, mask dtype/values, finite scalar settings,
head features and FP8 scales are deliberately not authenticated. Neither cached
context independence nor exit zero establishes model fit or performance.
