# Generation-state failures

| Symptom | Discriminating evidence | Recovery/check |
| --- | --- | --- |
| Invalid `StepStateLayout` or wrong field values | `t_max`, `gamma_max`, compiled layout size/offsets and serialized byte count | Rebuild the program with a compatible shared layout; never patch one side's offsets alone. |
| Speculative compile rejects a block | Dynamic-T flag, draft pack, gamma versus layout and verify length | Supply compatible bounds and policy. A smaller runtime `L` cannot repair an undersized compiled allocation. |
| Correct hidden rows but wrong continuation after rejection | Accepted prefix plus correction, checkpoint index, GDN/conv state, draft context length | Compare the first rejected round's complete persistent state. Resetting only target K/V misses recurrent/draft owners. |
| Unexpected acceptance differences | Argmax versus sampled proposals, target sampling, draft precision/head and feature taps | Match policies/checkpoints before blaming a kernel. Never reinterpret confidence scheduling as the fixed serving default. |
| Ring overflow / error 1 | Capacity, produced batch, head/tail sequences and host drain cadence | Reproduce with tiny synthetic ring; review bounded pump/capacity choices separately. Do not discard overflowed tokens and claim correctness. |
| Capacity reached / error 2 | Prompt plus output, target/draft capacities and reserved block rows | Reduce within an authorized context or rebuild compatible packs/programs; distinguish stopped-short output from queued no-op overrun. |
| Stop seems late | Submitted steps versus productive acceptance logs, callback cap and in-flight pumps | Inspect committed output and `done`; cancellation does not preempt an active Metal dispatch. |
| Repeated streaming step publishes nothing | `done`, state error and ring progress | Preserve `Streaming decode made no progress` as failure; avoid an unbounded retry loop. |
| Cache-resumed output differs | Exact tokens, saved recurrent parity, StepState and target/draft buffers | Use the serving-cache route to inspect snapshot integrity/identity before disabling generation safeguards. |

Unknown target/draft pairings, unavailable checkpoints/oracles, unsupported row
recipes or unobserved state remain explicit limits. Do not count CPU mocks as
DSpark numerical validation or publish target-compute projections as E2E rates.
