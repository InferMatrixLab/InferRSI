# Case: zero-overhead scheduling in DeepInfer

A worked, source-level instance of hiding exposed host prep behind device execution. It is the same trade-off this skill's loop optimizes, applied one layer down: instead of making the Python cheaper, it moves the Python so it runs while the GPU is busy.

Source: [deepseek-ai/DeepInfer @ 8b16149741a4935e1dec8cea27853f273b374c5b](https://github.com/deepseek-ai/DeepInfer/tree/8b16149741a4935e1dec8cea27853f273b374c5b) (Apache-2.0), read statically. Nothing was built or run. **F** is observed source behaviour at this pin; **P** is proposed. The bounded readset is the cited worker, engine, scheduler, remap, constructor and synchronization paths; it does not establish native preemption safety or an end-to-end speedup.

## What the bubble is

A decode step alternates device work with CPU work, and the CPU work must consume a device-to-host result from the step it post-processes. The naive order is:

```text
forward(N) -> sample(N) -> D2H -> post-process(N) -> schedule(N+1) -> forward(N+1)
```

The D2H wait plus post-process plus schedule sit between two device launches, so the GPU idles for their duration. That is exposed host prep: the same phenomenon this skill measures before deciding whether to optimize or redirect.

## The reorder

```text
forward(N) -> post-process(N-1) -> sample(N) -> [defer post-process(N)]
```

`F`: [deepinfer/worker/worker.py:182-187](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/worker.py#L182-L187). Prompt steps never defer; only decode steps, and only when `DEEPINFER_ZERO_OVERHEAD_SCHEDULING` is on:

```python
if is_prompt or not envs.DEEPINFER_ZERO_OVERHEAD_SCHEDULING:
    request_outputs = np.concatenate([request_outputs, self._post_process_step(curr_step_state)])
    self.prev_step_state = None
else:
    self.prev_step_state = curr_step_state
```

After launching the next forward, the worker post-processes the retained previous state ([worker.py:113-144](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/worker.py#L113-L144)). This is the source's intended overlap; its duration was not measured here.

## What becomes stale, and the repair

This is the part worth copying. Three quantities the scheduler reads are now one step behind:

| Quantity | Why it is stale | Repair |
|---|---|---|
| Per-request query length | Under adaptive verification the per-request split uses previous-step confidence estimates | Redistributed on device from those estimates while preserving the CPU-selected total row budget |
| Per-request key length | Rejected drafts mean the previous step accepted fewer tokens than it requested | Recomputed on device from previous-step accepted counts |
| Input token ids | Rows continuing from the previous batch reuse the previous step's sampled ids | Scatter from the previous batch via a remap |

`F`: [worker.py:191-245](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/worker.py#L191-L245). The remap matches current batch slots to previous batch slots by stable sequence id; `-1` marks a fresh row. Equal batch order produces an identity remap; otherwise an ID lookup builds it. The correction path is skipped when there is no overlap, not merely when order matches ([csrc/engine/zos.cpp:142-175](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/zos.cpp#L142-L175)).

```python
if envs.DEEPINFER_ENABLE_MTP_VARLEN:
    compute_seqlens_q_by_confidence_rates(total_q, remap[:n_seq], prev.sampler_output.confidence_rates_gpu, seqlens_q[:n_seq])
if self.nextn > 0:
    compute_seqlens_k_zos(...)
```

Input-token repair consumes that remap and the previous sampled/draft IDs in [prepare_tensor_input_zos.py:235-244](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/input_metadata/prepare_tensor_input_zos.py#L235-L244), with fresh rows prepared in [zos.cpp:104-113](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/zos.cpp#L104-L113). Corrected query lengths feed the main forward, then the worker synchronizes their D2H metadata before current-step sampling ([worker.py:118-152](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/worker.py#L118-L152)).

Note the dependency this creates: the deferred path is only correct because the *next* step repairs what the deferred post-process would have produced. If your engine cannot enumerate the stale quantities, deferring the post-process silently produces wrong metadata rather than a crash.

## Conditions and their source support

1. **Keep host scheduling independent of the device work being hidden.** The inspected [Scheduler::_schedule releases the GIL](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/scheduler.hpp#L275-L277). This permits other Python work; it is not by itself a proof that every scheduler branch is free of device synchronization.
2. **The standard ZOS constructor selects a host DP group.** [LLMEngine._create_scheduler selects cpu_data_parallel_group when ZOS is enabled](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/llm_engine.py#L307-L314); [that group is created with Gloo](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/parallel_utils/parallel_state.py#L89-L94). The scheduler [recognizes Gloo](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/scheduler.hpp#L109-L111) and [uses a CPU tensor for its synchronous vote](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/scheduler.hpp#L169-L181). The alternate group path can use the default device; do not generalize the host property to arbitrary scheduler construction.
3. **The launch scope has a synchronization debug guard.** Forward and sample launches use `forbid_cuda_sync()` ([model_runner.py:321-324](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/model_runner.py#L321-L324), [356-359](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/model_runner.py#L356-L359)). It targets torch-visible CPU-GPU synchronization, but Event.synchronize is outside its coverage, another thread's allow scope lifts enforcement, and DEEPINFER_DISABLE_SYNC_GUARD disables it ([utils.py:119-132](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/utils.py#L119-L132)). Guard presence is not a measured absence of synchronization.

## The cost

- One extra step of retained metadata, request outputs, state slots and KV blocks.
- A device-side repair path that must be maintained alongside the scheduler.
- Deferred output delivery needs a final drain; the worker supplies [flush_inflight_reqs](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/worker.py#L274-L283). End-to-end output latency was not measured.
- The standard ZOS path's CPU DP group must remain available; a custom construction must preserve the intended host/device ordering.

## Relevance to this skill

Use this case to interpret the exposed-prep metrics rather than to replace the loop. A large exposed-prep ratio with a large inter-step gap is the signal; the options are to make the prep cheaper (this skill's line-profiling loop) or to move it (this case). The second is cheaper to implement when the prep is Python-bound and the device has slack, which is exactly the condition a profile should show first.

Do not copy the repair list. It is specific to engines where speculation width and accepted length feed back into the next step's row layout.

## Unresolved

- **F — preemption bookkeeping has guards.** [The scheduler rejects COMPLETION recompute configuration](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/scheduler.hpp#L98-L104). Its [_preempt path either stops the request or resets it to WAITING for recompute](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/scheduler.hpp#L766-L789). Deferred decode output [skips WAITING requests](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/scheduler.hpp#L917-L925), as does [MTP post-processing](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/scheduler.hpp#L1212-L1224). Therefore "no guard found" is not an accurate description of this readset.
- **F — some resource release is explicitly deferred.** [Worker post-processing synchronizes the step's sample event before its callback](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/worker.py#L259-L271); the engine [collects sequence metadata after post-processing](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/llm_engine.py#L1010-L1015). [DeferredRelease releases collected metadata/output objects and waits for a clone event before unpinning clone resources](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/llm_engine.py#L89-L116). These are specific lifetimes, not a proof about every state-slot or KV-block reuse path.
- **HYPOTHESIS / not established — device resource reuse under preemption.** An unsafe reuse claim would need a concrete in-flight write, release/reallocation path and ordering that allows them to conflict. No native experiment was run; the bounded source readset establishes neither such a reachable race nor complete preemption safety. Preserve it as an unvalidated lifetime question, not a known bug or a verdict that ZOS is unsafe.
- **The default is constructor-dependent.** [EnvVar.bool defaults false](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/environ.py#L69-L71), while [EngineArgs sets the unset variable and rearms it](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/arg_utils.py#L48-L55) from [NORMAL/COMPLETION true, PROMPT false](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/engine_type.py#L15-L17). This supports the README's default description for the standard NORMAL/COMPLETION path without treating the standalone environment default as a contradiction. Explicit environment overrides remain effective.
