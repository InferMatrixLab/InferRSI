---
name: sglang-omni-architecture
description: "Trace SGLang-Omni stage DAGs, schedulers, queues, state ownership and transport; distinguish implemented optimization knobs from extensions."
license: Apache-2.0
metadata:
  disco-role: operating
  repository: sgl-project/sglang-omni
  source-commit: 2cfb3b67becb437b70751defe37e63d3af4eedb0
  language: en
  skill-root: sglang-omni
  parent: sglang-omni
---

# Architecture and search space

Use for source-level explanations, stage bottlenecks, pipeline layout changes, queue stalls and communication defects. Read [runtime contracts](references/runtime.md), then inspect the matching pinned source rather than inferring behavior from a model name.

1. Resolve the concrete `PipelineConfig` and variant. Draw normal edges (`next`/`route_fn`), fan-in (`wait_for`/`wait_for_fn`/`merge_fn`), streaming (`stream_to`/completion targets), and terminal results separately. Stage list order can be construction order rather than execution order.
2. Annotate each logical stage with scheduler, owning process, replica binding, GPU/TP ranks, input/output tensor device, and lifetime owner. A process replica copies all stages in that process; it is not TP.
3. Trace one request through admission, preprocessing, scheduler inbox, model execution, outbox, downstream transfer, terminal merge, and cancellation. Locate the first observable wait before choosing a tuning parameter.
4. Classify the proposed change as an existing knob, model-specific capability, or a code extension. No generic transport selector and no supported `OmniScheduler.event_loop_overlap` toggle exist at this revision.
5. Check a success and failure path: fan-in completes only for active sources; ordered chunks precede EOS; aborted work cannot republish state; sender buffers remain alive until the correct completion mechanism.

If a stall follows a layout change, restore the known process/GPU layout, compare resolved routes and replica bindings, then inspect local-object eligibility, transport selection and cleanup. Do not hide a lifetime bug by dropping queued chunks or removing the overlap guard. Return an ownership map, bottleneck hypothesis, supported search space, and validation evidence. Route measured tuning to [serving](../sglang-omni-serving/SKILL.md) and code changes to [extension](../sglang-omni-extension/SKILL.md).
