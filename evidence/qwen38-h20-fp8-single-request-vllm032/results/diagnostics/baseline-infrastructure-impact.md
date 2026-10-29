# Baseline infrastructure readiness attempts

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE. No model, quality or performance result.**

Job1959 failed before startup readiness and before any request. File-backed
ZeroMQ IPC bind on the task shared filesystem returned EOPNOTSUPP. The server
exited1 and the owned process group was empty, with no forced kill. Slurm
FAILED1:0 after68 allocated GPU seconds. It also warned that FlashInfer was
disabled: the environment contained ninja1.13.2, but its bin directory was not
on PATH. Existing nvcc was present; no dependency installation was needed.

CPU-only job1960 completed0 in1 second. Both92-byte artifact and70-byte short
filesystem endpoints failed errno95; the59-byte Linux abstract endpoint passed
PAIR send/receive. This rejects a path-length-only explanation for1959. With
the environment bin on PATH, ninja and existing nvcc were found. No GPU was
allocated for this preflight.

The prospective retry uses the unchanged observer with job-owned abstract IPC,
existing environment/toolkit PATH and explicit cache paths. Its result is
pending in this snapshot. No engine optimizations or acceptance thresholds were
changed. Selected raw observations are retained; private startup trace/command
and device identities stay outside the repository. The exact script is retained
under validator/diagnostics; the CPU operational helper is private because it
binds authorized task-local paths, with selected results below.

Readiness cumulative allocation972/7200 GPU seconds, initial147 seconds separate.
All1959/1960 allocations released. Both environment dependencies are unchanged.
