# Source notes: streams and events

Inspection date 2026-11-02. Repository `Ascend/pytorch` at `54e365d3e3614299bccd17f06916544c3880c9fc` (v26.2.0-pytorch2.14.0).
**F** is a pinned-source fact. **P** is an unrun procedure. Nothing was installed or executed.
Upstream BSD-style terms stay with the pinned LICENSE; these notes paraphrase and do not copy kernels.
GitHub's license API reports `NOASSERTION` for Ascend/pytorch even though `LICENSE` is present; that API value is not a legal conclusion.


| ID | Where | Finding |
| --- | --- | --- |
| F1 | [streams.py L42-L54 and L179-L189](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/npu/streams.py#L42-L54) | `wait_stream` is wait-on-recorded-event. Event record is same-device; wait is cross-device. |
| F2 | [streams.py L113-L171](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/npu/streams.py#L113-L171) | External stream capability table and AsyncTaskQueue rationale as written in the docstring. |

P: the task queue implementation was not opened. Allocator `recordStream` rules remain at the older pin.
