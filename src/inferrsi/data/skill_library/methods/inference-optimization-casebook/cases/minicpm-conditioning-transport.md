# MiniCPM-o conditioning transport: avoid scalar-list roundtrips

This is a scoped host diagnostic from [acceptance issue #49](https://github.com/InferMatrixLab/InferRSI/issues/49).
The transport component preserves values and reduces synthetic CPU work.
The campaign remains **INCONCLUSIVE**: this observation does not establish
end-to-end throughput, speech quality or a peer-engine win.

## Observation and measurement limits

Ordinary turn-mode conditioning includes a reference waveform and thinker hidden
states. The bridge converts tensors to Python scalar lists; EngineCore transports
those lists, the worker traverses them, and the Talker constructs tensors again.
In this path the large reference list is also examined element by element by
`_store_value`, although its entries are ordinary numbers.

An initial 100 Hz multi-process GIL profile accumulated 67 seconds of sampling
lag and strongly perturbed serving. It was interrupted and invalidated for
quantitative attribution. A separate CPU-counter run and sparse 2 Hz nonblocking
samples also identified Talker host work, including the same list traversal.
The latter yielded only 35 samples with 8 stack errors: it corroborates a code
location, not its critical-path fraction. CPU counters also include polling,
warmup and client output-saving time. All diagnostic requests were excluded
from performance tables.

## Mechanism and bounded component result

The request's `model_intermediate_buffer` contains untyped values. A raw tensor
cannot rely on vLLM's typed msgpack decoder hook to reconstruct it there.
Replacing lists with raw tensors without a wire roundtrip check is therefore
not sufficient.

The candidate uses the existing Omni tensor serializer to create owned bytes
for ordinary-turn reference audio and hidden states. Consumers restore CPU
float32 tensors, matching the old list-to-float32 conversion. Native duplex
keeps its existing producer representation; legacy lists and local tensors
remain accepted. The change does not alter weights, sampling or acoustic
computation.

A CPU microbenchmark included production, the actual untyped msgpack roundtrip,
worker storage and tensor reconstruction. With a 144,000-sample reference and
32 × 4,096 BF16 hidden states, ten warmups and 100 alternating AB/BA iterations,
with `OMP_NUM_THREADS=4`, median time was 34.53 ms for lists and 0.498 ms for packed transport. Restored
float32 values were bitwise equal. These are synthetic component timings on a
shared host, not a service speedup or a reusable hardware-independent ratio.

Regression checks covered dtype conversion, scalar/empty/noncontiguous inputs,
producer mutation, independent consumer ownership, invalid packed types, both
codec handoff modes and Talker prefill. Empty transposed tensors exposed an
encoder stride constraint; the producer now supplies a canonical empty tensor
before encoding. The complete scoped suite passed 213 tests, with one existing
skip. Pre-commit and commit hooks passed.

## Reuse procedure

1. Inspect both the producer representation and the receiving field's declared
   wire type. Trace conversions through serializers and worker storage, rather
   than assuming a transport supports nested tensors automatically.
2. Treat observer lag as an invalidation signal. Use a separate low-overhead
   diagnostic and a component reproducer before estimating service impact.
3. Reuse an existing serializer and preserve the previous consumer dtype.
   Verify an actual wire roundtrip, empty/noncontiguous inputs and storage
   ownership; a same-process tensor assignment is insufficient.
4. Measure producer, wire, storage and reconstruction together. Alternate
   control/candidate order and keep timing separate from intrusive profiling.
5. Freeze the source, then compare unprofiled services with identical model,
   requests, warmup, concurrency and deployment settings. Evaluate generated
   speech separately before promotion.

## Counter-signals and rollback

Do not add another byte serialization layer when the existing typed transport
already preserves tensor metadata and ownership. Small payloads, compute-bound
serving or already-cached conditioning may show no useful service gain. Runtime
schedule changes can change generated outputs even when transport values are
bitwise equal; component equality does not waive speech gates.

The archived implementation changes only the ordinary-turn producer and its
consumers. Reverting that change restores scalar-list transport without changing
model assets. Any new field type, serializer version or consumer must revalidate
the wire and ownership checks.

## Evidence

- [Frozen experiment, component results and patches](https://github.com/InferMatrixLab/InferRSI/tree/6d9c3f8/evidence/minicpmo45-l20x-20261021).
- [Source implementation](https://github.com/amy-why-3459/vllm-omni/commit/60d71d16e0d77734239935ffc6b991c810ea1aa7).
- The sibling JSON owns source identities and rehashed artifact integrity.
  Service and quality outcomes remain owned by the campaign, not this case.
