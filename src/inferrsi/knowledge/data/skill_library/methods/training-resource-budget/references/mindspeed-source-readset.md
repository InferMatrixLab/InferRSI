# MindSpeed historical source readset

Source: [Ascend/MindSpeed](https://github.com/Ascend/MindSpeed), historical
`core_r0.8.0` document commit
`53193db8bf5def407c4041a9beb3f4c9e9773daf`. Inspected 2026-10-30.
The [historical case](mindspeed-historical.md) retains the separate 2026-10-15
documentation inspection and original HTML hash.

## Identity and rights

- The [original GitCode page](https://gitcode.com/Ascend/MindSpeed/blob/core_r0.8.0/docs/features/adaptive-memory.md)
  links its abbreviated history entry to the [full commit](https://gitcode.com/Ascend/MindSpeed/commit/53193db8bf5def407c4041a9beb3f4c9e9773daf).
  The official [GitHub commit API](https://api.github.com/repos/Ascend/MindSpeed/commits/53193db8bf5def407c4041a9beb3f4c9e9773daf)
  reports that SHA, `!2378` README-update message and timestamp
  `2025-06-04T04:43:14Z`. The branch name remains a moving reference; every source
  link below uses the recovered full revision.
- [Root LICENSE, lines 1–34](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/LICENSE#L1-L34):
  default BSD-3-Clause terms unless otherwise noted, including Bytedance, Huawei
  and NVIDIA attribution. The rest of the file supplies identified third-party
  exceptions; do not relabel the entire repository with a single guessed license.
  No separate license notice appears in the selected adaptive-memory document.
  The [historical `docs/LICENSE` path](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/docs/LICENSE)
  returned 404. No later license is substituted for this pin.
- [README](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/README.md#L901-L917),
  version table only: historical Core/PyTorch and in-development stack entries,
  not a complete frozen runtime stack. Its MIT badge near the beginning is not
  the inspected root license text. [Package version](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/setup.py#L11-L16)
  is `0.8.0`; `setup.py` was read, not executed.

## Bounded implementation reads

Paths are relative to that repository. Listed sections support the stated
decision only; surrounding framework internals and the full solver are not
audited.

| Pinned source | Inspected section | Observation used by the owner |
|---|---|---|
| [docs/features/adaptive-memory.md](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/docs/features/adaptive-memory.md) | Whole short document | Trigger, mechanism attribution, exclusions, wrapper requirement, affinity prerequisites and mismatched-layer performance table |
| [mindspeed/arguments.py](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/arguments.py#L353-L354) | Flag 353–354; [validation 839–849](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/arguments.py#L839-L849) | Default-off flag; explicit rejection of conflicting configurations, including ampipe and activation recomputation |
| [mindspeed/megatron_adaptor.py](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/megatron_adaptor.py#L639-L656) | 639–656; adaptation call 1077 | Effective selection guard, including `smart_swap`; allowed layer and setup-wrapper registration; allocator replacement |
| [mindspeed/core/memory/adaptive_recomputing/pluggable_allocator_adpator.py](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/core/memory/adaptive_recomputing/pluggable_allocator_adpator.py) | Whole 24-line adapter | Shared historical allocator builder, allocation/free symbols and current-allocator/stat callback setup |
| [mindspeed/op_builder/adaptive_recomputing_builder.py](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/op_builder/adaptive_recomputing_builder.py) | Whole short builder; `op_builder/__init__.py` import mapping | Extension source, PyTorch/TorchNPU includes and `torch_npu` link dependency |
| [mindspeed/ops/csrc/pluggable_allocator/adaptive_recomputing/NpuCachingCustomAllocator.cpp](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/ops/csrc/pluggable_allocator/adaptive_recomputing/NpuCachingCustomAllocator.cpp#L44-L53) | Allocation forwarding 44–53 | Exported allocator reaches the device allocator defined in the header |
| [mindspeed/ops/csrc/pluggable_allocator/adaptive_recomputing/NpuCachingCustomAllocator.h](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/ops/csrc/pluggable_allocator/adaptive_recomputing/NpuCachingCustomAllocator.h#L548-L678) | Allocation/retry/callback/OOM 548–678; exports 1572–1592 | Failed cache/allocation attempts reach Python `common.swap_out_by_size`; false ends rescue; OOM remains possible |
| [mindspeed/core/memory/common.py](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/core/memory/common.py) | Whole 11-line router | Adaptive flag selects adaptive-memory rather than adaptive-recomputation SwapManager |
| [mindspeed/core/memory/adaptive_memory/adaptive_memory_swap_manager.py](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/core/memory/adaptive_memory/adaptive_memory_swap_manager.py#L231-L378) | Copy state 25–84; eligibility 120–141; rescue pack/unpack, shared storage and selection 231–378; layer hooks 375–415 | Rescue concerns tracked eligible saved tensors; shared-storage CPU move/restore, pinned allocation and false result when none is eligible |
| [mindspeed/core/memory/adaptive_memory/adaptive_memory_opt.py](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/core/memory/adaptive_memory/adaptive_memory_opt.py#L189-L213) | Setup 189–213 | Optimizer/profiling hooks; CPU binding conditional on 910A/910B SoC; cache loader identified only |
| [mindspeed/core/memory/adaptive_memory/cpu_binder.py](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/core/memory/adaptive_memory/cpu_binder.py) | Whole 110-line helper | `npu-smi` → PCIe → `lspci` NUMA → `lscpu` CPU ranges; contiguous-device assumption, historical ratio/env selection and process-affinity mutation |
| [mindspeed/core/memory/adaptive_memory/adaptive_memory_function.py](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/mindspeed/core/memory/adaptive_memory/adaptive_memory_function.py#L99-L136) | Saved-tensor wrapper and action dispatch 99–136 | Explicit autograd-subclass integration; phase/action-specific profiling, swap, checkpoint or original `.apply` |

The solver, policy cache, complete prefetch schedule, framework allocator ABI,
device kernels and model training results remain outside this bounded extraction.
The builder and binder are referenced for their prerequisites; neither is copied,
imported or executed by this skill. No current-stack or numerical qualification
follows from source inspection.
