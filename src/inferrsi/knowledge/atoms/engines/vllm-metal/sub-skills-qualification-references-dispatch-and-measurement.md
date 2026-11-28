# Executed attention and serving measurement

## Selection is not execution

The default GQA decode planner counts complete partitions independently per
request: `Q * sum(floor(L_i/P)) >= 33*C`, trying P512 then P256. `L_i` is
post-append KV length, not the longest request repeated across the batch.
For example `[1,10752]` with Q32 and C40 admits P256, not P512.
The empirical policy budget is not a hardware identity or portable gain gate.

Geometry is bounded to `(Q,KV,head)=(32,8,128),(24,4,256),(16,2,128),(16,2,256)`
with kernel block16 and head256 also block32. A measured 10-core M3 policy
narrows a six-request short head128 batch and may prefer P256 over P512 for
long head256 work, subject to reducer resource bounds. Do not generalize this
calibration to all devices or replicate the policy as an inference benchmark.

Real dispatch additionally checks ordinary single-query decode rows,
verification-window≤1, FP16/BF16 matching cache/query types, supported kernel
pages, positive core count, reducer allocation and scratch. Default GQA excludes
TurboQuant, sinks, soft capping and sliding windows. The disable switch can
force fallback, never force eligibility. Shader availability and ABI control
capabilities are separate from default production admission.

Mixed prefill/decode uses only the decode-prefix plan and its actual lengths;
the long prefill must not admit a short decode. A per-forward immutable CPU
length plan is retained for lazy execution. Kernel page size after cache
translation is not always the upstream scheduler page size. Actual lengths and
allocation upper bounds both matter to reducer/scratch checks.

An authorized native route check enables diagnostics in the worker while MLX
evaluation is idle, evaluates the operation, reads family/partition/request
count, synchronizes and restores the prior diagnostic state. Last-dispatch
getters are process-wide and reset on toggles; they are not concurrent request
traces. A selector query, simulated architecture, or enabling recording only in
the client cannot prove which worker kernel ran. Native numerical parity and
dispatch must both be observed before reporting supported-path coverage.

## A controlled experiment, not a fastest-run anecdote

1. Choose kernel, offline-generation or real HTTP-service scope first. Keep
   `VLLM_ENABLE_V1_MULTIPROCESSING`, executor, server limits and client concurrency
   explicit. Offline `LLM(...)` does not by itself identify process topology.
2. Freeze model/tokenizer bytes, quantization, prompts/token IDs, output lengths,
   cache dtype and prefix policy, context/dispatch lengths, chunking, sampling
   and concurrency. Pin target and draft revisions independently.
3. Separate load/compile/readiness/warmup from measured work. Warm each arm with
   the actual workload; repeat alternating/randomized arms with identical
   power mode, background load, memory pressure and cleanup controls.
4. Record actual completed/failed request counts and token counts, TTFT/TPOT/
   E2E definitions and distributions. HTTP headers are not the first token;
   chunks may contain multiple tokens. Do not infer token count from text.
5. Observe worker-side dispatch separately and consistently. Profiler captures
   perturb timings; keep expensive capture outside throughput windows.
6. Retain raw records, noisy/order-sensitive/regressing samples and all missing
   evidence. No thermal warning does not prove stable clocks. Missing platform
   utilization output is unavailable, not zero and not absence of contention.
7. Compare model quality independently. Close attention outputs, greedy token
   agreement on selected prompts, high acceptance or throughput alone do not
   establish broad model-quality or E2E service acceptance.

No engine/server command is automatically authorized by this procedure. Use a
separately approved compatible Apple host, already authenticated local assets
and bounded workload before any execution. The bundled summarizer only checks
record syntax/accounting and does not run this protocol.

Sources: [GQA routing and validation](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/docs/gqa-decode.md),
[planner implementation](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/metal/paged_attention.cpp#L1-L185),
and [macOS benchmark controls](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/docs/benchmarking-macos.md).
