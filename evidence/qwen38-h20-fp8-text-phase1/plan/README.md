# FP8 text engine and service preparation

[Acceptance #57](https://github.com/InferMatrixLab/InferRSI/issues/57) owns this
separate FP8 campaign under [parent #53](https://github.com/InferMatrixLab/InferRSI/issues/53).
The historical BF16 preparation and evidence remain in their existing tree.

Status: preparation only; INCONCLUSIVE. The workload is proposed, not frozen.
Authenticate the official Qwen/Qwen3.8-27B-FP8 checkpoint at `<model_revision>`.
Freeze its byte manifest, this workload, control/baseline/candidate revisions,
registered environment lock, exact GPU, validator sources, gates and budget in
the acceptance issue before any candidate experiment. No pins or numerical
gates are supplied by this template.

The checkpoint uses dynamic e4m3 FP8 linear weights with 128 by 128 blocks and
BF16 activations; unquantized layers remain BF16. Reference and candidate must
retain and execute FP8 weights. Whole-checkpoint BF16 dequantization is excluded.
The reference additionally requires an immutable kernel-registry revision and
trusted source fingerprint for the prepared torch-cuda build of
kernels-community/finegrained-fp8, with offline caches and DeepGEMM disabled.

The bounded `native_text_smoke` compares full-prefix Transformers teacher forcing
with the native hybrid-state engine through the common correctness loop.

The accepted phase-1 scope also includes the public engine entrypoint and a
loopback-default HTTP text-completion service with non-streaming and SSE output.
The service supports a documented greedy-generation subset. Unsupported fields
and values must fail explicitly. Model calls may serialize while independent
requests interleave; concurrency support is not a throughput claim.

The separate `native_service_functional` qualification compares public native
serial generation with HTTP/SSE serial and concurrent output. It must cover
normal completion, EOS and token limits, explicit cancellation, client disconnect,
malformed and over-limit requests, execution errors, shutdown and subsequent
reuse. Cancellation is cooperative at model-call boundaries. Every terminal path
must release request-owned KV, convolution and recurrent state and admission
capacity without affecting another request.

Record ordered output tokens and SSE events, request IDs, terminal reasons,
overlapping admissions, state ownership, capacity and owned-process cleanup.
Logical request-state bytes are distinct from allocator-reserved GPU memory.
Freeze the service workload, protocol, source identities, admission limits and
all readiness/request/release/shutdown deadlines before candidate execution.

CPU fake-engine socket tests establish protocol coverage only. Final service
qualification requires the real FP8 model and real HTTP sockets, separately from
the reference numerical comparison. Missing required coverage is INCONCLUSIVE.
Phase 1 includes L4 functional service evidence, with no performance gain,
broad task-quality, continuous batching, stochastic sampling, vision, MTP or
multi-GPU acceptance claim.
