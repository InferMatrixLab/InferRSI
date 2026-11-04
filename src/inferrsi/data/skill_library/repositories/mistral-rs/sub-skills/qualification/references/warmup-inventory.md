# Offline warmup boundary inventory

`scripts/warmup_shape_inventory.py` is a standard-library adaptation of
[`paged_decode_warmup_shapes`](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/kernels/mod.rs#L1002-L1279)
at the pinned source revision. It answers only: **which batch/context boundary
pairs does this source enumeration consider for a declared maximum?**

## Input and API

```json
{"schema_version":1,"max_batch":32,"max_context":32768}
```

Exactly these three keys are required. All values are integers, not booleans;
schema version is 1. Maxima must be positive and at most `2**64 - 1`. The
unsigned-64-bit domain explicitly models the source's `usize` enumeration on
64-bit targets. It does not validate an actual target architecture, allocation
size, tensor geometry or runtime ability to support those maxima.

The importable API is `inventory(plan: dict) -> dict`; invalid plans raise
`PlanError`. `example()` returns a fresh valid plan. CLI input is one UTF-8 JSON
object from a regular file or `-`/omitted input for stdin. `--example` emits its
inventory without reading input. Input is capped at 16 KiB; duplicate keys,
unknown/missing keys, nonfinite values, malformed JSON and out-of-domain values
are rejected. Errors use fixed diagnostics without echoing supplied input;
CLI failure returns 2. There are no engine imports, network calls, subprocesses,
model loads or output-file writes.

## Exact modeled operation

1. Start context candidates with 1, the maximum, and the source limits 256,
   768 and 4096. Add packed-short limits 288/320 and HND profile limits
   512/1024/1024/512/512.
2. Add a saturating increment of **each original candidate**, not an iterative
   closure. Retain values no greater than the declared maximum; sort/deduplicate.
3. Batch candidates are 1, the maximum, and HND profile maxima 1/4/4/8/8 plus
   one beyond each profile maximum. Retain, sort and deduplicate.
4. Emit their Cartesian product in batch-major, increasing-context order.

Output includes `batches`, `contexts`, `shapes`, `count`, and invariant labels
`source_boundary_inventory_only`, native verification `not_run`, runtime
eligibility `not_verified`. For the example, batches are
`[1,2,4,5,8,9,32]`; contexts are
`[1,2,256,257,288,289,320,321,512,513,768,769,1024,1025,4096,4097,32768]`.
The resulting 119 pairs are not a set of executed benchmarks or proof that all
these shapes are legal for an arbitrary model.

## Explicit omissions

The helper does not reproduce attention selectors, function constants, pipeline
names, actual-model warmup shape construction, packed/HND eligibility, window
visibility, dtype, cache scales, alignment, buffer validation or GPU reduction.
It cannot show that a prepared pipeline was dispatched, that outputs match a
reference, or that prewarm removed compilation from a request. It creates no
benchmark scores and clears no required-backend blocker. Reconcile source
changes before reusing the inventory against another revision.
