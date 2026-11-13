---
name: pytorch
description: "Operate and diagnose PyTorch installation, tensors and autograd, training and data, compilation and export, accelerator lifetimes, distributed execution, checkpointing, profiling and custom operators from pinned repository evidence."
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
[host memory management](../../../hardware/host/host-memory-management/SKILL.md)
and [DCP async save performance](../dcp-async-save-performance/SKILL.md).
Their source revisions and evidence stay independent; following a link does not
update their pins or qualify the current PyTorch snapshot.

Read [notices](references/notices.md) before redistribution. This InferRSI
package preserves the AREX operating-role, visibility and repository-license
fields in local-skill-v1 sidecars. It does not imply deployment into a managed
DisCo installation. No TorchNPU/PyTorch compatibility pairing is inferred.
