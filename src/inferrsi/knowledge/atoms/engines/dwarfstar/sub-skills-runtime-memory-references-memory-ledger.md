# DwarfStar memory ledger and placement invariants

## Source and evidence boundary

This reference distills `antirez/ds4` source revision
`ee7e8405232c8971000cc7ba2b945b00bf6d20d3`. The bounded readset is listed below.
Source observations and proposed checks are not measurements. No Metal/CUDA/ROCm
inference, real model fit, SSD latency or distributed execution was verified by
this extraction. The source license file is MIT; the skill's `NO_LICENSE` value
is AREX's unavailable authenticated-CLI lookup fallback, not a legal conclusion.

## Representation and ownership

| Item | Owner/lifetime | Budget implication | Smallest discriminating check |
| --- | --- | --- | --- |
| Model mapping and non-routed weights | Engine/model; backend-dependent residency | Routed-cache size excludes other weights; mapping bytes are not identical to resident physical pages | Observe startup model accounting and physical/process memory in cold and warm phases |
| Routed expert cache | Engine/backend streaming state | Requested bytes or slots are constrained by model, graph and backend headroom | Compare requested/effective cache and actual expert I/O under a fixed prompt |
| Prefill workspace | Shared engine-owned arena where supported; sessions borrow pointers/views | Count shared storage once, but preserve capacity/tier compatibility and scheduling rules | Change prefill chunk with slot count fixed, then slot count with chunk fixed |
| KV/recurrent/history state | Per session, possibly views into an engine pool | A shared physical pool does not merge logical session identities | Interleave independent sessions and compare against isolated continuations |
| Speculative, vision and host buffers | Selected model path and session | Additional weights, logits, frontier snapshots and staging can overlap other phases | Compare the identical configuration with the optional path absent, without claiming semantic equivalence |
| File I/O/page cache and OS headroom | Host/storage, outside a tensor counter | Unified-memory expert cache and pinned staging compete with OS memory | Retain physical pressure, compressed/swap memory and storage-read observations |

`ds4_engine` stores expert-cache bytes, prefill headroom, full-layer bytes,
decode-map bytes and extra map bytes separately. Its transient guard adds
dynamic expert-cache bytes, prefill headroom and decode-map extras using
saturating arithmetic. The startup report additionally estimates raw/compressed
KV and active/resident model storage. These internal counters are not a complete
OS peak-memory measurement.

## Cache controls: meaning before tuning

| Control | Interpretation | Constraint |
| --- | --- | --- |
| `--ssd-streaming` | Stream supported routed experts; retain a bounded cache | Model/backend/tensor-layout support is specific, not universal |
| `--ssd-streaming-cache-experts 32GB` | Request a 32-GiB expert-cache target | The `GB` suffix maps to powers of 1024; effective allocation can be reduced |
| `--ssd-streaming-cache-experts 4000` | Request 4000 dynamic expert slots | A bare number is not a GiB value; non-routed weights and state remain additional |
| `--ssd-streaming-full-layers N` | GLM reservation for full routed prefix layers | Trades cache distribution, not a guarantee that every other allocation fits |
| `--ssd-streaming-cold` / `--ssd-streaming-preload-experts N` | Control preload state for selected measurements | Fix these between comparisons; a warm cache is not a cold-start result |

The argument parser accepts positive decimal integer slots or positive integer
`GB`-suffixed budgets, case-insensitively; it rejects zero, fractional values,
negative values, other suffixes and overflow. The bare-integer GiB parser used
elsewhere is not the expert-cache parser: do not transfer its semantics.

`ds4_ssd_auto_cache_plan` computes a target from the recommended memory and its
selected percentage, clamps it to a nonzero model limit, subtracts non-routed
bytes where possible, then derives expert count. It enforces at least one slot
and caps by the available model experts and integer capacity. Consequently the
effective cache is slot-quantized and can exceed a tiny nominal remainder; this
helper is not final proof that mandatory runtime allocations fit. Its
`DS4_SSD_AUTO_CACHE_PCT` override accepts the implementation's bounded percentage
range; invalid values warn and fall back. Do not turn this override into a
generic cross-hardware tuning default.

More cache is not monotonic progress. On Metal GLM, keeping non-routed weights
resident avoids paging frequently needed data after prefill. An oversized
routed cache can displace those weights or reduce room for sessions and scratch.
First identify whether the failing/slow phase is cache-miss-bound or
mandatory-state-bound.

## Sharing is an ownership contract

`metal_graph_transfer_prefill_workspace` moves allocation ownership to the
destination and clears the source's ownership flag; pointer copying does not
duplicate tensor allocations. `metal_graph_free_prefill_workspace` frees only
the owner. A borrowed workspace is checked against the required prefill
capacity and embedding tier. Whole-graph teardown invalidates captured decode
graphs before releasing their baked-in buffer addresses. Preserve these
boundaries when proposing lifetime or reuse changes.

The engine also owns Qwen shared workspace and recurrent-state pools, with
borrower/slot accounting. Sessions still hold their graph, checkpoint, image
identities, CPU cache/scratch and speculative state. Inspect the selected path
before asserting that every backend or model shares the same workspace.

Metal GLM's next-graph budget is existing reserved session graph bytes plus
the next graph's bytes multiplied by still-planned slots (at least one). It
saturates on overflow. Other backends return the next-graph input unchanged in
this helper; that is not evidence they have no separate memory policy. The
model-free test exercises these bookkeeping distinctions, not actual GPU
allocation or the safety of an arbitrary slot count.

## CUDA read policy and topology

V4.1 CUDA's selected-read path protects existing cache hits before assigning
misses, and can order misses by file offset while preserving router/remap
order. Its prefill default coalesces selected reads; single-token decode retains
its original ordering unless the experimental override is present. Whole-next-
layer prefetch is a distinct opt-in policy with its own cache-capacity and
single-GPU prerequisites. Do not attribute a difference to routing/quantization
when only read scheduling changed.

These diagnostic switches use **presence**, not string-valued booleans:

- `DS4_CUDA_ENABLE_SSD_PREFETCH` enables the V4.1 prefetch call site.
- `DS4_CUDA_DISABLE_SSD_PREFETCH` overrides prefetch enablement.
- `DS4_CUDA_SSD_SORT_SELECTED_READS` extends ordering to the selected
  single-token path; `DS4_CUDA_DISABLE_SSD_SORT_SELECTED_READS` wins over it.
- Unset the switches to recover defaults. `NAME=0` still means present.

Ordinary CUDA placement assigns complete layers using per-device free-VRAM
budgets after reserving graph/context space. Flash in-process TP instead pairs
GPUs: routed experts are split, dense attention/router/shared experts are
replicated within a pair, and the output head is vocabulary-sharded. Device
ordering encodes layer-home devices followed by partners. Do not copy one
eight-card ordering to a different interconnect, add all VRAM as fungible RAM,
or substitute network TP flags for this mode.

## Bounded source readset

- `README.md:5-33`: specialized models/layouts and stated hardware targets.
- `docs/SSD_STREAMING.md:5-93`: cache controls, headroom and CUDA switch semantics.
- `docs/CUDA_MULTI_GPU.md:24-90`: layer placement, pair ordering and launcher limits.
- `docs/SERVER.md:60-91`: shared prefill versus per-session state and fallback distinctions.
- `ds4_ssd.h:7-36`, `ds4_ssd.c:16-140`: parser, byte/slot plan and arithmetic.
- `ds4.c:17900-17962`, `19545-19579`: workspace copy/transfer/free and compatibility.
- `ds4.c:43174-43321`, `43324-43385`: engine fields, graph budget and selected startup accounting.
- `ds4.c:61171-61282`: selected session ownership/state fields.
- `ds4_cuda.cu:29098-29155`, `29408-29450`: selected-cache ordering and prefetch prerequisites.
- `ds4.c:42625-42638`: V4.1 prefetch opt-in call site.
- `tests/test_session_state.c:163-190`: model-free memory bookkeeping assertions.

The selected source paths agree on the distinctions above; this readset does
not establish a complete support matrix or inspect every allocator/kernel.
