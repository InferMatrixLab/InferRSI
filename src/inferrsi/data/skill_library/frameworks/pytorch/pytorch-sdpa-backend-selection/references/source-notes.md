# Source notes: SDPA backend selection

Inspection date 2026-11-02. Repository `pytorch/pytorch` at `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` (v2.15.0).
**F** is a pinned-source fact. **P** is an unrun procedure. Nothing was installed or executed.
Upstream BSD-style terms stay with the pinned LICENSE; these notes paraphrase and do not copy kernels.
GitHub's license API reports `NOASSERTION` for Ascend/pytorch even though `LICENSE` is present; that API value is not a legal conclusion.


| ID | Where | Finding |
| --- | --- | --- |
| F1 | [__init__.py L74-L174](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/torch/nn/attention/__init__.py#L74-L174) | Five named backends. Exit restores the previous set. `set_priority` appends the old order after the user list. |
| F2 | [__init__.py L121-L153 versus L154-L174](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/torch/nn/attention/__init__.py#L121-L174) | Docstring exit text and the `finally` block disagree. The code path is the restore. |
| F3 | [_registry.py L61-L137](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/torch/nn/attention/_registry.py#L61-L137) | Register does not activate. Activate restores first. Restore removes a handle or warns. |
| F4 | [sdp_utils.h](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/aten/src/ATen/native/transformers/cuda/sdp_utils.h) and [sdp_utils_cpp.h L65](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/aten/src/ATen/native/transformers/sdp_utils_cpp.h#L65) | Selection is declared. The body was not in the inspected headers. |

P: shape, dtype, mask and GQA eligibility remain unread kernel constraints.
