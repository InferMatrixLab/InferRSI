# MRv2 MTP batch observer — source-only design

Scope UNTESTED; no implementation, GPU job or active-file change. Source HEAD4645c450ba4ed036433a30dfcb9782f22b0c3bfd. Paths below relative to vllm-omni.

## Exact observation points

`worker_v2/omni_ar_model_runner.py:221–228` invokes model_state.run_eager_mtp after sampled outputs. The state forwards to eager_mtp.py; fused path at572–575 calls owner._mtp_forward with batch.slots and batch.req_ids, fallback at414 calls the same method without cached IDs. Legacy batched path omni_model_state.py1165 also calls it. Therefore `_mtp_forward` is a shared CPU dispatch boundary, unlike a model.forward hook.

In `worker_v2/model_states/omni_model_state.py:1218–1260`, bsz=len(req_indices). A cached direct-replay branch reads `_mtp_replays[bsz]`, obtains `(num_tokens,entry)`, fills uniforms and invokes `entry.cudagraph.replay()` then returns. It bypasses model.forward, the descriptor dispatcher and wrapper sampling call. An observer only on any of those downstream functions misses steady-state work.

The generic branch1268–1313 resolves the actual descriptor, graph mode and num_tokens (padded capacity), then invokes the sampling wrapper. `worker_v2/omni_model_runner.py:502–521` chooses the smallest capture size >=actual count within max_num_seqs, else modeNONE. Record its returned descriptor; do not recompute a presumed bucket independently. Cached branch must record the already-resolved num_tokens before replay. Prefer exactly one dispatch record per _mtp_forward, emitted immediately before its selected replay/wrapper invocation.

## Minimal opt-in CPU record

A disabled-by-default private observer with bounded preallocated/ring storage can record:

- local monotonically increasing invocation sequence, stage logical label, `time.monotonic_ns()` at CPU dispatch;
- branch `{direct_cached_replay, descriptor_wrapper, wrapper_no_descriptor}`;
- `scheduled_mtp_rows=bsz`, `execution_rows=num_tokens`, descriptor graph mode;
- `padding_rows=num_tokens-bsz` when nonnegative; `graph_bucket` only if actual graph mode isFULL, otherwise null;
- capture/warmup/measurement phase marker supplied by harness, and dropped-record count.

No request IDs, slots, PIDs, physical GPU selectors or tensor data. No tensor.item/cpu/numpy, no CUDA event, no synchronization, no per-call logging/file writes, no extra dispatcher/RNG calls. Flush bounded records after the measurement window or process exit. Monotonic collection still introduces CPU overhead and must remain diagnostic, separately compared with observer-disabled behavior. Capture-time callbacks must be excluded/tagged so Python graph construction is not miscounted as actual replay. Preserve counters even when detailed ring fills, with explicit drop evidence.

## “Effective valid rows” is not equal to scheduled rows

The fused eager post kernel (`eager_mtp_kernels.py:108–110`) defines validity from sampled layer0 token vocabulary range and input-token validity or prefill. These values are GPU tensors. Some scheduled rows can be EOS/invalid even though predictor ran. CPU bsz excludes graph padding but does not prove that all those rows produce a valid audio frame.

A zero-sync CPU observer cannot directly obtain exact per-call effective-valid count from this code boundary. First version must emit `effective_valid_rows=null` plus “not observed”, while retaining scheduled rows and padding. If required later, reuse the existing completed asynchronous output-to-CPU path (`omni_ar_model_runner.py` around605/887) to count codec_frame_valid after its normal readiness wait, joining by a private invocation sequence, not request identity. This needs a verified one-to-one output mapping before implementation; don't add a new D2H copy or wait merely for logging. Completion timestamp is different from dispatch timestamp. GPU-side observer reductions are outside this CPU-only design.

## Outputs and interpretation

Produce count-weighted histograms of(actual scheduled rows,execution bucket,branch), total scheduled/padded rows and padding ratio. Report invalid-row histogram separately only if the optional completed-output mapping is validated. Distinguish per-invocation averages from time-weighted and audio-frame-weighted measures; none are interchangeable. Batch evolution can reveal overpadding or small-batch scheduling despite clientC64, but cannot by itself determine whether Thinker supply, queues, stream dependencies or CPU launch overhead is causal.

CPU inter-dispatch intervals are not GPU idle time: kernels execute asynchronously and other stages share the GPU. Profile envelopes likewise do not show removable gaps. Clock alignment would require monotonic/perf/epoch bridging with uncertainty and stage/device mapping; do not infer it from sequence order alone. No throughput/RTF speedup claim or scheduler change follows from the histogram.

## CPU test plan before any observer run

Fake dispatcher/graph entries should verify one record for direct replay and generic paths, no extra dispatcher calls in direct replay, correct actual/bucket distinction, eager NONE has nullbucket, capture tagging, no IDs in serialized schema, overflow/drop accounting and unchanged method return values. <GPU_UUID>ree AST/mock tests cannot validate async output joins or actual runtime overhead; those remain explicit later checks.
