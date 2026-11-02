# Source notes: CUDA allocator and streams

Inspection date 2026-11-02. Repository `pytorch/pytorch` at `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457` (v2.15.0).
**F** is a pinned-source fact. **P** is an unrun procedure. Nothing was installed or executed.
Upstream BSD-style terms stay with the pinned LICENSE; these notes paraphrase and do not copy kernels.
GitHub's license API reports `NOASSERTION` for Ascend/pytorch even though `LICENSE` is present; that API value is not a legal conclusion.


| ID | Where | Finding |
| --- | --- | --- |
| F1 | [CUDAAllocatorConfig.h L217-L261](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/c10/cuda/CUDAAllocatorConfig.h#L217-L261) | Env order and the CUDA-specific key set. |
| F2 | [CUDAAllocatorConfig.h L306-L337](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/c10/cuda/CUDAAllocatorConfig.h#L306-L337) | Defaults: fraction 1.0, graph record-stream reuse false, reserve 1.125 only when set. |
| F3 | [CUDAAllocatorConfig.cpp L16-L28](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/c10/cuda/CUDAAllocatorConfig.cpp#L16-L28) | Unsupported expandable segments warn and return false. |
| F4 | [CUDACachingAllocator.h L141-L173](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/c10/cuda/CUDACachingAllocator.h#L141-L173) | `recordStream` versus pool routing versus `markCaptureBegin`. The comment names `use_mem_pool`, NCCL registration and Inductor warmup as pool users without capture. |
| F5 | [CUDAStream.h L11-L39](https://github.com/pytorch/pytorch/blob/31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457/c10/cuda/CUDAStream.h#L11-L39) | Three pools; 32-wide round-robin; aliasing blocks concurrency. |

P: deprecated split-size wrappers are not a tuned value. Host allocator reuse is a different pin.
