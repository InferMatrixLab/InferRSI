# Qualifying Omni optimization experiments

Use this protocol when a multimodal pipeline has feedback, stochastic audio
sampling, internal graphs, or stateful streaming. Freeze selected checks and
quality tolerances in the acceptance issue and `plan/` before searching. This
adds no default hardware job or model-specific threshold.

## Reference and preflight

- Map per-step feedback before splitting stages: a depth head whose output feeds
  the next temporal step may need to stay in the same AR stage. Module names do
  not establish process boundaries.
- Pin reference code/checkpoint, dependency versions, dtype, attention backend,
  buffer construction device, and cast/move order. Nonpersistent rotary buffers
  can differ despite identical weights. Match per-request RNG device, random
  operation order/shapes and reveal schedule, not just a seed. Locate the first
  divergent token/frame before relaxing tolerances. Isolate reference packages
  when serving requires a different supported dependency range.
- Compare full decode with reference full decode, and streaming with reference
  streaming under the same codec chunk schedule. Measure the reference's own
  full/stream difference separately; it cannot excuse additional integration
  error. Keep transport chunk coalescing from silently changing decoder shapes.
- Inventory outer and internal graph switches, effective backend, capture,
  replay and fallback. An outer eager flag may leave component graphs enabled.
- Preflight the benchmark consumer with metadata-only, empty-final and coalesced
  payloads. Count first audio only on nonempty samples while preserving completion
  events. Distinguish text-end, audio-end and request-end; verify flush and abort
  cleanup. Preserve processor signatures when adding diagnostic wrappers.
- Validate mixed prompts, seeds and lengths concurrently, cancellation followed
  by a new request, and the campaign's accuracy dataset. Repeating one prompt
  or matching a few fixtures does not replace these checks.

## Executable trial qualification

Select adapter-produced boolean fields with repeatable CLI options, for example:

```text
--require-trial-check evidence.requests_complete
--require-trial-check evidence.workers_closed
--require-trial-check evidence.graph_controls_verified
```

Use the same flags for `inferrsi plan` and `inferrsi run`. They are frozen as
`required_trial_checks` in `run.lock.json`. Each baseline and candidate benchmark
command writes its normal metric plus the selected fields to `{result}` (or
`INFERRSI_RESULT_PATH`), for example:

```json
{
  "metrics": {"latency_ms": 100},
  "evidence": {
    "requests_complete": true,
    "workers_closed": true,
    "graph_controls_verified": true
  }
}
```

These are illustrative adapter-defined keys, not built-in hardware probes. Derive
fields from actual request counts, worker exit receipts, and effective graph
controls; keep the underlying receipts in the trial's output directory. Emit
completion only after checking worker exits. Process exit zero, lack of an error
message, or executor-forced cleanup does not establish normal worker shutdown.
Never hardcode `true` to obtain a verdict.

The harness snapshots only selected boolean fields into each `execution.json`.
Literal `true` is required on every measured trial, on both arms. Missing,
unreadable, non-boolean or false values make the comparison `INCONCLUSIVE` and
leave `improvement_pct` unset; raw metrics remain available for diagnosis.
Qualification describes completeness and comparability, not an accuracy score:
quality rejection still belongs to the explicit validation command and its frozen
gates. A completed quality rejection remains `FAIL` when evidence is otherwise
complete. No selected checks preserves the existing command contract; it does
not imply lifecycle or graph qualification. Adapter attestations do not replace
independent validation, source integrity, L3 quality or L4 service evidence.

## Comparable experiments and repair

Use the site's reservation mechanism on shared devices (such as `npu run` where
provided). Freeze device allocation, workload and software, including CANN,
torch-npu and vllm-ascend for Ascend. Record contention and graph/backend settings;
CUDA tooling and MPS are platform-specific. Use portable device labels in shared
artifacts and keep private machine addresses out of logs.

Retain the common AB/BA loop. Report independent process repetitions separately
from requests within each process. Warm up before steady-state measurements;
report startup/capture costs separately when relevant. A new model unsupported
on upstream main needs a clearly labelled integration-with-optimizations-off
control, not a fabricated main baseline.

Retain failed and slow attempts. If a consumer or harness bug is repaired, start
a fresh complete comparison with new frozen commands/source/validator identities;
do not splice successful samples across attempts or rewrite old evidence. A
receipt failure does not automatically retry commands or reserve more hardware.

Skipping multimodal memory profiling can help diagnosis but cannot qualify
deployment capacity. Exercise normal profiling at declared modality limits and
headroom at target concurrency. Distinguish sampled device memory from allocator
peaks, component timing from service timing, and request success from clean exit.
