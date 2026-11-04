# Metadata-only helper

`audit_decode_metadata.py` is newly authored support from selected source
guards, not a Rust API wrapper, tensor validator, allocator or GPU simulator.
Use `--example` for the complete synthetic schema; pass a JSON file or `-` for
stdin. The API is `audit(plan) -> dict` and `example() -> dict`.

Fields are exactly: schema_version=1; query_shape; key_shape; value_shape;
query_dtype/cache_dtype; context_lens; max_context_len; block_table_shape;
k_scale/v_scale; sliding_window; has_alibi/has_sinks; softcapping. Shape entries
and lengths are positive signed-32-bit integers, not booleans. The helper
accepts 1..1024 context declarations and at most 64 KiB of JSON. These are
support-tool limits, not engine admission limits. Duplicate/missing/unknown
keys, malformed ranks/types/nonfinite controls fail with exit 2.

The helper's selected domain is block 32. Q is rank 3; K rank 4 (HND) or 5
(packed), V rank 4. It checks declared geometry, sequence counts and table width
against the declared max context, and selected sliding/dtype/scale contracts.
FP8 requires two scale descriptors `{"dtype":"f32","elements":1}`; non-FP8
requires both null. Actual scale bytes, device, table IDs and floating values
are not read. Positive finite softcapping 1 means disabled; flags merely
declare ALiBi/sink presence and do not validate their tensor vectors.

Exit 1 reports declared contract/helper-domain conflicts; exit 0 means selected
metadata is internally consistent only. A source-specialization predicate
candidate is not observed dispatch or proof of full engine compatibility.
The helper deliberately does not select short/split/grouped variants or
calculate scratch capacity. `declared_cache_payload_bytes` counts only K+V
elements from declared dimensions/dtype bytes; it excludes scale storage,
allocator rounding, aliases, scratch, weights, other pools and physical fit.

Every result preserves `native_verification=not_run`, `physical_fit=not_verified`
and the omitted tensor/stride/table/device/dispatch/numerical scope. Errors do
not echo raw input values or private paths. This helper never imports Candle,
compiles code, sends requests, installs dependencies or modifies a cache.

Python finite-number declarations are screened without implicit float conversion. An accepted positive integer, including a very large one, does not prove native F32 scalar representability; actual Rust/device binding remains outside this helper.
