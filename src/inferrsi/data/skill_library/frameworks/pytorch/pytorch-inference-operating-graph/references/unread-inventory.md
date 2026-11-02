# Unread or not re-mined at PyTorch `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457`

Located during the tree listing or fetched only for identity. These are not extracted procedures.

| Area | What was seen | Why it is not a skill claim |
| --- | --- | --- |
| c10d, ProcessGroupNCCL, functional collectives, symmetric memory | `torch/distributed/` exists | No `distributed_c10d.py` body was read at this pin |
| Inductor codegen, Triton templates, `max_autotune` implementation | `torch/_inductor/config.py` was checked out and not mined; the AOTI doc names the flag | Config surface is not a tuning result |
| Dynamo guards and bytecode rewriter | Overview document only | Guard implementation unread; existing compiler card keeps its own pin |
| `CUDACachingAllocator.cpp` and `AcceleratorAllocatorConfig` bodies | Header shims deprecate `max_split_size` onto the shared config | Numeric split and GC semantics were not re-derived |
| Host caching allocator | Left with the v2.8.0 owner | v2.15 host copy path was not re-read |
| FlexAttention, SDPA CUDA selection function | Headers declare `select_sdp_backend`; Python context manager was read | Kernel choice for a shape is not established |
| Quantization, torchao, ONNX, MPS, XPU, MTIA, functorch | Directories exist under `torch/` | Out of this readset |
| Kineto, CUPTI, CUDA graph runtime | Profiler Python and one CUDA-graph document | Native collectors and capture runtime unread |
| Autograd engine and AMP | `c10::InferenceMode` appears in the AOTI C++ example | Mode implementation unread |

Candidate status stays `not_run`. Absence from this list is not coverage.
