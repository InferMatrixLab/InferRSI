# Source notes: HCCL process groups

Inspection date 2026-11-02. Repository `Ascend/pytorch` at `54e365d3e3614299bccd17f06916544c3880c9fc` (v26.2.0-pytorch2.14.0).
**F** is a pinned-source fact. **P** is an unrun procedure. Nothing was installed or executed.
Upstream BSD-style terms stay with the pinned LICENSE; these notes paraphrase and do not copy kernels.
GitHub's license API reports `NOASSERTION` for Ascend/pytorch even though `LICENSE` is present; that API value is not a legal conclusion.


| ID | Where | Finding |
| --- | --- | --- |
| F1 | [distributed_c10d.py L347-L397](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/distributed/distributed_c10d.py#L347-L397) | Availability test; resume returns None; abort path returns the group. |
| F2 | [distributed_c10d.py L415-L532](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/distributed/distributed_c10d.py#L415-L532) | Uneven collectives and all_to_all_vc use the NPU backend object. |
| F3 | [registry_manager.py L89-L107](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/_init/registry/registry_manager.py#L89-L107) | Distributed registration precondition. The callee was not read. |

P: HCCL C++ and CANN transport are out of scope for this readset.
