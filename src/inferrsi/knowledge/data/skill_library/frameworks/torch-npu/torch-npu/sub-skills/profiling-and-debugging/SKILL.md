---
name: profiling-and-debugging
description: "Capture bounded TorchNPU CPU/NPU traces, memory timelines and synchronization-aware diagnostics; distinguish collection, parsing, completion and performance claims."
---

# Profile and debug TorchNPU

Use for kernel/communication/host gaps, memory traces, async exceptions or stream
sanitizer diagnosis. Read [the profiling procedure](references/profiling.md)
and [failure recovery](references/troubleshooting.md).

Inputs: tiny correct reproduction, stack/backend, selected activities, bounded
schedule, trace output location and question to discriminate. Output: trace
collection/analysis status, relevant events/counters, completion boundary and
one source-grounded hypothesis.

1. Reproduce correctness without profiling.
2. Select CPU/NPU activities and minimal trace options.
3. Advance the schedule with `prof.step()` and verify actual artifacts.
4. For memory timelines include the required shape/memory/stack-or-module options.
5. Use [the bundled profile case](../../scripts/runtime_smoke.py) with
   `--case profile --run --output <NEW_TRACE_DIRECTORY>` on a qualified host.

For async error location use a fresh bounded run with the documented launch
blocking setting, then restore the normal timing mode. Profiling overhead and
microbenchmarks do not establish L4 service performance. Device trace collection
remains `BLOCKED_REQUIRED_BACKEND` without NPU/CANN profiling support.
