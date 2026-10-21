---
name: diffusers-invocation-state
description: Trace Diffusers pipeline-wrapper and scheduler invocation state when repeated calls, from_pipe reuse or interruption produce unexpected schedules or retained request state; scoped to FluxPipeline and FlowMatchEulerDiscreteScheduler source evidence.
---

# Trace Diffusers invocation state

Use for a concrete repeated/overlapping-call, wrapper-reuse, interrupted denoising or scheduler-progress question. Do not use as a blanket thread-safety decision, an offload tuning guide, a model quality certificate or a concurrency manager implementation.

This source-derived candidate has runtime validation not_run. Its [source map](references/source-map.md) covers FluxPipeline and FlowMatchEulerDiscreteScheduler at one pin; other pipelines and schedulers need their own contracts. Read the [ownership path](references/ownership.md) before proposing a change.

## Inputs

Record the exact Diffusers/PyTorch revisions, pipeline and scheduler classes and object identities, construction/from_pipe path, actual model/adapter/tokenizer contents, scheduler config, effective timesteps/sigmas, image/latent shape and dtype, callback, interrupt timing, output_type and cleanup path. If calls overlap, inspect the existing caller's admission/serialization contract and keep their actual intervals.

## Procedure

1. **Separate wrapper and component identities.** register_modules stores supplied objects; components/from_pipe can pass those same objects to another wrapper. Check scheduler identity explicitly instead of assuming a new wrapper deep-copied its execution state (S1).
2. **Follow request setup.** The inspected Flux call writes guidance/attention state, clears current_timestep and resets interrupt. Its timestep adapter calls the selected scheduler's set_timesteps. Record the resolved schedule, not only the requested step count (S2).
3. **Trace the scheduler cycle.** FlowMatchEulerDiscreteScheduler replaces timesteps/sigmas and resets step/begin indices. Flux sets begin_index=0; step initializes its index if needed, reads adjacent sigmas and advances the index. Pass an actual scheduler timestep, not enumerate's integer position (S3).
4. **Trace interruption to its consumer and tail.** Flux observes interrupt at the loop boundary and continues past remaining work; the callback runs after a scheduler step. Normal control flow can still decode/postprocess and free hooks. This is cooperative iteration skipping, not cancellation of an already submitted kernel, a complete image-quality result, or proof of exception cleanup (S4).
5. **Resolve the real owner.** Establish one invocation's ownership from schedule setup through output/cleanup under the existing caller's contract. If that caller already serializes shared mutable pipeline/scheduler state, preserve it. A proposal for independent request state must distinguish scheduler/wrapper state from shared model weights and be tested; do not create another manager solely from field names.
6. **Validate only the reached boundary.** Use the [validation reference](references/validation.md). A short real scheduler CPU check can verify its cycle; pipeline interruption/reuse and actual serving behavior require their matching fixtures and environment. Preserve the original assertions and record missing evidence.

## Output and stop

Return an object-identity/ownership map, call → schedule reset → step progression → interrupt/output/cleanup trace, the caller's admission contract, one proposed next check and passed/failed/not-run evidence. Stop when the ownership question is resolved or a required fixture/backend is absent. Do not infer that every Diffusers service races or serializes from this source readset.
