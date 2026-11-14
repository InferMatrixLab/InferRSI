---
name: audit-recurrent-kv-finalization
description: Audit vLLM-RLT synchronous early-exit KV propagation, later depth-specific attention reads, and request storage retirement. Use when shallow token exits leave deeper history or release order in question.
---

# Audit recurrent KV finalization

Use this procedure to distinguish copied KV contents, logical written positions and completion ownership in the pinned vLLM-RLT implementation. This is candidate source guidance; backend correctness, model quality, performance and agent efficacy remain unverified.

## Select the supported path

Record the repository revision, model/configuration, recurrent-layer set, total loops, cache layout, block size, dtype/device, selected attention backend and effective execution flags. The [source map](references/source-notes.md) pins the inspected implementation and its assumptions.

The bounded path is native Ouro with synchronous scheduling, host-owned `KVMetadata`, no speculation or connector, preemption disabled, atomic prefill, and graphs/static buffers/packed prefill disabled. The Torch reference consumer is traced. CUDA event operations are source observations; they do not qualify a native kernel or a different backend. `common` catalog placement is discovery scope.

Use another investigation for `DeviceKVMetadata`, asynchronous preemption/speculation, split/packed prefill, boundary-KV models, transfers, prefix sharing or memory-capacity planning. Record a changed condition before extending this procedure.

## Two invariants

1. For LAST_EXITED, copy the final executed recurrent-layer K/V into only the skipped deeper planes before later attention consumes that history. Preserve values already computed at shallower/executed depths. Allocated pages, written-position validity and copied data are different facts. SHARED has one plane for every depth and performs no deeper-plane propagation.
2. Keep completion ownership through finalization and later consumers, then retire runner resources before releasing cache references. A recorded event provides an ordering handle; only the appropriate wait establishes the completion needed by its consumer or reclaimer.

## Trace one token and its next consumer

1. **Resolve the exit boundary.** Follow the completed recurrent output into the scheduler. It increments `loops_done`, applies the selected exit policy and enqueues CODA when exiting. The cache exit depth is zero-based `loops_done - 1`; CODA's execution descriptor uses zero for boundary addressing and is not the token's actual completed-loop count.
2. **Follow the copying caller.** The engine applies `finalize_many(exited)` before returning the update. With synchronous execution, the runner has no async state and selects ordinary `finalize`. If a CUDA boundary stream and preceding request event exist, it waits for that predecessor, calls `finalize_token`, then records the new request event. Recording is not a host wait.
3. **Separate data from validity.** Identify the source plane/page/offset at the exit depth and destinations strictly deeper than it. The manager first requires the configured recurrent layers to have written the exit position. LAST_EXITED copies those layers' K/V to each skipped plane, then records their written positions. `mark_finalized` updates bookkeeping without copying and cannot replace this synchronous path. SHARED maps every depth to plane zero and returns without a propagation copy.
4. **Check the complete history.** The host tracker maintains a contiguous prefix plus sparse pending positions. A position in a later gap does not make the whole prefix readable. The selected host-row attention path requires all positions through the current query; reserved capacity is not evidence of that history. Do not infer these host checks for device-owned metadata.
5. **Follow a later deeper token.** CODA appends the generated token; the next PRELUDE resets loop progress. Immutable execution spans bind the new position and recurrence depth. Metadata retains the allocation identity and selects that depth's block table. Ouro's recurrent layers write current K/V before calling prepared attention. The traced Torch consumer gathers K/V through the selected table and context length, including finalized earlier tokens. Confirm the request's next submission waits on its preceding recorded event when a separate stream is used.
6. **Follow normal retirement.** The engine calls runner `release` before scheduler `finish`. Runner release synchronizes the latest recorded event when present, then recycles its slot and drops request RNG ownership. Scheduler finish calls cache `free`, removes request state, and drops allocation references. A block becomes reusable when its reference count reaches zero. This does not erase stale physical bytes, free the whole tensor pool, or establish transfer/prefix-sharing retirement.

## Decisive observations

| Observation | Interpretation / next check |
|---|---|
| Deeper plane still holds a sentinel after `mark_finalized` | Bookkeeping was observed; copying has not been established. Locate the actual copying producer. |
| Allocated pages exist but the written prefix has a hole | The later read is not established. Trace the missing write/finalization; do not manufacture validity flags. |
| Executed shallower data changes during deeper propagation | Compare source/destination depth and recurrent-layer selection against the copy contract. |
| SHARED reports one plane for every depth | Do not apply LAST_EXITED's physical-copy or per-depth-isolation expectations. |
| Event was recorded but release/wait ordering is unknown | Completion/reuse remains unestablished. Follow the last consumer and event owner before attributing stale data to allocation. |
| New request reuses old pages | Old bytes are not logical history. Check fresh allocation identity and written state before attention. |

## Verify and recover within scope

For an authorized native CPU check, use real Torch tensors with the original manager and Torch attention path. Exercise distinct values at executed and skipped depths, a later deeper token across a page boundary, SHARED as a control, premature finalization, an unwritten prefix and reused pages. A bookkeeping-only sentinel case must distinguish marking from copying. Preserve the exact input/layout/dtype tuple and outputs.

If a prerequisite or complete-prefix check fails, retain the first failing token/depth/layer and producer/consumer identities. Trace the missing operation instead of bypassing the check, substituting `mark_finalized`, or releasing pages early. If the execution flags or metadata owner leave the selected path, stop the conclusion and obtain a new bounded source/runtime check.

Report separately: source call order, actual data/validity observations, actual completion evidence, and unrun model/backend/performance checks. CPU manager checks cannot prove CUDA completion, end-to-end output equivalence or a speedup.

## Sources and notices

Read the owner-local [source observations and exact anchors](references/source-notes.md) and [immutable file ledger](references/source-identity.json) as needed. The retained [Apache-2.0 license](LICENSE) and [NOTICE](references/NOTICE.md) preserve upstream model/configuration attribution. These are source provenance, not a model-weight license audit.
