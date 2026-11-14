# Profiling and diagnostic workflow

## Select a question and bounded trace

State the completion boundary and account for profiling overhead separately.
Choose whether the uncertainty is host submission, NPU execution, transfer,
collective readiness, memory retention or an error boundary. Keep inputs and
correctness assertions fixed. Use an explicitly named output directory and
avoid capturing private filenames/stacks or real service endpoints for sharing.

```python
with torch_npu.profiler.profile(
    activities=[torch_npu.profiler.ProfilerActivity.CPU,
                torch_npu.profiler.ProfilerActivity.NPU],
    schedule=torch_npu.profiler.schedule(wait=0, warmup=1, active=2, repeat=1),
    on_trace_ready=torch_npu.profiler.tensorboard_trace_handler("<TRACE_DIRECTORY>"),
    record_shapes=True, profile_memory=True, with_stack=True,
) as prof:
    for _ in range(3):
        result = workload()
        prof.step()
torch.npu.synchronize()
```

Replace the placeholder output path and workload. The bundled profile helper
uses a tiny matrix multiply, refuses an existing output directory and checks
that output files were produced. A nonempty directory proves artifact creation,
not complete parsing, usable hardware counters or a measured speedup.

## Collection versus analysis

The Python profile controls a schedule of NONE, WARMUP, RECORD and
RECORD_AND_SAVE. `step()` advances the action controller and markers; calling
it after stop warns and has no effect. Invalid schedule parameters may be
reset with warnings, so record effective wait/warmup/active/repeat and execute
enough iterations. A trace with no active interval cannot answer a kernel
timing question (F20).

`tensorboard_trace_handler` supports synchronous/asynchronous parsing and
optional archive output. In async gzip mode it waits for all analysis futures
and retains original data if parsing failed. Collection, parse, archive and
viewer availability are separate statuses. The C++ profiler manager selects
trace levels/metrics and delegates to CANN profiling create/start/warmup APIs;
unsupported features may warn or default (F21). No Python callback can prove
those external device APIs succeeded without actual output.

Memory timeline export checks `record_shapes=True`, `profile_memory=True`, and
either `with_stack=True` or `with_modules=True`. Missing options can produce a
warning and early return rather than a useful timeline. Use device allocator
versus host-pinned statistics with their respective ownership definitions;
correlate FREE_REQUESTED and reusable/free events instead of equating a Python
`del` with released device memory.

## Error and race diagnosis

`ASCEND_LAUNCH_BLOCKING=1` forces synchronous operator execution to localize
asynchronous exceptions and disables the task queue setting's effect. It changes
performance, overlap and memory behavior; use it for one reduced diagnostic
run and restore the ordinary mode before timing. Preserve the first error and
the exact setting rather than timing the diagnostic run as an optimization.

`TORCH_NPU_SANITIZER=1` enables stream/record-stream checks. The inspected
sanitizer chooses a separate kernel-check path when its debug-kernel environment
is configured and registers trace callbacks for stream/event/memory lifecycles.
These modes require their corresponding runtime/debug support and may create
debug output. A stream race finding points back to the independent ordering
and lifetime obligations in [memory](../../memory-streams-and-events/SKILL.md).

Silent-fault detection/checksum, recovery/UCE controls and stress tooling are
named in [support workflows](../../../references/support-workflows.md). Preserve
the exact error; device reset/restart and stress are not generic smoke steps.
Do not disable fault detection merely to obtain a clean trace.

## Interpretation deliverable

Return the measurement boundary, warmup, activities/options, collection and
parsing observations, a relevant event timeline, competing explanations and a
next bounded test. Distinguish host enqueue time from completed NPU execution
and collective work from host-future state. Avoid assigning a bottleneck from
a single aggregate percentage without input/stream/overlap context.
