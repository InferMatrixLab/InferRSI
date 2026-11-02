# Source notes: AOTInductor

Inspection date 2026-11-02. Repository `pytorch/pytorch` at `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` (v2.15.0).
**F** is a pinned-source fact. **P** is an unrun procedure. Nothing was installed or executed.
Upstream BSD-style terms stay with the pinned LICENSE; these notes paraphrase and do not copy kernels.
GitHub's license API reports `NOASSERTION` for Ascend/pytorch even though `LICENSE` is present; that API value is not a legal conclusion.


| ID | Where | Finding |
| --- | --- | --- |
| F1 | [torch.compiler_aot_inductor.md L1-L100](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/docs/source/user_guide/torch_compiler/torch.compiler_aot_inductor.md#L1-L100) | Export, package, device choice, freezing hint, dynamic dim and dtype/stride rule. |
| F2 | [same document L112-L129](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/docs/source/user_guide/torch_compiler/torch.compiler_aot_inductor.md#L112-L129) | C++ path uses `c10::InferenceMode` and a second batch only on the dynamic dim. |
| F3 | [torch.compiler_dynamo_overview.md L1-L35](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/docs/source/user_guide/torch_compiler/torch.compiler_dynamo_overview.md#L1-L35) | Dynamo extracts FX; Inductor targets Triton or C++/OpenMP. Training dashboard is an upstream pointer only. |
| F4 | [torch.compiler_cudagraph_trees.md](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/docs/source/user_guide/torch_compiler/torch.compiler_cudagraph_trees.md) | SHA-256 matches the existing card's source digest. No new semantic extraction. |

P: `max_autotune` remains an unread implementation. No artifact was compiled.
