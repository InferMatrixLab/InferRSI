# DCP source and version boundaries

Inspected 2026-10-15. Scope: asynchronous saving/staging only, plus directly
called storage-cache and thread-executor code; not a distributed restore audit.

## Documentation matched against implementation

- [Official recipe](https://docs.pytorch.org/tutorials/recipes/distributed_async_checkpoint_recipe.html):
  retrieved page identifies tutorials `2.14.0+cu130`; page metadata says updated
  2026-02-03, last verified 2024-11-05. Base prerequisite 2.4+, asynchronous
  `DefaultStager` section introduced in 2.9. This live page is not an immutable
  release specification. Retrieved HTML SHA-256:
  `343ae0f4a354f0e857c73a1d30f00d47af0f30d89eba831bcf5059fb26d3a396`.
- Implementation: `pytorch/pytorch` at
  `7d239835e773c91689eb298692097f4a3340491f`, the full 40-character revision in
  Dot B. The older GLM handoff accidentally omitted the final `f`; no revision
  was guessed. This is an inspected main snapshot, not asserted to be 2.9.
- [LICENSE](https://github.com/pytorch/pytorch/blob/7d239835e773c91689eb298692097f4a3340491f/LICENSE):
  BSD-style license with attribution notices; no source code copied into this
  skill. Recipe attributed to Lucas Pasqualin, Iris Zhang, Rodrigo Kumpera,
  Chien-Chin Huang and Yunsheng Ni. Tutorial copying rights are not established
  by the implementation license; guidance is independently paraphrased.

| Source | Observed mechanism and limit |
|---|---|
| [state_dict_saver.py, 207–395](https://github.com/pytorch/pytorch/blob/7d239835e773c91689eb298692097f4a3340491f/torch/distributed/checkpoint/state_dict_saver.py#L207-L395) | Two-future response when staging returns a Future; otherwise upload Future. Initialized process group requires a CPU backend. Absent explicit stager/writer-stager, internal `DefaultStager` disables all four staging options. `_stateful_to_state_dict` runs before stage submission. Caller-owned stager cleanup is explicit. |
| [staging.py, 106–270](https://github.com/pytorch/pytorch/blob/7d239835e773c91689eb298692097f4a3340491f/torch/distributed/checkpoint/staging.py#L106-L270) | `StagingOptions`, single background worker, stream synchronization before resolving staging, non-thread-safe stager and `close`. Docs mention CUDA; code uses generic accelerator APIs in some branches. Neither establishes NPU qualification. |
| [staging.py, 273–325](https://github.com/pytorch/pytorch/blob/7d239835e773c91689eb298692097f4a3340491f/torch/distributed/checkpoint/staging.py#L273-L325) | Legacy blocking CPU staging; optional cached pinned snapshot. Reuse decreases repeated allocation at the cost of persistent RAM. |
| [_state_dict_stager.py, 129–191 and 262–275](https://github.com/pytorch/pytorch/blob/7d239835e773c91689eb298692097f4a3340491f/torch/distributed/checkpoint/_state_dict_stager.py#L129-L191) | Cached storage reused via in-place copy; source storage size changes rejected; shared/pinned CPU allocation; cleanup clears storage cache. Inference: next staging must not overwrite buffers still consumed by prior upload. |
| [_async_thread_executor.py, 12–69](https://github.com/pytorch/pytorch/blob/7d239835e773c91689eb298692097f4a3340491f/torch/distributed/checkpoint/_async_thread_executor.py#L12-L69) | Upload worker first calls staging future's `result`, then `save`; each executor owns a thread. This supplies error observation and ordering, not a global in-flight request cap. Process executor internals were not mined. |
| [filesystem.py, 762–798 and 973–1038](https://github.com/pytorch/pytorch/blob/7d239835e773c91689eb298692097f4a3340491f/torch/distributed/checkpoint/filesystem.py#L973-L1038) | `cache_staged_state_dict`, `sync_files`, I/O threads; async staging sets copy-ahead to zero. Metadata is written then renamed; unsupported `fsync` can fall back to flush with warning. No arbitrary-backend or power-loss proof. |

## Reconciled differences, not silently merged

1. The live tutorial describes state-dict creation as background work. At this
   pin, Stateful conversion remains on the caller (`state_dict_saver.py:323`).
   Only the subsequent staging work is dispatched. Time that caller cost.
2. The pinned-buffer tutorial comment says `cached_state_dict`; the constructor
   actually accepts `cache_staged_state_dict`. Use the inspected signature.
3. The tutorial constructs `DefaultStager()` per checkpoint without showing its
   cleanup. The inspected implementation explicitly requires caller-owned
   stagers to be closed after the last save. Safe reuse also waits for the
   previous upload, not only the previous staging future.
4. Code observation: the already-completed-future branch at
   `state_dict_saver.py:378–381` sets staging success without retrieving the
   original exception. The upload executor still calls the original future's
   `result()`. Therefore always observe upload completion/errors as well; no
   failure injection was performed and no patch to PyTorch is proposed here.
5. The tutorial's wait-before-optimizer example assumes its relevant state is
   not mutated earlier. Extending overlap to arbitrary forward/backward code
   requires identifying actual state mutations. This is a derived lifetime
   constraint, not an empirical claim.

No model, GPU/NPU, checkpoint writer, recovery or performance test was run.
