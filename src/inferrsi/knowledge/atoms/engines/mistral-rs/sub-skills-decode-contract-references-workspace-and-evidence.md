# Instantaneous scratch versus capacity and execution

`bytes()` validates positive shape dimensions, then estimates output plus
partition buffers for the selected shape. Each modeled buffer uses checked
products and next-power-of-two size. Output is query dtype. When partitions
exceed one, exp sums and max logits are F32, and partial output is query dtype
except the HND fixed-split route, whose partial output is F32. Sinks add an
F32 head-vector allowance. These byte estimates are not total process/model
memory and do not inspect current pressure or actual allocations.

The generic policy uses V1 only when `(ceil(context/512)==1 OR sequences*heads>512)`
and 512 is divisible by the cache block size; otherwise it uses partitioned V2.
The first condition alone does not select V1 for every block layout. A source
planner query and a compiled shader name do not prove the runtime path.

`capacity_bytes()` intentionally takes a maximum beyond current `bytes()`:
generic 512-partition storage, specialized 128-partition storage, and where
reachable the one-sequence fixed-split case. The latter can have a different
partial dtype. This gives a monotonic workspace bound for batches/contexts up
to the declared shape. A max-batch/max-context instantaneous estimate can miss
an interior variant's larger scratch; reducing batch or context is not always
a monotonic reduction in actual selected scratch.

The bundled metadata helper does **not** reproduce these allocation/variant
functions and does not return a scratch bound. It only exposes selected layout,
scale and specialization declarations, plus dense cache payload arithmetic.
Use a matched actual Rust/Candle/native plan and observed allocation for any
memory-budget or performance claim.

For an authorized change, require native tests for both HND and packed bytes,
cache writes/copy, exact window/tail behavior, every supported dtype/scale pair,
generic fallback and specialized branch boundaries. Inspect numerical
references separately from route evidence; a compiled feature check is not
execution, and a host reference inside a Metal test is not a CPU substitute.
Capture actual runtime/source/dependency/device identity, scope and missing
results. Do not import a source test tolerance or dispatch crossover into a
portable campaign acceptance threshold.

Sources: [workspace functions](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_attention.rs#L194-L300),
[native branch allocation](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/backend/paged_attention.rs#L490-L655),
and [head-512 split versus grouped policy](https://github.com/EricLBuehler/mistral.rs/blob/9459891e7697238225885518119682ac8209a612/mistralrs-paged-attn/src/metal/kernels/mod.rs#L1181-L1236).
The source's comments describe intended monotonic capacity; this delivery has
not compiled or executed that Rust contract on any backend.
