# Qwen B300: rejected directions to check before retrying

Scope: Qwen-Image-2.1-Turbo, four B300, BF16, native eight-step image generation.
The [pinned ledger](https://github.com/InferMatrixLab/InferRSI/blob/d51c941dc57807c1e16ea698cd9291f414110c45/docs/qwen-image-2.1-turbo-b300.md#optimization-ledger)
and [acceptance issue #3](https://github.com/InferMatrixLab/InferRSI/issues/3)
own the observations. The final campaign PASS belongs to its retained stack,
not these rejected alternatives. No source experiment is rerun here.

| Direction | Recorded observation and disposition | Suggested revisit condition and first check |
| --- | --- | --- |
| H3: initial Q/K RMSNorm + complex RoPE fusion | Operator tests passed; complete images failed; reverted. This is a quality rejection, not a kernel-speed result. | First match the actual reduction, complex FMA order and BF16 materialization; compare full native images after operator checks. H10/H13 show later, different implementations were retained, so the technique is not permanently excluded. |
| H1: packed Q/K/V 5D exchange | Quality passed but the exploratory trial was discarded. | Changed layouts/topology may justify another trial; measure staging/copies and the complete request against a matched control. Do not infer the cause from the one ledger timing. |
| H6/H7: graph projection/norm/RoPE or post-attention work | Removed for no material E2E gain; H7 records replay/copy costs. | A new capture boundary or buffer lifetime may change the tradeoff; include capture/replay, copies and full request cost. |
| H14/H16: broadcast decode scale/gate or skip empty concatenation | No demonstrated benefit; removed/reverted. | Confirm these operations are on the current critical path before repeating; retain a matched E2E control. |
| H17 and the noisy H13 attempt | Observed host load/concurrent diagnostics invalidate causal attribution. | Repeat on a qualified, uncontended host. Do not classify the numerical timing difference as a confirmed code regression. |
| H18: compiled launch API probe | Host enqueue improved in a diagnostic; no E2E integration was performed. | Treat it as an unintegrated lead; verify actual execution, correctness and complete service overhead before accepting it. |

The last column is a proposed diagnostic procedure, not an observed root cause
or permission to reopen the campaign. A new revision, workload or hardware
requires its own frozen controls and quality gate. Old helper hashes remain
bound to the original source revision.
