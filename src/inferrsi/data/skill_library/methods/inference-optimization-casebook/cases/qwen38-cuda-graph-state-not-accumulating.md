# CUDA Graph replay read capture-time state: ids stayed equal while logits diverged

A single-request Qwen3.8 decode engine (64 layers: 48 linear-attention/DeltaNet
plus 16 full-attention) captured its whole decode step into a CUDA Graph. Greedy
token ids matched the eager path exactly, so three successive regression gates
passed. Per-step logits comparison later showed the graph path was not computing
the same thing: the hybrid state was rebuilt as fresh tensors every step, so
replay kept reading the addresses captured on the first step and never
accumulated state.

| Observation | Value |
| --- | --- |
| Per-step max_abs logits, graph vs eager | 0.70 (greedy ids identical) |
| After preallocating and writing state in place | 0.00e+00 on the tiny fixture |
| TPOT delivered by the affected configuration | unchanged (the bug costs no time) |

Disposition: a token-id equality gate is not a correctness oracle. A graph path
needs a per-step logits comparison against eager, plus an explicit statement of
which buffers are captured by address. The fix is to preallocate every recurrent
buffer the graph writes and to capture into a dedicated memory pool so later
eager allocations cannot alias it.

Revisit condition: any engine that captures a step whose state is created inside
the step. First check: print the data pointers of every state tensor before and
after capture; if they change between steps, replay is writing to stale storage.

Applicability: single device, batch size 1, hybrid linear-attention models,
PyTorch CUDA Graph. Not established for multi-request graphs or for graphs whose
state lives in a paged allocator.

Limitations: observed on one H20-3e card with one workload; no concurrency and
no cross-device qualification. The configuration was recorded as INCONCLUSIVE
for acceptance purposes because the measurement that exposed it happened after
the timing run.
