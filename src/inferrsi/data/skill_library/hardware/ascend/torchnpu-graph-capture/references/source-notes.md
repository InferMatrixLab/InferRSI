# Source notes: NPUGraph capture

Inspection date 2026-11-02. Repository `Ascend/pytorch` at `54e365d3e3614299bccd17f06916544c3880c9fc` (v26.2.0-pytorch2.14.0).
**F** is a pinned-source fact. **P** is an unrun procedure. Nothing was installed or executed.
Upstream BSD-style terms stay with the pinned LICENSE; these notes paraphrase and do not copy kernels.
GitHub's license API reports `NOASSERTION` for Ascend/pytorch even though `LICENSE` is present; that API value is not a legal conclusion.


| ID | Where | Finding |
| --- | --- | --- |
| F1 | [graphs.py L844-L932](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/npu/graphs.py#L844-L932) | Sync, optional GC, both empty-cache calls, then capture. Single-capture comment. |
| F2 | [_config.py L5-L8](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/_compiler/_config.py#L5-L8) | Default false versus docstring "backward-compatible" true. |
| F3 | [graphs.py L607-L664](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/npu/graphs.py#L607-L664) | Capture modes and update gate. `capture_begin` passes `report_shape=True`. |
| F4 | [graphs.py L935-L967](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/npu/graphs.py#L935-L967) | `num_warmup_iters=3`. Docstring still says CUDA graph. |
| F5 | [utils/_graph_tree.py L386-L404](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/utils/_graph_tree.py#L386-L404) | Backend name `npugraphs` and Inductor monkeypatches. |

P: tree manager in `npu/_graph_tree.py` and the C++ capture path remain unread. Tests were not run.
