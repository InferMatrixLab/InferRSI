# Trace MiniMax-M3 cache dtype from configuration to storage

1. Record hardware capability, model architecture, checkpoint weight format, requested cache dtype, sparse-attention frequency list and explicit skip layers. The 950DT tutorial uses MXFP8 weights with an FP8 KV request. The release table separately describes a W8A8C8 deployment. Keep the actual checkpoint identity when reporting either configuration.
2. Inspect `_configure_minimax_m3_a5_mixed_kv_cache` in platform configuration. It gates on the two MiniMax-M3 sparse architectures, an FP8-attention-capable profile and a cache request of `fp8` or `fp8_e4m3`. Nonzero frequency entries identify sparse layers. The complement over all hidden layers becomes dense skip IDs. Existing skips are stringified and deduplicated in order before missing dense IDs are appended. Check the actual sparse list, especially when absent or short. An absent list makes every hidden layer a dense ID for this calculation.
3. Trace the affected prefix through `_resolve_layer_kv_cache_dtype` and `_resolve_layer_kv_cache_dtypes`. A skipped layer resolves to `auto`; its physical dtype follows model configuration (BF16 in the tested fixture). An eligible unskipped FP8 layer resolves to native `torch.float8_e4m3fn`. Inspect the index cache's returned spec as well as the attention layer's resolved dtype. Preserve raw request, effective skip list, layer ID and physical dtype in the report.
4. Narrow a mismatch with the tagged tests below in a prepared checkout. With frequencies [0,0,0,1,1] and explicit skips [4,"sliding_window"], the platform test expects ["4","sliding_window","0","1","2"]. Layer 3 remains eligible for FP8 while layer 4 uses its explicit skip. On the A3 profile, the automatic amendment does not run. Changing all layers to FP8 would lose both boundaries.

   ```bash
   pytest -q tests/ut/test_platform.py -k 'minimax_m3'
   pytest -q tests/ut/models/minimax_m3/test_msa_m3.py -k 'skip_layers or spec_follows_resolved_fp8'
   ```

5. If policy and specs match but outputs differ, distinguish prefill from decode. Select the matching one-card kernel/reference test, e.g. `test_decode_index_topk_correctness` in `tests/e2e/pull_request/one_card/test_minimax_m3_sparse_attn.py`. Preserve input shape, phase, dtype, top-k differences and hardware. A passing spec test alone leaves device numerics unresolved.

See the [pinned platform, resolver, spec and test definitions](sources.md).
