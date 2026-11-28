# Prefill troubleshooting

Apply the [host/kernel contract](prefill-and-metadata.md) before changing
settings. These checks do not authorize toolchain installs, model downloads,
service launches or edits to external data.

| Signal | Broken distinction | Small discriminating check / recovery |
| --- | --- | --- |
| Workspace looks constant across much longer prefixes | Prefill output/metadata reservation versus KV, tables, masks and work | Keep the context-independent formula, then account for excluded allocations separately; do not call total memory constant |
| Sum-rounded estimate differs from source | Each allocation has independent next-power-of-two and 16 KiB floor | Compute output and metadata separately with the bundled helper; the granule is not ordinary 16 KiB multiple rounding |
| `supports()` true but request rejected | Shallow shape versus actual tensor/binding guards | Inspect real Q/cache/table shapes, dtypes/device and options; do not weaken runtime guards or cite helper zero as eligibility |
| Ragged packed Q shape rejected | Batch-one total Q versus padded batch/max Q | Reconcile complete length vectors and actual query axis; query packing does not automatically select mask packing |
| FP8 cache has missing/mismatched scale error | Cache dtype does not validate scale tensors | Require both explicit scalar F32 K/V tensors on the common Metal device; non-FP8 rejects supplied scales |
| K/V dimensions or strides read wrong values | Prefill parser versus neighboring decode geometry; logical shape versus view addressing | Preserve this parser's independent V dimension, cache rank/layout, real element strides and byte offsets; check consuming kernel with actual narrowed/strided fixtures |
| Packed mask shifts second-sequence columns | Concatenated Q and K coordinate systems differ | Without explicit offsets K concatenates context; explicit K offsets replace K origin only; packed Q remains concatenated |
| Mask shape accepted but values wrong | Broadcast extents are not tensor data validation | Compare actual rank/dtype/start offset/strides and loaded indices; last-axis oversizing is allowed, not arbitrary Q-axis oversizing |
| Range appears to permit future or old tokens unexpectedly | Absolute half-open ranges can override causal/window rejection | Check both absolute positions lie in `[start,end)`; attention-chunk mismatch still rejects first; historical nonintersecting ranges do not make current queries bidirectional |
| Window edge differs by one token | Strict distance `<window`, not `<=window` | Freeze a boundary fixture in absolute coordinates; positive left/right window equality is excluded |
| Large ALiBi origin changes small relative distances | Integer difference versus subtracting rounded floats | Keep integer origins/difference and native source's order; require actual numerical test, not arithmetic-only helper |
| Non-power-of-two block rejected by an assumed bitmask rule | General block arithmetic versus power-of-two optimization | Retain positive block geometry; inspect division/remainder fallback and real native block-seven evidence |
| 56-sequence batch works, 57 fails | 4096-byte inline metadata boundary | Compare `9*batch*8` plus range words; 56 no-range rows are inline, 57 buffered; verify metadata-copy pipeline and actual synchronization |
| Linux reports zero tests | File-level macOS+Metal cfg | Record not_run rather than pass; even the pure workspace test is gated; do not install missing compiler/SDK without authority |

The helper screens declarations only. Compiler absence, unavailable SDK/runtime
and missing actual Apple Metal execution leave native results
**BLOCKED_REQUIRED_BACKEND**, not skipped-success. Kernel parity, model quality,
memory pressure and serving speed require separately scoped evidence; use
[qualification](../../qualification/SKILL.md) for that boundary.
