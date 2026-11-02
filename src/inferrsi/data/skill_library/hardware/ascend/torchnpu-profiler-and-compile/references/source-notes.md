# Source notes: profiler and compile hooks

Inspection date 2026-11-02. Repository `Ascend/pytorch` at `54e365d3e3614299bccd17f06916544c3880c9fc` (v26.2.0-pytorch2.14.0).
**F** is a pinned-source fact. **P** is an unrun procedure. Nothing was installed or executed.
Upstream BSD-style terms stay with the pinned LICENSE; these notes paraphrase and do not copy kernels.
GitHub's license API reports `NOASSERTION` for Ascend/pytorch even though `LICENSE` is present; that API value is not a legal conclusion.


| ID | Where | Finding |
| --- | --- | --- |
| F1 | [profiler.py L201-L236 and L132-L158](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/profiler/profiler.py#L201-L236) | Schedule fallback and export prerequisites. |
| F2 | [experimental_config.py L27-L79](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/profiler/experimental_config.py#L27-L79) | Level, metric and export names. |
| F3 | [trace_rule.py L10-L103](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/dynamo/trace_rule.py#L10-L103) | In-graph NPU APIs, `set_device` skip, guarded constant fold of `current_device`. |

P: default schedule function body is the PyTorch profiler when TorchNPU imports it; this note does not re-prove that identity beyond the symbol `_default_schedule_fn`. No trace file was written.
