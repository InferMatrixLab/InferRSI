# Dense pool ledger helper

[screen_pool_budget.py](../scripts/screen_pool_budget.py) is a standard-library,
offline adaptation of selected
[default pool](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/kv_offload/config.py#L58-L79)
and [cap/floor](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/cache_policy.py#L1303-L1382)
arithmetic. It does not import or start the engine, read model payloads, allocate
cache, probe macOS, access a store or test actual runtime eligibility. Its strict
schema and diagnostics are newly authored support, not an upstream public API.
Compressed/grouped/sliding/hybrid/MLA layouts are outside this helper's domain.

Print a complete synthetic input with `--example`; feed JSON file or stdin (`-`).
All documented fields are mandatory; unknown keys and duplicate JSON keys fail.

| Field | Contract |
| --- | --- |
| `schema_version` | Integer `1` |
| `layout` | Exactly `dense-uniform-full-attention`; a declaration, not authentication |
| `layers`, `kv_heads`, `head_dim`, `max_model_len`, `block_size` | Positive integers; dimension values already resolved for the supported one-process route |
| `dtype_bytes` | Dense element bytes: `1`, `2`, `4` or `8`; not nominal quantization bits |
| `kv_budget_bytes` | Positive bytes; automatic mode: after weights/overhead and before the host pool; explicit-cache mode: cache-only bytes |
| `blocks_per_chunk` | Positive block count after any offload-block-size override has been resolved |
| `chunk_alignment_bytes` | Positive actual matched-vLLM alignment supplied by caller; no guessed host page size |
| `budget_mode` | `automatic` or `explicit-cache` |
| `pool_mode` | `automatic` or `explicit` |
| `pool_bytes` | `null` for automatic; positive integer for explicit |
| `auto_fit_length`, `block_override` | Booleans; suppress the source full-request reservation when applicable |

Integers/derived products are bounded to signed 64-bit positive byte arithmetic;
booleans are not integers. The helper uses exact integer quarter-budget flooring,
not floating-point emulation of the source at unrealistically large byte counts.
Inputs up to 1 MiB are accepted; malformed JSON, nonfinite/nontyped values, missing
keys or unsupported layouts fail with exit `2` and a fixed diagnostic.

The callable API is `screen(plan) -> dict`; invalid input raises `ValueError`.
`example() -> dict` returns the same synthetic fixture as `--example`. Main reads
only its selected input and prints JSON. Exit `0` means conflict-free declared
arithmetic, `1` means a flagged arithmetic conflict, `2` means malformed input.
Every result carries `native_verification=not_run`, `physical_fit=not_verified`
and `runtime_eligibility=not_verified`; none is a campaign verdict.

Important outputs:

- `rounded_request_tokens`: max length rounded up to block size.
- `default_two_request_pool_bytes`: nominal default before cap/floor.
- `aligned_chunk_bytes`: one actual aligned host chunk.
- `selected_pool_bytes`: automatic cap/floor result or unchanged explicit pool.
- `reserved_request_plus_null_block_bytes`: ordinary automatic sizing only.
- `remaining_cache_budget_bytes`: automatic mode subtracts host pool;
  explicit-cache mode leaves declared cache bytes intact.
- `physical_cache_plus_pool_capacity_bytes`: a declared capacity sum excluding
  model/overhead/workspace, not committed resident memory or peak usage.
- `problems`: insufficient chunk, overlarge explicit pool, or failure to leave
  the one-request-plus-null-block reservation. An oversized request that cannot
  fit even without offload is distinguished from offload causing the shortage.

Do not feed real private model paths, prompts, hostnames or credentials: the
schema needs only abstract dimensions and bytes. The program does not fix a
conflict or mutate a checkpoint/store. Reconcile actual physical headroom,
zeroing/layout policy, pressure probe and qualified model execution separately.
