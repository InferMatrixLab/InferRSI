# fastsafetensors distributed delivery contract

Source: [foundation-model-stack/fastsafetensors](https://github.com/foundation-model-stack/fastsafetensors/tree/219e2561a41ede2d5d8eba611c248bb0effbf580),
commit `219e2561a41ede2d5d8eba611c248bb0effbf580`, statically inspected on
2026-10-22. This resolves the owner's historical `219e256` prefix; it does not
replace that pin or revalidate its inherited loading/save claims.

License: [LICENSE:1-5](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/LICENSE#L1-L5)
identifies Apache License 2.0; the inspected implementation and test Python files also declare
`SPDX-License-Identifier: Apache-2.0`. This source attribution applies to this
slice, not the other sources in the multi-source owner.

## Caller → ownership/completion → collective

| Owner §9 clause | Pinned source readset | Source observation and boundary |
|---|---|---|
| Register files and keep collective order | [loader.py:175-201,237-258](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/loader.py#L175-L258), [file_buffer.py:14-28](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/file_buffer.py#L14-L28), [examples/run_parallel.py:49-60](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/examples/run_parallel.py#L49-L60) | CODE assigns a copier only to the designated rank. DOC/example requires identical method order on all ranks. File ownership and consumer tensor partition are separate decisions. |
| Whole tensor versus TP slice | [file_buffer.py:110-191](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/file_buffer.py#L110-L191), [tensor_factory.py:162-237](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/tensor_factory.py#L162-L237) | CODE routes dim -1 to broadcast; other dims use ceiling-sized rank slices and contiguous scatter inputs. The source clone/receive allocation is device-memory work; scatter is the collective. Uneven-shape collective acceptance is not established by this calculation. |
| Rank namespace and per-tensor completion | [frameworks/_torch.py:150-205](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/frameworks/_torch.py#L150-L205), [frameworks/_paddle.py:125-170](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/frameworks/_paddle.py#L125-L170) | CODE uses PyTorch `group_src`; Paddle maps group ranks to world ranks. Per-tensor wrappers synchronize the CUDA device when available. These facts do not qualify either backend on a local host. |
| Pipeline dispatch and incompatible modes | [parallel_loader.py:149-250](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/parallel_loader.py#L149-L250), [658-680](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/parallel_loader.py#L658-L680), [824-870](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/parallel_loader.py#L824-L870), [932-968](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/parallel_loader.py#L932-L968) | CODE gates coalescing on multi-rank PyTorch, positive limits and no resident predicate. It rejects per-rank filtering or borrowed tensors in distributed loader groups. `all_local=True` selects independent reads. The iterator delivers whole tensors, not automatic TP slices. |
| Coalescing boundaries and readiness | [file_buffer.py:208-305](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/file_buffer.py#L208-L305), [tensor_factory.py:47-98,162-171](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/tensor_factory.py#L47-L171) | CODE splits runs at file/owner, gaps, limits, alignment or empty tensors; the first oversized tensor is still a singleton. Source bytes must be ready before cloning. The run iterator preserves its final stream drain on early exit. |
| Byte transport and shared run storage | [frameworks/_torch.py:259-308](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/frameworks/_torch.py#L259-L308) | CODE validates adjacency, clones the source byte span, allocates a byte receive buffer, performs one async broadcast and waits on its work, then creates dtype/shape views. The source's stream-ordering comment is specific to NCCL/CUDA, not CPU/Gloo completion. A view can retain the complete run. Reduced call count is a mechanism, not a measured throughput result. |
| Output ownership and early close | [file_buffer.py:14-28,77-95](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/file_buffer.py#L14-L95), [tensor_factory.py:308-347](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/tensor_factory.py#L308-L347), [parallel_loader.py:731-792](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/fastsafetensors/parallel_loader.py#L731-L792), [docs/overview.md:61-69](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/docs/overview.md#L61-L69) | CODE/DOC distinguishes owning outputs from borrowed local views; close drains I/O and releases the factory's references. Pipeline iterator cleanup precedes loader close. Non-resident consumers must relocate each yield; retaining all views contradicts the budget contract. |

The relevant concrete call chains are:

```text
SafeTensorsFileLoader.add_filenames → owner-only copier → copy_files_to_device
  → FilesBufferOnDevice.get_tensor/get_sharded → LazyTensorFactory.shuffle
  → source clone or contiguous slices + receive allocation → group broadcast/scatter

ParallelLoader.iterate_weights → _consume_single_batch (coalescing eligibility)
  → FilesBufferOnDevice._iter_tensors → wait source ranges → owned byte run
  → TorchOp.broadcast_contiguous_run → work.wait → shared typed views
  → per-run/final stream drain → file-buffer close → iterator/loader cleanup
```

## Source tests inspected, not executed

- [test_broadcast_runs.py:17-219](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/tests/unit/test_broadcast_runs.py#L17-L219)
  supplies author tests for bounded source spans, mixed dtype/alignment, empty
  tensors, scalar values, chunking, overlap, residency and early close. It
  compares bytes after buffer/iterator close and checks run counts and memory
  counters; it does not measure performance.
- [test_subgroup.py:1-132](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/tests/unit/test_subgroup.py#L1-L132)
  defines four-rank, non-prefix subgroup broadcast/scatter/send-receive cases.
  Its Paddle Gloo subgroup case is skipped for a documented rendezvous issue.
  That skip is a source test restriction, not a local failure or validation.

Inspected supporting intent: [docs/overview.md:1-27](https://github.com/foundation-model-stack/fastsafetensors/blob/219e2561a41ede2d5d8eba611c248bb0effbf580/docs/overview.md#L1-L27).
Selected implementation ranges above establish the delivery mechanism. The
remaining runtime, native extension, device/backend compatibility, uneven
scatter, model integration, transport topology and performance are unverified
here. No source tests, model loads or accelerator runs were executed. Existing
§7 I/O and §8 saver evidence is carried forward rather than re-mined.

Completion terminology was cross-checked against the
[PyTorch 2.14 distributed operation contract](https://docs.pytorch.org/docs/2.14/distributed.html#synchronous-and-asynchronous-collective-operations):
CPU `wait()` blocks the process until completion, whereas CUDA `wait()` orders
the active stream. This distinction does not qualify this repository against
PyTorch 2.14 or extend its supported version range.
