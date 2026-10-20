---
name: cgroup-resource-controls
description: 'Diagnose and configure cgroup v2 resource controls for serving/training workloads: distinguish quota stalls from sibling contention (cpu.max vs cpu.weight, cpu.stat vs cpu.stat.local), audit requested-versus-effective cpuset with migration-cost budgeting, triage memory pressure with PSI plus event deltas (high/max/low semantics), and gate io.max caps on confirmed block-backed traffic. Includes hierarchy/delegation/permission preflight and a rollback contract. Extra resource allocation is treated as a capacity spend, never as an efficiency improvement. Control-plane procedures only — applying settings requires separate authorization.

  '
---

# Cgroup v2 Resource Controls

Status: candidate. Source-grounded from the Linux cgroup v2 documentation —
kernel.org live page (retrieved 2026-10-15; rolling document, kernel
revision unidentified by the page) and Linux v6.12
`Documentation/admin-guide/cgroup-v2.rst` (reproducible baseline, not a
claim about any deployment kernel) — via the supplied Dot cgroup pack.
Facts marked **F** are direct documentation facts; procedures marked **P**
are proposed and unvalidated. No workload inspection, settings change, or
validation has occurred.

## SearchSpace mapping

OS / System row → Observe + Diagnose + Configure + Optimize + Verify cells;
RAM / Host row (memory controls); SSD / Storage row (io controls,
conditional on confirmed block-backed traffic).

Second-level targets: CPU quota and shares, cpuset placement, memory
limits and protection, device I/O caps, delegation boundaries.

Related skills: `os-process-placement` (affinity/NUMA placement — this
skill adds the cgroup control plane), `host-memory-management` (allocation
mechanics), `storage-io-measurement` (device-level measurement this
control plane acts on).

---

## Prime rule: allocation is not efficiency

**P**: a larger allocation spends shared host capacity. Treat every
resource increase as a capacity trade requiring (a) an observed
quota-associated stall or contention evidence, (b) an application-outcome
measurement, and (c) a sibling-impact check. Pressure counters alone are
not causal proof of the application bottleneck.

## CPU: quota versus contention

**F**: `cpu.max` sets budget/period in microseconds; `cpu.weight`
distributes relative shares. Current `cpu.stat` bandwidth counters exclude
ancestor-caused throttling; `cpu.stat.local` can include it.

**P** diagnosis branch for slow host-side work:
1. Align CPU counters, pressure, and ancestor budgets (read both `cpu.stat`
   and `cpu.stat.local`; the difference is ancestor-caused throttling).
2. Stalls correlated with the group's own quota → draft a **quota review**
   (`cpu.max`).
3. Stalls with quota headroom but competing siblings → draft a **weight
   review** (`cpu.weight`) — shares redistribute, they do not add capacity.
4. Verify with application latency/throughput and sibling impact, not with
   counter movement alone.

## Cpuset: requested versus effective

**F**: effective CPU/node sets respect ancestors and hotplug. Changing
`cpuset.mems` can cause costly, incomplete migration.

**P** placement audit: compare requested (`cpuset.cpus` / `cpuset.mems`)
against effective (`cpuset.cpus.effective` / `cpuset.mems.effective`)
before interpreting any placement result — a difference means an ancestor
or hotplug constraint is silently shaping the placement. Propose placement
changes only with application/topology evidence; budget the migration
overhead of `cpuset.mems` changes; never auto-pin.

## Memory: pressure plus events triage

**F**: `memory.high` triggers reclaim/throttling without invoking OOM;
`memory.max` can invoke OOM; `memory.low` supplies best-effort protection.
`memory.pressure` exposes PSI; `memory.events.local` excludes descendant
events.

**P** triage for host-memory stalls (latency regression):
1. Align `memory.pressure` (PSI), `memory.events` vs `memory.events.local`
   deltas (high / max / OOM), and the footprint mix of the group.
2. Reclaim/throttle symptoms → draft a `memory.high` review.
3. OOM risk → explicit `memory.max` review with OOM-risk assessment
   (raising `max` trades crashes for capacity).
4. Protection needs → `memory.low` is best-effort only; do not rely on it
   as a guarantee.
5. Track application outcomes and sibling pressure; additional headroom
   consumes host capacity.

## IO: caps and their preconditions

**F**: `io.max` limits device BPS/IOPS with delays and permitted bursts.
Weight control needs iocost or BFQ support. Buffered-write accounting
requires filesystem support; shared-inode attribution is problematic.

**P** applicability gate: io controls apply only to **confirmed
block-backed model/checkpoint traffic** (resolve the backing device first —
see `storage-io-measurement` §6). A slow storage phase → align IO rates and
pressure → draft a cap (`io.max`) or a supported-weight review. Caps trade
throughput for containment of the capped group; evaluate phase duration and
peer service together.

## Hierarchy, delegation, permissions

**F**: controllers require parent enablement; non-root domain-controller
parents must be process-free; delegation cannot escape ancestor limits;
writes require appropriate access.

**P** deployment preflight before proposing any change:
- Kernel release/config and fair-class scheduling policy.
- Target PID membership (which cgroup the workload actually runs in).
- Mount/namespace view and the relevant ancestor controller files.
- Identify the **authorized owner** of each file — orchestrators may own
  parts of the hierarchy; record inaccessible ancestors as uncertainty, do
  not infer container authority or attempt permission escalation.
- Prepare a rollback manifest (previous values of every file to be touched)
  and stop conditions before any separately authorized trial.

## Documentation-conflict caution

**F**: in v6.12, the IO overview text conflicts with the iocost section
(the live prose corrects the overview); both versions retain a
memory-pressure-unimplemented sentence despite documenting
`memory.pressure`.

**P**: treat overview statements cautiously; prefer the per-controller
interface sections. The live page's kernel revision is unidentified — pin
expected behavior to the deployment kernel's own documentation/config.

## Verification contract (proposed)

For any separately authorized trial: matched baseline/outcome windows;
application metrics (not just counters); raw counter deltas retained;
configuration provenance recorded (file, old value, new value, time);
rollback and stop conditions specified in advance. No numeric optimum is
claimed by this skill; a green matrix cell here means "candidate procedure
with sourced facts", never an empirical result.

## Limitations

- Scheduler priorities (nice / ionice / SCHED_FIFO / SCHED_RR) are **not**
  covered by this source — cgroup v2 file interfaces only.
- Unknown on any target: kernel version and backports, delegated write
  rights, hidden ancestor limits, orchestrator ownership, scheduler and IO
  backend, filesystem, device topology, NUMA layout, peer budgets, counter
  availability (live-only CPU counter semantics especially).
- The pack's coverage table (RAM/SSD/OS × lifecycle) is proposed mapping,
  not achieved capability.
