# Recurrence and carried-state ownership

This distillation uses the inspected
[GatedDelta.swift](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/GatedDelta.swift)
and selected callers/tests. Source comments describe upstream observations; no
Swift compiler, MLX backend or native test was executed for this candidate.

## Public entry versus fused kernel

`gatedDeltaUpdate` computes beta as `sigmoid(b)` converted to FP32. Its compiled,
shapeless decay expression is `exp(-exp(aLog.float32) * softplus(a + dtBias))`.
The source comment says compilation preserves per-node dtype rounding; retain
that as an upstream claim rather than a new local bitwise result. Removing
intermediate dtype behavior based only on real-number algebra is not justified.

The public entry defaults state to FP32 zeros shaped `[B,Hv,Dv,Dk]` and casts
an explicitly supplied non-FP32 state to FP32. The literal fused-kernel gate is
`useKernel`, availability of the **unmasked** kernel and `Dk % 32 == 0`.
Otherwise it calls the MLX ops path. The gate is not a complete input validator.
Its source order checks manager availability before the Dk remainder, so a
tail-driven ops result does not establish that kernel-manager initialization
was avoided. The bundled helper does not model initialization or lazy effects.
See [public entry](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/GatedDelta.swift#L340-L383).

The kernel receives Q/K `[B,T,Hk,Dk]`, V `[B,T,Hv,Dv]`, gate/beta `[B,T,Hv]`
and state `[B,Hv,Dv,Dk]`. Each value head maps to a key head through
`hv_index / (Hv/Hk)`. The selected Qwen model constructors enforce divisible
head counts; direct helper calls do not acquire those constructor checks.
Launch geometry is grid `(32,Dv,B*Hv)`, thread group `(32,4,1)`. Y uses Q's
dtype and state output uses the supplied effective state dtype (FP32 through
the public entry).

The fused loop distributes `Dk/32` elements per SIMD lane using integer division.
Calling the lower-level kernel directly with Dk=48 would cover only 32 dimensions;
the public entry therefore routes nonmultiples to ops. This is a source-tail
contract, not a restriction that all Dk must be powers of two, or evidence that
every positive multiple compiles and fits the device's resources.

State is FP32 inside the fused loop. Decay first scales each state element; the
K-state dot uses per-lane compensated Kahan summation with reassociation and
contraction disabled, then a SIMD sum. Delta is `(v-dot)*beta`; state is updated
by `k*delta`, then contracted with Q to form Y. Arithmetic order and compensation
are material: a real-arithmetic rearrangement can drop low-order terms. See
[kernel body and launch](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/GatedDelta.swift#L29-L186).

## Ops, gradients and precision boundaries

Ops repeats Q/K heads by `Hv/Hk` when needed, performs the recurrence using MLX
operations and casts Y back to Q dtype. It is still an MLX execution path; the
term “ops fallback” does **not** establish a CPU-only engine.

It processes the sequence in recompute chunks of 16 through a `CustomFunction`
with VJP. The backward pass recomputes chunk work instead of retaining every
per-token state; boundary state is carried between chunks. The source comments
describe memory motivation, not a universal peak-memory bound or measured model
fit. Forward order is preserved within the ops formulation. The custom fused
Metal kernel has no gradient, so selected model callers pass `useKernel:
!training`. Do not depend on an incidental unsupported-Dk fallback to make a
training path differentiable. See
[ops/recompute implementation](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/GatedDelta.swift#L191-L335).

One carried FP32 state contains `B*Hv*Dv*Dk*4` payload bytes, independent of T.
That excludes convolution state, live inputs/outputs, copies, gradients,
recompute boundaries, allocator rounding and model weights. A caller retaining
old states/checkpoints can keep additional memory alive. Upcasting BF16 state
after it was rounded does not restore the information lost at the prior boundary.

## Mask and stride limits

With a false `[B,T]` mask step, the fused masked kernel skips the update, emits
zero Y and later writes the retained state. The ops step computes candidate
state and Y, then uses `where(mask,candidate_state,old_state)` on **state only**;
it returns that already computed Y. The inspected core parity tests do not test
masked outputs. Preserve this source-only asymmetry as an unexecuted parity gap,
not an asserted numerical failure or established user-visible model bug. Some
callers may ignore masked positions; that does not prove generic equivalence.

Masked/unmasked kernel objects are created separately. The public gate tests
the unmasked object; the lower-level wrapper selects the masked object when a
mask exists, then `fatalError`s if that selected object is nil. Do not merge
the two availability facts in a plan or claim that every missing masked kernel
will automatically fall back. This is source control-flow reasoning, not an
observed device failure.

The kernel body uses contiguous pointer arithmetic with no explicit stride
arguments. The wrapper passes MLX arrays, including slices used by callers.
Packing/row-contiguity behavior belongs to the `MLXFast.metalKernel` dependency
contract, not established by this source snapshot alone. Do not claim arbitrary
strides are supported, or that a strided caller is a confirmed bug, without
inspecting and testing the matched dependency and actual bytes. The helper does
not read tensors or convert views. Relevant source spans are
[mask branch](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/GatedDelta.swift#L61-L106)
and [ops state mask](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/GatedDelta.swift#L200-L230).

## Caller normalization and paired checkpoints

Selected Qwen35/Qwen3Next callers use low-precision convolution state matching
inputs, but zero recurrent state in FP32. They reshape Q/K/V to the recurrence
contract and require `Hv % Hk == 0` at construction. Their Q/K normalization
matches L2 sum epsilon `1e-6` by applying RMS mean epsilon `1e-6/Dk`; Q and K
have distinct scale factors. Substituting unadjusted RMS epsilon changes behavior
near zero. See [Qwen35 caller](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLLM/Models/Qwen35.swift#L347-L487)
and [Qwen3Next caller](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLLM/Models/Qwen3Next.swift#L241-L334).

Qwen35 can split at an internal speculative checkpoint. It runs prefix then
suffix with the prefix recurrent state, concatenates outputs and saves both
prefix convolution state and recurrent state. The cache stores final conv/rec
state and advances by input token count. `MambaCache` checkpoint restore replaces
the saved pair plus offset, padding and lengths, then consumes the checkpoint.
This is not arbitrary tokenwise trimming of recurrent history. See
[checkpoint producer](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLLM/Models/Qwen35.swift#L433-L470)
and [checkpoint owner](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/KVCache.swift#L1795-L1857).
Restoring one tensor while retaining incompatible conv/position metadata can
create a different computation; native checkpoint/model evidence remains needed.
