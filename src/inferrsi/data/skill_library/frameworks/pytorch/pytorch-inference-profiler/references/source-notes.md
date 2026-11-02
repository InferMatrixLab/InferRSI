# Source notes: PyTorch profiler

Inspection date 2026-11-02. Repository `pytorch/pytorch` at `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` (v2.15.0).
**F** is a pinned-source fact. **P** is an unrun procedure. Nothing was installed or executed.
Upstream BSD-style terms stay with the pinned LICENSE; these notes paraphrase and do not copy kernels.
GitHub's license API reports `NOASSERTION` for Ascend/pytorch even though `LICENSE` is present; that API value is not a legal conclusion.


| ID | Where | Finding |
| --- | --- | --- |
| F1 | [profiler.py L949-L1031](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/torch/profiler/profiler.py#L949-L1031) | Schedule phases and the warmup warning. |
| F2 | [profiler.py L322-L329](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/torch/profiler/profiler.py#L322-L329) and [L386-L398](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/torch/profiler/profiler.py#L386-L398) | Shape tracing retains tensors. PrivateUse1 is a code branch beside CUDA, XPU, MTIA and HPU. |
| F3 | [profiler.py L1042-L1073](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/torch/profiler/profiler.py#L1042-L1073) | Default export name contains hostname and pid. |

P: no chrome trace, kineto file or timing table was produced.
