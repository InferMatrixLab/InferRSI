# Diagnosing the R12 and R13 greedy-output differences

The frozen R12 and R13 throughput trials used four Ascend 910B1 NPUs, TP4, BF16 eager execution, batch eight, and 32 greedy output tokens. The same two (R12) and three (R13) requests diverged in all 15 repetitions per candidate. This follow-up traces numerical differences on another reserved four-card allocation. Instrumented runs supply correctness observations only.

| Diagnostic arm | Effective change | Requests matching the 2,048/cache-off reference |
|---|---|---:|
| Reference | 2,048 scheduler token budget, cache off | 8/8 |
| R12 | 4,096 scheduler token budget | 6/8 |
| R12 control | Keep 4,096 capacity, cap actual scheduled tokens at 2,048 | 8/8 |
| R13 cold control | Cache enabled, prime with an isolated salt; zero hits per request | 8/8 |
| R13 warm | Prime the same 1,227-token template; 1,152 cached tokens per request | 5/8 |

The reference scheduled five steps containing prefill work; R12 scheduled three. Restoring the 2,048 scheduling cap reproduced the full reference prefill schedule and greedy outputs. Enabling the prefix cache with zero hits also reproduced the reference schedule and outputs. The warm arm scheduled the eight request tails together after reusing nine 128-token prefix blocks.

All four unmodified-upstream controls (reference, 4,096, cold cache, warm cache) matched the corresponding R6 run in each of the eight token sequences and per-request cache-hit counts. The source was Omni `f171117291cd40e2d5f877069520cdb8583deb26`; the matching R6 reference plus deployment YAML was `f58f8780ea176d6359f9bb6202198ccdcb7c8551`. The behavior reproduces independently of the RoPE patches in #11295 and #11309.

## First numerical differences

For each rank the trace keyed rows by prompt digest and absolute input-token position. It compared the bytes of per-token vectors before and after layer operations in each of the 32 decoder blocks. Hashes are 64-bit BLAKE2b of the original bytes; retained sample vectors also provide direct elementwise checks. For the warm arm the seed prefix has its own comparison over the reused positions 0..1151, and the tail compares the positions actually executed for each request. All layer and input-position indices in the files are zero-based; generated-token indices below start at one.

| Comparison | Affected prompt from the throughput run | First observed tap | Example TP rank | Input position |
|---|---:|---|---:|---:|
| 4,096 vs 2,048 | 2 | `l02_attention` | 2 | 896 |
| 4,096 vs 2,048 | 4 | `l12_attention` | 0 | 1010 |
| Solo prefix vs reference prefix | 2 | `l02_attention` | 2 | 896 |
| Solo prefix vs reference prefix | 4 | `attention` | 3 | 419 |
| Solo prefix vs reference prefix | 7 | `attention` | 3 | 955 |
| Warm tail vs reference tail | 2 | `l03_attention` | 0 | 1152 |
| Warm tail vs reference tail | 4 | `l01_attention` | 0 | 1152 |
| Warm tail vs reference tail | 7 | `l01_attention` | 0 | 1152 |

The R12 requests that eventually changed a generated token first differed at an attention output in decoder block 2 (compiler/interpreter) and block 12 (wind direction). These are zero-based block numbers. Earlier traced activations and the corresponding Q/K/V inputs matched. A third request had a hidden-state difference but kept its greedy output sequence. For R13, the cold cache control matched the reference at every captured layer tap on all four ranks. The seed comparison found a first-layer attention-output difference for some prompts even when the Q/K/V inputs matched. The trace recorded `npu_fused_infer_attention_score_batch_invariant` in the sampled first-layer NPU attention call.

For the R12 compiler prompt, decoder block index 2, TP rank 2, position 896, one of the 1,024 local attention-output elements differed by 0.00006103515625. For R13, comparison of the solo seed with the reference at block index 0, TP rank 3, position 419 for the wind-direction prompt found one element differing by 0.000000059604644775390625. Q, K and V at each witness matched exactly.

Read the hashes of Q, K, V, the attention output, projection and router at the same row in [row-receipts.json](row-receipts.json). The per-rank counts and earliest observed taps are in [layer-summary.json](layer-summary.json). A tap locates a boundary in the traced model; attribution to an internal kernel reduction or a particular CANN tiling strategy would require operator-level replay.

## Greedy token selection

| Round | Prompt | First different generated token | Reference → candidate |
|---|---|---:|---|
| R12 | Describe the difference between a compiler and an interpreter. | 25 | `6` → `1` |
| R12 | Outline a simple experiment to measure wind direction. | 28 | ` so` → ` best` |
| R13 | Describe the difference between a compiler and an interpreter. | 25 | `6` → `1` |
| R13 | Outline a simple experiment to measure wind direction. | 10 | `,` → ` experiment` |
| R13 | Describe how a bicycle gear changes the effort needed to pedal. | 1 | ` **` → ` of` |

[Controls and top-eight post-mask logits](controls.json) retain each matched step before divergent generation histories accumulate. [First-token records](first-token-differences.json) provide token IDs and repeat counts. These results evaluate token equality. The experiment did not score semantic task quality. The R7 total and R12/R13 throughput figures remain those of the original, uninstrumented benchmark.
