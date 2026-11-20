# Define and qualify an operator boundary

## Choose the smallest extension surface

Inputs: intended operation, shape/dtype/device/layout/mutation/alias contract,
derivative and target compiler/backend support. Output: an accurately registered
operator and separate schema, FakeTensor, numerical, gradient and execution
results. Ordinary compositions of existing torch ops generally need no custom
autograd.Function or custom_op; they already record gradients and can be traced.

Use a custom_op to represent opaque external code/kernel calls across PyTorch
subsystems; use a custom Function when its explicit derivative boundary is
needed; use C++/CUDA/SYCL extensions when compiled code is required. A compiled
Python module alone does not register a dispatcher operator for export/compile.

## Python registration workflow

1. Choose a project namespace (`project::operation`) to avoid collisions. Type
   annotate the function and infer schema where appropriate. Enumerate mutable
   argument names accurately; `mutates_args=()` means none. This metadata feeds
   functionalization and compiler transformations, so lying can cause undefined
   behavior even when one eager example looks correct.
2. Return outputs with the declared alias contract. A functional custom op that
   promises a fresh Tensor must not return an input or view. For intended in-place
   or out operators use the appropriate supported schema/tags and qualify their
   autograd limitations. Avoid declaring a fallback valid for every device when
   its foreign implementation only works on CPU.
3. Register FakeTensor/meta behavior using torch ops and input metadata only.
   It must reproduce size/stride/storage_offset/dtype/device properties without
   reading tensor data, data_ptr or NumPy values. Data-dependent output sizes
   need the supported symbolic-size mechanism and corresponding constraints.
4. Register autograd with `register_autograd(backward, setup_context=...)` when
   gradients are supported. Save needed tensors via save_for_backward. Return
   one input gradient per differentiable argument and None for non-Tensors
   where required. Make setup/backward traceable; opaque backward work can be
   another explicitly registered custom op.
5. Incoming gradients can be noncontiguous even when the forward output is
   contiguous. A native/Triton backward kernel must honor strides or explicitly
   materialize a valid layout before access. Do not assume grad_output layout.
6. Run `torch.library.opcheck` over representative dtype/device/stride/shape
   and requires_grad cases. It checks schema/mutation/aliasing, autograd
   registration, FakeTensor metadata and compiled functionalization behavior.
   Use `gradcheck` separately for derivative mathematics, plus gradgradcheck if
   double backward is supported. opcheck success is not a mathematical proof.
7. Compare eager, compile and export on the intended target. One CPU test cannot
   qualify the CUDA kernel or its stream behavior. Include empty/edge-size and
   noncontiguous inputs when the contract supports them; reject them explicitly
   when it does not.

Run the bundled [operator diagnostic](../scripts/custom_operator.py) for a tiny
fresh-output scale operator with a fake implementation and registered gradient.
Use `--check-registration` to add opcheck; the default compares eager values
and double-precision gradcheck. The helper is an adapted public-API example,
not a production kernel or blanket operator/backend support claim.

## C++/CUDA/SYCL extension workflow

1. Pin the installed torch wheel/build, compiler ABI, Python ABI, OS and backend
   toolkit before compiling. CUDA wheel runtime support does not imply nvcc is
   installed. SYCL uses its own compiler/toolchain; HIP requires its own build.
2. Use `torch.utils.cpp_extension.CppExtension`/CUDAExtension with BuildExtension
   for packaging or `load`/`load_inline` for a deliberate JIT build. They generate
   a build and load a native library; only use trusted sources and private build
   caches. JIT compilation is a filesystem/code-execution action, not metadata
   inspection, so it is not performed by the environment inspector.
3. Supply explicit sources, include paths, conservative parallelism and required
   link flags. CUDA files are compiled with nvcc, SYCL files with a SYCL compiler.
   Diagnose CUDA_HOME/CXX, compiler version, target architecture and Ninja errors
   independently. Set TORCH_CUDA_ARCH_LIST for intended deployment hardware;
   compiling on one GPU is not proof the resulting binary covers another one.
4. Register schema and kernels through TORCH_LIBRARY/TORCH_LIBRARY_IMPL or the
   supported Python API, with device, Autograd and Meta ownership distinct.
   Dispatcher wrapper keys/TLS can affect selection; inspect the actual table
   for missing overload/backend errors instead of guessing from file names.
5. Respect current device and current stream in native accelerator kernels.
   Preserve input/output lifetime, dtype/alignment and bounds checks. A default
   stream launch can pass a single-stream test and fail ordinary callers.
6. Separate compile/link/import checks, operator registration tests, numerical
   and gradient tests, and target-device stream/memory tests. Rebuild affected
   extensions after ABI-changing torch upgrades; preserve other environment
   packages rather than globally reinstalling to suppress undefined symbols.

## Backend and repository maintenance branch

Out-of-tree backends need dispatch registration, device/stream/allocator hooks,
serialization tags, fallback policy and compiler/FakeTensor coverage appropriate
to their API. PrivateUse1 naming/registration is not proof of CUDA equivalence.
Treat TorchNPU and other plugins as independently versioned stacks.

For a core operator change, identify schema/native YAML, derivative, meta,
functionalization, codegen, dispatch and OpInfo/test owners. Generated files
are outputs of their declared sources. Make a focused change and run the
repository's current focused tests/lints on a built matching revision; full CI,
release tooling and all-device qualification are external to this skill.
Repository contribution policy is separate from a user runtime procedure.


Source support at the pinned revision (exact inspected spans and byte digests are in the root [readset](../../../references/source-readset.json)):

- [`torch/_library/custom_ops.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/_library/custom_ops.py)
- [`torch/library.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/library.py)
- [`torch/utils/cpp_extension.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/utils/cpp_extension.py)
- [`docs/source/notes/extending.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/notes/extending.md)
- [`test/test_custom_ops.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/test/test_custom_ops.py)
