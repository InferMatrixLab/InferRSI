# Historical MindSpeed adaptive-memory case

Reference entry CR5. Documentation only; inspected 2026-10-15. This is a
historical NPU case, not a current implementation or compatibility claim.

## Provenance and permitted reuse

[Original document](https://gitcode.com/Ascend/MindSpeed/blob/core_r0.8.0/docs/features/adaptive-memory.md),
branch `core_r0.8.0`; page history displays `53193db8`, 2025-06-04. A full
immutable revision was not resolved. Retrieved HTML SHA-256:
`773d702b932534f96d037c07156604d7dd9e4c3b82f4a0a6e6e8ff70e5365eef`.
The actual document body was readable; the implementation named by it was not
retrieved. Source-license terms for this historical document were not verified;
retain attribution to Ascend/MindSpeed and link the source. Do not copy source
text/code or infer a license from the organization. This note paraphrases the
mechanism and records evidence limits; redistribution of adapted source
material requires license review.

## Incremental decision

The documented trigger is **unused NPU memory under full recomputation**.
Adaptive memory combines lossless tensor swapping, strategy generation/search,
SwapManager and allocator integration to choose how much state to retain versus
move to CPU. The document describes intercepting out-of-memory conditions via
PTA's `NPUPluggableAllocator`, allowing SwapManager to intervene. This is a
source design claim; the allocator and search implementation were not audited.

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
| CPU affinity | Document requires `npu-smi` and `lspci` to support binding; no package installation or affinity change is authorized by reading this case |
| Custom `torch.autograd.Function` integration | Some functions require `adapt_mem_func_wrapper`; named path `mindspeed/core/memory/adaptive_memory/adaptive_memory_function.py` remains implementation-unverified |

## Evidence quality

The document reports cropped GPT-175B experiments on eight NPUs. One comparison
uses `NL=8` for adaptive memory and `NL=3` for full recomputation. Its headline
percentage is not a controlled fixed-workload gain and is deliberately not
carried into coverage or performance claims. Other tables remain author reports;
no raw traces, correctness outputs or matched reruns were inspected.

Open: immutable full revision, license, allocator/wrapper implementation,
current torch/CANN/MindSpeed compatibility, transfer exposure, whole-model
correctness and measured end-to-end benefit. No hardware run or failure
injection was performed. Do not treat this case as an implementation recipe.
