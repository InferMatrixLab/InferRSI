# Audit abort acknowledgment and resource reclamation

Incremental source: vllm-project/vllm-omni at `18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e`, inspected 2026-10-22. Apache-2.0; copyright contributors to vLLM-Omni/vLLM per the cited files. This reference extends the existing validation procedure; it does not replace its older source pin or qualify the engine on a device.

CODE below describes this implementation. TEST-SOURCE describes inspected upstream assertions, not executed tests. The diagnostic procedure and proposed checks are HYPOTHESIS until applied to a matching environment. Runtime, model, transport and performance validation are **not_run**.

## Keep three completion boundaries separate

| Boundary | CODE at this pin | Limit |
|---|---|---|
| Abort submitted | `OmniEngineBase.abort` enqueues without a correlation ID | Return does not acknowledge stage abort or request cleanup |
| Logical abort acknowledged | A received correlated result with `success=True` follows awaited stage-pool aborts, binding release and logical-state removal | An empty/shutdown no-op can also return `[]` without a receipt; neither return shape nor a receipt is an all-device synchronization or transfer-reclamation acknowledgment |
| Transfer resources reclaimed | Request teardown schedules per-replica release tasks when the chunk-transfer adapter exists | Tasks are queued, best effort and separately bounded; a successful abort result does not establish their completion |

The decisive path is `_handle_abort` → `_cleanup_request_ids(abort=True)` → `_abort_request_ids`, followed by binding release, **scheduling** transfer reclamation and logical-state removal. `_release_stage_transfer_resources` explicitly queues rather than awaits release. Do not strengthen a comment saying “cleanup finished” into proof that every remote buffer was freed (A1–A4).

StagePool routes abort by the existing request-to-replica binding. For AR stages it collects output-processor partial tokens without committing processor state, awaits the client abort and then commits that state. An abort exception prevents that commit. Orchestrator output filtering retains only the request's final-output stages and marks the final message per request. Diffusion stages supply no partial abort outputs on this path (A2/A4). This is an implementation observation, not a recommendation to retry every model automatically.

## Correlation and timeout ownership

`CorrelatedRpcClient` registers a waiter before submission and unregisters it in `finally`. Its router delivers by `(namespace, rpc_id)` and drops late/unknown results; unregistering a waiter does not retract a queued request (A5).

`abort_async` uses `block_on_submit=True`. Submission can block on queue backpressure; the specified timeout is passed to `waiter.get` **after** submission. It therefore does not bound the entire submit-plus-wait operation. A timeout means acknowledgment was not obtained within that wait, not that the orchestrator stopped processing the abort. The coroutine also delegates its wait to an executor; do not infer that cancelling the caller interrupts the worker or engine (A1/A5, deduction from the inspected control flow).

## Apply the existing validation procedure

Prerequisites: exact engine/vLLM revisions, actual entry API, stage types, request IDs and replica bindings, async-chunk setting, connector/backend, output contract and a supported local fixture. Select the actual caller: the methods above are engine-base APIs, not proof that every serving wrapper exposes identical behavior.

1. Trace submission, stage abort, logical cleanup, acknowledgment and deferred transfer release as separate events for the same request ID. Include classifier-free-guidance companion IDs where enabled: cleanup expands parent/companion state, and losing an unfinished companion can fail its waiting parent (A3).
2. Preserve partial AR outputs and their external request IDs through abort. Check failure before processor-state commit. Treat diffusion's empty abort-output list separately from successful media completion.
3. Exercise queue backpressure, delayed/reordered acknowledgment, timeout and shutdown. Inspect whether the original abort is still pending before issuing a subsequent request; a missing receipt is not an acknowledgment of cancellation.
4. Inspect per-replica pending release batches and completion/error evidence. A hung replica must not be treated as reclaimed because a healthy replica or the logical abort finished. Without an async-chunk adapter, this release path intentionally does no work (A4).
5. Verify the subsequent request and affected resource ownership in the actual backend. Stop at a missing fixture, failed contract or unsupported entry path; retain the gap instead of substituting a synthetic engine for device evidence.

Suggested evidence: a request/companion/replica table, terminal outputs, submission and acknowledgment timestamps, pending release state, actual backend completion/reclamation evidence and next-request correctness. Only then investigate leaks or latency. No reproduced speedup or end-to-end timeout bound is supplied here.

## Pinned evidence and bounded readset

| ID | Evidence | Supports |
|---|---|---|
| A1 | CODE: [omni_engine_base.py L774–838](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/vllm_omni/engine/omni_engine_base.py#L774-L838) | Enqueue-only versus correlated wait, submission backpressure, result/error handling |
| A2 | CODE: [orchestrator.py L660–746](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/vllm_omni/engine/orchestrator.py#L660-L746) | Ack/error result, final-stage partial outputs and binding release |
| A3 | CODE: [orchestrator.py L1791–1854](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/vllm_omni/engine/orchestrator.py#L1791-L1854); [release helper L748–766](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/vllm_omni/engine/orchestrator.py#L748-L766) | Companion closure, logical cleanup and queued transfer release |
| A4 | CODE: [stage_pool.py L1339–1459](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/vllm_omni/engine/stage_pool.py#L1339-L1459) | Bound-replica abort, processor commit, adapter gate and independent best-effort release batches |
| A5 | CODE: [rpc_result_router.py L39–150](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/vllm_omni/engine/rpc_result_router.py#L39-L150); [messages.py L120–131](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/vllm_omni/engine/messages.py#L120-L131) | Waiter lifetime, late-result routing and typed correlation |
| T1 | TEST-SOURCE: [abort acknowledgment tests L23–180](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/tests/engine/test_async_omni_engine_abort_ack.py#L23-L180) | Queue-level assertions for receipt, failure, timeout and backpressure; no real stage/backend |
| T2 | TEST-SOURCE: [processor failure test L146–173](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/tests/engine/test_stage_pool_collective_rpc.py#L146-L173); [release batching L42–89](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/tests/engine/test_stage_pool_release_batching.py#L42-L89) | Upstream tests use synthetic clients; inspect their scope before claiming native validation |
| T3 | TEST-SOURCE: [router assertions L34–123](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/tests/engine/test_rpc_result_router.py#L34-L123) | Reordered/late results, fatal errors and close |
| E1 | CODE: [test setup L15–32](https://github.com/vllm-project/vllm-omni/blob/18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e/tests/conftest.py#L15-L32) | Test bootstrap imports vLLM-related helpers; a CPU marker is not a standalone environment |

Readset is limited to these ranges plus API/import navigation. Full duplex/session lifetimes, all serving wrappers, native engine abort guarantees, connector internals, model semantics and performance are deferred. The pinned source archive has unexpanded submodules; one manifest-selected file was independently matched to a GitHub blob, not the entire tree. No model weights, engine scripts or upstream tests were executed for this reference.
