---
name: gated-delta-contract
description: "Investigate mlx-swift-lm gated-delta kernel versus differentiable ops, FP32 recurrent-state boundaries, SIMD tails, masks and caller checkpoints without confusing declared predicates with actual Metal execution."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Gated-delta state and execution contract

Use this source-derived **candidate** when GDN prefill/decode diverges across a
chunk, a key dimension loses its tail, training cannot differentiate, or a mask
changes state/output unexpectedly. It owns the selected `gatedDeltaUpdate`
mechanism and Qwen callers, not every model or kernel in mlx-swift-lm.
Read the [recurrence and state contract](references/recurrence-and-state.md)
before proposing a precision or route change.

## Choose the failing invariant

| Question | First distinction |
| --- | --- |
| A BF16 prompt split changes subsequent output | Carried state is FP32 even when Q/Y are low precision |
| A configured Dk is not a multiple of 32 | Public entry falls back to ops; direct fused kernel would truncate the tail |
| LoRA/backward hits a custom-kernel VJP error | Model callers disable the custom kernel while training |
| `useKernel:false` was reported as CPU evidence | It selects MLX ops, not a demonstrated CPU backend |
| Masked kernel/ops outputs differ | Retained state and emitted Y have different source mask treatment |
| A sliced tensor seems contiguous by shape | Kernel indexing versus dependency-owned packing/stride contract |
| A speculative prefix must be restored | Restore the coupled conv/recurrent checkpoint and metadata, not a guessed token trim |

## Procedure

1. Record source/dependency build, actual device/backend, B/T/Hk/Dk/Hv/Dv,
   input/state dtypes, tensor layouts, mask, model training mode and the route
   actually observed. Availability flags in a plan are declarations, not a
   backend probe. Native compilation and execution remain **not_run** here.
2. Reconcile the [shape and caller boundaries](references/recurrence-and-state.md):
   Q/K `[B,T,Hk,Dk]`, V/Y `[B,T,Hv,Dv]`, recurrent state `[B,Hv,Dv,Dk]`.
   The selected model constructors require value heads divisible by key heads.
   Preserve distinct convolution state and recurrent state precision/lifetimes.
3. For declared shape, FP32 payload and literal public-gate screening, use
   [audit_gated_delta_declarations.py](scripts/audit_gated_delta_declarations.py)
   with its [strict schema and usage](references/helper-contract.md):

   ```bash
   python scripts/audit_gated_delta_declarations.py --example
   python scripts/audit_gated_delta_declarations.py --example | python scripts/audit_gated_delta_declarations.py -
   ```

   Resolve the paths from this installed sub-skill, or run from its directory.
   The helper reads bounded declarations only; no MLX, model, compiler, GPU or
   service operations occur. Exit zero is neither native support nor parity.
4. Separate the literal public gate from complete tensor support. The gate is
   `useKernel && unmaskedKernelAvailable && Dk % 32 == 0`. It does not validate
   every shape, dtype, mask, stride or selected masked-kernel availability.
   Unknown availability stays undetermined. Direct lower-level kernel calls
   must not be used to evade the public Dk tail guard.
5. Preserve FP32 state across calls and chunk/checkpoint boundaries. Upcasting
   previously rounded BF16 state cannot recover discarded precision. One state
   tensor's byte ledger is not peak allocation, a model fit or a speedup.
6. Treat masks as a [source-only parity gap](references/recurrence-and-state.md#mask-and-stride-limits):
   the fused masked branch writes zero Y and retains state on false steps;
   ops restores carried state after computing Y. That asymmetry is inspected,
   not a locally executed failure or a confirmed end-to-end model bug.
7. For training, preserve callers' `useKernel: !training` policy. The ops path
   has recompute-backed differentiation; the custom Metal kernel has no VJP.
   A current shape accidentally falling back to ops is not a durable training
   policy, and selecting ops is not proof that it executes on CPU.
8. Before any numerical conclusion, use the
   [native discriminators and evidence limits](references/verification-boundaries.md):
   chunk-boundary drift, tail perturbation, compensated recurrence dot product,
   multi-chunk gradients, normalization near epsilon and checkpoint restore.
   Verify actual route execution independently when a test requests a kernel
   that may fall back. Do not transplant source tolerances into campaign gates.

## Stop and report

Use [troubleshooting](references/troubleshooting.md) to name the conflicting
invariant and smallest authorized check. Report declared inputs, inspected
source, actual execution and missing evidence separately. Apple Swift/MLX/Metal
absence remains **BLOCKED_REQUIRED_BACKEND**, not a CPU substitute or skipped
success. Model quality, service gains, broad skill efficacy and arbitrary-stride
qualification remain unverified. Reading this route does not authorize
installation, downloads, training, service startup or upstream changes.
