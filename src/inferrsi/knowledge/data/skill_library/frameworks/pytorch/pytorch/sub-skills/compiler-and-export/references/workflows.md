# Capture, lowering, export and deployment

## Inputs and output contract

Inputs: an eager-correct module/function, sample inputs, shape/value ranges,
state/gradient modes, target backend and deployment consumer. Output: graph and
guard assumptions, correctness comparisons, compiler-stage error or export
artifact with a consumer compatibility test. A graph being captured does not
establish kernel speed or downstream runtime support.

## Compile diagnosis in stages

1. Freeze eager inputs/state/seed and compare forward outputs plus gradients
   where training matters. Remove data access, network and unrelated side
   effects from the reproduction, preserving the operation that fails.
2. Try `torch.compile(fn, backend="eager")` to isolate Dynamo capture. Then
   `backend="aot_eager"` exercises AOTAutograd/decomposition and functionalization;
   finally the actual Inductor/backend target exercises lowering/codegen/runtime.
   Compare the same initial state for each run; backend names are diagnostic
   routes and remain version-specific.
3. Enable `TORCH_LOGS="graph_breaks,recompiles,guards"` for a bounded run.
   Use `fullgraph=True` as a capture requirement when appropriate: it raises
   on a break rather than silently accepting segmented execution. Preserve
   Python/data-dependent control flow in the reproduction before rewriting it.
4. Distinguish a graph break from a guard failure. A break segments capture and
   resumes through Python; a failed guard prevents reuse of a cached compiled
   result and may compile another variant or fall back after limits are hit.
   Repeated shape, dtype/stride/device, Python scalar or object-state changes
   can matter. Inspect the actual failed guard, not just the count of graphs.
5. Dynamic shape policy is explicit: dynamic=False specializes; True attempts
   dynamic kernels; None may generalize after a shape-changing call. Some
   operations still specialize. Supply intended ranges and test boundary shapes,
   including size 0/1 where appropriate. Never drop correctness guards merely
   to reduce recompilation or hard-code one observed shape as a general fix.
6. Only after correctness, choose default/reduce-overhead/max-autotune modes.
   CUDA graph capture and autotuning have eligibility, cold-start and memory
   costs; `reduce-overhead` is not an unconditional acceleration promise.
   Separate cold compile time, cache reuse and steady execution latency.

## Lower-level mechanism

Dynamo converts Python frames, builds runtime guards and packages rewritten
code with a GuardManager in `GuardedCode`. `TENSOR_MATCH` inspects tensor type
and metadata/dispatch properties; ordinary eager guards execute through the C++
guard path, while export has a distinct shape/soundness boundary. The code
object can own multiple guarded variants; recreating Python function objects
does not necessarily isolate their shared code cache.

Inductor's compile_fx receives FX graphs after upstream transforms and constructs
`GraphLowering` with example inputs, shape environment and inference/backward
flags. `graph.run()` lowers nodes; code generation produces callable code.
Operator lowerings can call generated kernels, templates or external ATen
fallbacks. Missing operators may use a configured fallback/decomposition or
raise a missing-lowering error. A captured graph is therefore not necessarily
one fused kernel. Layout constraints can insert copies and affect mutation
writeback. Preserve strides/aliasing and backward semantics during diagnosis.

If only Inductor fails, retain the AOT eager control, failing overload and
metadata, relevant generated code and first error; route custom ops to fake,
mutation and autograd registration before attempting private lowering patches.
Debug artifacts may contain model structure/paths/tensor values: share only a
reviewed minimal reproduction. Compiled caches are trusted local code artifacts.

## FX transformation

`torch.fx.symbolic_trace` executes a function with Proxies and records a
GraphModule with placeholders/get_attr/call_function/call_module/call_method
and output nodes. It is a Python-to-Python transformation tool; arbitrary
data-dependent Python control flow is not a universal symbolic-tracing contract.
After editing `gm.graph`, call `gm.graph.lint()` and `gm.recompile()`, then
compare outputs and state with the original. A syntactically valid graph can
still change mutation, aliasing, hooks or parameter semantics.

## torch.export workflow

1. Choose a Module and concrete args/kwargs. `torch.export.export` returns an
   ExportedProgram with tensor computation, lifted state and shape assumptions.
   Export is an ahead-of-time input contract, not arbitrary Python serialization.
2. State strict=True/False deliberately; the pinned signature defaults to False.
   Strict uses Dynamo and has different Python coverage/soundness behavior.
   Both still enforce critical shape constraints. Do not infer the default from
   an old release or silently toggle strict to hide an unsupported assumption.
3. Specify shared dynamic dimensions with `torch.export.Dim` and matching
   nested argument structure. Inspect suggested bounds/relations when export
   raises ConstraintViolationError. The pinned source also exposes newer
   ShapesSpec/ParamsSpec unbacked specifications; check installed API identity
   before using that newer surface. A Dim-based recipe is not a claim that
   every dynamic API has equal specialization behavior.
4. Execute `ep.module()(*args)` and compare with eager on several valid shapes;
   test an out-of-contract shape fails or is handled by the declared contract.
5. Save via `torch.export.save`, load via `torch.export.load`, and rerun the
   same comparisons. Export archives are versioned/trusted program artifacts,
   not interchangeable with a torch.save state_dict or portable native binary.
6. Native compilation/deployment such as AOTInductor needs its own compiler,
   target libraries/device, package format and compatible runtime. Qualify
   artifact loading and execution on that target; saving an ExportedProgram
   alone does not qualify AOTI deployment.

Run the bundled [export diagnostic](../scripts/export_contract.py) with
`--batch 3` and optionally `--compile-backend eager`. It creates only a tiny
module and temporary archive, checks a second valid batch and shape rejection,
and removes the temporary artifact. `--compile-backend inductor` explicitly
selects compilation and requires its real toolchain; it is never the default.

## ONNX and legacy deployment

Use `torch.onnx.export(model, (x,), dynamo=True, dynamic_shapes=..., report=True,
artifacts_dir=...)` for the export-based path, with ONNX/ONNX Script and, for
`verify=True`, ONNX Runtime installed. Choose opset by consumer support. Prefer
the returned ONNXProgram's save interface when appropriate; external-data
weights are part of the artifact and must travel with it. Non-Tensor arguments
may specialize into constants. Validate names/order, dynamic bounds, unsupported
translations and target outputs, including numerical tolerances. `dynamic_axes`
belongs to legacy dynamo=False flow; it does not replace dynamic_shapes.

TorchScript `script`/`trace` and save/load remain compatibility surfaces;
trace captures example execution and can miss data-dependent branches. Do not
load untrusted TorchScript/mobile `.ptl` programs just to inspect them. This
snapshot marks Mobile unsupported and points to ExecuTorch. Migration to that
separate repository or torchao requires independent source/version/consumer
qualification, not a PyTorch wheel import or this graph's source coverage.


Source support at the pinned revision (exact inspected spans and byte digests are in the root [readset](../../../references/source-readset.json)):

- [`torch/__init__.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/__init__.py)
- [`torch/_dynamo/convert_frame.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/_dynamo/convert_frame.py)
- [`torch/_dynamo/guards.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/_dynamo/guards.py)
- [`torch/_inductor/compile_fx.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/_inductor/compile_fx.py)
- [`torch/_inductor/graph.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/_inductor/graph.py)
- [`torch/export/__init__.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/export/__init__.py)
- [`torch/onnx/__init__.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/onnx/__init__.py)
- [`torch/fx/__init__.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/fx/__init__.py)
- [`docs/source/user_guide/torch_compiler/torch.compiler_troubleshooting.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/user_guide/torch_compiler/torch.compiler_troubleshooting.md)
- [`docs/source/onnx.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/onnx.md)
- [`docs/source/utils/mobile_optimizer.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/utils/mobile_optimizer.md)
- [`torch/jit/__init__.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/jit/__init__.py)
