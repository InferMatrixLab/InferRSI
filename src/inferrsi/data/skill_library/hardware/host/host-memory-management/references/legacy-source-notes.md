# Retained historical source links

The former owner procedure cited the following live pages. They are retained
for provenance, not asserted as inspected or immutable sources in this update.
Some URL labels or API names came from the former procedure and may be stale.
No full revision, content hash, access date or license has been invented for them.

The new PyTorch and CPython readsets supersede their use for the corrected
asynchronous-copy, pinning and free-threading guidance. Former numeric bandwidth,
size, RAM-percentage, multiprocessing-time and NUMA-gain recommendations are
removed because no matching measurement scope supported universal use.

- [PyTorch CUDA semantics](https://pytorch.org/docs/1.2.0/notes/cuda.html)
- [PyTorch pinned memory DevLog](https://docs.pytorch.org/devlogs/eager/2026-08-09-pinned-memory-allocator/)
- [PyTorch nn API](https://pytorch.org/docs/main/torch_cuda_memory)
- [pinned memory Discourse thread](https://discuss.pytorch.org/t/when-to-set-pin-memory-to-true/19723/25)
- [pytorch/torch/utils/data/_utils/pin_memory.py](https://github.com/pytorch/pytorch/blob/main/torch/utils/data/_utils/pin_memory.py)
- [pin_memory().cuda() being slow](https://discuss.pytorch.org/t/why-is-tensor-pin-memory-cuda-significantly-slower/216122)
- [sync-free CUDA graph best practice](https://docs.nvidia.com/dl-cuda-graph/latest/torch-cuda-graph/sync-free-code.html)
- [PyTorch DevLog on hidden H2D syncs](https://docs.pytorch.org/devlogs/eager/2026-08-11-hidden-h2d-sync/)
- [Stack Overflow question on non_blocking H2D synchronization](https://stackoverflow.com/questions/79751502/when-does-non-blocking-h2d-copy-from-pinned-memory-in-pytorch-require-synchronization)
- [CUDA Streams documentation](https://pytorch.org/docs/main/generated/torch.cuda.Stream.html)
- [async H2D on side stream](https://discuss.pytorch.org/t/is-it-possible-that-pytorch-can-make-async-host-to-device-transfer-execute-on-side-stream-while-the-transferred-data-on-the-main-stream/223702)
- [PEP 703](https://peps.python.org/pep-0703/)
- [concurrent.futures.ProcessPoolExecutor](https://docs.python.org/3/library/concurrent.futures.html)
- [Python 3.13 release notes](https://dev.to/zackch/python-313-no-gil-what-you-need-to-know-352i)
- [Python 3.14 roadmap](https://dev.to/mechcloud_academy/unlocking-true-parallelism-a-developers-guide-to-free-threaded-python-3-14-175i)
- [NUMA affinity guide](https://tonyseah.medium.com/numa-numactl-and-taskset-a-practical-guide-for-ai-ml-engineers-0fbacb450f22)
- [NVIDIA hardware-coherent memory blog](https://developer.nvidia.com/blog/understanding-memory-management-on-hardware-coherent-platforms/)
- [Production-grade NUMA pinning guide](https://ssadaniowski.substack.com/i/198715659/numa-pinning-and-gpu-affinity)
- [CUDA semantics](https://pytorch.org/docs/master/notes/cuda.html)
- [Stack Overflow on CUDA device allocation](https://stackoverflow.com/questions/60593317/any-guarantees-that-torch-wont-mess-up-with-an-already-allocated-cuda-array)
