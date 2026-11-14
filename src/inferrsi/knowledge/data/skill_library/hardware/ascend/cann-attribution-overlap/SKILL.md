---
name: cann-attribution-overlap
description: 'Attribute NPU trace kernels to model source and plan bounded multistream overlap: select a representative step, map kernels to source owners via code_ref, build the module/operator dependency DAG (data, state, event, collective-order edges), classify serial/candidate/pending groups, choose minimal-first overlap with an explicit execution-mode synchronization contract, and accept only through correctness-first checks. Keeps the !302 import lineage distinct from later revisions, carries known formula/threshold conflicts as unresolved, and qualifies memory evidence by domain (device HBM/UB counters are not host RAM). Planning procedure only — no formula automation for disputed definitions.

  '
---

# CANN Attribution and Overlap Planning

Status: candidate. Source-grounded from cann/oam-tools skills
(`cann-perf-breakdown`, `cann-multistream-optimize`, `cann-npu-perfanalysis`)
via the supplied Dot CANN pack (read-only inspection, 2026-10-15).
Facts **F** = directly inspected source behavior/instruction; procedures
**P** = proposed mapping/procedure. No empirical validation.

**Lineage (preserve; do not merge):**
- !302 import revision **I = `8440935f`** (PR merged 2026-06-12, PR head
  `a86ab510`). Declared lineage: `jinyingqi/perf-breakdown-skill` →
  `cann-perf-breakdown`; `jinyingqi/multi-stream-skill` →
  `cann-multistream-optimize`; `jinyingqi/npu-perfanalysis` →
  `cann-npu-perfanalysis`. These are copies in one lineage, **not
  independent corroboration**; original-repo SHAs and byte equivalence are
  unverified.
- Later master **CURRENT = `f3cf4115`**: breakdown is now three-stage; its
  `1-perf-breakdown/SKILL_en.md` last changed at `5f42532`. Later material
  is labeled **[V2]** and never attributed to !302.
- Imported scripts carry Apache-2.0 headers; preserve copyright/license
  notices on reuse.

## SearchSpace mapping

Accelerator + Communication rows → Observe / Diagnose / Configure /
Optimize / Verify cells (attribution and overlap planning). Partial OS
bridge: host-event coverage of device bubbles (uncertainty-aware only).

Related skills: `ascend-performance-analysis` (5-layer step-trace
analysis), `ascend-operator-profiling` (single-operator measurement),
`ascend-distributed-parallel` (strategy-level comm), `ascend-operator-tuning`
(the campaign that runs after a target is chosen).

---

## The chained procedure

### Stage 1 — Representative-step selection [B]

**F**: the breakdown skill selects a representative step; CSV rows carry
kernel IDs; source modules/functions own kernels.

**P**: retain the selection reason, shapes, streams, and `code_ref` for
each kernel owner. Kernel names alone do not establish semantics. The
compact mapping view omits timing; the full `kernel_details.csv` retains
it — choose deliberately per question.

### Stage 2 — Attribution-aware bottleneck diagnosis [N, F]

**F**: rankings exist for duration and for duration+wait; wait-anchor
context distinguishes compute / memory / latency hypotheses.

**P**: join hotspots to source owners; inspect adjacent kernels and wait
windows before selecting an optimization target. Keep host gaps, waiting,
and true compute cost distinct — a wait-dominated hotspot is not a compute
problem. Thresholds are hypotheses, not verdicts.

### Stage 3 — Dependency DAG [D]

**F**: the decomposition builds a whole-network module DAG, then an
operator DAG, with four edge classes: data, state, event, and
collective_order.

**P**: classify groups as serial / candidate / pending. Two rules:
- **Shared input alone creates no dependency** — a common input read by
  two operators does not serialize them.
- **Logical independence does not prove resource compatibility** —
  independent ops may still contend for the same cores, streams, or
  bandwidth; classify resource/runtime uncertainties separately from DAG
  edges.

### Stage 4 — Execution-mode synchronization contract [M, A]

**F**: two API families exist — eager streams/events versus TorchAir
scope/tagged events/tensor waits.

**P**: choose one API family per campaign; record stream/event joins, the
enable switch, and the fallback path. Graph-mode and eager semantics
differ; source API references span runtime versions — pin the installed
CANN/torch_npu/TorchAir versions before choosing.

### Stage 5 — Bounded overlap choices [M, A]

**F**: minimal overlap first; core/stream limits come into play only after
contention evidence.

**P**: establish one correct overlap point, verify, then compare bounded
resource allocations stepwise. More overlap can increase host work,
contention, or tail latency — overlap degree is a trade-off knob.

### Stage 6 — Evidence-gated acceptance [M, C, P]

**F**: the sources define correctness/synchronization/performance/profile
checks and coverage/interval-union metrics.

**P**: acceptance requires all of — fallback works; no KV/state reordering;
actual overlap observed (not just configured); latency gain; no regression
outside the target module. Overlap ratio alone can hide slower compute or
new tails. Mechanical coverage does not prove correct semantic ownership.

## Communication-specific rules [N, F, M, D]

- Exposed communication, transport/rank metrics, wait pollution, and device
  imbalance come from `communication.json` plus step/rank inventory.
- Correlate collective and wait intervals; retain transport units and rank
  coverage. Zero/missing bandwidth is **unavailable evidence**; single-rank
  data cannot establish cross-rank bandwidth or balance.
- Overlap compute with communication only when both sides are
  independently ready and ordering/joins are preserved; no comm
  recommendation without comm evidence.

## Metric separation rules [C, P]

Keep four quantities separate; never substitute one for another:
1. Wall time.
2. Union of busy intervals.
3. Summed kernel durations.
4. Summed duration+wait.

The imported metric implementation multiplies representative-node metrics
for repeated instances — record that product as an **estimate**, not an
observed whole-model critical path.

## Memory-domain qualification [N, F]

**F**: MTE and GM↔UB counters and arithmetic intensity describe **device**
memory (HBM/UB), not host RAM.

**P**: label the memory domain and units on every memory claim. The RAM /
Host SearchSpace row is fed by this source only if that axis explicitly
includes device memory — by default it does not. The 50 FLOPs/byte balance
point in the sources is a heuristic fallback; use a verified chip balance
point where available. `npu_prefetch` candidates require spare-bandwidth
evidence; prefetch can worsen contention.

## Unresolved formula/threshold conflicts — carry forward, do not automate

These conflicts are recorded **as-is**; any automation requires actual step
boundaries and formula tests first:

- Free-ratio warning labels differ between `cann-npu-perfanalysis/SKILL.md`
  [N] and its `thresholds.md` [T].
- One worked example calls 20.9% "less than twice" a 10% threshold — the
  comparison direction is inconsistent with a strict reading.
- [N] omits the tail gap from underfeed; the metrics-formulas reference
  [F] includes it.
- [F] anchors `step_start` to the first kernel, forcing `prelaunch_gap`
  to zero by construction.

## Source heuristics requiring applicability checks

Not portable truth — check each against the target before use: diagnostic
cutoffs; the default 910B3 peak values; the zero-bandwidth → single-rank
inference; the fixed causal-attention FLOPs factor; categorical MoE/decode
exceptions. **Profiling-only layer-count guesses must never override
source-derived architecture** [N, F, T, S].

## Later-revision safeguards [V2 — not !302]

Evaluate separately, never retrofitted onto the import: learned-layer vs
runtime-invocation separation; explicit trace scope; unmapped-operator
blocking; source/semantic critique kept distinct from mechanical coverage;
hash-bound critique with evidence-cap-aware gating.

## OS bridge (partial, uncertainty-aware)

**F**: host-event coverage of device bubbles can carry sync / H2D / comm /
launch-lag labels when host trace evidence exists.

**P**: record the timestamp domain and missing-evidence list before naming
a root cause. This source has no scheduler/cgroup/CPU-affinity
instrumentation — free time alone cannot prove a Python/GIL/OS cause (use
`os-process-placement` / `cgroup-resource-controls` for that plane).

## Limitations

- SSD row and OS Configure/Optimize/Verify remain outside this source's
  coverage; host-RAM coverage is not established. NPU HBM/UB evidence,
  runtime stream limits, and offload/reload node names must not silently
  fill those cells.
- Unknown: original jinyingqi commit IDs and import byte equivalence;
  installed CANN/torch_npu/TorchAir versions; local model/config/trace
  completeness; measured speedup (none exists — no local validation was
  performed).
