# Decode troubleshooting

| Signal | Distinguishing contract | Recovery / stop |
| --- | --- | --- |
| Equal bytes but wrong attention after layout switch | HND versus packed K and V indexing, strides/offsets and producer identity | Reconcile actual layout and bytes; do not merely relabel or reshape a live cache |
| FP8 cache rejected or wrong scale use | Both scales scalar F32 only for F8E4M3 | Fix declared descriptors, then separately qualify real storage/scales and outputs |
| General decode works but specialized path absent | Narrow dtype/block/head/GQA/feature predicate | Generic fallback can be valid; do not force a shader or label the entire model unsupported |
| Sliding decode with packed cache fails | Exact trailing window requires HND | Use an explicitly matched producer/layout; helper success cannot change existing cache bytes |
| Smaller batch/context exceeds preallocated scratch | Instantaneous bytes versus monotonic capacity, FP32 split partials | Inspect native capacity contract across reachable interior variants; do not use only one max-shape estimate |
| Prepared kernels log but no numerical evidence | Pipeline preparation is not a dispatch or inference run | Follow qualification route and retain required Apple block |
| CPU call to paged attention fails | Native custom op explicitly has no CPU support | A CPU helper/reference is not the op's fallback; stop without matched Metal |
| Rust compile/test command unavailable | Missing Rust/Cargo and Apple dependencies | Report not_run with exact prerequisite; do not install tools or count skipped/gated tests as passes |

No caller-provided metadata proves device ownership or bounds of actual block
IDs. Native invalid-input and byte-consumer tests are necessary before changing
cache transfers, strides, barriers or aliasing; source arithmetic alone cannot
justify such a patch or a public quality/performance claim.
