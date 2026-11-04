# Hybrid Graph boundary repair: HTTP impact

Refs InferRSI Issue #67. **Campaign INCONCLUSIVE.**

Candidate80e5108e44c43f3f54fabb5723e6154d18088516 builds on
7ec5d224e983e437530355b94b0d6d08153bc27d. The rebase changes only the separately
reviewed readiness test; all runtime bytes equal previously reviewed e69035d.
The model patch only distinguishes real KV from linear state during demotion.

Job1955 completed10/10 requests with exact usage, healthy terminal framing and
no remaining request state. Both owned processes exited0 without forced kill.
The previous876-token boundary error now completes1024 output tokens; the next
16-token request succeeds. All1951 observed Graph prefixes remain identical.

Full Graph/eager sequences match3/5 pairs. Case783 first differs at zero-based
index81 in both natural-EOS and forced1024-token variants, before demotion.
NaturalEOS output lengths differ529 vs503. This is retained unresolved numerical
evidence. Neither request success nor these timings establishes full numerical,
quality, long-context or vLLM parity qualification.

## Descriptive HTTP observations

Official pinned client with response recording; fixed Graph-then-eager order,
short inputs, no matched vLLM baseline. The table records actual per-request
latency, not a causal speedup estimate. Different naturalEOS outputs further
preclude equal-work latency comparisons. Full tokens/ITLs are in the JSONL.

| Arm | Case | Output policy | Tokens | TTFT (s) | Latency (s) | TPOT (ms) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| graph | gsm8k/test/783 | naturalEOS | 529 | 2.672960 | 49.137462 | 88.000951 |
| graph | gsm8k/test/1 | naturalEOS | 169 | 1.300144 | 16.004033 | 87.523149 |
| graph | gsm8k/test/424 | naturalEOS | 314 | 1.925834 | 29.317723 | 87.514019 |
| graph | gsm8k/test/783 | ignoreEOS/1024 | 1024 | 2.546314 | 92.730485 | 88.156570 |
| graph | gsm8k/test/783 | ignoreEOS/16 | 16 | 2.712920 | 4.026041 | 87.541409 |
| eager | gsm8k/test/783 | naturalEOS | 503 | 3.526064 | 49.761498 | 92.102459 |
| eager | gsm8k/test/1 | naturalEOS | 169 | 1.255985 | 16.675945 | 91.785477 |
| eager | gsm8k/test/424 | naturalEOS | 314 | 1.880406 | 30.637043 | 91.874239 |
| eager | gsm8k/test/783 | ignoreEOS/1024 | 1024 | 2.543291 | 96.650859 | 91.991758 |
| eager | gsm8k/test/783 | ignoreEOS/16 | 16 | 2.546986 | 3.927188 | 92.013462 |

GPU allocation464 seconds; readiness total839 seconds, of approved7200 seconds
(total campaign ceiling44 GPU-hours). Initial147 seconds remain separate.
1952/1953 preflight failures and1954 CPU repair are retained in demotion-preflight.
Combined74 local tests passed; no full numerical suite rerun is claimed.

KnowledgeStore (candidate state, verified readback):
case.qwen38-hybrid-graph-demotion-cand at sha256:48e720c89ca6cf511186b36a83a76ce236d6adcb99d7f3138d444191c671db49.

Source-only upstream research is also retained under
store:case.qwen38-vllm032-upstream-dispatch-cand at
sha256:6824c5489a6775534e00163405d7e9228891bf709c7af14d7623f50554fa6a89.
It distinguishes FlashInfer/DeepGEMM and GDN eligibility from measured dispatch.
The current unchunked attention materializes a192-GiB BF16 score tensor at64K
(24 heads), before FP32 softmax and weights. This is a static memory bound,
not a GPU measurement; no64K/128K candidate request has been run here.

## Integration

Independent reviewer Codex review_fp8_graph verified all10 raw SSE streams,
source/observer hashes and cleanup against base7ec5d224e983e437530355b94b0d6d08153bc27d
and head80e5108e44c43f3f54fabb5723e6154d18088516. No introduced blocking finding;
GPU conditions for this limited boundary repair are satisfied. The reviewer
explicitly retained pre-boundary numerical divergence and INCONCLUSIVE.
Engine PR9 merged as3e918df2dd7b478d3d2985350bb5efb523ea4981 under the owner's
review/integration delegation. Fetched main tree exactly matches tested head.
No governing acceptance Issue was closed.
