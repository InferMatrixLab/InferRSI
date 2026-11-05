# Predictor generated-code copy audit (CPU read-only)

Scope: inspected only the known user's `<PATH_1> generated Python cache and the two backbone cache directories named by the completed profile server log. No imports/execution of generated code, cache mutations, GPU calls or broad home scan.

## Concrete generated-code finding

K's intermediate contiguous materialization is absorbed into its normalization/RoPE kernel; V retains a separate copy kernel in inspected full17 predictor artifacts. Therefore “both K and V contiguous each add an independent copy launch” is incorrect. There is concrete V-copy work worth a bounded experiment, but no proven removable service latency.

B64 artifact `hf/chfpt6cywvjeg2jodxm3qttncmdgl3xlhentjso74qvdjviq5o3n.py` under that cache has exact input guard[64,17,1024], QKV weight[4096,1024], Q16/KV8/head128, five layers and causal FlashAttention scale1/sqrt128. Generated source-node/ATen mappings identify `qkv`, `kv_raw`, `split`, `k_raw`, `v_raw`, clone and SDPA together; this is stronger than kernel-name inference.

At438–532, K kernel reads packed QKV directly at offset2048 +128*head +4096*token, performs FP32 reduction/casts/norm/RoPE and writes final dense K. There is no prior separate K-contiguous buffer kernel in the call sequence. At629–638, the kernel with a very long `...mean_mul_pow_rsqrt...` name actually contains only V load/store: packed source offset3072 +feature +4096*token to dense output. Its broad name reflects graph ancestry, not executed arithmetic. At1586–1597, caller runs K transform, then standalone V copy into[64,8,17,128], then FlashAttention(Q,K,V). The V output contains1114112 BF16 elements, 2,228,224 bytes; nominal read+write payload is4,456,448 bytes/layer/depth, not measured DRAM traffic.

B1 artifacts `5u/c5uv3itmwotulj3iowcvxsnihqy57goxjjdvwlzzam5v6ioj52rr.py` and `6m/c6mf55emyvgav7o6molkrpa75fu5diacf7vxiv5aqqhvkktxfjjg.py` have input[1,17,1024], Q16/KV8/head128. First has Q/K transforms288/494 and V-only load/store678–687, output allocation1389 and SDPA1395; second has corresponding V-only copy664–673. Some linear GEMMs are padded24 rows in B1; that is another reason not to equate these wrappers with every trace event solely by name. V payload is17408 BF16 elements,34816 bytes, or69632 bytes read+write per layer/depth. At15 depths×5 layers, the counted payload is~5.22MB/frame B1, plus75 copy launches if this exact compiled wrapper executes each depth. This does not imply all bytes reach HBM.

## Profile correlation boundary

Completed profile summary stage1 has the analogous V-copy ancestry kernel `triton_poi_fused__scaled_dot_product_flash_attention__to_copy__unsafe_view_add_clone_index_mean_mul_pow_rsqrt_slice_split_transpose_unsqueeze_view_3`25200 times at C1, and companion Q/K kernels25200 times. Count matches336 codec frames×15×5. Source-node identities and exact model shapes establish the cache artifacts are predictor implementations, and their long-name structure explains a plausible profile classification.

However: these shared cache artifacts lack a retained run-to-generated-wrapper hash mapping; profile was captured with with_stack=false, and B1 artifact names include `mm`/different suffixes while observed high-count names do not. The available summary alone cannot establish which exact wrapper/hash was executed, or map every C1 frame to B1 versus padded/graph bucket shapes. Therefore this is **verified generated-code V-copy existence + corroborating profile fingerprint**, not exact event-to-source-stack attribution. Do not publish per-request copy-time savings or assert all25200 events are proven to be these artifact bytes. A future trace/code mapping should retain generated wrapper hash, compiled function ID and tensor-shape/correlation metadata.

## Narrow next experiment, not deployment recommendation

Test removing only V `.contiguous()` while retaining K's layout and all norm cast points, or integrate V copy with an existing Q/K transform. A strided V view may be supported by SDPA but can select a different backend/layout and alter BF16 numerical results; a copy-free view is not automatically faster. A fused K/V transform can retain dense final layout while saving one launch, but adds V stores to a reduction kernel and may worsen occupancy. First validate fixed-input eager/compiled logits and full model quality, then measure actualshape component timing with generated-code confirmation. Do not reimplement K copy removal: it is already fused in inspected artifacts. No engine edit or experiment was performed.
