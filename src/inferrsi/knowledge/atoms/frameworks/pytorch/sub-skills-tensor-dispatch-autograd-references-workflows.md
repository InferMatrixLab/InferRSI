# Tensor, dispatch and gradient contracts

## Tensor workflow

Inputs: an operator, shape/stride/storage offset, dtype/layout/device, mutation
and alias expectations, grad mode and expected values. Output: the first
contract mismatch and a tiny eager reproduction.

1. Record `shape`, `stride()` for strided tensors, `dtype`, `device`, `layout`,
   `requires_grad`, `is_leaf` and `grad_fn`. Avoid applying dense-only metadata
   methods blindly to sparse/nested layouts. Record alias expectations explicitly.
2. Separate dtype promotion/broadcasting from device placement. Move operands
   deliberately; selecting a current CUDA device does not move existing tensors.
3. `view` requires compatible strides; `reshape` may copy. A transpose changes
   strides and often creates a view. `clone` makes independent storage, while
   `detach` removes autograd history and can still share storage. Avoid `.data`
   as a way to bypass version/gradient tracking.
4. Compare values with `torch.testing.assert_close` under an application-defined
   tolerance and finite-value policy. Mathematically identical reductions can
   differ across layouts, devices or batching because floating point is not
   associative. Check condition numbers/nonfinite inputs for linear algebra.
5. For NumPy/DLPack interop, decide copy versus shared storage and lifetime
   ownership before mutation. Keep autograd-tracked computation in torch or
   provide an explicit custom derivative; foreign code is not automatically AD.

The bundled [tensor diagnostic](../scripts/tensor_contracts.py) exercises a tiny
view mutation, reverse-mode derivative and coalesced sparse COO duplicate. Run
`python <SUBSKILL_DIR>/scripts/tensor_contracts.py`; it uses CPU only and is a
bounded control, not validation of every tensor layout/operator.

## Dispatcher mechanism and missing-kernel diagnosis

An operator is selected by schema and overload before autograd. Dispatch is
more than choosing a device name. `MultiDispatchKeySet` unions keys carried by
Tensor inputs (and supported lists/optionals). `computeDispatchKeySet` applies
thread-local inclusion/exclusion and the operator's fallthrough mask:
`((tensor_keys | tls_included) - tls_excluded) & key_mask`.
`Dispatcher::call` extracts that keyset, looks up the kernel in the operator
table and calls it; wrapper keys can redispatch with an explicit reduced set.

To investigate a missing implementation:

1. Record exact `torch.ops` overload/schema, operand layout/backend and active
   transforms: autograd, autocast, vmap, functionalization or subclasses.
2. Reproduce with plain eager tensors, then add one transform at a time.
3. A CPU/CUDA kernel, a Meta/FakeTensor implementation and an autograd formula
   are different registrations. Do not treat a missing Meta kernel as evidence
   the CPU math is broken, or register an autograd wrapper as a device kernel.
4. Internal diagnostics such as `torch._C._dispatch_dump_table` can reveal the
   installed registration table, but are version-specific debugging aids.
   Preserve their output as evidence rather than building application logic on
   private dispatch APIs. Use the custom-operator route for registration fixes.

## Autograd workflow

1. Establish a differentiable scalar loss (or supply grad_outputs for a vector).
   The eager backward graph is recreated each iteration. Operations record
   history only when grad mode and relevant tensor inputs permit it.
2. Freeze parameters with `requires_grad_(False)` where intended. Gradients
   accumulate into leaf `.grad`; non-leaf inspection needs `retain_grad()`.
   Clear gradients at the intended accumulation boundary before another update.
3. `model.eval()` changes training behavior such as dropout/batch norm; it
   does not disable autograd. Use `no_grad()` when outputs must later participate
   in grad computation. Use `inference_mode()` only when its new tensors will
   not be reused in a subsequent recorded gradient computation.
4. Saved tensors retain values needed for backward. In-place mutation increments
   a version counter; backward compares saved and current versions. Remove the
   mutation or move it outside the recorded computation instead of hiding the
   error through `.data`. A detached alias can still cause a version mismatch.
5. Debug missing/NaN gradients at the earliest operation. Masking a bad output
   after dividing by zero does not remove the bad operation from the backward
   graph. Bound invalid operations before applying them. Use anomaly detection
   only for diagnosis because it changes overhead.
6. For custom derivative formulas, test double-precision `gradcheck` and, if
   supported, `gradgradcheck`. Registration correctness uses `opcheck`
   separately. For forward AD/Jacobians/per-sample gradients use torch.func
   `grad`, `vjp`, `jvp`, `jacrev`/`jacfwd` and `vmap` on an appropriate pure
   function; tensor `.item()` and side effects may defeat transformation.

## Sparse, nested and specialized tensor branch

For COO/CSR/CSC/BSR/BSC, specify dense shape, index structure and values. Validate
index bounds and compressed-row invariants before launching native kernels.
COO duplicate indices mean summation; `coalesce()` combines duplicates and sorts
indices. Some operations preserve zeros and sparsity, others densify or lack a
layout-specific implementation. Check output layout and gradient support for
the exact operator. Sparse storage is not automatically a speedup.

For ragged data, distinguish strided nested versus jagged layout. Jagged packs
values plus offsets for one ragged dimension in these docs; preserve input
history with the appropriate constructor. Binary jagged operations may require
the *same offsets constituent*, not merely equal lengths. Retry an unsupported
op through padded dense plus masking only if that preserves semantics and
memory budget. The snapshot's nested page both warns development is inactive
and retains older active-development wording: treat support as limited and
qualify the actual installed operator rather than promising roadmap or speed.

FFT, linalg, special functions, distributions, masked/experimental tensors and
torch._numpy share this contract-first route. Validate their domain, complex
gradient convention, dtype/layout/backend and numerical behavior individually.
Private/experimental interfaces and every operator combination remain a named
long-tail qualification requirement, not blanket support from a tensor import.


Source support at the pinned revision (exact inspected spans and byte digests are in the root [readset](../../../references/source-readset.json)):

- [`docs/source/notes/autograd.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/notes/autograd.md)
- [`aten/src/ATen/core/dispatch/Dispatcher.h`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/aten/src/ATen/core/dispatch/Dispatcher.h)
- [`aten/src/ATen/core/dispatch/DispatchKeyExtractor.h`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/aten/src/ATen/core/dispatch/DispatchKeyExtractor.h)
- [`docs/source/sparse.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/sparse.md)
- [`docs/source/nested.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/nested.md)
- [`docs/source/func.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/func.md)
- [`docs/source/notes/numerical_accuracy.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/notes/numerical_accuracy.md)
