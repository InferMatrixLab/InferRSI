# Attributing a vLLM-Ascend service delay with MindStudio

Use this reference when a client observes slow first or subsequent tokens and
you need to choose between investigating queueing, host dispatch, model compute
and communication. Start with the affected request phase and traffic cohort.
Use the owner's CANN procedure when the investigation reaches device work.

## Scope and attribution

The source is MindStudio Service Profiler at `04bd9bf0cb804e7bca92103d47b3ad029b999f51`.
The [service diagnostics guide](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/docs/en/best_practices/vllm_ascend_observability_analysis_guide.md)
and [hook tracing guide](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/docs/en/user_guide/vLLM_hook_tracing_instruct.md) describe independent metrics and
tracing paths. The latter requires vLLM V1 with native OpenTelemetry and a
compatible vLLM-Ascend pair. Its documented support floor is vLLM-Ascend
`0.20.0`, with vLLM-Ascend `0.20.2rc1` and vLLM `0.20.2` the first public
pair cited at the pin. Individual YAML hook version guards apply to particular
symbols. They do not establish end-to-end tracing support for older releases.

MindStudio's software is [MulanPSL-2.0](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/LICENSE), also identified in
the inspected Huawei Technologies handler headers. Its [license notice](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/docs/zh/legal/license_notice.md)
assigns the material in `docs/` to [CC BY 4.0](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/docs/LICENSE). This
reference summarizes the two MindStudio guides and independently describes
selected Python handlers. It includes no upstream implementation or figures.

## What the hooks measure

Use the [symbol map](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/ms_service_profiler/patcher/vllm/config/service_profiling_symbols.yaml) to identify the concrete
entry point for each observation. A named OpenTelemetry span and a profiling
event are different outputs. Check which collector produced the data before
joining observations.

| Question | Observation at this revision | Boundary |
| --- | --- | --- |
| Did the request wait for scheduling? | `Scheduler.add_request` emits a `WAITING` enqueue after insertion. `schedule` compares the waiting and running queues before and after the call. Match request and queue to the corresponding dequeue on the same time base. [Batch handlers](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/ms_service_profiler/patcher/vllm/handlers/v1/batch_handlers.py#L29-L118) | A schedule call can serve many requests. Its duration measures scheduler work, not one request's queue residence. The handler returns early when classification yields no request IDs. |
| Was KV block pressure present? | For scheduled tokens, `schedule` records free and used blocks after scheduling. `AllocatedBlocks` is the change in used blocks across the call. `free` records remaining free capacity after freeing, and `get_computed_blocks` records a request token-hit fraction when the return shape and request length allow it. [Batch handler](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/ms_service_profiler/patcher/vllm/handlers/v1/batch_handlers.py#L65-L109) and [KV handlers](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/ms_service_profiler/patcher/vllm/handlers/v1/kvcache_handlers.py#L20-L40) | A net delta can hide allocations offset by frees. A low free-block reading or one cache miss is insufficient to attribute a queue stall. Look for coincident allocation failures, wait growth or recomputation under matched load. |
| Did time accumulate around model execution? | `modelExec` spans the executor call. For a future it ends on completion callback, for an awaitable on completion of the await. `modelRunnerExec` wraps the worker's runner invocation. The executor's `batch_size` attribute is populated from the **number of scheduled tokens**. [Model handlers](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/ms_service_profiler/patcher/vllm/handlers/v1/model_handlers.py#L91-L181) | Compare associated intervals and account for overlaps before attributing a gap to dispatch or IPC. A runner span includes host work. Separate a compute kernel from HCCL only with aligned device activities on the affected ranks. |
| Where are request boundaries? | The request handler emits `httpReq` and `tokenize` together **before** awaiting the original function. A finished output with accessible request state emits `httpRes` before the original output processor runs. [Request handlers](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/ms_service_profiler/patcher/vllm/handlers/v1/request_handlers.py#L28-L56) | These event names do not measure tokenizer duration or client receipt. Use a client observation for end-to-end latency and first-token timing. |

## Recheck a proposed attribution

1. Record the model and software revisions, device and parallel topology,
   warm-up, arrival pattern, input/output lengths, concurrency, sampled window
   and enabled collection domains. Compare a reference and an affected window
   with the same settings. Measure instrumentation overhead separately with
   collection off and on at fixed load. Some [model hooks](https://github.com/Ascend/msserviceprofiler/blob/04bd9bf0cb804e7bca92103d47b3ad029b999f51/ms_service_profiler/patcher/vllm/handlers/v1/model_handlers.py#L24-L89)
   synchronize the NPU stream around the sampled function.
2. With metrics alone, compare first-token and per-output-token distributions
   against queue depth, scheduler duration and KV counters for the same
   instance and phase. With tracing, follow a parent, span link or recorded
   request ID across boundaries. For cross-process gaps, require aligned
   clocks and a shared trace or unified timeline. The documented per-span cap
   is 128 request IDs and links. Missing identities beyond that cap leave
   batch-level evidence only.
3. Pick the narrowest hypothesis supported by the data. For a scheduler
   hypothesis compare queue residence with scheduler duration. For a host
   dispatch hypothesis match the executor/runner gap to a host timeline. For
   compute versus communication use device kernel and HCCL activities and
   check overlap on the critical path. If linkage, device activities or a
   comparable baseline are missing, record the observed phase and the missing
   discriminator. Overlapping or nested spans cannot be added as wall time.
4. To test causality in a separately authorized experiment, change one
   suspected factor, then compare the same cohort, instrumentation and client
   measurements. A service-level improvement requires its own end-to-end
   evidence. The upstream examples illustrate diagnostic patterns only.

**Static verification.** At the pinned revision, follow the YAML targets for
`Scheduler.schedule`, `KVCacheManager.free`, `Executor.execute_model`,
`NPUModelRunner.execute_model` and `AsyncLLM.add_request` into the linked
handlers. Inspect their event ordering, early returns, return-type branches
and the value assigned to each counter. Compare the tracing guide's
compatibility section with the YAML version guards. This checks source
semantics without collecting a trace.

**Evidence status.** `empirical_validation: not_run`. InferRSI has not run
this integration or measured tracing overhead, any suspected bottleneck or a
service gain for this intake.
