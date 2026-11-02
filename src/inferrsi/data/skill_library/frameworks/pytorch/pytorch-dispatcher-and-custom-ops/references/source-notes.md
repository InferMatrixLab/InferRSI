# Source notes: dispatcher and custom ops

Inspection date 2026-11-02. Repository `pytorch/pytorch` at `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` (v2.15.0).
**F** is a pinned-source fact. **P** is an unrun procedure. Nothing was installed or executed.
Upstream BSD-style terms stay with the pinned LICENSE; these notes paraphrase and do not copy kernels.
GitHub's license API reports `NOASSERTION` for Ascend/pytorch even though `LICENSE` is present; that API value is not a legal conclusion.


| ID | Where | Finding |
| --- | --- | --- |
| F1 | [Dispatcher.h L45-L70](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/aten/src/ATen/core/dispatch/Dispatcher.h#L45-L70) | Listeners observe `def` registration and deregistration. The comment says `impl` and `fallback` do not emit those events. |
| F2 | [DispatchKey.h PrivateUse1, BackendSelect, PythonDispatcher](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/c10/core/DispatchKey.h) | The key list contains `PrivateUse1` and `AutocastPrivateUse1`. `BackendSelect` is documented for calls that need a backend choice. `PythonDispatcher` is described as intercepting the key from Python and as higher priority than a neighboring key. Full fallthrough order was not re-derived. |
| F3 | [custom_ops.py custom_op docstring](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/torch/_library/custom_ops.py#L80-L113) | Name, mutation list, device types, inferred schema and tags are the registration contract. `unknown` mutations are pessimistic. `out` tags do not support autograd. |

P: confirm the installed PyTorch matches `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` before relying on a tag or key. No kernel was compiled.
