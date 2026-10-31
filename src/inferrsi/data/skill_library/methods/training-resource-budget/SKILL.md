---
name: training-resource-budget
description: 'Choose training offload and resource-budget changes using pinned DeepSpeed configuration, attributed expert diagnosis and a historical MindSpeed case. Balance accelerator capacity, CPU work, pinned RAM and local storage; keep host/device transfer exposure distinct from collective network bottlenecks.

  '
---

# Training Cross-Resource Budget Decisions

Status: candidate. No hardware validation, measured gain or current NPU
compatibility claim. [Source boundaries](references/sources.md) identify exactly
what was inspected; no checkpoint implementations are mined by this skill.

## Start with ownership and one bottleneck

Attribute state to parameters, optimizer state, gradients or activations;
record its current memory tier, lifetime and next consumer. Distinguish an
allocation-capacity failure from a throughput bottleneck. A change that enables
a model to fit can still slow each training step.

Keep a per-host budget for input buffers, checkpoint snapshots, offloaded state,
OS cache and CPU workers. Count the actual ranks sharing that host. Record the
host/device link separately from inter-device/inter-node collective traffic.
A tensor copied to CPU does not establish an InfiniBand/RoCE bottleneck.

SearchSpace: Accelerator and RAM / Host → Diagnose, Configure, Optimize;
SSD / Storage → Configure, Optimize (DeepSpeed NVMe state); OS / System →
Diagnose, Configure (CPU share/locality/garbage-collection attribution).
Network → Observe, Diagnose, Verify only through the scoped expert collective
measurement principles, not through CPU/NVMe offload itself.

## CR1 — DeepSpeed offload decision surfaces

| Surface | Inspected contract | Decision consequence |
|---|---|---|
| Parameter offload `device=cpu/nvme` | ZeRO stage 3 only | Establish parameter state residency before spending buffers or CPU RAM |
| Optimizer offload `device=cpu/nvme` | Stages 1/2/3; computation remains on CPU for either target | NVMe placement does not remove CPU optimizer demand |
| Parameter `max_in_cpu` | Parameter **elements** retained in CPU when NVMe is enabled | Convert using actual dtype/storage; this is not a byte or total-host-memory cap |
| Parameter `buffer_count`, `buffer_size` | NVMe buffer-pool count and size | The approved config/doc excerpt does not explicitly define `buffer_size` units; verify its consumer before calculating bytes or tuning it |
| Optimizer `buffer_count` | At least the number of optimizer states per parameter; source illustrates Adam's four | Do not transplant the parameter-pool count or assume all optimizers have identical states |
| `pin_memory` | Defaults True at this pin; page-locked CPU memory supports async transfers/overlap | Budget resident memory and existing memlock allowance; no privileged limit change authorized |
| `pipeline_read` / `pipeline_write` | Next-tile read / previous-tile write overlap with current optimizer tile compute | Applicable to tiled ZeRO-Infinity execution; configuration presence does not prove actual overlap |
| `ratio` | Fraction in [0,1] for CPU Adam, stage 3 only | Not a general placement ratio for parameters or activations |
| `super_offload`, `cpuadam_cores_perc` | Superchip CPU offload; core fraction valid with stage 3 plus `super_offload=True` | Not a universal CPU throttle or generic recommendation on every host |
| `fast_init` | NVMe optimizer initialization | Startup cost and steady-state step time have different denominators |

A justified overlap proposal needs evidence that compute can hide the relevant
read/write segment, sufficient CPU/pinned-RAM/storage capacity and unchanged
state semantics. Measure the executing path before claiming a knob ran. The
config schema and live documentation are not dispatch/performance evidence.

## CR6 — Attributed expert diagnosis

Read [the scoped Stas Bekman note](references/stas-decision-notes.md) for
MFU/HFU denominator checks, transient-versus-sustained compute, collective
measurement semantics, NUMA locality and garbage-collection stragglers. This
note explicitly retains CC BY-SA 4.0 attribution and share-alike conditions;
no upstream runbook commands or automatic-update instructions are adopted.

Use these principles to form a hypothesis, not to import a platform tuning
constant. Garbage-collection or affinity changes require separate task
approval and memory/correctness evidence; this extraction changes neither.

## CR5 — Historical NPU case

[MindSpeed adaptive memory](references/mindspeed-historical.md) illustrates
spending spare NPU memory versus CPU swapping/recomputation. Preserve the
`core_r0.8.0` exclusions and distinguish its validation assertions from the
separate feature-selection guard. The [pinned source readset](references/mindspeed-source-readset.md)
recovers the historical full revision and license, allocator-to-swap callback
and 910A/910B affinity branch. Check compatible allocator symbols, tracked
swappable storage, host capacity and actual device/NUMA/CPU mapping before
separately authorized reuse; `npu-smi` and `lspci` presence alone is insufficient.
One reported comparison changes layer count; its headline gain is not reused.
Current-stack compatibility, whole-model correctness and measured benefit remain
unverified. These historical source observations do not establish current Ascend
support.

## Paper-derived training decisions

[ZeRO-Offload ownership and semantics](references/papers-20261015/knowledge/offload-delta.md)
extends the configuration evidence above with CPU optimizer state/compute
colocation, shard ownership and tiled update/return costs. Compare the whole
step's critical path, not host capacity alone. Delayed parameter updates change
training semantics and require explicit approval and quality evidence; ordinary
overlap does not imply permission for staleness.

Use [activation residency](../plan-activation-residency/SKILL.md) for live-range,
address-packing and rematerialization choices;
[parallel training plans](../choose-parallel-training-plan/SKILL.md) for stage,
mesh and sharding choices; and
[split backward](../assess-split-backward-schedule/SKILL.md) for input-gradient
versus weight-gradient ordering and optimizer post-validation. These are distinct
contracts: activation checkpoints are not restart snapshots, Alpa's conditional
plans are not unrestricted global optima, and Zero Bubble's rollback preserves
semantics rather than authorizing ZeRO-Offload's stale updates.

The [mechanism comparison](references/papers-20261015/notes/training-memory-scheduling.md),
[readset](references/papers-20261015/references/source-readset.md) and
[hypothetical cases](references/papers-20261015/cases/paper-grounded-cases.md)
retain resource costs, counter-signals and unresolved table discrepancies.
Paper versions are separate from the DeepSpeed implementation pin. No current
runtime, NPU support or measured application outcome follows from these notes.

## Candidate decision record

For each proposal, retain:

1. The observed limiting interval and owning state/resource.
2. The exact source version and enabled execution mode.
3. Capacity released and resources consumed, with units and uncertainty.
4. Overlap readiness/mutation boundaries and expected contention with input,
   checkpoint and network activity.
5. Fixed-workload training step/throughput and correctness evidence required
   for later validation; initialization and auxiliary metrics separately.

No broad source expansion, newest-wheel installation, scheduler-priority
changes, benchmarks or failure injection follow from this skill. Source
support and extracted coverage remain separate from measured improvement.
