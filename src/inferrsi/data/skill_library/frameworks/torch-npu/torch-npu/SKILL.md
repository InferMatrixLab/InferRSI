---
name: torch-npu
description: "Operate and diagnose TorchNPU on Ascend across installation, PrivateUse1 dispatch, operator development, memory and streams, graphs and compilation, HCCL, precision and profiling, with pinned source evidence and explicit backend limits."
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
