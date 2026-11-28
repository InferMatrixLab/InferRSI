# SGLang diffusion lifetime source notes

Inspected on 2026-10-22 from the supplied SGLang archive at `df13d5dce31abfeff0e701a62e8c39a136758e6c`.
This is a bounded source read, not whole-tree verification or a native run.
The supplier manifest independently matched only `schedule_batch.py` to a Git blob;
that selected-file check does not verify every archive member. Submodules are not expanded.

## Scope and attribution

This slice covers `sglang.multimodal_gen`, the monolithic worker's composed-pipeline
path, shared stage scheduling hooks and the inspected video/client lifecycle.
It does not cover SGLang-Omni, the LLM `srt` scheduler, Radix/HiCache, model-specific
realtime/rollout behavior, pool/disaggregated event loops or all backend strategies.
The existing SGLang owner retains the independent LLM pin
`16176278d0180f1a1a578e53e6eef432577876c2`; its HiCache peer retains
`f7ad4345b86d147a1c3095a3cebabca9a33ebaa1`. This supplement does not refresh them.

Upstream root LICENSE is Apache-2.0, copyright 2023-2024 SGLang Team (L1).
The composed pipeline, executor and stage files carry FastVideo copied/adapted
attribution; scheduler utilities also attribute Diffusers. Preserve those origins
when adapting code. This guide paraphrases mechanisms and carries no upstream
implementation. The candidate's [complete upstream license](../LICENSE) remains
packaged. A future code copy must separately retain applicable notices and licenses.

## F1: execution intervals and resource placement are separate

**CODE:** `ComposedPipelineBase.build_executor` selects `ParallelExecutor`, not
`SyncExecutor` by default (P1). All three forward entrypoints install the
process-global, pipeline-refreshed residency manager before executing (P2, M7).
Parallel executor follows each stage's declared rank policy; some branches wait
at barriers or broadcast results/errors (P3). A Python `finally` does not prove
cross-rank failure recovery or synchronized device completion.

After successful request-scope entry, the executor's `finally` invokes
`finish_request`; after successful `begin_stage`, the stage-run `finally` invokes
`end_stage` (P4-P5). Entry/setup failures before those `try` blocks are not covered
by that same cleanup guarantee. Component-use scopes separately pair begin/end
(M3). `begin_request` rebuilds ordered uses and warmup-local state (M1-M2).
Preparation calls both strategy `prepare_for_use` and `wait_for_use` before
consumption (M4); the strategy's concrete device semantics must be inspected for
a backend claim.

Closing a logical interval need not evict a module. Consecutive compatible uses,
warmup hints, `keep_ready_after_request`, resident single-DiT handling and explicit
policy interact; stage-end also releases tracked prefetched uses never consumed
(M3, M5-M6). Request-tail processing can prepare future-request components again
(M5). This is not an invariant that every request ends with empty device memory.
The worker separately schedules allocator-cache release when idle and orders a
deferred save stream after a producing event (W2); residency finish, output-save
completion and allocator reserved bytes are different observations.

**HYPOTHESIS:** an ownership ledger can distinguish an intentional retained module
from a lost use interval or in-flight save. A lower device-memory reading alone
does not prove correct output, safe reuse or improved throughput.

## F2: a field on Req is not necessarily an isolated scheduler

**CODE:** `Req.scheduler` is optional. `get_or_create_request_scheduler` defaults
to reusing the stage template; `isolate=True` deep-copies it only when creating
the request's first scheduler (S1-S2). The timestep stage returns early when both
scheduler and timesteps already exist; otherwise it sets the schedule and writes
the scheduler back to the request (S3). Denoising consumes that exact field (S5-S6).
Do not infer distinct objects merely from distinct `Req` instances.

Grouped stage reuse is explicit, not a global cache. The default fingerprint is
unique per request. Opted-in stages declare their output-copy contracts: shallow
containers preserve tensor references, tensor trees clone tensors, and runtime
objects in deepcopy fields are deep-copied (S4). The timestep stage declares
scheduler deepcopy plus timestep/sigma tensor-tree outputs (S3). This proves
the duplicate-output copy path, not isolation of every possible grouped,
model-specific or disaggregated path. Trace aliases through the actual grouping
and producer/consumer before changing concurrency or reuse.

**HYPOTHESIS:** retain serial warmup reuse until overlapping/outliving requests
require isolation; then test all affected paths with real scheduler objects.
Blind deepcopy can add work, while blind sharing can couple mutable step state.
No bug, concurrency certification or measured deepcopy cost is asserted here.

## F3: stop waiting, remove a job, and stop device work are different

**CODE:** synchronous and asynchronous scheduler clients create a request socket,
wait for a reply, translate receive timeout, and close the socket in `finally`
(C1-C2). Those inspected timeout paths send no cancellation request. Local CUDA
producer retains are released in the successful output materialization path
(C3); timeout/exception cleanup of those retains requires a separate IPC audit,
not a blanket leak or cleanup claim from this readset.

The video job task awaits generation and runs model-owned cleanup plus temporary
directory removal in `finally` (E1). Shutdown cancels HTTP-process tasks (E3).
`delete_video` only pops the store entry and returns `deleted`, beside an explicit
TODO to support aborting the job (E2). Neither operation is evidence of a device
preemption signal. The inspected control protocol contains no per-generation
abort type (C4). The monolithic scheduler receives and dispatches work, converts
execution exceptions to error output, then replies/drains finalizers (Q1-Q3, W1).
Its docstring saying “Handles abortion” is not an implementation guarantee.

**TEST-SOURCE:** the scheduler-client tests include real in-process ZeroMQ deadline
cases; the cancelled-socket test replaces the socket with mocks (T1). That test
asserts socket closure only. It cannot certify worker cancellation or release
latency. All listed upstream tests are inspected, **not_run** here.

**HYPOTHESIS:** correlate client task, request ID, scheduler dispatch, stage/use
completion, finalize completion and device timeline before claiming cancellation.
A timeout should preserve an unknown execution outcome until worker evidence
resolves it. Do not retry a side-effectful job as though the original never ran.

## Pinned readset

CODE means observed implementation, TEST-SOURCE means inspected assertions;
neither means the upstream code was run. Ranges below are the primary readset;
adjacent imports/declarations were read only to resolve the named chain.

| ID | Evidence | Inspected symbol/scope | Immutable source |
|---|---|---|---|
| E0 | CODE | `process_generation_batch to scheduler_client.forward` | [python/sglang/multimodal_gen/runtime/entrypoints/openai/utils.py:516-555](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/entrypoints/openai/utils.py#L516-L555) |
| E1 | CODE | `_dispatch_job_async; finally cleanup` | [python/sglang/multimodal_gen/runtime/entrypoints/openai/video_api.py:371-469](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/entrypoints/openai/video_api.py#L371-L469) |
| E2 | CODE | `delete_video; TODO abort` | [python/sglang/multimodal_gen/runtime/entrypoints/openai/video_api.py:835-850](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/entrypoints/openai/video_api.py#L835-L850) |
| E3 | CODE | `shutdown_video_jobs; task cancellation` | [python/sglang/multimodal_gen/runtime/entrypoints/openai/video_api.py:79-98](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/entrypoints/openai/video_api.py#L79-L98) |
| C1 | CODE | `SchedulerClient._forward_one/_forward_routed` | [python/sglang/multimodal_gen/runtime/scheduler_client.py:174-206](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/scheduler_client.py#L174-L206) |
| C2 | CODE | `AsyncSchedulerClient.forward/_forward_one` | [python/sglang/multimodal_gen/runtime/scheduler_client.py:264-308](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/scheduler_client.py#L264-L308) |
| C3 | CODE | `local CUDA IPC retain release on successful round trip` | [python/sglang/multimodal_gen/runtime/scheduler_client.py:344-354](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/scheduler_client.py#L344-L354) |
| C4 | CODE | `control request protocol` | [python/sglang/multimodal_gen/runtime/entrypoints/control_requests.py:1-50](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/entrypoints/control_requests.py#L1-L50) |
| Q1 | CODE | `_dispatch_items/_handle_generation` | [python/sglang/multimodal_gen/runtime/managers/scheduler.py:300-370](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/scheduler.py#L300-L370) |
| Q2 | CODE | `monolithic event_loop receive/dispatch` | [python/sglang/multimodal_gen/runtime/managers/scheduler.py:1397-1516](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/scheduler.py#L1397-L1516) |
| Q3 | CODE | `result reply/finalize drain` | [python/sglang/multimodal_gen/runtime/managers/scheduler.py:1518-1572](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/scheduler.py#L1518-L1572) |
| W1 | CODE | `GPUWorker.execute_forward` | [python/sglang/multimodal_gen/runtime/managers/gpu_worker.py:567-608](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/gpu_worker.py#L567-L608) |
| W2 | CODE | `deferred finalize stream; release_cache_if_idle` | [python/sglang/multimodal_gen/runtime/managers/gpu_worker.py:840-943](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/gpu_worker.py#L840-L943) |
| W3 | CODE | `_forward_group` | [python/sglang/multimodal_gen/runtime/managers/gpu_worker.py:1258-1262](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/gpu_worker.py#L1258-L1262) |
| P1 | CODE | `constructor/build_executor defaults` | [python/sglang/multimodal_gen/runtime/pipelines_core/composed_pipeline_base.py:106-178](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/composed_pipeline_base.py#L106-L178) |
| P2 | CODE | `forward paths/_install_component_residency_manager` | [python/sglang/multimodal_gen/runtime/pipelines_core/composed_pipeline_base.py:1088-1189](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/composed_pipeline_base.py#L1088-L1189) |
| P3 | CODE | `_execute_stages; rank policies/collectives` | [python/sglang/multimodal_gen/runtime/pipelines_core/executors/parallel_executor.py:29-181](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/executors/parallel_executor.py#L29-L181) |
| P4 | CODE | `request residency/cache scopes and stage hooks` | [python/sglang/multimodal_gen/runtime/pipelines_core/executors/pipeline_executor.py:58-140](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/executors/pipeline_executor.py#L58-L140) |
| P5 | CODE | `stage execution context and finally` | [python/sglang/multimodal_gen/runtime/pipelines_core/executors/pipeline_executor.py:188-223](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/executors/pipeline_executor.py#L188-L223) |
| M1 | CODE | `ComponentUse/ResidencyState` | [python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py:39-78](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py#L39-L78) |
| M2 | CODE | `begin_request; ordered stage uses` | [python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py:197-236](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py#L197-L236) |
| M3 | CODE | `begin/end stage/use and use_component finally` | [python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py:280-407](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py#L280-L407) |
| M4 | CODE | `finish_active_use; prepare and wait` | [python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py:462-498](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py#L462-L498) |
| M5 | CODE | `finish_use/finish_request; retention and tail prefetch` | [python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py:586-692](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py#L586-L692) |
| M6 | CODE | `unconsumed prefetch release and keep/preferred policy` | [python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py:817-883](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py#L817-L883) |
| M7 | CODE | `process-global manager refresh` | [python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py:967-986](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py#L967-L986) |
| S1 | CODE | `Req.scheduler and timestep state` | [python/sglang/multimodal_gen/runtime/pipelines_core/schedule_batch.py:173-196](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/schedule_batch.py#L173-L196) |
| S2 | CODE | `clone_scheduler_runtime/get_or_create_request_scheduler` | [python/sglang/multimodal_gen/runtime/pipelines_core/diffusion_scheduler_utils.py:72-93](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/diffusion_scheduler_utils.py#L72-L93) |
| S3 | CODE | `scheduler reuse and output declarations` | [python/sglang/multimodal_gen/runtime/pipelines_core/stages/timestep_preparation.py:48-174](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/stages/timestep_preparation.py#L48-L174) |
| S4 | CODE | `grouping/copy contracts for stage-owned outputs` | [python/sglang/multimodal_gen/runtime/pipelines_core/stages/dedup.py:18-157](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/stages/dedup.py#L18-L157) |
| S5 | CODE | `_prepare_denoising_loop reads batch.scheduler` | [python/sglang/multimodal_gen/runtime/pipelines_core/stages/denoising.py:1209-1243](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/stages/denoising.py#L1209-L1243) |
| S6 | CODE | `denoise/step loop/use completion` | [python/sglang/multimodal_gen/runtime/pipelines_core/stages/denoising.py:2012-2150](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/runtime/pipelines_core/stages/denoising.py#L2012-L2150) |
| T1 | TEST-SOURCE | `real inproc timeout tests vs mocked cancelled-socket test` | [python/sglang/multimodal_gen/test/unit/test_scheduler_client.py:72-138](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/test/unit/test_scheduler_client.py#L72-L138) |
| T2 | TEST-SOURCE | `three entrypoint install tests; patched manager` | [python/sglang/multimodal_gen/test/unit/test_pipeline_residency_manager_install.py:1-127](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/test/unit/test_pipeline_residency_manager_install.py#L1-L127) |
| T3 | TEST-SOURCE | `inference-mode and conditioning scopes; mocks` | [python/sglang/multimodal_gen/test/unit/test_pipeline_executor.py:1-160](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/test/unit/test_pipeline_executor.py#L1-L160) |
| T4 | TEST-SOURCE | `component policy and CUDA snapshot tests` | [python/sglang/multimodal_gen/test/unit/test_component_residency.py:62-209](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/sglang/multimodal_gen/test/unit/test_component_residency.py#L62-L209) |
| D1 | CODE | `runtime/diffusion dependencies` | [python/pyproject.toml:1-132](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/python/pyproject.toml#L1-L132) |
| D2 | CODE | `manual GPU consistency generation workflow; external CI data` | [.github/workflows/diffusion-ci-gt-gen.yml:1-224](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/.github/workflows/diffusion-ci-gt-gen.yml#L1-L224) |
| D3 | CODE | `manual 1-NPU consistency generation entry` | [.github/workflows/diffusion-ci-gt-gen-npu.yml:86-141](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/.github/workflows/diffusion-ci-gt-gen-npu.yml#L86-L141) |
| L1 | CODE | `Apache-2.0; SGLang Team attribution` | [LICENSE:1-201](https://github.com/sgl-project/sglang/blob/df13d5dce31abfeff0e701a62e8c39a136758e6c/LICENSE#L1-L201) |

## Validation boundary

No upstream import, native scheduler/executor test, model generation, device test,
quality comparison or performance measurement was run. InferRSI source/packaging
checks validate this knowledge delivery only. GPU/NPU generation workflows
require their own dependencies, model/checkpoint and CI-data inputs (D1-D3).
CPU transport or object-copy checks cannot substitute for stage collectives,
device event ordering, offload behavior or real-model output quality.
