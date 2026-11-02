# Source notes: PrivateUse1 registration

Inspection date 2026-11-02. Repository `Ascend/pytorch` at `54e365d3e3614299bccd17f06916544c3880c9fc` (v26.2.0-pytorch2.14.0).
**F** is a pinned-source fact. **P** is an unrun procedure. Nothing was installed or executed.
Upstream BSD-style terms stay with the pinned LICENSE; these notes paraphrase and do not copy kernels.
GitHub's license API reports `NOASSERTION` for Ascend/pytorch even though `LICENSE` is present; that API value is not a legal conclusion.


| ID | Where | Finding |
| --- | --- | --- |
| F1 | [backend.py L46-L66](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/_init/registry/backend.py#L46-L66) | Rename, device module, generated methods, five excluded quantized dtypes. |
| F2 | [backend.py L6-L23](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/_init/registry/backend.py#L6-L23) | Profiler alias and the 2.12 comment. |
| F3 | [registry_manager.py L70-L87](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/torch_npu/_init/registry/registry_manager.py#L70-L87) | Must not initialize NPU runtime. Missing `torch.npu` is a hard error. |
| F4 | [version.txt](https://github.com/Ascend/pytorch/blob/54e365d3e3614299bccd17f06916544c3880c9fc/version.txt) | Lines 2.15.0, 2.14.0, 2.13.0 only. |

P: CANN package check and native kernels were not inspected.
