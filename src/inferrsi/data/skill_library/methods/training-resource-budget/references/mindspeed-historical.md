# Historical MindSpeed adaptive-memory case

Reference entry CR5. Initial documentation inspection: 2026-10-15. Historical
source follow-up: 2026-10-30. This remains a source-derived candidate with no
current runtime or compatibility qualification.

## Provenance and permitted reuse

[Original document](https://gitcode.com/Ascend/MindSpeed/blob/core_r0.8.0/docs/features/adaptive-memory.md),
branch `core_r0.8.0`; the 2026-10-15 inspection recorded page history
`53193db8`, 2025-06-04. Full revision, license and implementation were unresolved
at that inspection. Retrieved HTML SHA-256:
`773d702b932534f96d037c07156604d7dd9e4c3b82f4a0a6e6e8ff70e5365eef`.
The document body was readable then; its named implementation was not retrieved.

The 2026-10-30 follow-up resolved the original page's commit link to
[`53193db8bf5def407c4041a9beb3f4c9e9773daf`](https://gitcode.com/Ascend/MindSpeed/commit/53193db8bf5def407c4041a9beb3f4c9e9773daf).
The official Ascend/MindSpeed [GitHub commit](https://github.com/Ascend/MindSpeed/commit/53193db8bf5def407c4041a9beb3f4c9e9773daf)
has the same identity, the `!2378` README-update message and commit timestamp
`2025-06-04T04:43:14Z`. The pinned document and bounded implementation were read
at that revision; the [source readset](mindspeed-source-readset.md) distinguishes
those new observations from the original HTML snapshot. The snapshot hash is
retained as historical evidence, not claimed to hash the fetched Markdown.

Historical license evidence is the same pin's [root LICENSE](https://github.com/Ascend/MindSpeed/blob/53193db8bf5def407c4041a9beb3f4c9e9773daf/LICENSE):
BSD-3-Clause terms apply by default unless otherwise noted, with separate
third-party terms for identified files. The adaptive-memory document has no
separate license notice; `docs/LICENSE` is absent at this pin. The README's MIT
badge does not replace the root terms, and a later branch's documentation license
does not resolve historical rights. Attribution remains Ascend/MindSpeed, with
Bytedance, Huawei and NVIDIA copyright notices retained in the linked license.
This note independently paraphrases mechanisms; no upstream code or prose is
copied or adapted into an executable helper.

## Incremental decision

The documented trigger is **unused NPU memory under full recomputation**.
The document describes lossless tensor swapping, strategy generation/search,
SwapManager and allocator integration to choose how much state to retain versus
move to CPU. The document describes intercepting out-of-memory conditions via
PTA's `NPUPluggableAllocator`, allowing SwapManager to intervene. This is a
source design claim. The bounded source observations below confirm the allocator
callback path, not the complete search algorithm or whole-model losslessness.

Derived decision: assess retained activation capacity, recomputation work and
NPU↔CPU transfer exposure together. Less recomputation can spend host RAM and
host/device bandwidth. This does not demonstrate a network optimization, nor
a guarantee that OOM interception makes arbitrary workloads safe.

## Historical configuration boundary

| Surface documented at this branch | Constraint |
|---|---|
| `--adaptive-memory-optimization` | Historical opt-in flag, not a recommendation for current releases |
| Full recomputation; adaptive selective recomputation; `swap-attention`; `recompute-in-bubble` | Documented incompatible combinations; do not combine policies merely because their memory objectives overlap |
| Memory-fragmentation optimization | Both modify PyTorch memory management; document says an assertion rejects simultaneous enablement |
| CPU affinity | Document names `npu-smi` and `lspci`; the source has additional topology/tool and SoC conditions below |
| Custom `torch.autograd.Function` integration | The document names `adapt_mem_func_wrapper`; its pinned implementation accepts a `torch.autograd.Function` subclass and selects profiling, recomputation, swap or the original `.apply` by phase/action |

## Pinned implementation decisions

Use the [exact paths and line ranges](mindspeed-source-readset.md) for these
observations, all inspected 2026-10-30 at the historical revision above.

1. **Check effective selection before allocator assumptions.** `arguments.py`
   rejects adaptive recomputation, configured `recompute_granularity` or
   `recompute_method`, `recompute_activation_function`, `swap_attention`,
   `recompute_in_bubble`, memory fragmentation and `ampipe_degree > 1`.
   Separately, `megatron_adaptor.py` only installs the adaptive-memory wrappers
   and allocator when the flag is true and adaptive recomputation, fragmentation,
   swap-attention and `smart_swap` are false. The `smart_swap` exclusion is a
   dispatch guard, not the same validation assertion. A present flag alone does
   not establish that this policy was selected.
2. **Treat the allocator as a process runtime dependency.** That dispatch branch
   invokes `change_allocator()`, whose builder loads the historical C++ extension.
   It supplies `my_malloc`/`my_free` to TorchNPU's `NPUPluggableAllocator`, changes
   the current allocator and installs init/reset/stat callbacks. The builder
   depends on PyTorch/TorchNPU headers and links `torch_npu`; API names alone do
   not establish compatibility with another wheel or CANN stack.
3. **Bound OOM rescue to its captured state.** After ordinary allocation/cache
   attempts fail, the C++ allocator calls `common.swap_out_by_size(size)` and
   retries. `common.py` routes to the adaptive-memory manager under this flag.
   Its saved-tensor hooks track eligible tensors; rescue moves shared storage
   through pinned CPU memory and restores it for unpack. The manager returns
   false when no tracked tensor is eligible, and the allocator retains an OOM
   error path. This mechanism does not promise recovery for arbitrary allocations
   or unlimited host capacity. Charge shared storage once and account for its
   return before the backward consumer, rather than counting tensor views as
   independent savings.
4. **Check the historical affinity branch and topology.** Setup calls `bind_cpus`
   only when `acl.get_soc_name()` contains `910A` or `910B`. The helper queries
   `npu-smi`, `lspci` and `lscpu`, then sets process affinity through `psutil`.
   It derives NUMA CPU ranges from `lscpu`, uses a contiguous device-ID range,
   and assigns CPUs per device from a historical `ratio=0.5` default or
   `CPU_BINDING_NUM`. These are source assumptions, not a recommended CPU share.
   Before separate authorized reuse, reconcile visible device numbering, parsed
   topology and granted CPU affinity; command presence alone is insufficient.
   Reading this case authorizes no package installation or affinity change.

## Evidence quality

The document reports cropped GPT-175B experiments on eight NPUs. One comparison
uses `NL=8` for adaptive memory and `NL=3` for full recomputation. Its headline
percentage is not a controlled fixed-workload gain and is deliberately not
carried into coverage or performance claims. Other tables remain author reports;
no raw traces, correctness outputs or matched reruns were inspected.

Still open: current torch/TorchNPU/CANN/MindSpeed compatibility, complete strategy
search and cache behavior, actual transfer exposure, whole-model correctness and
measured end-to-end benefit. The historical full revision and default license
terms are now recoverable; the selected allocator, wrapper and affinity paths
are source observations only. No hardware run or failure injection was performed.
