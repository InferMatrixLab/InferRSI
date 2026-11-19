---
name: torch-npu
description: "Operate and diagnose TorchNPU on Ascend across installation, PrivateUse1 dispatch, operator development, memory and streams, graphs and compilation, HCCL, precision and profiling, with pinned source evidence and explicit backend limits."
metadata:
  inferrsi: |
    {
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "license": "NOASSERTION",
      "disable-model-invocation": true,
      "metadata": {
        "disco-role": "operating"
      },
      "tags": [
        "torch-npu",
        "ascend",
        "pytorch"
      ],
      "applicability": {
        "scope": "Source-grounded TorchNPU operation and diagnosis; qualify the selected installed stack independently.",
        "prerequisites": "Compatible Linux, PyTorch, TorchNPU, CANN, driver and authorized Ascend device access for device execution.",
        "input_contract": "Exact stack identities, bounded workload, tensor metadata and intended correctness/measurement boundary.",
        "produced_artifact": "A source-supported procedure or diagnostic trace with actual pass/fail/not-run observations.",
        "failure_modes": "Confusing registration with device readiness, CPU fallback with NPU execution, or source inspection with runtime proof.",
        "refusal_point": "Withhold backend correctness/performance conclusions when required device/runtime evidence is missing.",
        "hardware": "Ascend NPU required for device, stream, graph, precision, profiling and HCCL checks."
      },
      "limitations": [
        "Source-derived candidate; installed API and NPU/CANN execution were not validated.",
        "BLOCKED_REQUIRED_BACKEND: Linux Ascend NPU/CANN stack, multi-rank HCCL and optional compiler runtime checks remain unavailable.",
        "No model quality, benchmark gain, service/E2E claim or candidate promotion follows from static checks.",
        "Representative pinned op-plugin inspection does not cover every operator or external CANN kernel implementation."
      ],
      "consumption_mode": "packaged",
      "references": [
        "../../../platforms/ascend/torchnpu-device-memory-lifecycle/SKILL.md",
        "../../../platforms/ascend/torchnpu-pinned-host-memory-lifecycle/SKILL.md"
      ],
      "provenance_readsets": [
        "references/source-map.md",
        "references/source-manifest.json"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/Ascend/pytorch",
          "commit": "046934140b96836c3fcef14d0f39ae54dc0a06bf",
          "paths": [
            "COMPATIBILITY.en.md",
            "README.md",
            "docs/en/api/environment_variable/op_execution/ASCEND_LAUNCH_BLOCKING.md",
            "docs/en/installation_guide/building_from_source.md",
            "fxrt/README.md",
            "generate_code.sh",
            "setup.py",
            "test/distributed/test_hccl_group.py",
            "test/npu/test_aclgraph_multi_stream.py",
            "test/npu/test_amp.py",
            "test/npu/test_cpu_fallback_control.py",
            "test/npu/test_import_contract.py",
            "test/npu/test_stream.py",
            "tools/setup_helpers/version.py",
            "torch_npu/__init__.py",
            "torch_npu/_inductor/__init__.py",
            "torch_npu/_init/core/module_loader.py",
            "torch_npu/_init/registry/backend.py",
            "torch_npu/_init/registry/distributed.py",
            "torch_npu/_init/registry/dynamo.py",
            "torch_npu/_init/registry/registry_manager.py",
            "torch_npu/contrib/transfer_to_npu.py",
            "torch_npu/csrc/aten/AutoCastOps.cpp",
            "torch_npu/csrc/aten/VariableFallbackKernel.cpp",
            "torch_npu/csrc/core/npu/CachingHostAllocator.cpp",
            "torch_npu/csrc/core/npu/NPUCachingAllocator.cpp",
            "torch_npu/csrc/core/npu/NPUEvent.cpp",
            "torch_npu/csrc/core/npu/NPUGraph.cpp",
            "torch_npu/csrc/core/npu/NPUHooksInterface.cpp",
            "torch_npu/csrc/core/npu/NPUStream.cpp",
            "torch_npu/csrc/distributed/ProcessGroupHCCL.cpp",
            "torch_npu/csrc/framework/utils/CpuFallbackUtils.h",
            "torch_npu/csrc/profiler/profiler_mgr.cpp",
            "torch_npu/distributed/tensor/__init__.py",
            "torch_npu/dynamo/__init__.py",
            "torch_npu/npu/__init__.py",
            "torch_npu/npu/_sanitizer.py",
            "torch_npu/npu/amp/autocast_mode.py",
            "torch_npu/npu/amp/grad_scaler.py",
            "torch_npu/npu/graphs.py",
            "torch_npu/npu/streams.py",
            "torch_npu/onnx/__init__.py",
            "torch_npu/optim/__init__.py",
            "torch_npu/profiler/profiler.py",
            "torch_npu/profiler/scheduler.py",
            "torch_npu/utils/serialization.py",
            "torchnpugen/gen_backend_stubs.py",
            "version.txt"
          ],
          "readset": "references/source-manifest.json"
        },
        {
          "type": "git",
          "url": "https://github.com/Ascend/op-plugin",
          "commit": "ad946817034b3270e309c81c54f0ee808d0b62cb",
          "paths": [
            "examples/cpp_extension_full/torch_lib_impl/cpp_extension_full/ops.py",
            "examples/cpp_extension_full/torch_lib_impl/csrc/add_custom.cpp",
            "op_plugin/config/op_plugin_functions.yaml",
            "op_plugin/ops/aclops/AddKernelNpu.cpp",
            "op_plugin/ops/opapi/AddKernelNpuOpApi.cpp",
            "torchnpugen/gen_op_plugin_functions.py"
          ],
          "readset": "references/source-manifest.json"
        }
      ]
    }
---

# TorchNPU operating graph

Use for Ascend/pytorch's TorchNPU adapter. Collect exact torch/torch-npu builds,
CANN/driver/hardware, the selected eager/compile/distributed mode, tensor
shape/dtype/layout and a bounded reproduction. This is a source-derived
candidate, not a validated installed stack. NPU, CANN, HCCL and optional compiler
checks remain `BLOCKED_REQUIRED_BACKEND` until exercised on the actual backend.

Choose the narrowest route, then compose routes when the failure crosses an
ownership boundary:

| User goal or symptom | Owning procedure |
|---|---|
| Install, select versions, missing shared library, build/package mismatch | [Installation and compatibility](sub-skills/installation-and-compatibility/SKILL.md) |
| Missing `torch.npu`, import ordering, unsupported op or hidden CPU fallback | [PrivateUse1 and dispatch](sub-skills/privateuse1-and-dispatch/SKILL.md) |
| Add an overload/custom op; fix schema, backward or Meta support | [Operator development](sub-skills/operator-development/SKILL.md) |
| Async corruption, stream waits, allocation reuse, pinned copies, memory retention | [Memory, streams and events](sub-skills/memory-streams-and-events/SKILL.md) |
| NPUGraph replay, `torch.compile`, graph breaks, compiler choice or eager fallback | [Graph and compile](sub-skills/graph-and-compile/SKILL.md) |
| Multi-rank launch, HCCL/P2P, hangs, work completion or sharding boundary | [Distributed and HCCL](sub-skills/distributed-and-hccl/SKILL.md) |
| Training migration, autocast/scaler, overflow, optimizer or checkpoint state | [Training and precision](sub-skills/training-and-precision/SKILL.md) |
| Trace collection, memory timeline, async exception or sanitizer | [Profiling and debugging](sub-skills/profiling-and-debugging/SKILL.md) |

For migration shims, serialization/export, fused modules, RPC, DTensor/FSDP,
FXRT deployment and fault tooling, read [support workflows](references/support-workflows.md).
The [capability inventory](references/capability-inventory.md) distinguishes
substantive inspection from directory discovery and names remaining boundaries.

## Operating contract

1. Qualify the environment before executing a device workflow. Run
   `python <SKILL_ROOT>/scripts/inspect_environment.py` for package metadata only;
   use `--device` explicitly for a tiny allocation/matmul/completion check.
2. State the relevant source mechanism and the actual last inspected boundary.
   Use [the evidence ledger](references/source-map.md) and
   [immutable provenance](references/repo-provenance.md) for revision alignment.
3. Establish correctness before changing precision, compilation, allocator or
   overlap policy. Keep producer ordering, storage lifetime and completion
   observations distinct.
4. Use [runtime smoke examples](scripts/runtime_smoke.py) only after selecting
   their exact case and `--run`; the default is non-executing. The
   [operator contract checker](scripts/operator_contract.py) requires only
   standard-library Python and checks declarations, not a device kernel.
5. Return exact stack identities, chosen path, observations and pass/fail/not-run
   scope. Restore a known-correct configuration if a bounded experiment fails.

Expected output is an executable proposal or diagnostic trace with explicit
verification state. Reading this graph does not authorize installations,
multi-rank launches, device reset, stress tests or arbitrary upstream scripts.
Use only the operations needed for the caller's authorized task.

## Boundaries and related owners

Do not infer device readiness from registration, NPU coverage from CPU fallback,
memory safety from ordering alone, completed HCCL transfer from a host future,
compilation from an eager fallback, or service gains from submission timing.
CPU/helper/static checks cannot substitute for required accelerator execution.
No convergence, benchmark gain, L4 service result or candidate promotion is
established by this graph.

Existing skill IDs `torchnpu-device-memory-lifecycle` and
`torchnpu-pinned-host-memory-lifecycle` own focused allocator tuning at their
earlier exact source pin. Metadata declares those relationships; their evidence
is not refreshed here. This graph provides newer end-to-end operating routes
and preserves both revision boundaries.

Full-repository inventory does not mean every operator, CANN kernel, compiler
pass or device family was inspected. The pinned op-plugin readset covers real
adapter/generator/registration mechanisms; other gitlinks remain explicit
external dependencies. See [source-script decisions](references/source-script-inventory.md)
and [attribution and retained licenses](references/NOTICE.md).
