# Measuring a pair on MUSA

Applies to both lanes. These rules exist because the MUSA stack has three
independent sources of drift: device remapping, the compat layer, and the pinned
Omni image.

## Before the first trial

- One repository revision, one installed stack, one model checkpoint, one
  workload; write them down.
- Print the physical device set through `pymtml` (UUIDs) and confirm both arms
  will use the same set; see [device-identity.md](device-identity.md).
- Decide the metric and direction **before** running: engine E2E latency,
  requests/s, TTFT, RTF, frames/s — one of them, not whichever improves.
- Freeze the quality gate: a command that exits non-zero on a bad output, or an
  explicit numeric comparison against a stored reference.

## Running

- Alternate arms (AB/BA), not AA then BB. Sequential blocks absorb thermal and
  neighbour drift into the comparison.
- Discard the first trial per arm; state how many warmups you discarded.
- Restart the service between arms when the change touches compilation, graph
  capture, allocator settings or the model loader. Otherwise the second arm
  inherits the first arm's caches.
- Keep the same process count, port, batch/concurrency and request mix. A
  concurrency change is a different experiment, not a second repetition.
- If a trial fails or times out, keep the failure and stop attributing the rest:
  a partially failed pair is INCONCLUSIVE, not a smaller sample.

## Reporting

- Report median and range per arm plus the raw trials; a single mean hides the
  bimodality that a wrong device or a recompilation produces.
- Report the physical UUID set, the plugin/compat/toolkit versions and the image
  digest beside the numbers.
- Keep profiled and unprofiled numbers separate; a profiled wall time is not an
  engine E2E measurement.
- If the quality gate did not run, say so. Silence is not a pass.

## Minimum evidence for a claim

| Claim | Required |
| --- | --- |
| "X is faster on MUSA by N%" | AB/BA pair, same UUID set, same pins, range reported |
| "This kernel/graph got faster" | profile of both arms naming the kernel or step |
| "Output is unchanged" | a byte/numeric comparison against the same-seed baseline |
| "This CUDA optimization transfers" | all three above, on MUSA, at the pinned revisions |
