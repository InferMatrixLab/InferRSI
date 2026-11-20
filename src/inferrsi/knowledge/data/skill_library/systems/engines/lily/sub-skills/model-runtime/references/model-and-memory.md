# Lily checkpoint, tensor and state contract

## Source boundary

This bounded readset is from `perplexityai/pplx-garden`, subdirectory `lily`,
at revision `1ed972ed3f0bd5616c997c9507c25616c63394fc`. No Rust build, native
test, shader compile, weight load, Metal execution or memory measurement is
implied. The source is Apache-2.0 with its retained MLX/MLX-LM notices; weights
have separate licensing. The generated `NO_LICENSE` field records AREX's
unavailable authenticated-CLI lookup, not an absence of legal source licensing.

## Exact model identity, not a family guess

The wrapper's `model_type` is `qwen3_5_moe`; the runtime name Qwen3.6-35B-A3B
does not change that JSON spelling. Lily reads `text_config` and intentionally
ignores vision weights. The native architecture check requires:

| Area | Required values |
| --- | --- |
| Core | hidden size 2048; 40 layers; vocabulary 248320; untied embeddings |
| Sparse FFN | 256 experts; 8 per token; routed and shared intermediate widths 512 |
| Full attention | 16 query heads; 2 KV heads; head dimension 256; output gate enabled |
| Linear attention | 16 key heads; 32 value heads; key/value dimensions 128; convolution width 4 |
| Layer pattern | Repeated three `linear_attention` layers then one `full_attention`, exactly 40 entries |
| Top-level quantization | required; `bits: 4`, `group_size: 64`, `mode: affine` or omitted/null mode |

The native parser also consumes required RMS epsilon, RoPE parameters, EOS and
other typed fields. A top-level EOS setting overrides the text-config EOS when
present. This skill's helper intentionally screens selected shape/quantization
rules only: a JSON passing it can still fail required-field deserialization,
tokenizer/template, weight, native geometry or runtime checks. No config-only
screen proves it is the benchmark's immutable checkpoint.

## Packed weights and loader checks

Ordinary quantized matrices use `w = scale * q + bias` per 64 input elements.
For logical shape `[out, in]`, Q4 codes are U32 `[out, in/8]`, low element/nibble
first; BF16 scales and additive biases are `[out, in/64]`. A signed symmetric
int4 matrix, a zero-point convention from another library, an AWQ/GPTQ packing,
GGUF blocks or raw BF16 weights are not interchangeable with these triples.

The global Q4 setting has deliberate per-role Q8 exceptions:
`mlp.gate` and `mlp.shared_expert_gate`. The native loader infers bits from
packed width and checks against the expected role. Their code width is
`in/4` U32 words rather than the ordinary Q4 `in/8`; BF16 scale/bias grouping
still uses the configured group size. Mixed precision here is an exact
checkpoint-layout contract, not a newly selectable broad quantization mode.

Expected text names begin with `language_model.model.`; the untied head is
`language_model.lm_head`. Expert stacks flatten expert and output-row axes.
Some projections concatenate gate/up or q/k/v rows into one physical buffer,
then hand out row views. The loader validates expected features/shapes,
quantized-code U32 and BF16 scale/bias types, and records consumed tensor names.
Only explicitly skip-listed `vision_tower.` names can remain unused; arbitrary
extra names trigger a drift error rather than being silently ignored.

The safetensors reader discovers shards from the index or a single file,
rejects duplicate tensor names across shards and reversed data offsets, and
uses exact range reads into caller-sized destinations. Recognizing a header
or index is not payload integrity authentication. Do not claim that the
inspected reader is a complete untrusted-file security validator or that a
digest of a header authenticates complete weights.

## Tensor and Metal ownership

`Tensor` is a reference-counted shared Metal buffer plus shape, dtype and byte
offset. Clone and row views share data. Views must stay within the logical
tensor and start on a four-byte-aligned offset; BF16 views therefore start at
an even element. Kernel binding must use `binding()` rather than assume a
zero offset. Weight cache identity includes base storage plus view offset.

`MetalContext` owns the device/queue and compiled-pipeline cache keyed by
function name and MSL version. It refuses GPU families below 10. MSL sources
compile at runtime, so a Rust binary build is not a shader-compile result.
Shared buffers are zero-initialized by the allocator because Metal fresh
contents are not a model-state reset guarantee.

Serial prefill passes provide order; concurrent decode encoders require
explicit buffer barriers between dependency levels. A pending committed pass
must be waited before reading its output on the host or mutating any buffer
it touches. Decode position increments at encode/submit time, not proof that
the GPU has completed. Retaining a tensor handle protects ownership but does
not by itself establish synchronization.

## Memory ledger and sequence capacity

| Item | Owner/lifetime | Budget implication |
| --- | --- | --- |
| Model weights | Model, with fused-view aliases | Count each backing buffer once, including packed codes, scales and biases |
| GDN recurrent state | Each DecodeState, FP32 `[32,128,128]` per linear layer | Fixed state for 30 linear layers, plus double BF16 convolution windows |
| Full-attention K/V | Each DecodeState, BF16 `[2,max_seq,256]` for K and V per full layer | Linear in selected maximum sequence for 10 full layers |
| Decode scratch | Engine execution scratch, fused output segments are views | Count unique scratch allocations and dequant/routing/attention intermediates |
| Prefill scratch | Scratch-owned, grown on demand in bounded powers of two | Growth drops old buffers first; warm larger prompts can retain larger scratch |
| Cached session state | Session store, not only current request | Two resident cache entries may retain separate DecodeStates; key equality does not merge buffers |
| Host/checkpoint/runtime objects | Host loader and Metal runtime | Tensor payload sums are not total physical/RSS/driver peak memory |

For illustration of the **payload geometry**, full-attention KV alone uses
`10 layers × 2(K,V) × 2 KV heads × max_seq × 256 × 2 bytes` per allocated
DecodeState. GDN state adds
`30 layers × 32 heads × 128 × 128 × 4 bytes`, plus two convolution windows per
linear layer. These are source-derived component formulas, not a capacity
guarantee or a measured peak; no model-weight and scratch bytes are omitted
from an actual fit decision.

Reset requires an idle GPU, clears GDN/conv state and rewinds position; K/V
rows past the reset position need not be cleared because they must never be
read before being overwritten. Preserve this frontier invariant during reuse.

`--max-seq` is not output tokens alone. Server load clamps it to a smaller
nonzero `max_position_embeddings`; zero means no checkpoint-declared clamp.
The effective value must be at least two for serving and must satisfy the
262144-token kernel limit. Request validation uses rendered/tokenized prompt
length plus `max_tokens` **plus one** extra slot, with checked arithmetic.
Do not use character count, omit template overhead, or fill the whole ceiling
with prompt plus output and assume equality is accepted.

## Bounded readset

- `README.md:1-23,70-84`: supported checkpoint/platform and high-level capacity.
- `Cargo.toml:1-8,47-52`, `rust-toolchain.toml`, `src/lib.rs:8-33`: compiler and macOS gates.
- `src/config.rs:17-30,54-111,114-197`: native configuration and exact shape.
- `src/weights.rs:22-82,85-112,163-224,276-321,324-425,539-586`: packing, roles, loader and drift checks.
- `src/safetensors.rs:11-24,81-114,135-163,167-205`: index/header/read boundaries.
- `src/tensor.rs:26-77,80-127,173-203`: aliases, views, offset identity and idle-GPU contract.
- `src/metal.rs:76-175,208-242,275-345,378-390`: native family gate, pipeline/buffer and pass ownership.
- `src/model.rs:35-43,100-185,199-233,505-577,660-713`: model/state/scratch and encode frontiers.
- `src/serve.rs:41-46,144-160,179-191`, `src/kernels/attention.rs:10`, `src/kernels/gdn.rs:18`: sequence/kernel/state rules.
- `tests/unit/weights.rs:1-32`, `tests/unit/serve.rs:27-30`: role-bit and extra-token assertions, read not executed.
- `NOTICE:1-69`: source and MLX/MLX-LM attribution, not weight-license permission.
