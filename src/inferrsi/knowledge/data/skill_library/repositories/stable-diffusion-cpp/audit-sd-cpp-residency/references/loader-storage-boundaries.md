# Loader, byte delivery and storage ownership

This source-derived extension applies to leejet/stable-diffusion.cpp at
`b13a48219d5cdf408edcb93da6cd69b612ed03d3`. Use it when source refresh, load failure or
host/mapped storage affects the existing residency audit. Select ordinary
non-ZIP safetensors and its index-to-shard catalog path. The surrounding loader
dispatch is observed; full GGUF/Torch/ZIP parsing, special quantization and
conversion correctness are outside these rules. Native loading and performance
remain unverified. The complete [MIT text](../LICENSE) is retained.

## 1. Identify the catalog without treating it as a content hash

First record the model/component paths, selected root/index and required shard
files, an independent content manifest when byte identity matters, and the
actual runtime/GGML/build/backend. Then follow the caller:

- [src/pipeline/diffusion_engine.cpp L726–783](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/diffusion_engine.cpp#L726-L783)
  submits component files to `init_from_file`. The shown initialization calls
  include warnings/errors; these excerpts do not establish that every failed
  optional component immediately aborts context creation.
- [src/model_loader_files.cpp L15–39](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader_files.cpp#L15-L39)
  defines a dependency stamp from path, file size and modification time.
  Matching those fields can reuse an existing catalog. The atomic source
  revision and catalog revision are internal generations, not file digests.
- [src/model_loader_files.cpp L86–205](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader_files.cpp#L86-L205)
  parses into a candidate, validates storage dimensions/type/byte intervals,
  checks dependency stamps again, and accepts the copied candidate only on
  success. The non-ZIP bound uses `nbytes_to_read()`, not an assumption that
  raw file bytes always equal target memory bytes. The safetensors parser also
  checks its header reads, data intervals and dtype-dependent payload size
  ([src/model_io/safetensors_io.cpp L151–413](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_io/safetensors_io.cpp#L151-L413)).
- Index/shard discovery and declared-name checks are in
  [src/model_loader.cpp L289–357](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader.cpp#L289-L357) and
  [src/model_io/safetensors_io.cpp L416–459](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_io/safetensors_io.cpp#L416-L459).
  These checks do not authenticate shard contents cryptographically.
- Before generation, engine refresh checks for changed sources, refreshes a
  copied loader and applies the update
  ([src/pipeline/diffusion_engine.cpp L270–316](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/diffusion_engine.cpp#L270-L316)).
  ModelManager compares source identity/version/offset/type/shape and refuses
  replacement with active workspace reclaimers or pinned states; accepted
  changes invalidate the affected storage/prefetch/staging consumers
  ([src/model_manager_files.cpp L5–118](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager_files.cpp#L5-L118)).

**Decision:** use stamps and source generations to explain this implementation's
reuse/invalidation, and a separately recorded digest to establish byte identity.
A same-size edit with preserved mtime is a counterexample to equating these
contracts. Pre/post stamp checks also do not provide an immutable snapshot:
a file can change between checks. Do not call candidate catalog replacement a
transaction covering every runner, allocation or write in the process.

## 2. Require byte-delivery success and name the retaining owner

For one requested tensor, record source ID/revision, physical file index,
offset, raw read bytes, target type/bytes, selected destination and return path.
[src/model_io/tensor_storage.h L16–68](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_io/tensor_storage.h#L16-L68) separates
`nbytes()` from `nbytes_to_read()`: F64/I64 input uses twice the internal
storage bytes, and upstream-GGML FP8 has a separate conversion-size branch.
Those source branches do not qualify numerical conversion.

Follow the actual path rather than inferring it from a flag:

| Selected path | Producer → consumer | Failure/completion boundary |
|---|---|---|
| Ordinary file read | Per-worker binary `ifstream` → seek/read at the storage offset → chosen destination | Open failure or a failed/short stream read returns failure. A valid earlier catalog does not make a later short read successful. |
| Mapped bytes copied | Retained `MmapWrapper` → bounds-checked `copy_data` → chosen destination | `copy_data` rejects an offset/length outside the mapping. Its `memcpy` is a local memory operation, not a disk-read receipt. |
| Host destination | Same-type ordinary input can read directly into the destination; special or converted input uses a worker read buffer and conversion | A destination callback only selects/provides storage; it can also skip a tensor by leaving the destination null. It does not certify data correctness. |
| Non-host destination | Worker host read buffer → optional conversion buffer → `ggml_backend_tensor_set` under the loader mutex | The call is observed; GGML/backend completion, physical transfer and allocation type require their own evidence. A host pointer or requested host buffer does not establish pinned allocation. |
| Eligible mapping alias | File mapping and CPU/device host-pointer buffer → tensor data at mapped offset → shared mapping stores retained by loader/parameter blocks | Requires supported buffer capability, matching type/shape/byte size and manager eligibility. Requesting mmap does not ensure this path is selected or eliminate page faults. |

The direct implementation is
[src/model_loader.cpp L1060–1404](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader.cpp#L1060-L1404).
It validates requested source stamps before loading and after workers join,
propagates read failures, and separates read, memory-copy, conversion and
backend-copy calls. Each regular worker's stream and temporary vectors have
scope-bound lifetime; this statement does not extend to every external ZIP
failure path.

Mapping creation/fallback and alias eligibility are in
[src/model_loader.cpp L853–1048](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader.cpp#L853-L1048) and
[src/model_manager.cpp L805–865](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L805-L865).
[src/core/util.cpp L136–336](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/util.cpp#L136-L336) shows Windows
handle cleanup, POSIX unmap/close and the copy bounds. Writable mappings are
private/copy-on-write in these branches, not a checkpoint persistence promise.
OS population/read-ahead/drop-cache advisory calls do not establish actual
physical I/O, cache eviction or speedup.

At the immediate consumer,
[src/model_manager.cpp L1023–1116](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L1023-L1116)
groups compatible sources, passes destinations to the loader and requires its
successful return before publishing all selected states as loaded. Its callback
records a selected name before the payload read; that name set alone is not a
completion oracle. If one group fails, earlier writes may already have occurred.

**Decision:** accept a completed load only with the caller's success and a real
byte/output oracle under the actual selected path. On failure, track ownership
rather than assuming rollback:

- [src/model_manager.cpp L425–492](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L425-L492)
  releases blocks created for this loading attempt after mapping/allocation/load
  failure. It does not promise restoration of earlier writes or all pre-existing
  storage.
- Parameter blocks retain mapping stores
  ([src/model_manager.h L55–85](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.h#L55-L85)).
  [src/model_manager.cpp L1232–1252](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L1232-L1252)
  frees the block buffer, clears its mapping owners and resets attached state.
  The loader's file-data cache or another shared owner can still retain the
  mapping. Unmap/close belongs to destruction of the final mapping owner, not
  merely pin release or deletion of one block.
- Keep bytes read, host staging, converted bytes, retained mapping pages and
  device allocations separate. Load success does not prove that an image fits
  or that the existing segmented/prefetch path will run.

The loader logs total wall time and stage counters divided by the last file's
thread count ([src/model_loader.cpp L1394–1401](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader.cpp#L1394-L1401)).
These are not interchangeable cold-storage/device bandwidth denominators.
For startup optimization, use the generic weight-loading method and measure
preparation, first load/request and warm work separately under fixed controls.

## Proposed checks

These are independent expected decisions, not executed native tests. Require a
matching real GGML library/private headers/build and a legal small fixture.
Do not substitute extracted formulas, fake backends or mock native headers.

| Input/condition | Expected decision and decisive observation |
|---|---|
| A required shard has genuinely changed | Refresh/invalidate before reuse; observe the actual caller result and new source/consumer state. |
| Same path, size and mtime but different independently recorded digest | Identity is unresolved by stamps; retain the differing digest and reject a content-equality claim. |
| Selected tensor interval exceeds the real fixture file | Actual parser/add-file rejects the candidate; the previous accepted catalog is not replaced by that failed candidate. |
| File becomes short after catalog admission | Observe loader failure and consumer flags/new-block cleanup. Callback invocation or earlier metadata acceptance is insufficient; no universal rollback is presumed. |
| Supported ordinary dtype on the actual direct-read, staging or mapping path | Compare real tensor bytes to an independent small-fixture oracle; distinguish raw input bytes from target bytes and retain mapping owners through use. |
| One mapping/block owner is released | Check other retained owners before predicting unmap. A successful map or host-buffer request alone cannot establish pinned RAM, cold-disk throughput or device completion. |

Preserve the existing residency counterexamples: CPU or multi-device dispatch is
not the inspected non-CPU single-device segmented path; unpin is not immediate
physical free; advertised async capability is not useful overlap. The
[validation boundary](validation-boundaries.md) still governs image completion,
quality, memory and performance. Agent efficacy is uncovered.

## Fixed readset and attribution

The 2026-10-23 extension checked the following exact Git blobs: eleven fixed-blob
fetches, the reused engine seed and the already retained MIT text. Range links
record the semantic readset, including declarations needed to resolve owners.
Keyword inventories and complete file retrieval are not complete-file audits.
The original [nineteen-blob archive receipt](source-identity.json) remains a
separate historical record at the same source revision.

| Source path | Git blob | Read ranges at the fixed revision |
|---|---|---|
| `src/model_loader.h` | `aae359099e5dcea55a6eba17570c7afe6b0c559f` | [1–164](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader.h#L1-L164) |
| `src/model_loader_files.cpp` | `9ac5456cc15118a3218455431096d60aa95e4305` | [1–354](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader_files.cpp#L1-L354) |
| `src/model_loader.cpp` | `8822b2c3f12fced42d6223958916c465cad5c29e` | [1–42](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader.cpp#L1-L42); [193–239](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader.cpp#L193-L239); [289–360](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader.cpp#L289-L360); [827–1049](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader.cpp#L827-L1049); [1060–1420](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_loader.cpp#L1060-L1420) |
| `src/model_manager_files.cpp` | `10c7d2e68fdd1d1f9a024a1d99a411f4fc2e9414` | [1–169](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager_files.cpp#L1-L169) |
| `src/model_manager.cpp` | `4562ebdfd4f834e3bfe7bfa4e01c2b51f0dda104` | [425–492](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L425-L492); [805–965](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L805-L965); [1023–1148](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L1023-L1148); [1232–1252](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.cpp#L1232-L1252) |
| `src/model_manager.h` | `fdb110825d98f4aeebe071d15daf5bf94e24c502` | [1–18](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.h#L1-L18); [30–105](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_manager.h#L30-L105) |
| `src/model.h` | `c8d803a667b8e047d183f0dcd898557507438c39` | [1–40](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model.h#L1-L40) |
| `src/core/util.h` | `0929f60e01ae4f8239abe150d45cc539bd1b205d` | [1–124](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/util.h#L1-L124) |
| `src/core/util.cpp` | `c1d463e4da9339b5138ad500b99942028750f974` | [128–344](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/core/util.cpp#L128-L344) |
| `src/model_io/tensor_storage.h` | `1916d1f5e512f19762fba00a2b655066ff171a68` | [1–158](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_io/tensor_storage.h#L1-L158) |
| `src/model_io/safetensors_io.cpp` | `cf424af921e04453f88b5a27a4c20774208ead8c` | [151–460](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/model_io/safetensors_io.cpp#L151-L460) |
| `src/pipeline/diffusion_engine.cpp` | `70338bd99380cca800e1277e243335db6f380311` | [1–65](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/diffusion_engine.cpp#L1-L65); [229–342](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/diffusion_engine.cpp#L229-L342); [726–783](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/src/pipeline/diffusion_engine.cpp#L726-L783) |
| `LICENSE` | `56e1e5a63852c3bcd5ac4fcdfecb7666f5274169` | [1–21](https://github.com/leejet/stable-diffusion.cpp/blob/b13a48219d5cdf408edcb93da6cd69b612ed03d3/LICENSE#L1-L21) |

The selected mapping implementation ends before the unrelated physical-core
helper's attribution. No upstream implementation is copied into this guidance.
Root MIT attribution is not extended to unexpanded dependencies, external ZIP
code, models or unrelated embedded helpers. Full other-format parsing, special
quantization/conversion semantics, native failure injection, allocator/backend
completion, physical storage/cache behavior, image quality and performance
remain outside this source-only candidate.
