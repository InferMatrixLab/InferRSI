# Qualification troubleshooting

| Signal | Contract to inspect | Safe recovery / retained limit |
| --- | --- | --- |
| Configured drafts but no proposals | Non-greedy/constraints, effective context, dynamic K0 | Record actual eligible rows and worker context-limit counter; don't label target-only work speculative |
| Hybrid partial acceptance diverges | GDN family, FP32 recurrent state, lazy scan, pre-span staging and boundary caps | Unsupported pairings must fail; actual state/greedy parity requires Apple model evidence |
| Pending−1 token or evicted request reappears | Placeholder bookkeeping, direct-reference backfill and begin-step barrier | Inspect ownership/order, not just numerical kernels; stop before publishing correctness |
| MPS output differs with same seed | CPU fallback setting and RNG/sampler path | Disable optional CPU fallback for MPS qualification; native MLX versus torch stochastic equality is not promised |
| GQA flag enabled but no GQA dispatch | Eligibility/geometry/page/features/actual decode work/resources | Zero only permits selection; both A/B arms may validly fall back. Observe evaluated worker-side dispatch |
| Last-dispatch record changes between requests | Process-wide last observation under concurrency | Use a separate isolated route check or scoped trace, not request attribution from one getter |
| Faster kernel but slower HTTP service | Topology, mixed work, queueing, pressure, acceptance or timing boundary | Keep measurements separate; repeat controlled service arms and retain regression |
| Missing/failed arm in JSON summary | Execution incomplete | Keep explicit status and null measurement. Completed-subset arithmetic is not failure-adjusted service throughput |
| Long prompt with short draft context | Minimum positive width cannot fit | Target-only fallback may be expected; temporary skips/K0 differ from a lifetime context fallback |

Upstream benchmark tools can load models, access datasets, launch services or
run long captures. They remain source evidence only. Bundled helpers are offline
and cannot clear any required backend, quality or performance gap.
