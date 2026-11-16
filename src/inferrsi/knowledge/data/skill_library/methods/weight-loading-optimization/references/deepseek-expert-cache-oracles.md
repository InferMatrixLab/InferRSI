# Audit streamed expert-cache bytes and overlap

Status: source-derived candidate. Use this reference when changing aligned reads,
cache-slot placement or overlapped routed-expert loading. The
[source record](deepseek-expert-cache-source.json) fixes the repository revision,
inspected regions, file hashes, rights and exclusions. It describes checks to
perform on an authorized target; it supplies no loader implementation or measured
gain.

Keep startup loading separate from request-time expert traffic. Before judging a
change, identify the checkpoint and tensor metadata, effective direct/buffered
read path, cache-slot budget, requested expert keys, source callback table and
numerical reference. A higher cache hit rate can accompany corrupted expert
bytes and changed routing.

## Check bytes through an independent read path

Compare each cached weight and scale with a plain buffered read of the same
tensor bytes. Serial and concurrent cache loads can agree while sharing the same
placement error; matching pointers, shapes or the two fast paths is insufficient.
The source's byte oracle uses the safetensors reader's tensor offsets and buffered
file descriptors, then bypasses its aligned/coalesced placement code. It does not
independently validate the shared metadata parser.

Exercise the layout that can expose the error. The source fixture separates an
expert's scale and weight runs, gives the runs different 4096-byte alignment
residues and writes nonconstant payload bytes. A single contiguous run cannot
expose a later widened read overwriting an earlier run. An aligned read starts
before its payload; reserving space only for the payload leaves that earlier
storage vulnerable.

For an aligned-placement check, confirm that the actual run selected direct I/O.
A successful buffered fallback does not exercise the widened-window path. Retain
the compared tensor set and actual checked count; a skipped or absent tensor is
not byte-identity evidence.

Sources: [fixture geometry and payload](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/tools/make_st_fixture.py#L130-L202),
[independent byte check](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/tests/unit/test_cache.c#L137-L186),
[run placement](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/src/cache/dsv4_cache.c#L260-L389),
[aligned and buffered reads](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/src/io/dsv4_st.c#L470-L508).

## Trace resident and pending ownership

At this source pin, `begin` makes hit/miss, victim and recency decisions serially
in request order before starting the reads. Slots already claimed by this call
cannot be chosen again as victims. It returns usable resident experts immediately;
misses and duplicate requests for an in-flight expert remain unpublished until
`end` completes that read.

| State | Bytes and visibility | Required boundary |
| --- | --- | --- |
| Returned resident | `out[k]` points to a complete claimed slot. | Keep its bytes usable while pending reads run. |
| Pending miss | The selected slot is marked invalid while a reader fills it; `out[k]` is null. | Publish its key and output only after successful completion in `end`. |
| Missing or invalid tensor metadata | Resolution fails before choosing a victim. | Surface failure; do not interpret it as a completed cache load. |
| Partial I/O failure | The chosen slot can contain partial replacement bytes and stays invalid. | Complete the batch wait and reject the unavailable expert; do not reuse its old key. |

Only one batch may be active per cache. Call `end` before another `begin` or any
other cache operation. Shutdown stops and joins readers before freeing their slot
storage. When the reader pool is unavailable, the source performs reads inside
`end`; the same callback pair then supplies no overlap with caller computation.
Callback selection alone does not prove the asynchronous path executed.

The resident check warms a subset, calls `begin` with both hits and misses,
copies resident `w1` bytes during the gap, then compares them after `end` and with
serial loads. This specifically tests those resident `w1` bytes. It does not
establish every tensor's stability under all eviction, capacity or timing cases.
The separate serial/concurrent check compares weight and scale bytes and includes
a duplicate request.

Sources: [single-batch interface](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/src/cache/dsv4_cache.h#L220-L270),
[decide, wait and publish](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/src/cache/dsv4_cache.c#L563-L701),
[reader cleanup](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/src/cache/dsv4_cache.c#L199-L210),
[concurrent and resident checks](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/tests/unit/test_cache.c#L188-L298).

## Follow the model consumer and its accumulation order

Check the callback table used by both the real caller and its oracle. The layer
selects overlap only when both `begin` and `end` exist; otherwise it uses
`get_many` or serial `get`. A test wired only to `get` cannot cover the overlap
branch. The CLI and current model-oracle test both supply the overlapped pair.

The caller computes available residents while misses are being read, waits in
`end`, and then computes the remaining experts. Each expert writes to its own
per-`k` output storage, separate from the MoE input. The weighted sum happens
afterwards in `k` order. Completion order must not change that sum: floating-point
addition can produce different results when reordered. Expert matmuls remain
sequential because their working scratch is shared; I/O is what overlaps them.

The batched caller deduplicates expert requests and fetches the union in bounded
chunks, while retaining a separate output for each `(token, k)` and summing in
`k` order per token. An unavailable expert after the wait aborts the model path;
silently skipping it would change the routed computation.

Sources: [source interface and scratch](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/src/model/dsv4_layer.h#L9-L74),
[per-token consumer](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/src/model/dsv4_layer.c#L369-L483),
[batched consumer](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/src/model/dsv4_layer.c#L714-L831),
[CLI wiring](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/src/cli/dsv4_run.c#L313-L315),
[oracle wiring](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/tests/unit/test_model_oracle.c#L57-L83).

## Interpret the numerical evidence at its actual scope

| Check | Source-defined comparison | Interpretation |
| --- | --- | --- |
| Cache byte oracle | Buffered tensor bytes versus cached weights/scales. | Read/placement identity for the checked bytes, with shared tensor metadata. |
| Tiny per-token model | C logits against a repo-owned PyTorch reference, using a vector-scaled tolerance and matching argmax. | Numerical agreement for the synthetic checkpoint and supplied positions; not bit equality to PyTorch. |
| Batched prefill | Bitwise C-logit comparison against the per-token run after its PyTorch check, across several chunk sizes and fresh layer states. | Batched/per-token agreement within that anchored fixture. |

The tiny checkpoint draws FP8/FP4 weights from exactly representable values and
uses the real config/reader/binder/trunk/cache entry points. Its dimensions and
token sequence are synthetic. The repo-owned PyTorch reimplementation omits
activation-quantization simulation and Hadamard rotation; it is not an execution
of the released model's official GPU reference. Missing tiny checkpoint or trunk
resources print `SKIP` and return exit status 0, so an exit code alone is not a
model-oracle pass.

Return the selected I/O and callback paths, byte/resident coverage, failure and
cleanup boundaries, numerical comparison and unresolved gaps. Retain the
campaign's independent acceptance and workload controls. These source
definitions and historical reports establish no locally executed C/model check,
full-model quality, device performance or agent efficacy.

Sources: [fixture/reference producer](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/tools/make_tiny_checkpoint.py#L17-L50),
[reference exclusions](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/tools/dsv4_ref.py#L3-L30),
[model comparisons and cleanup](https://github.com/ronak-create/deepseek-v4-in-c/blob/d0402056d0da4bf7edfd2d4977de479a0db9d201/tests/unit/test_model_oracle.c#L145-L390).

## Attribution

Original analysis of Ronak Parmar's `ronak-create/deepseek-v4-in-c` at the pinned
revision. The repository declares Apache-2.0 and attributes its streaming design
to Fareed Khan's `kimi-k3-in-c`, also Apache-2.0. Selected-file notices and excluded
third-party/model material remain in the source record. No upstream source code,
prose, checkpoint or fixture payload is redistributed.
