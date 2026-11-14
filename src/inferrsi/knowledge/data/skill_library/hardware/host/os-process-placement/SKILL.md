---
name: os-process-placement
description: 'Place and configure inference/training processes at the OS level before measuring or optimizing: check then pin CPU affinity to the accelerator-local NUMA node (taskset/numactl), keep affinity constant across measurement rounds, set thread-count environment variables (OMP_NUM_THREADS, OMP_PROC_BIND, CPU_AFFINITY_CONF) per scenario, run a device-busy preflight (npu-smi/nvidia-smi usages, graceful-then-force PID cleanup), and structure environment checks as ERROR vs WARNING with per-failure remediation. Use before any performance measurement on shared multi-socket or multi-tenant hosts. Does not cover cgroups, cpuset, isolcpus, or scheduler priorities — no source evidence for those.

  '
---

# OS-Level Process Placement and Runtime Configuration

Status: candidate. Source-grounded from TensorRT-LLM `perf-host-optimization`
skill @ f33e0e5f (NVIDIA/Apache-2.0) for affinity and placement methodology,
awesome-ascend-skills @ 75ec89c (license UNKNOWN) for NPU-side environment
discipline, device-busy preflight, and the env-check script pattern, and
ggml-org/llama.cpp @ 3e390af (MIT) for NUMA mode semantics and thread /
affinity control splits.

## SearchSpace mapping

OS / System row → Optimize cell (with Configure adjacency).

Second-level targets: process placement, thread pools, environment
configuration, device contention preflight.

Related skills: `host-memory-management` (NUMA **memory** allocation — this
skill covers **process** placement), `ascend-device-health` (card health,
SIGKILL residual state — this skill covers routine pre-launch checks),
`host-overhead-profiling` (the measurements whose variance this skill
controls).

---

## Scope

Covered: CPU affinity pinning, NUMA-local process placement, thread-count
environment discipline, device-busy preflight, structured environment
checks, container-level resource limits.

Cgroup v2 resource controls (cpu.max/weight, cpuset requested/effective,
memory high/low/max with PSI events, io.max) are covered by the companion
skill `cgroup-resource-controls` (kernel-doc-grounded). Still not covered
anywhere: isolcpus, nice/ionice, SCHED_FIFO/RR scheduler priorities.

---

## 1. CPU affinity: check, then pin, then keep constant

CPU core affinity significantly affects host-side overhead, especially on
multi-socket systems (author-reported impact: up to 2× difference in host
overhead on B300-class systems). Cross-socket memory access latency is the
mechanism.

**Check first** (never assume):

```bash
taskset -p <pid>        # current CPU affinity of a running process
numactl --show          # this shell's NUMA policy and node layout
```

**Pin to the accelerator-local NUMA node:**

```bash
numactl --cpunodebind=<node> --membind=<node> <launch command>
```

**Measurement discipline:** when comparing profiling results across runs,
affinity must be identical across rounds. Do not externally modify affinity
mid-campaign; if a round requires a different setting, document the affinity
in that round's report. An affinity change is a contract change — same rule
as a card-group change (see `ascend-optimization-casebook`).

NPU-side: `export CPU_AFFINITY_CONF=1` lets the Ascend driver bind NPU host
threads to CPUs; it appears in migration device-layer checklists as a
pre-launch env var.

### NUMA placement mode semantics (llama.cpp reference)

When a workload exposes NUMA modes, the three standard semantics
(llama.cpp `--numa`, Linux-only):

| Mode | Semantics | Implementation shape |
|---|---|---|
| `distribute` | spread execution evenly over all nodes | round-robin worker threads across nodes (`thread_n % n_nodes`) |
| `isolate` | only spawn threads on the node execution started on | pin to the current node — NUMA-local, lowest cross-node traffic |
| `numactl` | use the CPU map provided by numactl | re-apply the externally captured affinity cpuset |

Operating rules learned from the same source:

- Enabling NUMA handling changes memory behavior, not just thread
  placement: the mmap path drops eager prefetch and switches to
  `MADV_RANDOM` (see `weight-loading-optimization` §6) — tune placement and
  loading mode together.
- Drop the system page cache before the first NUMA-enabled run.
- Kernel auto NUMA balancing (`/proc/sys/kernel/numa_balancing` != 0)
  impairs performance for these workloads — check and warn.
- Manual CPU-mask affinity and NUMA thread placement both set affinity
  masks; combining them is order-sensitive and undocumented — prefer one
  mechanism, or use `numactl` as the single source of the mask.

### Thread and affinity control splits (llama.cpp pattern)

Separate controls for generation vs batch phases (decode vs prompt
processing): distinct thread counts (`-t` / `-tb`) and distinct affinity
masks/ranges per phase, plus strict-placement, thread-priority, and
spin-poll knobs. The transferable rules: (1) generation and batch have
different optimal thread counts — do not share one value; (2) HTTP/frontend
threads are decoupled from inference threads; (3) parallel-slot count (=
server concurrency) drives memory pool sizing, so thread/slot decisions are
also memory-placement decisions.

Use the [llama.cpp owner map](../../../repositories/llama-cpp/audit-llama-runtime-state/SKILL.md#choose-the-scope)
to distinguish this placement scope from loading modes and runtime-state diagnosis,
with each owner's source pin and readset.

## 2. Thread-count environment discipline

Default values observed across sources:

| Variable | Value | Where observed | When |
|---|---|---|---|
| `OMP_NUM_THREADS` | 1 | vllm-ascend Dockerfiles (ship default); mindspeed-mm model deltas; offline/single-card paths | Default unless a serving template says otherwise |
| `OMP_NUM_THREADS` | 8–10 | vllm-ascend-server launch templates + model configs (A2, 8-NPU online serving; deepseek-v3 → 8) | Multi-card online serving |
| `OMP_PROC_BIND` | false | vllm-ascend-server environment table | Online serving |
| `TOKENIZERS_PARALLELISM` | false | mindspeed-mm model deltas | Avoid tokenizer fork noise |
| `CPU_AFFINITY_CONF` | 1 | wan-ascend-adaptation, ascend-migration-analysis | NPU host-thread affinity |

Rules:
- Fix the thread count for every run in a measurement campaign (InferRSI run
  templates pin `OMP_NUM_THREADS=4` into each command) — uncontrolled thread
  counts pollute host-side variance.
- Container defaults (Dockerfile `ENV OMP_NUM_THREADS=1`) are a floor, not a
  tuned value; serving templates override per topology.

## 3. Device-busy preflight (practical contention mitigation)

Before any measurement or launch, check for processes occupying the device:

```bash
npu-smi info -t usages -i <device_id>    # list running processes on NPU
nvidia-smi --query-gpu=...               # CUDA equivalent
```

Escalation ladder (repeatable across awesome-ascend-skills workflows):
1. List occupying PIDs from the usages view.
2. Prefer graceful shutdown of the owning workload.
3. `kill <PID>`; `sleep 3`; re-check.
4. `kill -9 <PID>` only as last resort — SIGKILL leaves residual device
   state that `npu-smi` Health=OK does not reveal (see `ascend-device-health`
   for the 4-step smoke verify).

Do not misread idle-device driver overhead as occupation: a small amount of
HBM used by the driver on an otherwise idle device is normal.

## 4. Structured environment checks

Pattern from `ascendc-env-check` (CANN) and `exec-env-check` (TRT-LLM):

- **Ordered checks, each with an explicit verdict**: ERROR (must fix before
  running, exit 1) vs WARNING (proceed, exit 0). Each failure prints the
  exact remediation command, not just the symptom.
- **Named-env-var correctness**: the official variable is
  `ASCEND_HOME_PATH`, not `ASCEND_HOME`. Never hand-export derived paths
  such as `ASCEND_OPP_PATH`; use the official `set_env.sh`, which owns them.
- **STOP-on-missing-prerequisite** rules for hard dependencies: driver
  directory present, `/dev/davinci*` devices visible, docker daemon alive
  (container path), GPU count matches the plan.
- Check items (CANN example): `ASCEND_HOME_PATH` + `set_env.sh`; CANN version
  parsed from `compiler/version.info` and cross-checked against
  `required_package_runtime_version`; `ASCEND_OPP_PATH` + vendor package
  count; custom-op `op_api/lib` discovery and `LD_LIBRARY_PATH` validation;
  tool availability (msprof/cannsim); log directory; debug print config.

## 5. Container-level resource limits

The only isolation mechanisms with local evidence — Docker flags and
ulimits, not cgroups:

| Mechanism | Example | Use |
|---|---|---|
| CPU/memory caps | `docker run --cpus=8 --memory=32g` | Bound a co-tenant container's interference |
| Shared memory | `--shm-size=16g` | Distributed training / dataloader IPC |
| File descriptors | `ulimit -n 32768` | Linux default (1024) caps cluster size |
| Core dumps | `ulimit -c unlimited` | Crash-debug workflows |

Also apply least-privilege container defaults: non-privileged mode with
specific device mappings for inference/training containers.

---

## Known limitations

- The 2× host-overhead impact of affinity pinning is author-reported
  (TensorRT-LLM), not measured in this workspace.
- `OMP_NUM_THREADS` serving values (8–10) come from per-model templates;
  they are starting points, not tuned constants.
- Cgroup v2 controls are now sourced (see `cgroup-resource-controls`,
  kernel-doc-grounded via the supplied pack); isolcpus and scheduler
  priorities (nice/ionice/SCHED_FIFO/RR) remain unsourced.
- `CPU_AFFINITY_CONF` behavior (which threads it binds, interaction with
  taskset) is documented only as a checklist env var in the sources.
- llama.cpp NUMA/thread trade-offs are qualitatively documented with no
  numeric benchmarks; NUMA handling is Linux-only and CPU-centric — the
  semantics transfer, the flags are not Ascend APIs.

## Verification checklist (before a measurement campaign)

- [ ] Affinity checked (`taskset -p` / `numactl --show`) and recorded
- [ ] Process pinned to accelerator-local NUMA node (multi-socket hosts)
- [ ] Thread env vars fixed and identical across all rounds
- [ ] Device-busy preflight run; occupying PIDs resolved
- [ ] Env check verdict: no ERROR outstanding; WARNINGs logged
- [ ] Container limits / ulimits set if co-tenants share the host
