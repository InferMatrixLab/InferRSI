---
name: storage-io-measurement
description: 'Measure storage I/O for LLM/diffusion serving without conflating device metrics with application outcomes: match the fio workload to the observed loader signature, validate requested-versus-achieved I/O depth, keep a cache-state ledger (warm/cold/unknown with method), classify startup vs steady-state runs, read outputs with unit and latency-provenance awareness, attribute traffic per device (iostat) and per process (pidstat), and gate any "storage bottleneck" claim through a saturation-evidence check plus a separate application-outcome layer. Measurement methodology only — running benchmarks or manipulating caches requires separate authorization.

  '
---

# Storage I/O Measurement

Status: candidate. Source-grounded from axboe/fio HOWTO.rst (targeted
sections) + `examples/aio-read.fio` @ acb7a302, and sysstat `man/iostat.in` +
`man/pidstat.1` @ efd0c445, via the supplied Dot storage pack (2026-10-15;
read-only documentation research, no benchmarks run). Facts marked **F** are
direct documentation facts; procedures marked **P** are proposed and
unvalidated on any target.

## SearchSpace mapping

SSD / Storage row → Observe + Diagnose + Verify cells; RAM / Host and
OS / System attribution bridges.

Second-level targets: block-device profiling, per-process I/O attribution,
cache-state accounting, workload matching.

Related skills: `weight-loading-optimization` (§7 phase-timer protocol —
this skill adds the device-level layer beneath it), `kv-tier-management`
(L2 adapter traffic attribution), `os-process-placement` (CPU-side
scheduling pressure vs disk hypotheses).

---

## Prime rule: two evidence layers, never merged

**F**: fio/iostat/pidstat report I/O and system measurements — not model
readiness or token generation.

**P**: approve a performance claim only at the layer actually measured.
A synthetic bandwidth improvement is a *hypothesis* for startup or serving
benefit. Any storage-metric claim must be paired with a separately measured
application outcome (time-to-ready, TTFT, steady tokens/s, request tail
latency) on identical-model runs with fixed prompts, lengths, concurrency,
and cache labels, before it counts as a benefit.

## 1. Workload matching (fio)

**F**: a fio workload description includes access pattern, block sizes,
bytes, engine, depth, files, and workers; direct and buffered I/O differ.

**P**: before any benchmark, record the real workload signature — observe
the actual loader first. A generic 4 KiB random-read score cannot establish
checkpoint-load performance. Application block sizes may differ from merged
device requests. Choose read vs randread, block-size distribution, engine,
and worker count from evidence of the real access pattern; reject benchmarks
whose workload is unspecified or copied from shipped examples.

## 2. Requested versus achieved concurrency

**F**: `numjobs` clones workers; `iodepth` is per job and usually
ineffective above 1 with synchronous engines; Linux buffered libaio can
fail to achieve the requested async depth. The bundled example uses random
128 KiB reads at depths 4/32/8/16 — illustrative, not a model-loader
recommendation.

**P**: test concurrency only if the real workload can exploit it. Validate
the *achieved* depth distribution from fio's own output, not the requested
value. More queued work can increase latency — depth is a trade-off knob,
not a monotonic win.

## 3. Cache-state accounting

**F**: `direct=1` uses nonbuffered I/O (usually O_DIRECT); `buffered` is
its opposite; `invalidate` defaults to true and is conditional on
platform/file support; `pre_read` clears `invalidate`.

**P**: keep a cache-state ledger. Label every run warm / cold / **unknown**,
with the reset or warm-up method recorded. Never derive "cold" from
configuration alone: `direct=1` is not proof of a cold physical device, and
file-cache invalidation does not establish that all cache layers are cold.
In observational read plans, preserve state with `invalidate=0`.

## 4. Startup versus steady-state runs

**F**: `runtime` caps work; `time_based` repeats it; `ramp_time` executes
before recording and adds lead-in time; `size` bounds the region while
`io_size` can differ.

**P**: classify experiments before running: a single-pass description for
loader-like reads, with loops, lead-in, bytes, and working-set size
(relative to RAM) recorded explicitly. Warm-up or repeated reads can erase
the cold-start effect under investigation. Truncated runs need
completion/byte checks before their numbers are used.

## 5. Output schema, units, latency provenance

**F**: fio reports BW/IOPS, submission/completion/total latency (total =
submission + completion), percentiles, achieved depth, and errors. JSON BW
uses 1024 B/s; `json+` supplies latency bins; histogram durations represent
bin midpoints.

**P**: retain the JSON output, job definition, tool versions, bytes,
duration, error status, p50/p95/p99, and achieved depths for every run;
normalize units explicitly (watch the 1024 vs 1000 convention). Latency
provenance: async completion latency extends to when fio reaps the
completion — it is not bare media service time.

## 6. Device attribution (iostat)

**F**: `r/s` and `w/s` count completed requests after merges; `rMB/s` /
`wMB/s` are MiB/s; `await` includes queue plus service time; `aqu-sz` is
the mean queue length; the first report is since boot unless `-y` omits it.

**P**: bounded observation template — `iostat -d -x -m -y -t DEVICE 1
COUNT` — with the actual backing device resolved first (model-file-to-device
mapping). Device totals include other processes' traffic. Do not sum a
partition and its parent device as independent I/O. Synchronize the
observation window with the application phase being studied.

## 7. Saturation-evidence gate

**F**: `%util` near 100 indicates saturation for serial devices but does
not represent the performance limit of parallel RAID or modern SSDs;
`%iowait` is CPU idle time with outstanding disk I/O.

**P**: no universal percent threshold. Before naming a storage bottleneck,
corroborate with throughput, queue/latency trends, the workload signature,
and process activity. `%util` and `%iowait` alone demonstrate neither an
application storage bottleneck nor its cause.

## 8. Process attribution (pidstat)

**F**: `kB_rd/s` measures disk reads caused by the task; major faults
require disk page loads while minor faults do not; RSS is non-swapped
resident memory; `iodelay` uses clock ticks (not milliseconds); child
aggregate stats arrive when children finish and are not necessarily
contemporaneous; `%wait` means waiting to run (not device await); voluntary
context switches occur on unavailable resources, involuntary ones follow
time-slice loss; `-I` divides CPU use by CPU count.

**P**: bounded template — `pidstat -d -r -u -w -H -p PIDLIST 1 COUNT` with
verified worker PIDs (`-t` for threads). Correlate CPU/system time, `%wait`,
faults, I/O, and both context-switch classes **in the same interval**;
record the CPU normalization. Use `%wait` + involuntary switches to
distinguish CPU scheduling pressure from a disk hypothesis — they are not
equivalent to device `await` or `iodelay`, and context switches do not
identify which resource blocked.

## Proposed safe procedure (not executed)

1. Inventory: tool versions, OS/filesystem, model-file-to-device mapping,
   participating PIDs, model/config, phase timestamps. Start with passive,
   bounded iostat/pidstat observation during an already-authorized run.
2. Preserve original logs and units; parse JSON by keys, not field order.
   Compare a quiet baseline against the relevant application phase.
3. Only after explicit separate benchmark authorization: a matched fio
   read-only job using `--readonly`, `allow_file_create=0`, an explicit
   existing regular file, bounded bytes/runtime, and no write/trim options.
   No raw devices, no shipped examples unchanged, no global cache drops, no
   scheduler changes. Read-only I/O can still contend for bandwidth and
   change cache state.
4. Keep cold-start and warm/steady experiments separate; report unknown
   cache state honestly; re-run the real application before accepting any
   claimed improvement.

## Limitations

- Accelerator and Communication phases have no coverage in this readset;
  do not infer GPU-transfer, networking, mmap-loader, or model-cache
  behavior from these tools.
- Target hardware/topology, filesystem, installed tool versions/engines,
  direct-I/O support, accounting permissions, actual loader access
  pattern, worker lifecycle, and cache layers are unknown until inspected
  on the target.
- Unlisted SearchSpace cells are unsupported by this source, not negative
  findings. Nothing here validates any application-level gain.
