# Unread leads for a separate next gate

These are not mined sources, current-support claims or work started under Pack D. The approved extraction stops at three papers.

1. **Historical author-linked implementation, only if an implementation decision is next.** D2/D3 point to [Dao-AILab/flash-attention](https://github.com/Dao-AILab/flash-attention). No source code was opened. First resolve an immutable commit corresponding to the chosen paper version and the exact forward/backward/layout question; paper code availability alone is not a version pin. A narrow implementation read could resolve pseudocode boundary/rescaling details without treating the current main branch as historical evidence.
2. **Target-accelerator capability mapping, only if a specific port is authorized.** Needed evidence: actual device/compiler versions, local-memory/register budgets, asynchronous load/matmul completion semantics, legal low-precision layouts and supported numerical contracts. No vendor document or NPU kernel was inspected in this pack. Hardware similarity and a paper's expectation of transfer are insufficient.
3. **Representative low-precision quality validation, only if FP8 deployment/training is requested.** D3 leaves large-scale training effects open; Table 3 is synthetic RMSE. Define the actual model/task metric, accepted error and preprocessing boundary before selecting a bounded authorized test. This is an evidence gap, not permission to run a reproduction or heavy A/B.

No additional attention paper, distributed-attention implementation or compiler project is needed to complete the present extraction.
