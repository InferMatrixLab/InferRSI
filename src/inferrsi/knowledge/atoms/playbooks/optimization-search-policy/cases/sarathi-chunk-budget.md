# Sarathi-Serve: choosing a chunked-prefill token budget

This is an attributed, source-derived candidate decision example, not an
observed InferRSI incident. Its edition, source digest, readset and limitations
are in the [case record](sarathi-chunk-budget.json). The source is Agrawal et al.,
*Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve*,
[OSDI 2024 proceedings](https://www.usenix.org/system/files/osdi24-agrawal.pdf),
with the [publisher entry](https://www.usenix.org/conference/osdi24/presentation/agrawal).

## Trigger and source observation

Consider this mechanism when traces show that long prefills interrupt ongoing
token generation. Prefill processes a request's input tokens; decode generates
subsequent tokens. Time between tokens (TBT) measures the gap during generation,
whereas time to first token (TTFT) includes the wait before the first output.
A queue, memory shortage or suspended-request problem needs its own diagnosis
before attributing the delay to prefill interference.

In §§4.1–4.2, Sarathi-Serve splits a prefill across iterations and combines its
chunks with ongoing decodes. The source's scheduling order is:

1. Account for ongoing decodes first, at one token per decoding request.
2. Include partially completed prefills within the remaining token budget.
3. Admit new requests only when allocation permits and budget remains; size
   their prefill chunks to that remainder.

The budget covers the mixed batch, not just newly admitted prefill tokens.
Chunking limits prefill work in an iteration; it does not make that work free.
Figure 9 still shows added batch latency relative to decode-only execution.
The paper's algorithm describes this policy; its pseudocode is not a contract
for any current engine implementation.

## Decision and costs

Treat the budget as a deployment-specific candidate parameter. Section 4.3
balances a tighter TBT target against several costs:

- Smaller chunks reduce prefill work per iteration, but can lower compute
  utilization and repeat fixed launch costs.
- Each later chunk attends to earlier chunks of the same prompt, rereading
  their KV cache. The paper distinguishes these additional memory reads from
  unchanged attention computation.
- Matrix tile boundaries affect execution cost. Neighboring token counts need
  not have neighboring runtimes.
- With pipeline parallelism, differences between batch runtimes can leave
  stages idle. Larger chunks can increase that variation; excessively small
  chunks incur their own efficiency costs.

The paper uses profiling and Vidur to select a capacity-maximizing budget for
a specified hardware, parallelism and TBT objective. This does not establish a
universal chunk size or turn a simulator prediction into a measured result.
Figure 14's prefill-overhead study is specific to Yi-34B with tensor parallelism
across two GPUs, prompts of 2K/4K/8K tokens and chunks of 512/1024/2048 tokens.
Its normalization is unchunked prefill runtime, not end-to-end service time.

## What the reported comparison establishes

Table 4 evaluates 128 requests for Yi-34B on two A100 GPUs, with a token budget
of 1024, separately for `openchat_sharegpt4` and `arxiv_summarization`. In both
traces, the combined design has lower P99 TBT than either component alone. Its
P50 TTFT is lower than chunked-prefills-only, but higher than hybrid-batching-only.
Thus the combined design trades some first-token latency against tighter token
gaps; it does not improve every metric over each alternative.

Section 5 generates arrival times with a Poisson distribution and filters total
request lengths above 8192 and 16384 tokens for the two traces, respectively.
The capacity experiments also require median scheduling delay to stay within
2 seconds alongside the model-specific P99 TBT objective. Preserve those load,
queueing and percentile definitions when interpreting the reported capacity;
Table 4 alone is not a capacity or fairness result.

## Proposed adaptation and rejection conditions

Before a separately authorized experiment, establish a matched workload,
model, hardware, engine revision, parallelism, memory limits and latency
objectives. Use the existing admission and preemption owners to distinguish
capacity limits from decode interruption, and the calibration owner to qualify
profiling or simulator estimates. This case adds no scheduler implementation.

Compare bounded budget candidates while holding those conditions fixed. Record
P99 TBT, P50 TTFT, queueing/scheduling delay, sustainable throughput, prefill
runtime and any relevant pipeline idle time separately. A lower TBT with an
unacceptable TTFT or queueing cost rejects that candidate under the frozen
objectives. If traces do not support prefill interference, or required evidence
is unavailable, retain the incumbent and the unresolved diagnosis. These are
proposed checks, not results from this host.

No current-engine compatibility, local speedup, fairness guarantee or empirical
skill efficacy is established. Section 6 leaves quantitative comparison with
prefill/decode disaggregation open. Raw paper assets and the missing historical
supplier synthesis are not part of this case; their redistribution rights are
not inferred from public readability.
