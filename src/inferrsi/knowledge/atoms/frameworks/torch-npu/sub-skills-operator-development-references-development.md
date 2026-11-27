# Operator implementation procedure

## Define the contract before adding code

Capture a namespaced schema/overload, tensor and scalar arguments, output shape
and dtype, aliasing, broadcasting, in-place/out semantics, permitted layouts,
dynamic dimensions, gradients and compiler/capture expectations. The bundled
JSON checker checks that these decisions are explicit; it does not generate
or compile a kernel. A minimal input is:

```json
{"schema":"example::add(Tensor a, Tensor b) -> Tensor",
 "dtypes":["float32"],"layouts":["contiguous"],"shape_cases":[[2,2]],
 "mutates_inputs":false,"requires_grad":true,"has_autograd":true,
 "compile_requested":true,"has_meta":true,"reference":"a + b"}
```

```bash
python <SKILL_ROOT>/scripts/operator_contract.py <CONTRACT_JSON>
```

## Built-in adaptation and generation

TorchNPU's `torchnpugen` consumes the matching torchgen schema/model together
with NPU YAML and version-specific op-plugin YAML. The pinned op-plugin
configuration distinguishes official/custom/symbolic/autograd entries and ACL
versus op-api support ranges. Its generator filters entries by the selected
PyTorch major/minor and emits implementation namespaces; availability on one
line is not availability on another. The TorchNPU backend-stub generator
builds backend indices and rejects operator names absent from the native
schema map (F6). Generated registration files are build products, not the place
to hand-fix a lasting schema mismatch.

For a new overload, update the owning schema/configuration, implementation,
required autograd declarations and Meta/fake coverage coherently. Regenerate
with the matching torchgen version in a disposable build checkout. Review
generated diffs for exact overload/key bindings. The original build/codegen
scripts mutate files and initialize or remove submodule working directories;
they are reference-only in this portable graph.

## Trace an actual adapter

The inspected op-plugin Add implementation (F7) performs result-type inference,
broadcast-size inference and alpha validation before allocating an output.
The op-api tensor/scalar branches select `aclnnAdd`, `aclnnAdds` or a supported
`aclnnAddV3`; availability checks can route to the legacy ACL adapter. The
legacy adapter builds `OpCommand` inputs/outputs and selects Add or AxpyV2
based on alpha. Out/in-place paths also check memory overlap. These branches
are concrete evidence that replacing an adapter with one ACLNN call can lose
dtype, scalar, broadcast, format or aliasing semantics. CANN's internal kernel
implementation is outside the inspected source boundary.

## Namespaced extension

For a deliberate custom extension, define its schema with `TORCH_LIBRARY` and
register the NPU implementation with `TORCH_LIBRARY_IMPL(..., PrivateUse1, ...)`.
The pinned full extension example separately registers Meta, AutogradPrivateUse1
and AutogradMeta and loads its built shared library. Its NPU implementation
guards the input device, allocates output and invokes `EXEC_NPU_CMD_EXT`.
This demonstrates the registration pattern, not a complete broadcast-correct
Add replacement: the example allocates `empty_like(self)` and assumes its
sample input contract. Do not reuse its simple backward formula for a
broadcasted operation without summing gradients to each original input shape.

Prefer one small extension with explicit shape guards over copied build trees.
Retain upstream notices when adapting source. This graph bundles no compiled
binary or CANN kernel and promises no ABI compatibility across torch releases.

## Validation order and deliverable

1. Check schema/aliasing and Meta results without allocating accelerator storage.
2. On the target NPU compare dtype, output shape and values against a trusted
   reference for contiguous/noncontiguous, zero-size, scalar, broadcast and
   invalid-input cases that the operator promises.
3. Check out/in-place identity and overlap rules separately.
4. Check gradients, including broadcast reductions and retained intermediates.
5. Only then test compile/graph replay with updated input values and stable
   storage; record dynamic-shape/alias restrictions.

Return exact source/runtime identities, selected path, input matrix, expected
failure cases and actual pass/fail/not-run results. A successful shape-only Meta
test cannot clear `BLOCKED_REQUIRED_BACKEND` for the device kernel.
