---
name: pytorch
description: "Operate and diagnose PyTorch installation, tensors and autograd, training and data, compilation and export, accelerator lifetimes, distributed execution, checkpointing, profiling and custom operators from pinned repository evidence."
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
        "pytorch",
        "tensor",
        "autograd",
        "training",
        "compiler",
        "distributed",
        "repository-guide"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/pytorch/pytorch",
          "commit": "9a90a4fefcaafa63ac984621963a6fcc66aee68c",
          "paths": [
            "AGENTS.md",
            "LICENSE",
            "NOTICE",
            "README.md",
            "SECURITY.md",
            "aten/src/ATen/core/dispatch/DispatchKeyExtractor.h",
            "aten/src/ATen/core/dispatch/Dispatcher.h",
            "aten/src/ATen/native/transformers/cuda/sdp_utils.cpp",
            "c10/cuda/CUDACachingAllocator.cpp",
            "cmake/EnvVarForwarding.cmake",
            "docs/source/distributed/checkpoint.md",
            "docs/source/distributed/fsdp.fully_shard.md",
            "docs/source/distributed/tensor.md",
            "docs/source/func.md",
            "docs/source/nested.md",
            "docs/source/notes/amp_examples.md",
            "docs/source/notes/autograd.md",
            "docs/source/notes/cuda.md",
            "docs/source/notes/ddp.md",
            "docs/source/notes/extending.md",
            "docs/source/notes/modules.md",
            "docs/source/notes/numerical_accuracy.md",
            "docs/source/notes/randomness.md",
            "docs/source/notes/serialization.md",
            "docs/source/onnx.md",
            "docs/source/profiler.md",
            "docs/source/quantization.md",
            "docs/source/sparse.md",
            "docs/source/user_guide/torch_compiler/torch.compiler_troubleshooting.md",
            "docs/source/utils/mobile_optimizer.md",
            "pyproject.toml",
            "setup.py",
            "test/export/test_export.py",
            "test/profiler/test_profiler.py",
            "test/test_autograd.py",
            "test/test_cuda.py",
            "test/test_custom_ops.py",
            "test/test_dataloader.py",
            "test/test_serialization.py",
            "torch/__init__.py",
            "torch/_dynamo/convert_frame.py",
            "torch/_dynamo/guards.py",
            "torch/_inductor/compile_fx.py",
            "torch/_inductor/graph.py",
            "torch/_library/custom_ops.py",
            "torch/csrc/distributed/c10d/ProcessGroup.hpp",
            "torch/csrc/distributed/c10d/ProcessGroupNCCL.cpp",
            "torch/distributed/checkpoint/format_utils.py",
            "torch/distributed/checkpoint/state_dict_saver.py",
            "torch/distributed/distributed_c10d.py",
            "torch/distributed/elastic/rendezvous/c10d_rendezvous_backend.py",
            "torch/distributed/rendezvous.py",
            "torch/distributed/run.py",
            "torch/export/__init__.py",
            "torch/fx/__init__.py",
            "torch/jit/__init__.py",
            "torch/library.py",
            "torch/nn/functional.py",
            "torch/onnx/__init__.py",
            "torch/optim/optimizer.py",
            "torch/profiler/profiler.py",
            "torch/serialization.py",
            "torch/utils/benchmark/utils/timer.py",
            "torch/utils/checkpoint.py",
            "torch/utils/collect_env.py",
            "torch/utils/cpp_extension.py",
            "torch/utils/data/dataloader.py",
            "version.txt"
          ],
          "readset": "references/source-readset.json"
        }
      ],
      "provenance_readsets": [
        "references/source-readset.json"
      ],
      "references": [
        "../../../platforms/host/host-memory-management/SKILL.md",
        "../dcp-async-save-performance/SKILL.md"
      ],
      "applicability": {
        "scope": "Major user workflows and selected deep mechanisms of pinned pytorch/pytorch source; exact device/operator qualification remains task-specific.",
        "prerequisites": [
          "An explicitly selected installed torch environment for runtime helpers.",
          "Actual required devices, supported build and trusted ranks/storage for backend/distributed operations."
        ],
        "input_contract": "A concrete model/tensor/data/environment reproduction and desired operation or expected behavior.",
        "produced_artifact": "A route-specific environment, tensor/gradient, graph, memory/stream, rank/state or measurement contract with checked and missing evidence.",
        "failure_modes": [
          "Transferring pinned-source behavior to another release/backend without checking compatibility.",
          "Confusing source inventory, CPU diagnostics and target backend execution."
        ],
        "refusal_point": "Withhold backend success and performance conclusions when required runtime or workload evidence is missing."
      },
      "limitations": [
        "Source-derived candidate; empirical efficacy not_run.",
        "Required CUDA/ROCm/MPS/XPU/external accelerator and NCCL/graph checks unavailable locally retain BLOCKED_REQUIRED_BACKEND.",
        "Installed CPU wheel 2.15.0+cpu is separate from pinned source 2.16.0a0; CPU diagnostics are not same-source native verification.",
        "No automatic compatibility pairing with independently pinned TorchNPU.",
        "Directory inventory does not imply every file/operator/device was semantically read or run."
      ],
      "consumption_mode": "packaged"
    }
---

# PyTorch operating graph

Use this graph to plan a PyTorch workflow or isolate a source, API, numerical,
compiler, device, communication or serialization failure. It covers the major
repository workflows through eight routes. **Candidate** describes knowledge
state; source breadth does not mean every file or backend was executed.

Read [provenance](references/repo-provenance.md) before transferring a recipe to
another revision. The pinned source is `pytorch/pytorch` at
`9a90a4fefcaafa63ac984621963a6fcc66aee68c` (`2.16.0a0` source version).
Installed-wheel observations are a distinct evidence class. Accelerator and
distributed backend qualification must use the actual target stack.

| User task | Route | Expected artifact |
| --- | --- | --- |
| Choose a wheel/backend; build Python or LibTorch; repair import/ABI | [installation and build](sub-skills/installation-and-build/SKILL.md) | Environment/build identity and smoke result |
| Tensor layout/device/dtype, missing gradient, sparse/nested, torch.func | [tensor, dispatch and autograd](sub-skills/tensor-dispatch-autograd/SKILL.md) | Tensor/alias/gradient contract |
| nn/optim, training/eval, DataLoader, AMP, SDPA, activation recompute | [training and data](sub-skills/training-and-data/SKILL.md) | Bounded step with state and data checks |
| Dynamo guards, Inductor, FX, export, ONNX, TorchScript/mobile migration | [compiler and export](sub-skills/compiler-and-export/SKILL.md) | Graph/shape/deployment contract |
| OOM, allocated versus reserved bytes, streams, graph replay | [memory, streams and graphs](sub-skills/memory-streams-and-graphs/SKILL.md) | Storage/stream lifetime ledger |
| torchrun, c10d, DDP/FSDP2/DTensor, serialization and DCP | [distributed and checkpoint](sub-skills/distributed-and-checkpoint/SKILL.md) | Rank/collective schedule and restore plan |
| Trace/time/memory, nonfinite results, backend/compiler isolation | [profiling and debugging](sub-skills/profiling-and-debugging/SKILL.md) | Reproduction and bounded measurement |
| torch.library, FakeTensor, gradients, C++/CUDA/SYCL extension | [custom operators and extensions](sub-skills/custom-operators-and-extension/SKILL.md) | Schema, numerical and registration checks |

Start by identifying source commit or distribution version, wheel backend tag,
Python/OS, device and driver/runtime, workload shapes/dtypes/layouts, grad mode,
state/seed and the smallest failing example. Run the bundled
[environment inspector](scripts/inspect_environment.py) in the chosen environment:

```bash
python <SKILL_DIR>/scripts/inspect_environment.py
python <SKILL_DIR>/scripts/inspect_environment.py --require-backend cuda
```

`<SKILL_DIR>` is this skill's installed directory; helpers run from any current
directory. Inspection reports bounded software facts, never automatic package
repair, model downloads or a performance verdict. Use the installation route
for the source-build recipe and current backend prerequisites.

For cross-route tasks, preserve the earliest incorrect boundary. A custom op
needs tensor/schema correctness before compiler eligibility; graph replay needs
stream/address lifetimes before timing; distributed resume needs allocation and
state ownership before throughput tuning. Use eager CPU as a control where it
represents the same semantics; preserve a missing device check separately.

Cross-cutting failures are in [troubleshooting](references/troubleshooting.md).
[Repository coverage](references/source-directory-coverage.md) explicitly maps
all top-level source directories and public module families to their owners or
exclusions. [Readset](references/source-readset.json) distinguishes exact inspected
spans from tree inventory. [Script disposition](references/source-script-map.md)
explains bundled helpers and excluded source tooling.

Existing owners remain authoritative for their focused procedures:
[host memory management](../../../platforms/host/host-memory-management/SKILL.md)
and [DCP async save performance](../dcp-async-save-performance/SKILL.md).
Their source revisions and evidence stay independent; following a link does not
update their pins or qualify the current PyTorch snapshot.

Read [notices](references/notices.md) before redistribution. This InferRSI
package preserves the AREX operating-role, visibility and repository-license
fields in local-skill-v1 metadata. It does not imply deployment into a managed
DisCo installation. No TorchNPU/PyTorch compatibility pairing is inferred.
