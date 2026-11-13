# Reproduce, profile and measure

## Inputs and deliverables

Inputs: precise workload boundary, shapes/layouts/dtypes, state/seed, device,
thread/concurrency policy, warmup/cache state and expected correctness.
Output: the earliest failing stage or a trace/timing record with units,
replicates, environmental identity and explicit limits. Tracing is diagnostic
evidence, not automatically a trustworthy benchmark or service-level result.

## Minimal diagnosis

1. Run the root environment inspector in the intended interpreter outside the
   source tree. Preserve wheel version, build git identity and actual backend
   availability independently of the pinned source. The original collect_env
   utility probes compilers, package lists and hardware; full output can contain
   local identifiers. Review/redact it before sharing; the bundled inspector
   deliberately emits a smaller path-free record.
2. Reproduce one eager operator/step with fixed inputs/state. Check isfinite on
   inputs, intermediates and gradients, then shape/layout/device and loss scale.
   For linear algebra inspect conditioning and compare a higher-precision
   control where meaningful. A finite final value does not rule out unstable
   intermediates. Cross-device bitwise equality is generally not guaranteed.
3. Diagnose asynchronous device errors with a short synchronized reproduction.
   CUDA_LAUNCH_BLOCKING=1 can move error reporting nearer its source but changes
   scheduling and is unsuitable for reporting normal performance. C++ stack
   diagnostics and anomaly detection are similarly diagnostic settings.
4. For compilation, compare eager -> Dynamo eager -> aot_eager -> target backend
   and retain the first disagreement. Enable graph_breaks/recompiles/guards
   logs as needed; avoid discarding compiler errors with broad suppression.
5. For distributed hangs compare rank-local first errors and collective sequence
   before profiling communication or changing timeouts. For loader stalls try
   num_workers=0, then instrument data fetch/collation/transfer separately.

## Profiler workflow

1. Name the desired observation: CPU dispatch, actual device kernel,
   input pipeline, memory, backward or communication overlap. Select activities
   supported by `torch.profiler.supported_activities()` and actual hardware.
   Missing CUPTI/device events is not evidence no GPU work occurred.
2. Warm up the workload independently. Use `profile` with a finite schedule
   (wait/warmup/active/repeat) and call `prof.step()` once per intended step.
   Export or summarize on_trace_ready at the end of the active recording cycle.
3. Add record_function ranges around semantic boundaries. Inspect both inclusive
   and self time, CPU versus device duration, copies, syncs and launch gaps.
   Summing overlapping device kernels or CPU enqueue time is not wall time.
4. Enable record_shapes/profile_memory/with_stack only when answering a matching
   question. Shape/stack instrumentation adds overhead and can retain tensor
   references, changing lifetimes/copies. Exported traces can contain model
   structure, code paths and metadata; share only reviewed artifacts.
5. `with_modules` is deprecated at this snapshot and historically targets
   TorchScript; use the installed supported stack/range tooling for eager
   attribution. Experimental profiler extensions are not stable APIs.
6. Compare traces for equal workload/state/concurrency and consistent recording
   windows. If postprocessing times out or trace is partial, preserve that
   limitation rather than treating missing events as complete evidence.

The bundled [CPU trace fixture](../scripts/profile_step.py) runs a tiny
in-memory operation with a finite schedule; `--trace-file` explicitly selects
a trace output path. It does not trace another script or rerun arbitrary user
code. Its CPU trace does not qualify device profiling support or a model gain.

## Timing workflow

1. State whether the target includes loading, compilation, warmup, allocation,
   transfer, forward/backward, optimizer, or request queueing. Match initial
   states, shape distribution, thread count and precision between controls.
2. For microbenchmarks use `torch.utils.benchmark.Timer`, explicit globals and
   num_threads, with replicated blocked_autorange measurements. It warms up and
   synchronizes supported asynchronous accelerators as needed. Record the
   resulting median/distribution and timing scope, not a lone minimum.
3. For CUDA-only kernel spans use timing events and synchronize the end event
   before reading elapsed time. Include dependencies when timing multi-stream
   work. For end-to-end wall time, synchronize at the chosen workload boundary
   and include relevant host/transfer/queue work. Do not time only enqueue.
4. Report cold compile and steady-state execution separately, with cache state
   and shape changes. Autotuning, data caches and allocator warmup can dominate
   the first iterations. Keep profiler runs separate from final latency runs.
5. Record deterministic and precision settings. torch.manual_seed covers torch
   RNGs, but Python/NumPy generators and worker state need their own control.
   `use_deterministic_algorithms(True)` may reject unsupported operations and
   change speed. cuDNN benchmark selection and deterministic execution are
   distinct controls. Never hide unsupported deterministic kernels.
6. A faster operator or step supports that exact measured workload. InferRSI
   service/SLO claims require the campaign's frozen full-service evidence;
   source inspection or a CPU fixture cannot be promoted to such a result.

## Recovery decision

Keep a small artifact set: identity/config, exact repro, expected/observed
numerics, trace/timing boundary, actual checks and missing backend case. If a
probe changes timing or memory, qualify the observation and retest the original
workload after repair. For backend support gaps, change environment or preserve
BLOCKED_REQUIRED_BACKEND; do not infer zero latency or success from a skip.


Source support at the pinned revision (exact inspected spans and byte digests are in the root [readset](../../../references/source-readset.json)):

- [`torch/profiler/profiler.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/profiler/profiler.py)
- [`torch/utils/benchmark/utils/timer.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/utils/benchmark/utils/timer.py)
- [`torch/utils/collect_env.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/utils/collect_env.py)
- [`docs/source/notes/numerical_accuracy.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/notes/numerical_accuracy.md)
- [`docs/source/notes/randomness.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/notes/randomness.md)
