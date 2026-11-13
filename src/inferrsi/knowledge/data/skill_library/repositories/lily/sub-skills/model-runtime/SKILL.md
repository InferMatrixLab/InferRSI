---
name: model-runtime
description: "Screen Lily's exact Qwen3.6-35B-A3B MLX affine checkpoint contract and audit packed weights, Metal tensor views, per-session state and sequence capacity without claiming native execution."
license: NO_LICENSE
metadata:
  disco-role: operating
disable-model-invocation: true
---

# Lily model and runtime

Use this route for checkpoint compatibility, same-bit-width layout confusion,
loader errors, tensor-view changes, sequence-capacity questions and memory
ownership. Lily is not a generic Qwen or GGUF runner: the inspected engine
targets one exact Qwen3.6-35B-A3B architecture converted to MLX affine Q4,
group size 64, with specific Q8 router/gate exceptions.

Native execution needs Rust 1.92/Cargo and the locked dependency set, macOS 26
or later and Apple GPU family 10 (M5 or newer), plus compatible actual weights.
Non-macOS `cfg` gates expose some pure modules; they are not a CPU inference
backend. Python screening does not satisfy a missing Rust compiler or Metal
runtime. Required backend/compiler gaps remain explicit.

## Establish identity and representation

Record source revision, exact checkpoint bytes/revision, text configuration,
tensor names/shapes/dtypes, quantization group/mode/packing, requested maximum
sequence, actual tokenized workload, platform and compiler/runtime versions.
Read [model and memory](references/model-and-memory.md) for the full bundled
contract and [troubleshooting](references/troubleshooting.md) before changing
formats or lifetimes.

## Procedure

1. **Screen the exact shape.** Require the supported wrapper model type,
   dimensions, expert counts and 40-layer attention pattern. The top-level
   quantization is required; absent mode defaults to affine, but a non-affine
   mode, non-Q4 bits or group size other than 64 is rejected. An offline first
   screen is available in [screen_config.py](scripts/screen_config.py); its
   successful result is deliberately only `passed_selected_rules`.
2. **Verify actual tensor representation.** Ordinary projections and embedding
   use low-element-first packed U32 codes with BF16 scales and additive biases.
   The router and shared-expert gate require Q8 storage, inferred from packed
   width. Do not rewrite those to Q4 to match the global config. Native loading
   checks expected names, role-specific dimensions and consumed tensors; config
   screening cannot establish those facts.
3. **Separate loading from execution.** Shard/header discovery and range reads
   are followed by native dtype/layout and shape checks. Weight bytes are read
   into shared-storage Metal buffers, not proven usable by a file-size match.
   A skipped vision tower is not an implemented multimodal path. Preserve
   missing, unsupported and unconsumed-tensor failures instead of hiding them.
4. **Account unique allocations and views.** A cloned Tensor or fused-weight
   row view shares storage, with a byte offset. Bind `(buffer, offset)` and
   preserve four-byte view alignment; a bare buffer identity can collide across
   distinct weights. Do not sum view handles as full allocations or assume
   shared storage permits concurrent host writes.
5. **Preserve command ownership.** Concurrent decode dispatches require explicit
   dependency barriers; committed pending passes must finish before host reads,
   resets or overwrites touching their buffers. State position can advance at
   encoding before GPU completion. Idle-GPU assumptions are part of correctness,
   not optional measurement overhead.
6. **Budget state plus scratch, not weights alone.** Each decode state has GDN
   recurrent FP32 state and double BF16 convolution windows, plus full-attention
   BF16 K/V sized by maximum sequence. Scratch has fused views and prefill
   buffers grown on demand. Count cached session states and physical allocation
   overlap, not just active requests or checkpoint size.
7. **Respect sequence semantics.** The server clamps its requested ceiling to a
   smaller nonzero checkpoint window. The kernel ceiling still applies. A
   request is checked using actual rendered prompt tokens plus `max_tokens`
   **plus one** extra slot, with overflow rejection. Character counts and a
   nominal prompt-plus-output total are insufficient.

## Safe offline screening

From this sub-skill directory, with a small public JSON configuration:

```sh
python scripts/screen_config.py --config <CONFIG_JSON> --max-seq 4096
```

The helper reads only that JSON file and prints selected-rule findings. It
does not read weights, import an engine, compile Rust/MSL, allocate device memory,
verify tokenization or calculate a safe physical-memory budget. Its explicit
unchecked list remains part of every result; do not shorten it to “compatible.”

Stop at shape/layout mismatch, missing source bytes, a sequence exceeding the
effective ceiling, unsafe buffer lifetime, unavailable native resources or the
authorized task boundary. A candidate, header screen or installed knowledge read
does not qualify model quality, memory fit, performance or service behavior.
