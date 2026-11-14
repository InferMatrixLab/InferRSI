---
name: ascend-operator-tuning
description: 'Run a staged, accuracy-gated tuning campaign on a single Ascend NPU operator: set a numeric target up front, block tuning until an on-device accuracy pass is logged, escalate code-level then scheduling then instruction-level tuning with per-stage stall counters and kill-switches, and route each change by the metric contract (core utilization, bubble rate, load balance). Use after ascend-operator-profiling has measured a baseline and the operator is confirmed as the bottleneck.

  '
---

# Ascend Operator-Level Tuning

Status: candidate. Source-grounded from awesome-ascend-skills `pypto-op-perf-tune`
(orchestrator + perf-analyzer + tune-frontend + tune-swimlane + tune-incore) @ 75ec89c,
mirrored from cann/cannbot-skills @ ac5bbd2b (license UNKNOWN — verify before
production use). The campaign discipline is operator-generic; PyPTO-specific knobs
are marked **[PyPTO]**. PyPTO itself is never defined in the source [observed gap];
from usage it is a Python tile-programming frontend for Ascend (AIC/AIV cores,
L0/L1/UB buffers, NZ data format).

## SearchSpace mapping

Accelerator row → Optimize cell.

Second-level targets: operator task granularity, TileShape, scheduling, subgraph
merge, instruction selection.

Companion skills: `ascend-operator-profiling` (measure the operator and derive the
bottleneck verdict), `ascendc-tiling-design` (tiling pattern selection per operator
class), `kernel-writing-guide` (when to rewrite instead of tune).

## Relationship to profiling

`ascend-operator-profiling` answers *is this operator slow and why*. This skill
answers *how to run a bounded campaign that makes it faster without breaking it*.
Do not start here without a measured baseline.

---

## Hard gates

1. **Accuracy before performance.** No tuning step may run without a logged
   on-device accuracy pass ("passed/success" literal output; any timeout counts
   as failure), recorded with time + command + key output.
2. **Accuracy is re-verified after every single change.** One parameter per
   iteration; if accuracy breaks, the change is reverted and the failure recorded.
3. **Accuracy failure is an implementation bug, not a tuning bug.** A tuning
   campaign does not debug correctness. First failure: revert, optionally switch
   NPU card. ~3 failures or a timeout: stop and escalate to the operator author.
4. **All measurements on real hardware.** No theorizing about performance; a
   change is judged only by the measured delta it produces.

---

## Numeric goal and stop conditions

Ask for the target up front — speedup multiple or absolute µs ceiling. If the
requester did not state one, ask; do not guess.

Stop the campaign when any of these holds:

| Condition | Meaning |
|---|---|
| Execution time ≤ target | Goal met |
| Core utilization > 80% **and** bubble rate < 10% | Near hardware ceiling; further tuning is waste |
| Stage stall counter exhausted (5 rounds frontend, 8 rounds deep) | Stage headroom exhausted → escalate stage |
| 12 h wall clock (default) | Budget cap |

When all stages are exhausted and the target is still unmet, the answer is
re-designing the operator (or its caller), not more knob-turning.

---

## Metric contract

Derived from per-core work/wait counters (PyPTO `bubble_analysis.log`; the same
contract can be computed from msprof CSVs):

| Metric | Formula | Notes |
|---|---|---|
| Operator execution time | **max** total work time over all cores | The slowest core is the operator |
| Core utilization | busy / (busy + wait) × 100% | Busy = work − wait |
| Bubble rate | wait-schedule / (busy + wait-schedule) × 100% | Scheduling idle, not dependency wait |
| Load balance | (1 − std(busy)/mean(busy)) × 100% | Over AIC cores; 1−CV |
| Wait-predecessor | per-core blocked-by-predecessor time | Different fix playbook than scheduler idle |

Distinguish the two wait classes: **scheduler idle** (bubble) is fixed by bigger
work items and merge knobs; **predecessor-blocked** is fixed by cutting
dependencies. Rating bands (5★→1★): utilization and balance >90/>80/>60/>50;
bubble <2/<5/<10/<20.

---

## Staged escalation

Fixed order; each stage loads its own playbook. Stated weights (10/60/30) are
the source's expected headroom split, not effort quotas.

| Stage | What it tunes | Entry | Exit |
|---|---|---|---|
| 1. Out-of-box (code-level) | Loop structure, task granularity, TileShape, data ops | Accuracy passed | Target hit or 5 consecutive no-gain rounds |
| 2. Deep (scheduling) | Stitch, graph merge, buffer reuse, scheduling policy | Stage 1 exhausted | Target hit or 8 consecutive no-gain rounds |
| 3. In-core (instruction-level) | Operation selection, redundant-compute tricks, cache policy | Stage 2 exhausted and a specific long task isolated | Target hit or theoretical ceiling |

---

## Stage 1 playbook — code-level (out-of-box)

Claim from source: 80% of performance problems sit in the P0 list. Priority order:

1. **Task granularity** (most important): fewer, bigger work items.
   Canonical error: Matmul with M-axis = 1 wastes the Cube unit — chunk an outer
   axis instead. Worked example (Flash Attention): per-query loop (64 tasks,
   matmul [1,128]) → query blocked by 16 (4 tasks, matmul [16,128]) = 16× fewer
   tasks, 16× more compute per task. Block-size starting points 64/32/16, never
   exceeding that dimension's size.
2. **TileShape [PyPTO]**: Cube BF16/FP16 starting points `[128,128],[64,256],[256,256]`
   or `[128,128],[128,512],[128,128]` — big arithmetic strength within L0 limits,
   leaving DoubleBuffer headroom. Vector: `set_vec_tile_shapes(64,512)`. Principles:
   op-spec constraints; inputs/outputs fit UB; block 16–64 KB; tail axis 32 B
   aligned; **never split the reduction axis** (splitting forces GM round-trips
   and blocks subgraph merge).
3. **loop_unroll [PyPTO]**: `unroll_list` values are **parallel-block sizes, not
   unroll factors** — `[8,4,2,1]` means "prefer 8 blocks in parallel". Innermost
   loop only; max value ≤ loop count; ineffective if the innermost loop runs <8
   times (chunk an outer axis instead). Golden combination: outer static chunking
   + inner unroll.
4. **Loop style is a performance contract [PyPTO]**: static axes must use Python
   `for`, not `pypto.loop` — `pypto.loop` expands each iteration into a separate
   root function and subgraphs across root functions cannot merge.
5. **Data ops [PyPTO]**: big weight matrices in NZ format (higher L1 load
   bandwidth); fuse transpose into matmul (`a_trans`/`b_trans`); `concat` →
   `assemble`; `reshape(inplace=True)` to kill copies; >2-D shapes must be
   axis-merged before the loop (NPU instructions are 2-D).

P1: merge nested loops; remove redundant ops.

## Stage 2 playbook — scheduling (deep)

Man-in-loop: read swimlane data, change one config, re-measure.

| Knob [PyPTO] | Effect | Rule |
|---|---|---|
| `stitch_function_max_num` | Root functions dispatched together | Raise stepwise (1 → 128 → 512) within memory budget; watch swimlane compactness vs scheduling-time growth |
| `enable_multi_data_load`, `enable_split_k` | Cut repeated loads; split K across cores | Matmul TileShape deep options |
| Vector TileShape | Subgraph-merge friendliness | Downstream op prefers the upstream output TileShape; <half vector cores busy → shrink; short subgraphs + large scheduling share → grow |
| `sg_set_scope` | Depth-direction graph merge along dependency chains | Fuse where inter-op transfer is large; **Vector-only chains — Matmul+Vector merge unsupported** |
| `cube_l1_reuse_setting` `{sg_id: n}` / `-1` | Merges subgraphs with redundant L1 loads | Breadth-direction; default on |
| `cube_nbuffer_setting` / `vec_nbuffer_setting` | Isomorphic-subgraph / many-tiny-subgraph (<10 µs) buffering | When L1Reuse can't apply |
| `device_sched_mode: 1` | L2-affinity scheduling | Simple dependencies or L2-hit-rate-bound; trades against load balance |

## Stage 3 playbook — instruction-level (in-core)

Entry condition: swimlane isolates one specific long-running task.

1. **Special-shape matmul via Vector preprocessing**: case (884736,16)×(16,16)
   rebuilt as block-diagonal (64,64) right matrix (concat + zero-pad), reshape,
   larger tile shapes, matmul, reshape back, assemble. Author-reported 500 µs → 40 µs.
2. **Add redundant computation to break redundant dependencies**: replicate a
   shared bias tile per consumer so each merges with its own subgraph, removing
   one-to-many dependencies. Copies do not change numerics.
3. **Tail-axis rule**: avoid small tail axes; enlarge via concat/transpose/reshape
   or a larger TileShape.
4. **L2 cache policy [PyPTO]**: one-time GM reads should bypass L2
   (`tensor.set_cache_policy` — signature elided in source, verify in docs).
5. **Last resort — TileOperation audit**: standalone-benchmark the single
   Operation against a hand-written Ascend C small operator; check for better
   instructions or op combinations.

---

## Metric→action routing

| Symptom | First actions |
|---|---|
| Utilization < 50% | Bigger TileShape / task granularity; L2-affinity scheduling; memory layout |
| Bubble rate > 20% | Bigger task granularity; `stitch_function_max_num`; graph merge; `loop_unroll` |
| Bubble rate > 10% | Scheduling policy; L1 reuse |
| Load balance < 60–80% (AicoreTime spread > 20%) | Even task split; TileShape; `sg_set_scope` reordering |
| Max wait-predecessor > 500 µs | Cut dependencies; `sg_set_scope` merge |
| High control-overhead share, small data | Grow the workload to amortize (normal for small ops, not a defect) |

---

## Iteration discipline

1. Pick **one** point from the routing table; change one parameter.
2. Rebuild only if the change type requires it (framework C++ / core changes →
   rebuild; test/impl `.py` changes → rerun). **[PyPTO]** compile-policy table
   keys rebuild on change type; every device exec wrapped in a 300 s timeout;
   `npu-smi info` before starting.
3. Re-verify accuracy (hard gate).
4. Compare execution time to the previous round.
5. Positive delta → keep. Negative → revert the code, keep the log entry. Never
   change everything then measure.
6. Log every round: before/after µs, gain %, accuracy pass/fail, error excerpts.
7. Status board every 5 rounds: success rate, best win, current stage.
8. Human-escalation budget: 3 retries or 5-minute timeout on any blocked step →
   stop and ask, do not improvise.

---

## Correctness traps

- **Output inplace-reshape**: axis-merge is legal only on **read-only inputs**.
  Inplace-reshaping an *output* tensor then slice-writing silently produces
  all-zero results — the write indices break against the new view. [observed,
  tune-frontend]
- **Accuracy regression during tuning**: revert and record; do not debug inside
  the tuning loop.

---

## Known limitations (from source)

- All numeric recommendations (tile shapes, 16–64 KB blocks, 32 B alignment,
  stitch values) are hardware- and framework-bound; re-validate per SoC.
- Perf-analyzer's rating table lists memory-efficiency and control-overhead
  columns that its script never computes; utilization target is inconsistent
  (>98% in one doc sketch vs >90% in script/template). Trust the script.
- The analyzer parses `bubble_analysis.log` with a strict regex; a format change
  yields 0 cores and fabricates "low utilization" bottlenecks instead of
  erroring. Check the parsed-core count before believing a report.
- Case results (Flash Attention 5.89×, 500→40 µs) are author-reported, not
  independently reproduced.
- Env paths hardcode `aarch64-linux`; model-case references (`glm_moe_fusion.py`,
  `mla_prolog_quant_impl.py`) resolve outside the skill directory and were not
  verified in this snapshot.

## Verification checklist (before claiming a tuning win)

- [ ] Accuracy pass logged for the final configuration (not just intermediate)
- [ ] Baseline and final measured with same warmup policy (see ascend-operator-profiling)
- [ ] Execution time = max-over-cores, same shape/dtype, same card
- [ ] Every kept change has a round log entry; every reverted one too
- [ ] Stop condition documented (target / ceiling / stall / budget)
