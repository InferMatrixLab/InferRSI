# Qwen Ascend: reported rejected directions

These observations come from the [pinned Ascend guide](https://github.com/InferMatrixLab/InferRSI/blob/d51c941dc57807c1e16ea698cd9291f414110c45/docs/qwen-image-2.1-turbo-ascend.md),
which attributes them to amy-why-3459 at upstream head
`399cc01d1bc4542964d91aaa17fb43862a8cf3b3`.
They apply to its one-910B1, BF16, eager, 1280x704, native eight-sigma cohort.
They are author-reported, `locally_verified=false`, with InferRSI acceptance
INCONCLUSIVE. No raw timings, images or frozen validator were imported.

| Direction | Recorded observation and disposition | Suggested revisit condition and first check |
| --- | --- | --- |
| Cache eager RoPE cos/sin or expanded SDPA masks | Pixel-identical, but discarded as slower in the source trials. | Profile current recomputation and retained-tensor costs; qualify a matched timing cohort before attributing a regression. |
| Cache per-step masks and prompt tensors | NPU OOM. | First inventory live tensor lifetimes and allocator headroom. A different residency policy or workload may change feasibility; the report does not establish a universal memory limit. |
| Fusion attention, including precise=2/0 and mask-free steps | No gain or a gain below the source keep criterion. | Check exact mask, dtype, shapes and device support; run operator quality then complete pipeline timing. Do not reuse the source keep threshold as a repository default. |
| TASK_QUEUE_ENABLE=1/2 or enforce_eager=0 | No gain or slower than the source eager configuration. | Inspect the actual execution path and scheduling overhead under the new stack; repeat with unchanged workload and warmups. |
| RoPE + VAE fastpath + fusion attention | Initialization OOM for this triple stack. | Inventory initialization residency before attempting a new combination. |
| Separate kept RoPE + VAE stack on a later busy host | Later requests failed resource reservation; this is a different stack/host cohort from the triple-stack initialization failure. | Qualify current headroom and outside contention before retrying; do not attribute this resource blockage to fusion attention. |

Revisit checks are new diagnostic suggestions, not reproduced causes or a
performance claim. Pixel identity and a looser quality gate remain separate.
The independently reported 910B3 cohort and CUDA results are different scopes;
neither automatically overturns nor confirms a 910B1 observation.
