---
name: torchnpu-hccl-process-groups
description: "Control TorchNPU HCCL process-group resume and reinit, and route uneven collectives through the NPU backend. Use for those control-plane contracts, not for fabric bandwidth or algorithm choice."
---

# TorchNPU HCCL process groups

Status: candidate. Empirical validation: **not_run**. Pin: `54e365d3e3614299bccd17f06916544c3880c9fc`.

Native HCCL algorithm selection remains [ascend-distributed-parallel](../ascend-distributed-parallel/SKILL.md) at its CANN pin. This skill is the TorchNPU Python wrapper only.

## Procedure

1. F: `is_hccl_available` is `"hccl" in Backend.backend_list`. P: that is a registry membership test, not a device or link probe.
2. F: `reinit_process_group(..., rebuild_link=False)` walks process groups that include the NPU device and calls `resume_hccl_comm`, then returns `None`. With `rebuild_link=True` (the default), if the backend string contains `hccl` it deletes a tcpstore key and calls `abort_hccl_comm("reinit")`, then returns the group. P: resume and abort are different completions. Do not treat a returned group as proof the new communicator is ready; the function does not show a subsequent create in the lines that were read.
3. F: uneven `reduce_scatter` and `all_gather`, and `_all_to_all_vc`, take the group's NPU backend. `_batch_isend_irecv` also resolves the group backend for the tensor device. P: a Python call reaching the backend is not an HCCL algorithm, topology or byte-count result.
4. F: registration of the distributed backend requires `torch_npu._C._distributed_c10d` first. P: the register function body in `registry/distributed.py` was not read.
5. F: `_comm_switch_nic` reads `os.environ["RANK"]`. P: a missing `RANK` fails closed at that call. NIC switching was not otherwise inspected.

## Limits

No multi-rank process was started. Transport, bandwidth and numerical collectives are not_run. PyTorch c10d at v2.15 was not mined; do not import NCCL advice from an unread file.
