---
name: torchnpu-inference-operating-graph
description: "Route a TorchNPU inference question to PrivateUse1 registration, NPU graph capture, streams, HCCL process-group control or profiler and compile hooks. Use before combining those notes with the older allocator skills."
---

# TorchNPU inference operating graph

Status: candidate. Empirical validation: **not_run**. Pin: `Ascend/pytorch` `54e365d3e3614299bccd17f06916544c3880c9fc` (tag `v26.2.0-pytorch2.14.0`). DisCo was not executed.

## Choose an owner

| Question | Owner | Pin |
| --- | --- | --- |
| PrivateUse1 renamed to `npu`, generated methods, dtype exclusions | [torchnpu-privateuse1-dispatch](../torchnpu-privateuse1-dispatch/SKILL.md) | `54e365d3e3614299bccd17f06916544c3880c9fc` |
| NPUGraph capture, pools, replay, update | [torchnpu-graph-capture](../torchnpu-graph-capture/SKILL.md) | `54e365d3e3614299bccd17f06916544c3880c9fc` |
| Managed versus external streams and events | [torchnpu-streams-and-events](../torchnpu-streams-and-events/SKILL.md) | `54e365d3e3614299bccd17f06916544c3880c9fc` |
| HCCL reinit, resume or uneven collectives | [torchnpu-hccl-process-groups](../torchnpu-hccl-process-groups/SKILL.md) | `54e365d3e3614299bccd17f06916544c3880c9fc` |
| Profiler levels or Dynamo trace rules | [torchnpu-profiler-and-compile](../torchnpu-profiler-and-compile/SKILL.md) | `54e365d3e3614299bccd17f06916544c3880c9fc` |
| Device HBM allocator lifetime | [torchnpu-device-memory-lifecycle](../torchnpu-device-memory-lifecycle/SKILL.md) | `67511c53cd4c88014f6123de7097677e60e85faa` |
| Pinned host RAM | [torchnpu-pinned-host-memory-lifecycle](../torchnpu-pinned-host-memory-lifecycle/SKILL.md) | same older pin |
| vLLM-Ascend ACLGraph wrapper | [ascend-aclgraph-capture-replay](../ascend-aclgraph-capture-replay/SKILL.md) | `8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf` |
| TorchAir graph path | [ascend-graph-mode](../ascend-graph-mode/SKILL.md) | `e1118e8b0fc1b95190ab53b732c0872989550e20` |
| PyTorch CUDA SDPA, allocator, profiler, AOTI | [pytorch-inference-operating-graph](../../../frameworks/pytorch/pytorch-inference-operating-graph/SKILL.md) | `v2.15.0`, not a tested pair |

F: `version.txt` at this tag lists torch lines 2.15.0, 2.14.0 and 2.13.0 as versions the build script can be asked for. The tag name says pytorch 2.14.0. P: do not treat either string as proof that this commit was built or tested with PyTorch `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457`.

Allocator line numbers from the October pin were not re-checked. [Unread inventory](references/unread-inventory.md) lists the native graph runtime, HCCL transport and kernel sources.
