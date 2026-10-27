---
name: kernel-writing-guide
description: 'Decision guide for writing custom inference kernels: when to write one, which framework to choose (Triton, CuTe DSL, CUDA C++, AscendC/TileIR), universal correctness rules that apply regardless of framework, and the verify-before-benchmark workflow. Use before starting any kernel implementation to avoid common correctness and performance pitfalls.

  '
---

# Kernel Writing Guide

Status: candidate. Source-grounded from TensorRT-LLM `kernel-triton-writing`
and `kernel-cute-writing` skills @ f33e0e5f (NVIDIA/Apache-2.0). NPU-specific
content inferred from architecture parallels; verify against CANN/TileIR docs.

## SearchSpace mapping

Accelerator row → Optimize cell

Second-level targets: Kernel fusion, custom GEMM, attention variants, elementwise
chains, reduction kernels.

## When to write a custom kernel

Writing a kernel is expensive. Verify the bottleneck before starting.

**Write a custom kernel when:**
- A profiler (nsys/ncu or CANN msprof) confirms a specific kernel is on the
  critical path and near its hardware ceiling.
- Two or more adjacent operations can fuse: they share data that would otherwise
  go to/from DRAM between calls. The gain is the reduction in memory traffic,
  not the removal of Python overhead.
- A standard implementation exists but the specific dtype, shape, or quantization
  variant you need is not covered.

**Do NOT write a custom kernel when:**
- A single elementwise operation (relu, sigmoid on its own): the vendor library
  is already optimal.
- A standalone matmul: cuBLAS/CANN is better than a handwritten GEMM in almost
  all cases.
- Standard attention: use FlashAttention or the vendor's equivalent.
- The bottleneck is host-side scheduling: that is a Python/GIL problem, not a
  kernel problem. See `host-overhead-profiling`.

## Framework routing

| Pattern | CUDA / Ampere+ | Ascend NPU |
|---------|---------------|------------|
| Fused elementwise chain (2+ ops sharing data) | Triton (`@triton.jit`) | TileIR / AscendC |
| Reduction (softmax, LayerNorm, RMSNorm) | Triton | TileIR / AscendC |
| Tiled GEMM with autotune | Triton | AscendC |
| GEMM with explicit shared memory / tensor core MMA | CuTe DSL (CUTLASS 4.x) | AscendC cube unit |
| Flash Attention variant | CuTe DSL or Triton | AscendC (custom) |
| Custom collective (AllReduce variant) | NCCL/custom CUDA | HCCL plugin |

CuTe DSL requires Linux x86_64, Python 3.10–3.13, Ampere+ (SM80+), and
`pip install nvidia-cutlass-dsl`. It is not available on NPU.

Source: TRT-LLM kernel-triton-writing + kernel-cute-writing @ f33e0e5f.

## Universal correctness rules (apply to all frameworks)

These rules cause silent wrong results if violated. Check them before
benchmarking.

### 1. Transcendental functions require FP32 inputs

`exp`, `log`, `erf`, `tanh`, and similar transcendentals cause errors or
undefined behavior with FP16/BF16 inputs in Triton. Pattern:

```python
# Wrong — silent error or wrong result with fp16/bf16:
result = tl.exp(x)

# Correct — cast to fp32, compute, cast back:
x_fp32 = x.to(tl.float32)
result = tl.exp(x_fp32).to(x.dtype)
```

Rule: any math function beyond `+`, `-`, `*`, `/` needs an fp32 cast round-trip.

Source: TRT-LLM kernel-triton-writing @ f33e0e5f, §FP16/BF16 Precision Rules.

### 2. Never call `.item()` inside a kernel wrapper

`.item()` forces a CPU-GPU synchronization (~50–100 µs per call). This turns
into a pipeline stall if called inside the hot path.

```python
# Wrong — forces sync:
seed = some_tensor.item()

# Correct — use data pointer arithmetic, no sync:
seed = (some_tensor.data_ptr() % (2**31)) ^ n_elements
```

Source: TRT-LLM kernel-triton-writing @ f33e0e5f, §CPU-GPU Sync Avoidance.

### 3. C integer division semantics (Triton / AscendC)

Triton and most NPU DSLs use C semantics for `//` and `%`: they round toward
zero, not toward negative infinity like Python. This only matters when operands
can be negative (which they can in offset calculations).

```
Python:  -7 // 2  = -4,   -7 % 2  = 1
C/Triton: -7 // 2  = -3,   -7 % 2  = -1
```

Safe pattern: ensure all index and offset values are non-negative. If negative
values are possible: `(idx % BLOCK + BLOCK) % BLOCK`.

Source: TRT-LLM kernel-triton-writing @ f33e0e5f, §C Integer Division Semantics.

### 4. Pre-allocate output tensors

Allocating output inside the kernel wrapper on every call adds Python object
creation cost on the hot path. Accept a pre-allocated output buffer as a
parameter, or cache allocation outside the benchmark loop.

### 5. Use FP32 accumulators for matmul (Triton)

Triton does NOT auto-promote fp16/bf16 inputs to fp32 for accumulation in
`tl.dot`. Always declare the accumulator as `tl.float32`:

```python
acc = tl.zeros((BLOCK_M, BLOCK_N), dtype=tl.float32)
```

### 6. Always mask loads and stores for non-divisible shapes

If `n_elements % BLOCK_SIZE != 0`, an unmasked load reads past the tensor
boundary. Always include a mask:

```python
mask = offsets < n_elements
x = tl.load(x_ptr + offsets, mask=mask)
tl.store(out_ptr + offsets, result, mask=mask)
```

### AKG Affine loop tails (source-derived)

For AKG-MLIR static CUDA elementwise loops, use the
[Affine tail-guard reference](references/akg-affine-tail-guards.md) to trace the
effective target, option precedence and loop bounds before interpreting a
non-divisible tile. The compiler can expand point-loop bounds and move the body
under an `affine.if`; both input reads and output writes need the valid-index
contract. The pinned fixture's FileCheck expectations describe IR structure,
not executed CUDA correctness or a tuning gain. This addition preserves the
handwritten load/store mask rule above and requires separate validation of
later lowering, synchronization and numerics. CPU/NPU tail strategies are not
qualified by the CUDA fixture.

## Workflow: verify before benchmark

### Qualify a stateful serving operator

For vLLM Qwen3-Next GDN convolution/recurrence reuse, read the
[pinned phase/state contract](references/vllm-gdn-causal-conv-contract.md) and
[representative source cases](cases/vllm-gdn-source-contract.md). Trace the
concrete caller, effective phase/backend, state-row mapping and in-place writes
before choosing an operator. The in-tree vLLM wrappers do not establish a
standalone-package or HF-worker binding. Source selection remains separate
from executed correctness, hardware qualification and performance.

**Phase 1: Write the kernel with a reference function**

Every kernel must ship with three exports (used by companion verification and
benchmark scripts):

```python
kernel_fn = my_kernel_wrapper       # the implementation
reference_fn(*args) -> Tensor       # PyTorch reference with identical signature
get_inputs() -> list                # returns fresh CUDA/NPU tensors for testing
```

**Phase 2: Verify against reference**

Run `scripts/verify_kernel.py` (or equivalent) to check that the kernel output
matches the reference across a range of shapes and dtypes before any performance
measurement. Do not benchmark an unverified kernel.

Common verification failures:
- Shape boundary errors (off-by-one in mask)
- Accumulator dtype (fp16 accumulation in matmul)
- Transcendental precision (forgot fp32 cast)

**Phase 3: Profile to confirm bottleneck**

After verification, profile with ncu (CUDA) or msprof (Ascend) to confirm the
kernel has improved the target metric. An optimization that passes verification
but does not change the profiler output was not on the critical path.

## Block size selection

For Triton on CUDA:
- Start with `BLOCK_SIZE = 1024` for H100/Hopper, `512` for A100/Ampere.
- Block sizes must be powers of 2.
- For GEMM tiles (`BLOCK_M`, `BLOCK_N`, `BLOCK_K`): start from the tiled matmul
  skeleton configs in the source (128/256/64 for Hopper, 64/128/32 for smaller
  cards) and autotune from there.

For AscendC on Ascend NPU:
- The AI Core's local buffer (Unified Buffer / UB) is the equivalent of shared
  memory. Tile sizes must fit in UB.
- Cube unit (matrix unit) alignment requirements differ by SoC; check the CANN
  AscendC programming guide for the specific SoC target.
- TileIR (the higher-level DSL above raw AscendC) auto-tiles for standard
  patterns; use it before dropping to raw AscendC.

## Starting from examples

For CuTe DSL on CUDA: find the closest example in the CUTLASS repo at
`https://github.com/NVIDIA/cutlass/tree/main/examples/python/CuTeDSL`.
Match the GPU architecture first (SM80 for Ampere, SM90 for Hopper, SM100 for
Blackwell). Study the example's structure; do not copy it verbatim since shapes,
dtypes, and problem dimensions differ.

For AscendC: consult the CANN AscendC operator development guide for your
specific SoC (Ascend 910B, 910C, etc.). Templates and intrinsics differ between
generations.

## Attention mechanisms and scoped acceptance

Use [attention diagnosis](../../hardware/cuda/diagnose-attention-bottlenecks/SKILL.md) when IO
reduction exposes scalar work, insufficient independent tiles, reduction costs,
compiler ordering or precision/layout overhead. Its
[mechanism notes](../../hardware/cuda/diagnose-attention-bottlenecks/references/mechanisms.md)
retain FlashAttention 1/2/3 assumptions, operation-class costs and counter-signals.
Tiling, recomputation, ownership and overlap change the resource balance; no
single utilization threshold or paper tile size selects a winner.

Preserve dense/sparse/quantized semantics, masks, dropout, output/gradient
accuracy and real buffer lifetimes. Verify the executing instruction schedule
before claiming overlap. Include conversion/preprocessing and exactness costs
in the measured boundary. NVIDIA primitives establish no Ascend support.
[Author-reported cases](../../hardware/cuda/diagnose-attention-bottlenecks/references/papers-20261015/cases/overlap-and-fp8-counter-signals.md)
are counterexamples to unconditional tuning rules, not local successes.

## Limitations

- This skill is a routing and correctness guide, not a complete implementation
  reference. The source TRT-LLM skills contain full implementations for common
  patterns (fused GELU+dropout, softmax, LayerNorm, tiled GEMM, Flash Attention).
- CuTe DSL patterns are NVIDIA CUDA-only (Linux x86_64, SM80+).
- AscendC/TileIR patterns are source-inferred for this skill — verify against
  your specific CANN version and SoC before use. No local NPU verification done.
- Autotune (Triton `@triton.autotune`) adds substantial first-run compile cost.
  For serving, pre-warm the kernel at startup or cache the compiled binary.
