# Unread at TorchNPU `54e365d3e3614299bccd17f06916544c3880c9fc`

Tag name `v26.2.0-pytorch2.14.0`. `version.txt` lists buildable torch lines `2.15.0`, `2.14.0` and `2.13.0`. Those facts are not a tested pair with PyTorch `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457`.

| Area | What was seen | Not claimed |
| --- | --- | --- |
| Device and pinned-host allocators | Existing skills at `67511c53cd4c88014f6123de7097677e60e85faa` | Not re-read at this tag. Line numbers there are not confirmed here. |
| `torch_npu/npu/_graph_tree.py` | 2617 lines located | Tree-manager semantics not mined. Only `utils/_graph_tree.py` registration was read. |
| `NPUGraph` C++ / ACL runtime | Python calls `super().capture_begin` | Capture implementation and CANN behavior unread |
| op_plugin and native kernels | Not in the inspected file set; `third_party/torch-mlir` submodule was skipped by the clone | No kernel coverage |
| HCCL / csrc distributed | Python wrapper only | Transport, algorithm selection and bandwidth unread |
| FSDP, pipelining, RPC | Directories exist | Unread |
| Profiler parsers | `experimental_config.py` names levels and metrics | CSV interpretation and msprof execution unread |
| Tests | Present in the tree | Not run |

Gitee mirrors were not used. GitHub `Ascend/pytorch` is the remote this checkout used.
