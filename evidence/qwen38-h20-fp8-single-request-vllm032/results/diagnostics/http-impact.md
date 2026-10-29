# HTTP impact of the bounded publication repair

Acceptance: https://github.com/InferMatrixLab/InferRSI/issues/67
Campaign verdict: **INCONCLUSIVE**. This is a completed readiness comparison,
not the final benchmark or task-quality evaluation.

Baseline engine: `83b567c1b07d9a230f6a8ca8bff979144d719241`.
Publication candidate: `3e8636f04378ef7d316272f2051315515a9ac6b9`.
Commit `84eaffd` validates FP8 selection and discloses actual dispatch/counter
scope; commit `3e8636f` preserves initial-prefill operands with reserved KV.
These commits were tested together. The measurement does not estimate an
independent incremental speed effect for the provenance-only change.

The publication branch was reconstructed from main to exclude legacy HTTP API
changes and tolerance adjustments. Model, quant, graph, runner and engine bytes
match the previously reviewed implementation; server and model-test definitions
differ. Earlier HTTP/CPU totals therefore cannot substitute for this run.

## Observations

Job 1943 completed with exit 0 in 144 allocated GPU seconds (0.04 GPU-hours).
Each of three service arms returned 16 tokens for all six requests, with valid
terminal framing, no active request/state left after each request, and graceful
process exit 0 without forced kills. All GPU resources were released.

Original-main Graph differs from repaired eager in both repetitions of case783
(4/6 request outputs equal). Repaired Graph matches repaired eager exactly in
all six 16-token sequences, including pooled Graph reuse. This repairs the
observed short-output mismatch. It does not prove general Graph correctness;
the earlier diagnostic still records 13/48 nonidentical compact/fixed decode
logits, and long generation, bucket transition and task accuracy remain untested.

All 18 raw request samples are retained in http-readiness.jsonl and exported
without exclusions in http-timings.csv. Descriptive per-request ranges for
original Graph -> repaired Graph are:

| Measurement | Original Graph | Repaired Graph | Paired candidate/base range |
| --- | --- | --- | --- |
| Token-event TTFT | 1.2381–2.6922 s | 1.2305–2.6411 s | 0.9575–1.0166 |
| Token-event TPOT | 87.984–88.228 ms | 87.438–87.670 ms | 0.9931–0.9959 |
| Complete HTTP latency | 2.5616–4.0132 s | 2.5457–3.9535 s | See all six pairs in http-summary.json |

These small changes are **not established acceleration**: fixed engine order,
only two repetitions, short prompts/caps, cache and first-use effects, and a
different output sequence on the failing base case limit attribution. Startup
was 41.70 / 23.86 / 13.44 seconds for original Graph / repaired Graph / eager;
shared compilation caches make those startup figures noncomparable.
The observer's token-ID event clock differs from official benchmark semantics.
No vLLM service ran in this probe. The main HTTP server still rejects
ignore_eos, return_token_ids and stream_options; that prerequisite is tracked
separately and is not hidden by the passing short-response check.

## Checks and retained failures

Exact publication-head full Qwen CPU job 1944: **155 passed, 1 skipped, 1 failed**.
The failed production-head BF16 recurrent-state assertion reports 12/49,152
elements, maximum absolute difference 1.5277801139745861e-6 against atol1e-6.
Unmodified-main targeted job 1945 reproduces exactly the same failure and has
one passing FP32 variant. No tolerance was relaxed and the suite is not green.
New prefill/backend tests passed. The skipped test needs the separately gated
GPU contract environment. Local runner/service/entry tests: 58 passed.

Raw CPU logs remain in controlled storage; their digests and exact counts are
in http-summary.json. Independent reviewer review_fp8_graph found no introduced
blocker and confirmed this inherited failure does not alone block the bounded
repair; actual required repository checks must still be satisfied.

Budget: the new 44 GPU-hour ceiling has consumed 0.04 GPU-hours in readiness;
1.96 of the 2 readiness GPU-hours remain. Earlier 147 GPU seconds belong to the
separately approved diagnostic allowance. Search and finalization are unused.
