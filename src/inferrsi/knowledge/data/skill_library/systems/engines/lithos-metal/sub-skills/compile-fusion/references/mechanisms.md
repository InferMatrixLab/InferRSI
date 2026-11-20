# Compiler and fusion mechanisms

Use to turn a compile/fusion question into a concrete region and dependency
inspection. These are pinned implementation facts, not evidence of efficacy.

## Program boundary

`compile_program` lowers a model, checks IR and runs passes. `emit_program`
checks registered op bindings for the profile before emission. It specializes
kernels, binds packed weight windows, allocates role-tagged buffers, emits
operation metadata and places dependency barriers before backend finalization.
`Program` records `KernelSpec`, `BufferSpec`, `OpSpec`, `StepStateLayout`, context
capacity and backend identity. ICB arguments live in buffers rather than
per-replay `setBytes` calls.

The backend owns handler/finalize hooks, decoder/draft/prefill optimization,
device validation and serving recipes. Device selection matches chip, Apple
family and core count. Backend cache identity covers configuration fingerprint,
Metal sources, backend implementation and format decode sources. A tuning cache
hit does not establish correctness at a different source/device combination.

## Fusion comparison

`region_fusion.fuse_regions` validates disjoint, nonempty, uniquely named spans,
normalizes each region, repairs layouts/weight windows and returns both the
normalized control and selected program. `mode='native'` or `fuse=False` keeps
normalized dispatches. `merge_labeled_regions` merges eligible regions into a
megakernel and carries written-binding metadata and a StepState done/error guard.

`static_fusion.normalize` can change cooperative loading, tile packing, scratch
and threadgroup geometry before fusion. `merge` generates fixed-worker stage,
interleave or queue scheduling with validated geometry. These are distinct
transformations. The normalized control is necessary to attribute a difference
specifically to merging.

`decoder_fusion.optimize` discovers mixer and two-projection MLP boundaries from
emitted kernel roles. Mixer, MLP and vocabulary regions are independently
selected by recipe; prefill and draft regions remain separate owners. Static
GDN mixer finalization has narrower preconditions than dynamic speculative
decoder optimization. A general description of mixer fusion is not permission
to force one recipe through every emitter path.

## Ordering and storage ledger

| Mechanism | Actual obligation | Useful control/counter-signal |
| --- | --- | --- |
| `place_barriers` | Buffer-level RAW/WAR/WAW hazards over an open group; row views alias their base; first op waits for prior step | `minimal` versus `all`; unknown writes metadata is treated as writing all bindings |
| Mutually exclusive T variants | May share a variant group because only one executes | Prove predicate exclusivity and metadata before grouping new ops |
| Megakernel local scratch | Threadgroup barriers protect local use | ICB barriers cannot order two tasks inside one dispatch |
| Cross-worker publication | Device-memory ordering and bounded stage barriers/task queues | Bounded timeout is surfaced through StepState; launch order alone is insufficient |
| `reuse_arenas` | Known producer, later consumer, nonoverlapping physical lifetimes; preserve offsets and recompute barriers | Unknown producer, read-before-write, initialized storage and observable outputs stay separate |
| `Engine` shared buffers | Reuse compatible names/sizes except program-owned `params`; reject undersized state/weights/ring | Same name is insufficient for differently packed weight windows during session adoption |

The arena pass preserves StepState, ring, logits, acceptance/confidence logs,
non-arena roles, initialized/file-backed storage and externally supplied or
terminal values. Sequential attention partial workspaces can share capacity
only with dependency barriers ordering reuse; they are not persistent KV state.

## Numerical controls

Hoisting residual-producer RMS statistics preserves the producer's BF16 values
and specified reduction order. Commuted input normalization is a different
optimization and intentionally changes BF16 rounding; it is enabled by default
for eligible projections. Use `Session(..., commute_norm=False)` or the
generation command's `--no-commute-norm` when establishing a matching control.
Do not call a changed rounding path bit-exact without a corresponding comparison.

## Proposed verification sequence

1. Compile tiny graphs and inspect missing-op, layout/bounds, writes and arena
   assertions without allocating a device.
2. Run synthetic Metal ICB/reencode and state/ring checks on the selected device.
3. Compare original/normalized/fused region outputs and all bound state with
   matching decoded weights, rows and numerical options; include boundary rows.
4. Compare complete continuation and rollback before measuring round time.
5. For a service claim, include setup/warmup, prefill, drafting, target verify,
   acceptance/rewind and HTTP/stream completion under the frozen workload.

The sequence is proposed; no measured gain or full-model validation is bundled.
