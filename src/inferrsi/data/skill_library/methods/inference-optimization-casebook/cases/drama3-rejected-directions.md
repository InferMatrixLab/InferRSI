# Drama3 B300: rejected directions and invalid controls

The [pinned diagnostic ledger](https://github.com/InferMatrixLab/InferRSI/blob/d51c941dc57807c1e16ea698cd9291f414110c45/evidence/drama3-b300-scale150/results/diagnostic-lessons.md)
and [acceptance issue #10](https://github.com/InferMatrixLab/InferRSI/issues/10)
own the observations and exact runtime/artifact pins. The campaign remains
INCONCLUSIVE and optimization is paused. A completed individual gate failure
does not supply missing concurrency/repetition evidence. No experiment is
reopened and no external raw trace is rehashed here.

| Direction | Recorded observation and disposition | Suggested revisit condition and first check |
| --- | --- | --- |
| Fused tower projections / multi-step decode | Faster or correct in isolated checks but no full-service throughput gain; multi-step decode delayed admission. | Measure actual active batches, admission/drain and complete service latency, including sampling and codec. Kernel timing alone cannot select the runtime. |
| Async service / overlap | Early fixed-request controls passed while service WER failed in both arms. Later bounded dynamic replay identified shared ATen cuBLAS workspace interference: dedicated codec capture matched tested states, and fresh private-capture service WER passed while shared capture failed. The runtime added a dedicated-capture guard. | Preserve the required private/dedicated capture setup and unchanged controls. This specific reproducer does not establish one cause for every historical WER failure, or qualify arbitrary overlap/throughput; all-concurrency acceptance remains unmet. |
| Production prefix reuse | Extensive graph/state checks and both full quality groups passed, yet the complete C64 service continuation gate failed; default-off. | Retain final drain and all returned work. Investigate the actual schedule and GPU critical path before retrying; removed MoE rows and intake-only rates cannot replace the failed service score. |
| Initial prefix-reuse harness comparison | Compared different private padding histories; mismatch was confined to a private slot before later states were checked. Corrected identical-input controls reran it. | Reset complete physical input rows and run A/A before blaming production math. Do not reuse this superseded setup failure as evidence of model incompatibility. |
| Transparent VMM weight compression | Native correctness/lifetime checks passed, but the fixed three-body screen missed its frozen timing gate; no runtime promotion. | First measure the current bottleneck and physical traffic/compression where possible. Mapped flags and logical capacity do not prove a bandwidth benefit. |
| Producer scale-tile cache | Complete-body reductions missed the source gate; stopped without model/service promotion. | New shapes or a different resource regime may justify another bounded screen; do not subtract unrelated historical screens to infer a cause. |
| Fixed eight-lane FP8 SIMT proposal | Stopped at CPU/AOT cost analysis for that mapping, before a runtime benchmark. | Revisit only with a changed mapping or supported cost model; this is an analytical rejection, not an empirical GPU failure or universal ceiling. |

The last column is proposed diagnosis. Preserve native computation, precision
and frozen acceptance rules; none of these cases authorizes a lossy shortcut,
looser validator or a resumed hardware campaign.
