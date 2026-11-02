# PyTorch and TorchNPU repo-to-skill distillation

Method source: AREX-Skill Creator sequence in `docs/disco-workflows.md`
(scope, ground, construct, verify), adapted to InferRSI the same way as the
Local Dream distillation. The previously recorded method commit
`ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6` was not re-fetched. DisCo was not
installed or executed. This note is construction context, not a measured result.

## Pins

| Repository | Immutable commit | Label |
| --- | --- | --- |
| pytorch/pytorch | `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` | tag `v2.15.0` |
| Ascend/pytorch | `54e365d3e3614299bccd17f06916544c3880c9fc` | tag `v26.2.0-pytorch2.14.0` |

GitHub `Ascend/pytorch` is the remote already used by the allocator skills.
A Gitee mirror was not read. `version.txt` at the TorchNPU tag lists torch
lines 2.15.0, 2.14.0 and 2.13.0. The tag name says pytorch 2.14.0. Those
strings are not a tested pair with PyTorch v2.15.0.

The v2.15 file `torch.compiler_cudagraph_trees.md` has SHA-256
`0dbfcef13ad6baea52c6e989eaf6561440c02a26a6ef667da850439d3a88c6a5`, the same
digest as the existing compiler card at `f15b476814ebc5eade36fb40512e379ebf79dd60`.
That is one-document identity. Inductor was not re-mined.

## What was distilled

Twelve registered skills and five dependency cards. Older owners were not
rewritten: host copy at v2.8.0, DCP async save, the CUDA-graph card, and
TorchNPU device/pinned allocators at `67511c53cd4c88014f6123de7097677e60e85faa`.

Status on every new skill is candidate / empirical validation `not_run`.
No benchmark, model run or device command was executed.

## Left unread

PyTorch c10d and NCCL, Inductor codegen, Dynamo guard implementation,
`CUDACachingAllocator.cpp`, `AcceleratorAllocatorConfig` bodies, FlexAttention
and SDPA selection bodies, quantization, autograd, MPS, XPU, Kineto and ATen
kernels.

TorchNPU allocator sources at the new tag, `npu/_graph_tree.py`, NPUGraph C++,
ACL/CANN, op_plugin kernels, HCCL transport, FSDP, pipelining, RPC and profiler
parsers. Tests present upstream were not run.
