# Hardware skill navigation

The existing **22 registered owners** comprise 14 Ascend, 3 CUDA and 5 host
skills. Start with the question below, then read the selected procedure,
`metadata.json` and its source references. All 22 remain **candidate** with
empirical validation **not_run**.

The [source inventory](source-inventory.json) describes the evidence actually
retained by each owner: source channel, inspection depth, revision precision,
recorded reading date, license qualifications and gaps. It is a static
navigation aid, not another registry or coverage matrix. The
[Reference Matrix](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/reference-matrix.md)
and [SearchSpace Matrix](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/searchspace-matrix.md)
retain source and coverage authority.

## Read the source depth correctly

A **direct implementation read** covers the cited paths/ranges only; wrapper,
callback and test code do not establish the native implementation they call.
An **upstream skill/document import** retains instructions or reported results,
even when its source is a code repository. A **mirror** preserves a copy's
lineage and license limits, not independent corroboration. A **supplied pack**
may contain a substantive implementation or paper readset, but its supplier's
reading date is not a fresh local reread.

This inventory reviews local records on 2026-10-30 and performs no new upstream
reads. Historical prefixes, unknown dates/licenses and independent source
versions remain explicit. A resolved full SHA or a whole-file hash proves
identity, not full semantic inspection. The 2026-10-30 PyTorch/CPython readsets
under host memory are distinct from that owner's older Ascend readset and
unrevalidated historical links. Source and package checks establish no measured
gain, compatible combined stack or new empirical coverage.

## Ascend

| Question / owner | Retained source depth and principal boundary |
| --- | --- |
| [ACLGraph capture/replay](ascend/ascend-aclgraph-capture-replay/SKILL.md) | Supplied bounded vLLM-Ascend wrapper/docs/test readset; caller ownership and other runtime owners remain separate |
| [Device health](ascend/ascend-device-health/SKILL.md) | MindIE-SD and profiling skill guidance; environment observations are not a driver audit |
| [Distributed parallelism](ascend/ascend-distributed-parallel/SKILL.md) | Inherited strategy documents plus directly read communication-test wrappers; native collective/transport code not covered by that wrapper slice |
| [Graph-mode configuration](ascend/ascend-graph-mode/SKILL.md) | GitCode-mirrored skill documentation; no retained TorchAir implementation ledger in this state |
| [Model adaptation](ascend/ascend-model-adaptation/SKILL.md) | Historical vLLM-Ascend lesson documents; separate from the newer ACLGraph wrapper pin |
| [Operator profiling](ascend/ascend-operator-profiling/SKILL.md) | Imported mirrored profiling procedure; named summary helper is not bundled |
| [Operator tuning](ascend/ascend-operator-tuning/SKILL.md) | Mirrored PyPTO skill/playbook distillation; reported analyzer behavior and cases are not native validation |
| [Optimization casebook](ascend/ascend-optimization-casebook/SKILL.md) | Upstream skill-derived cases and inferences; no independent local reruns |
| [Performance analysis](ascend/ascend-performance-analysis/SKILL.md) | MindIE-SD guidance plus direct CannBot workflow/callback/helper reads; callback completion is not numerical evidence |
| [Video diffusion](ascend/ascend-video-diffusion-optimization/SKILL.md) | First-hand workflow/field notes, explicitly non-reproducible as published |
| [AscendC tiling](ascend/ascendc-tiling-design/SKILL.md) | Mirrored skill/reference distillation; chip-specific formulas and unwritten operator classes retain their limits |
| [CANN attribution and overlap](ascend/cann-attribution-overlap/SKILL.md) | Supplied skill/reference/script pack; import and later revisions remain separate, original lineage equivalence unknown |
| [TorchNPU device memory](ascend/torchnpu-device-memory-lifecycle/SKILL.md) | Supplied bounded allocator/caller/docs/test readset; device HBM only |
| [TorchNPU pinned host memory](ascend/torchnpu-pinned-host-memory-lifecycle/SKILL.md) | Supplied bounded host allocator/copy/docs/test readset; base-ATen and external-owner boundaries remain open |

## CUDA

| Question / owner | Retained source depth and principal boundary |
| --- | --- |
| [Attention bottlenecks](cuda/diagnose-attention-bottlenecks/SKILL.md) | Supplied versioned FlashAttention paper readset; linked implementations were not opened |
| [Host-overhead profiling](cuda/host-overhead-profiling/SKILL.md) | TensorRT-LLM skill methodology; named analysis scripts/reference are not bundled |
| [Hopper kernel reasoning](cuda/reason-hopper-kernels/SKILL.md) | KernelWiki header/body screening plus selected direct DeepGEMM/CUTLASS and NVIDIA document reads; unmined bodies, architecture exclusions and license discrepancies stay explicit |

## Host

| Question / owner | Retained source depth and principal boundary |
| --- | --- |
| [Cgroup resource controls](host/cgroup-resource-controls/SKILL.md) | Supplied Linux interface-document research; rolling-page revision and target-system behavior remain unknown |
| [Host memory and transfers](host/host-memory-management/SKILL.md) | Direct pinned PyTorch copy/allocator readset, CPython documentation and separate Ascend descriptor case; historical links retained only as lineage |
| [Host-overhead optimization](host/host-overhead-optimization/SKILL.md) | TensorRT-LLM skill import plus bounded DeepInfer code case and method-owned paper guidance; local case is linked despite an empty sidecar readset list |
| [OS process placement](host/os-process-placement/SKILL.md) | Historical skill/configuration guidance plus a direct llama.cpp NUMA/thread readset; no optimal affinity or thread count demonstrated |
| [Storage I/O measurement](host/storage-io-measurement/SKILL.md) | Supplied fio/sysstat documentation and job-example research; no tool-engine or loader implementation audit |

Directory placement describes ownership, not portability. Host RAM and device
HBM are different domains; H2D, IPC and local stream ordering do not establish
Network coverage. Read mixed-source licenses per slice: an outer README license
does not clear a mirrored UNKNOWN declaration or a third-party payload.

## Maintain this view

Keep complete procedures and source ledgers with their existing owners. Update
only the affected inventory row and navigation when evidence changes; preserve
original inspection dates, unknowns and candidate states. Do not turn source
counts into quality scores, replace the two matrices, or duplicate full
readsets here. Use the [library entry](../README.md) for discovery and packaging
contracts.
