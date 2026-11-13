# Generation-lifecycle troubleshooting

| Observation | Source-specific check | Safe conclusion |
| --- | --- | --- |
| Completion info arrived, cache reused immediately | Info is yielded before MLX default-stream synchronization and producer return. Which owner retained and joined the producer task? | Info alone is not deterministic cleanup evidence; retain the unresolved lifetime gap. |
| Task cancelled but one more token/work item appears | Was next already entered, or was prompt preparation performed before Task construction? next pipelines its successor before returning the previous token. | Cancellation is cooperative, not rollback or preemption. Preserve actual ordering rather than asserting zero post-request work. |
| Consumer break returns without final info | onTermination may request cancellation; the vanished consumer may never observe the attempted info yield. | Missing info is not automatically native failure. Join the producer through the task-handle path for deterministic lifetime evidence. |
| Cancelled consumer sees `.length` | Producer may have completed before consumer cancellation; no event ordering is recorded. | Do not rewrite stop reason from the consumer's final state alone. |
| Two streams overlap despite a shared container | Container generation serializes prefill/startup, then independent workers can overlap against evaluated weights. | Do not promise full-stream locking or mutate shared weights/caches on that assumption. |
| Actor-based replacement corrupts async access | Actor isolation can be released at awaits; source uses an explicit async mutex across the complete body. | Preserve the actual exclusivity contract; do not claim actor syntax alone is equivalent. |
| Cancelled operation still waits for container access | Inspected mutex continuations have no cancellation-removal handler. | Cancellation request is not immediate waiter eviction or queue preemption. |
| Application cannot call SendableBox/GenerationWorker | These are private/package implementation utilities, not public application APIs. | Use public container/task-handle entry points; do not invent exported helpers or ModelContainer.synchronize. |
| Joined record has no directly observed native sync | A source-level completed producer join follows cleanup, but the helper only sees caller declarations. | Label caller-declared join only; native observation authentication remains unverified. |
| CPU task-context test passed | Explicit CPU override tests executor/control-flow semantics, not Metal submission/backgrounding. | Preserve required Metal gap and any GPU-only skipped test. |
| Chunk count differs from generationTokenCount | Detokenization/tool events and stop filtering differ from returned token collection. | Retain raw token/info evidence and API settings; do not infer tokens from text chunks. |
| Record auditor exits 0 with gaps | Exit 0 means schema-valid declarations; unresolved rows/conflicts are reported separately. | No native pass, performance result or permission to reuse mutable state follows. |
| Record input rejected | Exact keys, bounded enums/opaque IDs, integer counts, duplicate/nonfinite/type/size and regular-file constraints apply. | Correct the schema, not its safety limits. Diagnostics do not echo private payloads or paths. |

Return source-supported ordering, actual observations and remaining uncertainty
as separate statements. No helper output or green scaffold CI closes native,
model/quality or end-to-end service gaps.
