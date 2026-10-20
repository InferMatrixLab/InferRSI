# InferRSI Reference Matrix

**Branch:** `opus/meta-skill-bootstrap` | **Integration date:** 2026-10-16 | **Comparison anchor:** `d96ff8d3`

Current skill links resolve to the complete categorized
[skill library](../src/inferrsi/data/skill_library/README.md). Hardware-specific
procedures live under their hardware owner; this relocation does not change
the source-inspection or maturity claims below.

Paper source inspection below is carried from Dot's 2026-10-15 readsets and the
owner's scoped review, not repeated full-paper extraction. The 2026-10-16
integration adds links and reconciles candidate guidance; packaging checks and
publication status are reported separately. No paper result is a local measurement.

One of exactly two primary matrices (decision D01, 2026-10-15). The official
name and path are **Reference Matrix**, `docs/reference-matrix.md`. The user
subsequently authorized this filename change on 2026-10-15, superseding only
D02's temporary filename-retention clause; the two-matrix contract is unchanged.

- **SearchSpace Matrix** (`docs/searchspace-matrix.md`) — resource ×
  optimization-stage coverage.
- **Reference Matrix** (this file) — sources, inspected scope, provenance,
  and extraction: repositories, papers, official documentation, PRs, and
  expert material; where the intelligence comes from and what remains
  unread. Skills, knowledge, and cases link the two (D03). Methodology
  sources live in §2, not in a third matrix.

Status key (per cell): `mined` (source intelligence extracted into a candidate skill/case — **not** experimentally validated) · `located-not-mined` (relevant material identified, not yet extracted) · `unknown` (not investigated at this revision) · `out-of-scope` (reference does not establish that layer within its approved scope).

Reading rules:

- Sparse / skill-doc-only checkouts carry curated methodology, not implementation
  code. **Not present in a sparse checkout does NOT mean absent upstream.**
- A cloned repo is not necessarily a mined repo.
- Negative findings are scoped to the paths and revisions actually inspected
  (see "Negative findings" below).
- Upstream benchmark numbers are author-reported, never local validation.

---

## 1 · Systems sources

| Reference (origin @ revision) | Inspected scope | Accelerator | RAM / Host | SSD / Storage | Communication | OS / System |
|---|---|---|---|---|---|---|
| NVIDIA/TensorRT-LLM @ f33e0e5fd | skill-doc-only (`.claude/skills/`) | mined — evidence taxonomy, kernel writing, casebook, roofline refs → `dense-performance-evidence`, `kernel-writing-guide`, `inference-optimization-casebook`, `performance-ceiling-analysis` | mined — host overhead verdict + line-profiling loop → `host-overhead-profiling`, `host-overhead-optimization` | mined — weight-movement/overlap + KV host-cache patterns → `weight-loading-optimization`; disk-level: negative (see below) | out-of-scope — host/device weight-movement overlap remains in RAM/Storage, not network coverage | mined — CPU affinity rule + env preflight → `os-process-placement` |
| Ascend/MindIE-SD @ 8481d39 | skill-doc-only (`.agents/skills/`) | mined — 5-layer analysis, bottleneck casebook → `ascend-performance-analysis`, `ascend-optimization-casebook` | mined — host-opt async/pattern sections → `weight-loading-optimization` | mined — load-path judgment, fixed-overhead accounting, offload tiers, weights-prep → `weight-loading-optimization` | mined — USP strategy, masking formula, topology rules → `ascend-distributed-parallel` | mined — device health, card-group contracts, measurement discipline → `ascend-device-health` |
| ascend-ai-coding/awesome-ascend-skills @ 75ec89c | full (`skills/`, `external/cannbot/`) | mined — graph mode, operator profiling/tuning, tiling design → `ascend-graph-mode`, `ascend-operator-profiling`, `ascend-operator-tuning`, `ascendc-tiling-design` | located-not-mined — `external/cannbot/model/model-infer-kvcache` identified, not extracted | mined — device-side prefetch + diffusers CPU-offload playbook → `weight-loading-optimization`; disk-level: negative | located-not-mined — hccl-test / torch-npu-comm-test read for contention preflight only | mined — env checks, device-busy preflight, thread/env tables → `os-process-placement` |
| vllm-project/vllm-ascend @ bc8115ed | skill-doc-only (`.agents/`) | mined — FP8/KV-replication/multimodal adaptation → `ascend-model-adaptation` | unknown — runtime host logic not in sparse checkout | mined — FP8 paired-tensor loading pattern → `ascend-model-adaptation` (Configure cell); runtime loader not in checkout | unknown | mined — Dockerfile thread/env ship defaults → `os-process-placement` |
| vllm-project/vllm @ `7f730b4cea9a66520a9200265928ebe016b48a39` (Apache-2.0) | Dot bundle-mediated; `scheduler.py` admission/budgets/preemption/deferred frees and connector `v1/base.py` contracts/consumers; concrete connector, worker, cache-manager internals, config schema and tests unread | mined — independent admission budgets and async-KV readiness → `diagnose-vllm-admission-pressure`; completion/retention/failure ownership → `audit-vllm-kv-lifetimes`; conditional proposals and unrun verification only | out-of-scope — device KV is not host RAM | out-of-scope — external-hit API establishes no physical tier | out-of-scope — connector contract is not transport implementation | out-of-scope — engine scheduling is not OS priority control |
| vllm-project/vllm-ascend @ `8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf` (Apache-2.0; separate runtime pin) | Dot bundle-mediated; `compilation/acl_graph.py`, pinned graph-mode guide and selected `test_acl_graph.py` cases; tests inspected by supplier, not run; caller/ENPU ordering and helpers untraced | mined — effective dispatch, caller-owned stable inputs, branch-specific replay/update order and capture-resource failures → `ascend-aclgraph-capture-replay`; separate from the older skill-doc pin | out-of-scope — host-launch attribution bridge, no host allocator evidence | out-of-scope | out-of-scope — offloader synchronization is not network evidence | out-of-scope |
| Ascend/pytorch (TorchNPU) @ `67511c53cd4c88014f6123de7097677e60e85faa` (upstream attribution notices retained in source notes) | Dot bundle-mediated; device/host allocators and bounded copy/record-stream/config/stats/binding/test paths in linked ledgers; underlying ATen host allocator and broader capture/IPC/driver behavior unread | mined — stream-use lifetime versus ordering, HBM counters/fragmentation and feature-gated controls → `torchnpu-device-memory-lifecycle`; tests unrun | mined — owned/external pinned buffers, host-specific counters, default/expandable paths and unresolved registration-version warning → `torchnpu-pinned-host-memory-lifecycle`; tests unrun | out-of-scope | out-of-scope — H2D/D2H, registration and IPC are not network coverage | out-of-scope — no OS-priority implementation |
| mindspore-ai/akg @ 5aa15f3f | full | located-not-mined — Ascend kernel compiler identified in bounded README/skills/docs discovery; implementation not extracted | unknown | negative — scanned 2026-10-15, no LLM storage material | unknown | negative — OS scan: identifier false-positives only |
| mindie-agent/mindie-agent @ 6a81b41 | full | out-of-scope — agent tooling, not serving performance | out-of-scope | mined (narrow) — logical-vs-physical I/O + cache-flush measurement caveat → `weight-loading-optimization` | out-of-scope | out-of-scope |
| hahnyuan/LLM-Viewer @ 1893e4b | full | mined — roofline model + hardware params → `performance-ceiling-analysis` (L1) | out-of-scope | out-of-scope | out-of-scope | out-of-scope |
| ebugger/Empirical-Roofline-Toolkit @ 0771fa9 | full | mined — empirical roofline method → `performance-ceiling-analysis` (L2) | out-of-scope | out-of-scope | out-of-scope | out-of-scope |
| foundation-model-stack/fastsafetensors @ 219e256 | full (shallow pin, wave 5) | out-of-scope — approved scope was model-loading I/O only | mined (partial) — pinned bounce-buffer staging, reader NUMA binding → `weight-loading-optimization` §7 | mined — loading I/O mechanics (no-mmap design, bounce reader, GDS, readiness overlap, partial reads, static planner) + measurement protocol → `weight-loading-optimization` §7; wave-6 approved `saver.py` semantics → §8 (carried evidence; not re-mined this wave) | located-not-mined — TP sharding as broadcast/scatter with coalesced runs extracted in evidence, not yet distilled | mined (narrow) — reader worker NUMA binding + O_DIRECT per-filesystem policy → `weight-loading-optimization` §7 |
| LMCache/LMCache @ c3b875a | full (shallow pin, wave 5) | out-of-scope — approved scope was CPU/local-storage KV management | mined — L1 DRAM tier, admission dial, watermark eviction, multi-L1 overflow → `kv-tier-management` | mined — L2 local adapters (fs/nixl/raw_block/dax), serde capacity lever, persist/recover → `kv-tier-management` | out-of-scope — remote adapters noted only | mined (narrow) — MP process/thread concurrency model (isolation, client-affinity pools, TTL locks) → `kv-tier-management` |
| ggml-org/llama.cpp @ 3e390af | full (shallow pin, wave 5) | out-of-scope — approved scope was loading modes and host placement | mined — mmap/mlock residency, lazy tensors, host weight placement (`--cpu-moe` family), KV host offload → `weight-loading-optimization` §6 | mined — loading modes (mmap/mlock/dio/lazy), page-cache interactions, fit-probe bypass → `weight-loading-optimization` §6 | out-of-scope | mined — NUMA modes (distribute/isolate/numactl), gen-vs-batch thread/affinity splits, numa_balancing rule → `os-process-placement` |
| axboe/fio @ acb7a302 | pack-mediated (wave 6; HOWTO.rst targeted sections + `examples/aio-read.fio`) | out-of-scope | located-not-mined — cache-state and run-shape material partially feeds the ledger/run-classification rules | mined — workload matching, requested-vs-achieved depth, cache-state ledger, run-shape classification, output schema/units → `storage-io-measurement` | out-of-scope | out-of-scope |
| sysstat/sysstat @ efd0c445 | pack-mediated (wave 6; `man/iostat.in`, `man/pidstat.1`) | out-of-scope | mined (narrow) — per-process I/O/fault attribution caveats → `storage-io-measurement` §8 | mined — per-device attribution, saturation guards (%util/%iowait) → `storage-io-measurement` §6-7 | out-of-scope | mined (narrow) — CPU-side scheduling-pressure vs disk-hypothesis rules (%wait, context switches) → `storage-io-measurement` §8 |
| Linux cgroup v2 docs — kernel.org live 2026-10-15 (revision unidentified) + v6.12 `cgroup-v2.rst` (reproducible baseline) | pack-mediated (wave 6; core/CPU/Memory/IO/Cpuset interface sections) | out-of-scope | mined — memory pressure/events triage, high/low/max semantics → `cgroup-resource-controls` | mined (conditional) — io.max caps gated on confirmed block-backed traffic → `cgroup-resource-controls` | out-of-scope | mined — cpu.max/weight quota-vs-contention (cpu.stat vs .local), requested/effective cpuset, hierarchy/delegation preflight → `cgroup-resource-controls` |
| cann/oam-tools @ `8440935f` (!302 import; later master `f3cf4115` labeled [V2], never merged into !302 claims) | pack-mediated (wave 6; `cann-perf-breakdown`, `cann-multistream-optimize`, `cann-npu-perfanalysis` + selected references/scripts). Lineage: `jinyingqi/*` originals → !302 import — one lineage, not independent corroboration; original SHAs/byte equivalence unverified | mined — representative-step selection, code_ref source ownership, attribution-aware diagnosis, dependency DAG (data/state/event/collective_order), bounded overlap, correctness-first acceptance, metric separation, device-memory domain qualification → `cann-attribution-overlap` | out-of-scope (host RAM not established; device HBM/UB evidence must not fill the RAM row) | out-of-scope | mined — exposed-communication diagnosis, wait pollution, evidence-gated compute/comm overlap → `cann-attribution-overlap` | mined (bridge only) — host-event coverage of device bubbles, uncertainty-aware → `cann-attribution-overlap` |
| **C1 / DCP async-save-only approval** — pytorch/pytorch @ `7d239835e773c91689eb298692097f4a3340491f`; live async recipe retrieved 2026-10-15 | `state_dict_saver.py` async path, `staging.py`, directly called `_state_dict_stager.py`, `_async_thread_executor.py`, `filesystem.py` staging/finalization; BSD-style implementation license | mined — training-visible staging pause/mutation boundary → `dcp-async-save-performance`; no NPU qualification | mined — separate staging/upload futures, cached pinned CPU buffers, reuse only after prior upload, CPU/RAM contention | mined — bounded in-flight saves and upload timing, writer-specific completion/durability distinction; no distributed restore audit | out-of-scope — D2H and same-host IPC are not network coverage | mined (narrow) — background-worker contention and caller-owned stager cleanup; no OS scheduling changes |
| **B1 / NVIDIA DALI** @ `6fe47c48d3b0ca335f5e1afd3c77c750b2c7e041` (Apache-2.0) | `pipeline.py` constructor/API, `executor_statistics`, queue deserialization; Python surface only | mined — CPU/GPU stage overlap and executor-mode gates → `training-input-pipeline` | mined — queue/buffer sizing and per-output real/reserved memory statistics; legacy stats require `exec_dynamic=False` | out-of-scope | out-of-scope — host/device copies and local buffers are not network evidence | out-of-scope |
| **B2 / Mosaic Streaming** @ `d99bf9c7cdf2dd4ed62a4960ed35270b93337a5f` (Apache-2.0) | `dataset.py` configuration, cache admission/eviction, prepare/ready/yield loops | out-of-scope | mined — per-worker sample look-ahead versus memory/cache budget → `training-input-pipeline` | mined — raw+compressed shard admission, cache minimum and LRU/redownload trade-off | mined — remote dataset download look-ahead/cache-churn decisions only; no collective optimization | out-of-scope |
| **B3 / FFCV** @ `3a12966b3afe3a81733a732e633317d747bfaac7` (Apache-2.0; historical 2024 pin) | `loader.py` configuration/manager selection, complete `os_cache.py`; process-cache algorithm not read | out-of-scope | mined — dataset-fits-RAM versus process cache, batches-ahead buffers → `training-input-pipeline` | mined — read-only mmap and documented quasi-random read-locality choice; `.beton` required | out-of-scope | mined — cache ownership and traversal configuration; distributed `QUASI_RANDOM` excluded, current compatibility unverified |
| **C3 / DLRover FlashCheckpoint** @ `e35b1ad90e2928ca6bacf5d22117f713566c5cb0` (Apache-2.0) | `engine.py` readiness, step equality, launcher lifetime and save/memory-recovery entry paths | located-not-mined — HCCL device branch observed; NPU compatibility not validated | mined — shared-memory readiness and consistent positive-step read gate → `checkpoint-recovery-consistency` | located-not-mined — persistent recovery is a failure-domain requirement; storage implementation not mined | mined — saver/loader-group agreement and replica availability conditions; replica transport not audited | mined — worker versus helper/host lifetime; fallback daemon cannot persist after parent exits |
| **C4 / NVIDIA Resiliency Extension** @ `49af0b03f14550d36a60dcfebd573848b5fd8435` (Apache-2.0 source headers; Megatron-Core lineage) | local `base_manager.py` complete-iteration selection/save/finalizer and `local_manager.py` dirty/final file lifecycle | mined (contract only) — CUDA D2H synchronized before async request returns; no NPU qualification | mined — snapshot/replica lifetime constraints → `checkpoint-recovery-consistency` | mined — clean/dirty publication, complete-rank generation selection and incomplete-save rejection; no power-loss proof | mined — all-rank availability/finalization and replica failure domains, not transport throughput | out-of-scope |
| **CR1 / DeepSpeed ZeRO-Infinity** @ `5f266e26d216a705d9c64cac88fb813cefdbac4b` (Apache-2.0) | complete short `offload_config.py`, official ZeRO-3 live offload-field docs; no runtime/checkpoint audit | mined — parameter stage-3 and optimizer stage-1/2/3 boundaries → `training-resource-budget` | mined — CPU optimizer budget, pinned RAM, element-count residency and gated core share | mined — NVMe buffer pools and tiled read/compute/write overlap intent; buffer-size units unresolved in approved excerpt | out-of-scope — CPU/device transfer is not network coverage | mined — CPU resource-budget qualification; no privileged changes |
| **CR5 / Ascend MindSpeed adaptive memory** — `core_r0.8.0`, page history `53193db8` (full pin and license unresolved) | original GitCode historical `docs/features/adaptive-memory.md` body directly read; implementation unavailable | mined (docs-only case) — spare-NPU-memory versus recompute/swap decision → `training-resource-budget` historical case; changed-layer comparison rejected as controlled gain | mined (docs-only) — CPU swap and allocator/affinity prerequisites | out-of-scope | out-of-scope — NPU/CPU copies not network evidence | mined (historical conditions) — incompatible allocator features and CPU-affinity prerequisites; no current compatibility claim |

Wave-8 implementation provenance (Dot bundles integrated 2026-10-15):
[admission](../src/inferrsi/data/skill_library/repositories/vllm/diagnose-vllm-admission-pressure/references/source-notes.md),
[KV lifetimes](../src/inferrsi/data/skill_library/repositories/vllm/audit-vllm-kv-lifetimes/references/source-notes.md),
[ACLGraph](../src/inferrsi/data/skill_library/hardware/ascend/ascend-aclgraph-capture-replay/references/source-notes.md),
[device HBM](../src/inferrsi/data/skill_library/hardware/ascend/torchnpu-device-memory-lifecycle/references/source-notes.md),
[pinned host RAM](../src/inferrsi/data/skill_library/hardware/ascend/torchnpu-pinned-host-memory-lifecycle/references/source-notes.md).
These preserve the supplier's 2026-10-15 code/docs inspection; upstream reads
were not repeated locally. F denotes pinned behavior or an identified contract;
P denotes an unvalidated procedure. The three source pins are independent,
not a tested dependency set. This batch extracts no paper-derived mechanism;
papers linked by discovery material remain unmined, with no coverage credit.

Home-repo note: InferMatrixLab/InferRSI @ 4c8e128 is the scaffold this branch lives
in (evidence/claim discipline, benchmark hygiene, RunSpec) — not an external
mining source. The local sibling clone at `codex/skill-eval-bootstrap`
(82218b4) is a **different fork lineage**; see §2.

### Reviewed systems-paper mechanisms

`mined` below means pack-mediated extraction into the linked candidate artifacts.
Readsets preserve exact sections, equations, tables, source hashes where supplied,
metric denominators and unreported limitations. Versions are paper identities,
not fabricated implementation SHAs or a version-matched runtime stack.

| Original source / version | Inspected scope and local evidence | Mechanism / consumer | Evidence limits |
|---|---|---|---|
| Vidur — [2405.05465v2](https://arxiv.org/abs/2405.05465v2) | [A readset](../src/inferrsi/data/skill_library/methods/performance-ceiling-analysis/references/papers-20261015/READSET.md); §§3–7, A.1–A.2 | mined — operator/queue model calibration and joint-SLO shortlist → [calibrate-serving-simulation](../src/inferrsi/data/skill_library/methods/calibrate-serving-simulation/SKILL.md), ceiling analysis | Empirical prediction, not physical bound; near-capacity CPU overhead and 12.65% maximum error in the specified appendix case; no current runtime calibration |
| Orca — OSDI 2022 proceedings | [Exact readset](../src/inferrsi/data/skill_library/repositories/vllm/diagnose-vllm-admission-pressure/references/papers-20261015/references/orca-readset.md); §§3–6, Algorithm 1 | mined — iteration eligibility, selective batching, FCFS/reservation → [assess-serving-preemption](../src/inferrsi/data/skill_library/methods/assess-serving-preemption/SKILL.md) | Historical engine/harness and normalized-median denominators; not present vLLM behavior or fairness proof |
| FastServe — [2305.05920v3](https://arxiv.org/abs/2305.05920v3) | [Exact readset](../src/inferrsi/data/skill_library/repositories/vllm/diagnose-vllm-admission-pressure/references/papers-20261015/references/fastserve-readset.md) | mined — service priority, promotion and suspended-state host residency → serving-preemption candidate | Aggregate tail improvement is not tenant fairness; same-engine contrast distinct from historical-vLLM comparison |
| Llumnix — [2406.03243v1](https://arxiv.org/abs/2406.03243v1) | [Exact readset](../src/inferrsi/data/skill_library/repositories/vllm/diagnose-vllm-admission-pressure/references/papers-20261015/references/llumnix-readset.md) | mined — replica migration, virtual headroom, pre-copy/downtime and host staging → [evaluate-elastic-serving-placement](../src/inferrsi/data/skill_library/methods/evaluate-elastic-serving-placement/SKILL.md) | Virtual headroom is not physical capacity; normal-class cost and evaluated-artifact fault-tolerance limit retained |
| LoongServe — [2404.09526v2](https://arxiv.org/abs/2404.09526v2) | [Exact readset](../src/inferrsi/data/skill_library/repositories/vllm/diagnose-vllm-admission-pressure/references/papers-20261015/references/loongserve-readset.md) | mined — elastic sequence groups, phase-dependent state placement and ongoing attention communication → elastic-placement candidate | Distributed device KV is not host RAM; group transitions have different migration costs; no current engine/NPU claim |
| ZeRO-Offload — [2101.06840v1](https://arxiv.org/abs/2101.06840v1) | [C readset](../src/inferrsi/data/skill_library/methods/training-resource-budget/references/papers-20261015/references/source-readset.md), ZO1–ZO3 [mechanisms](../src/inferrsi/data/skill_library/methods/training-resource-budget/references/papers-20261015/notes/training-memory-scheduling.md) | mined — CPU optimizer ownership, update/return pipeline and separately gated delayed updates → [training-resource-budget](../src/inferrsi/data/skill_library/methods/training-resource-budget/SKILL.md) | Restricted graph-cut model; Table 1 discrepancy; delayed updates change semantics; not the DeepSpeed config pin |
| Checkmate — [1910.02653v3](https://arxiv.org/abs/1910.02653v3) | [C readset](../src/inferrsi/data/skill_library/methods/training-resource-budget/references/papers-20261015/references/source-readset.md), CM1–CM2 | mined — event-level retain/recompute and dependency versus capacity feasibility → [plan-activation-residency](../src/inferrsi/data/skill_library/methods/plan-activation-residency/SKILL.md) | Static-cost model and rounded-plan limits; activation rematerialization is not recovery checkpointing |
| OLLA — [2210.12924v2](https://arxiv.org/abs/2210.12924v2) | [C readset](../src/inferrsi/data/skill_library/methods/training-resource-budget/references/papers-20261015/references/source-readset.md), OL1–OL2 | mined — lifetime shortening and static address packing → activation-residency candidate | Device address placement is not host/SSD tiering; runtime amortization estimate is not measured E2E gain |
| Alpa — [2201.12023v3](https://arxiv.org/abs/2201.12023v3) | [C readset](../src/inferrsi/data/skill_library/methods/training-resource-budget/references/papers-20261015/references/source-readset.md), AL1–AL2 | mined — stage/mesh/sharding and cross-mesh resharding → [choose-parallel-training-plan](../src/inferrsi/data/skill_library/methods/choose-parallel-training-plan/SKILL.md) | Conditional hierarchical plan, not global optimum; intra-op compute simplification does not describe all stage costs |
| Zero Bubble — [2401.10241v1](https://arxiv.org/abs/2401.10241v1) | [C readset](../src/inferrsi/data/skill_library/methods/training-resource-budget/references/papers-20261015/references/source-readset.md), ZB1–ZB3 | mined — split input/weight gradients, activation caps, V schedules and optimizer rollback → [assess-split-backward-schedule](../src/inferrsi/data/skill_library/methods/assess-split-backward-schedule/SKILL.md) | Calculated bubbles versus measured throughput; activation cap versus total HBM; rollback is distinct from stale updates |
| FlashAttention — [2205.14135v2](https://arxiv.org/abs/2205.14135v2) | [D readset](../src/inferrsi/data/skill_library/hardware/cuda/diagnose-attention-bottlenecks/references/sources.md) and [mechanisms](../src/inferrsi/data/skill_library/hardware/cuda/diagnose-attention-bottlenecks/references/mechanisms.md) | mined — online statistics, tiled IO and backward recomputation → [diagnose-attention-bottlenecks](../src/inferrsi/data/skill_library/hardware/cuda/diagnose-attention-bottlenecks/SKILL.md) | Scoped dense exact-attention/fast-memory assumptions; operation mix can change after IO reduction |
| FlashAttention-2 — [2307.08691v1](https://arxiv.org/abs/2307.08691v1) | Same [D readset](../src/inferrsi/data/skill_library/hardware/cuda/diagnose-attention-bottlenecks/references/sources.md) | mined — non-matmul work, output ownership and independent query tiles → attention diagnosis | Combined interventions are not isolated causal ablations; Accelerator only |
| FlashAttention-3 — [2407.08608v2](https://arxiv.org/abs/2407.08608v2) | Same [D readset](../src/inferrsi/data/skill_library/hardware/cuda/diagnose-attention-bottlenecks/references/sources.md); [author-reported cases](../src/inferrsi/data/skill_library/hardware/cuda/diagnose-attention-bottlenecks/references/papers-20261015/cases/overlap-and-fp8-counter-signals.md) | mined — async dependencies, compiler/register trade-offs and FP8 layout/accuracy → attention diagnosis | Hopper primitives establish no Ascend support; synthetic accuracy is not model-quality validation |

FlashVector's host materialization/assembly and Agentic Kernel Optimization's
regime-specific kernel cases are cross-links to the **same** source identities in
§2 below, not independent corroboration. B/C decision cases are hypothetical;
D experiments are author-reported. No new SSD or OS mechanism is credited from
A–F; Network links require actual inter-node state/collective transfer.

**Missing foundation input:** the approved earlier archive
`omnirsi-paper-intelligence-2026-10-15.zip` (ZeRO-Infinity, FlexGen, Sarathi-Serve,
DistServe, PagedAttention, Mooncake) is referenced by the packs but absent from
the supplied local directory. Its six-paper extraction and standalone candidates
are not imported or counted here. Existing DeepSpeed configuration evidence and
Mooncake transport discovery are not substitutes for those paper readsets.

### Negative findings (scoped to inspected paths and revisions)

- **Disk-level storage I/O mechanics** (mmap/pinned staging buffers,
  shard-parallel loading, fio/iostat/page-cache benchmarking, checkpoint
  save/restore I/O, disk-tier offload): zero material in the 8 first-layer
  repos listed above, as visible in their checkout coverage (TRT-LLM
  `.claude/`, MindIE-SD `.agents/`, vllm-ascend `.agents/` are skill-doc-only
  sparse checkouts). Queries used: safetensors, mmap, memory_map, pinned,
  O_DIRECT, posix_fadvise, readahead, page cache, fio, iostat, nvme, startup
  time, load latency, async save. Recorded 2026-10-15; also embedded in
  `src/inferrsi/data/skill_library/methods/weight-loading-optimization/SKILL.md`.
- **cgroups / cpuset / isolcpus / nice / ionice / SCHED_FIFO**: zero hits in
  the same 8 repos and scope. `os-process-placement` covers placement,
  affinity, thread env, and container flags/ulimits only.
- Wave evidence files (grep logs, per-theme verdicts, mechanism extractions)
  are session-local under the research tmp directory and not committed to
  this branch.
- Wave-5 approved mining (2026-10-15) closed part of the first negative
  finding: loading modes and mmap/mlock placement (llama.cpp), pinned-staging
  parallel-read mechanics and a load-path measurement protocol
  (fastsafetensors), runtime KV-to-disk tiering (LMCache).
- Wave-6 pack-mediated mining (2026-10-15) closed the rest: checkpoint
  save/restore semantics (`weight-loading-optimization` §8) and
  block-device measurement methodology (`storage-io-measurement`). Pack
  mediation: the gate owners supplied read-only research packs (fio,
  sysstat, kernel cgroup-v2 docs, cann/oam-tools); receiving a pack is not
  mining — extraction into the linked skills happened in this workspace.
  Pack facts are documentation-level; no benchmarks were run, no caches
  manipulated, no settings changed.
- Approval is scoped per `reference × inspected subject × SearchSpace gap` —
  repository paths, paper sections, documentation versions and expert-case
  boundaries are recorded rather than treating every reference as a repository.

---

## 2 · Methodology and corpus references

Role key: history learning · corpus · distillation · evolution · search ·
evaluation · reference. Methodology references are **not** scored against the
SSD/OS systems columns.

| Reference (upstream @ revision) | Role | Used for | Consumed by |
|---|---|---|---|
| LearningToCommit/LearningToCommit @ 7e5a1d7 | history learning | temporal-split method (train/test cutoff discipline) | `repository-evolution-analysis` |
| yetone/magpie @ 77800032 | corpus | carried 3,428-commit history and subsystem analysis; not causal proof of speed or automation | `repository-evolution-analysis`; new coordination case pending Dot delivery and owner review |
| VectorSpaceLab/AREX-Skill @ ac3fe1af | distillation | repo→skill distillation model, artifact lifecycle, refresh/provenance policy | `npu-skill-factory` |
| microsoft/SkillOpt @ 343db22 | evolution | bounded-edit skill evolution | `npu-skill-factory`, `skill-evolution-playbook`, `dense-performance-evidence`, `optimization-search-policy` |
| Qwen-Applications/Trace2Skill @ 3d0b52a | evolution | Trace2Skill pool consolidation | `skill-evolution-playbook` |
| JiusiServe/vllm-evolve @ 43cc82c | search | scheduling-algorithm evolution, search policy | `optimization-search-policy`, `dense-performance-evidence`, `inference-benchmark-design` |
| Dong1017/OmniRSI @ `codex/skill-eval-bootstrap` (82218b4) | evaluation | skill_distill / skill_eval harness, no_skill/human/distilled contract, Tier A pilot | `npu-skill-factory` (evaluation contract) |
| InferMatrixLab/InferRSI PR #9 @ 4ad551a9 | reference | `skill_library/` layout + knowledge records | `npu-skill-factory` (bundle layout) |
| RRSI — arXiv 2609.24972v3 | search; mined via reviewed Pack F | bounded harness proposals; calibrated noise/cost/novelty gates; grouped-ablation limits, replacing the earlier generic constraint summary | `optimization-search-policy`; [exact ledger](../src/inferrsi/data/skill_library/methods/optimization-search-policy/references/papers-20261015/references/source-notes.md#f1--rrsi) |
| arXiv 2608.01867 (CRISP) | search | critical-step classification | `optimization-search-policy` |
| **A1 / Agent Skills** @ `69ef37e9424c0a7ea9dd2293b559e43ec8176379` | reference; Dot A-approved minimal consumption | Specification frontmatter/body/progressive disclosure and client guide catalog/activation/resource sections directly verified 2026-10-15; format guidance, not an execution permission grant | `src/inferrsi/skill_catalog.py`, existing CLI/arguments; metadata projection + explicit selection + resource resolution; no installer/router/client configuration |
| **CR6 / Stas Bekman ML Engineering Open Book** @ `ee7517e0f562ff0e7d56c3e88c619d0c0c496ba7` (CC BY-SA 4.0 declared by source skill) | expert methodology | `skills/ml-engineering/SKILL.md` scoped principles, `skills/evaluate-cluster/SKILL.md` first 100 lines, targeted performance README MFU/HFU/NUMA/GC sections; scripts identified only, excluded storage/input/recovery lanes not mined | `training-resource-budget` + explicitly attributed/share-alike `references/stas-decision-notes.md`; Accelerator/RAM/Network/OS diagnosis and proposed verification, no local results |

### Reviewed paper methodology and cases

The following paper versions supplement, rather than replace or certify, the
repository pins above. `mined` means accepted candidate content. Source inspection
is supplier/owner evidence dated 2026-10-15; no methodology efficacy was measured
in InferRSI. These rows do not create hardware coverage merely from experimental
hardware or agent-development activity.

| Original source / version | Inspected scope / source notes | Accepted contribution and consumer | Boundary |
|---|---|---|---|
| Vidur v2 (same identity as §1) | [A readset](../src/inferrsi/data/skill_library/methods/performance-ceiling-analysis/references/papers-20261015/READSET.md) | mined — calibration/queueing uncertainty and constrained shortlist → ceiling/calibration/search | A cross-link, not a second independent source |
| InferenceBench — 2607.20468v1 | [Audit](../src/inferrsi/data/skill_library/methods/performance-ceiling-analysis/references/papers-20261015/references/inferencebench.md), A readset §§1–6, A–G | mined — bounded search, independent timing integrity, incumbent/final-artifact preservation → search policy and benchmark design | Within-vLLM two-hour main comparison differs from per-engine grid; displayed date/ID anomaly unresolved |
| FlashVector — 2609.17391v1 | [Audit](../src/inferrsi/data/skill_library/methods/performance-ceiling-analysis/references/papers-20261015/references/flashvector.md), §§4–5, Algorithm 1, Tables 1–4 | mined — noise-aware cross-layer redirection, host assembly/materialization, full-stack validation → ceiling/host guidance | Component versus service denominators; Model B SLO inconsistency retained; no Network from gRPC alone |
| Agentic Kernel Optimization — 2608.14560v1 | [Audit](../src/inferrsi/data/skill_library/methods/performance-ceiling-analysis/references/papers-20261015/references/agentic-kernel.md), main text and A–C | mined — regime dispatch, exactness/timing integrity and stalled-direction correction → search/ceiling cases | PyTorch versus FlashInfer baselines differ; SM utilization versus throughput is unresolved without matched definitions; date anomaly retained |
| Repo-To-Skill — 2609.02749v1 | [Ledger](../src/inferrsi/data/skill_library/workflows/npu-skill-factory/references/papers-20261015/references/repo-to-skill.md), [E readset](../src/inferrsi/data/skill_library/workflows/npu-skill-factory/references/papers-20261015/references/readset.md) §§2–5, A.1–A.2 | mined — case/knowledge/amendment/new-skill admission and independent verification axes → factory | Task-conditioned benchmark pools are not the entire public library; no AREX execution |
| Learning to Commit — 2603.26664v1 | [Ledger](../src/inferrsi/data/skill_library/workflows/npu-skill-factory/references/papers-20261015/references/learning-to-commit.md), §§1–5 | mined — contrastive historical lesson, scope/contradiction/expiration → repository evolution | Accepted implementation is not a timeless invariant; chronology does not prove every contamination path absent |
| Trace2Skill — 2603.25158v5 | [Ledger](../src/inferrsi/data/skill_library/workflows/npu-skill-factory/references/papers-20261015/references/trace2skill.md), E readset §§2–4, A–I | mined — causal error analysis, successful-behavior preservation, consolidation and interaction checks → evolution playbook | Consensus is not acceptance; no universal trace count; code pin not matched to paper |
| SkillOpt — 2605.23904v2 | [Ledger](../src/inferrsi/data/skill_library/workflows/npu-skill-factory/references/papers-20261015/references/skillopt.md), §§3–4, A–C | mined — bounded edits, versioned rejection context and optimizer-memory separation → factory/evolution/evidence | Protocol and cost-denominator discrepancies retained; no automatic promotion |
| Dream-RSI — 2609.14858v2 | [F2 ledger](../src/inferrsi/data/skill_library/methods/optimization-search-policy/references/papers-20261015/references/source-notes.md#f2--dream-rsi) | mined — prefix-safe replay and supported actions → search-policy interface knowledge | Replay does not generate unseen branches or prove online improvement; no controller implemented |
| AIDE² — 2609.26457v1 | [F3 ledger](../src/inferrsi/data/skill_library/methods/optimization-search-policy/references/papers-20261015/references/source-notes.md#f3--aide²) | mined — inner/private/outer evaluation and solver-versus-improver distinction → evolution/search | Task-solving gains coexist with an inconclusive improver experiment; costs differ by benchmark |
| JitRL — 2601.18510v4 | [F4 ledger](../src/inferrsi/data/skill_library/methods/optimization-search-policy/references/papers-20261015/references/source-notes.md#f4--jitrl) | mined — candidate-scoring/reward access and finite-memory evidence → adaptation-interface knowledge | Logit/scoring access is a prerequisite, not a Markdown capability; conditional theorem and matched counter-results retained |

Applied owner-review decisions: R1–R6. E-U1 maps to repository evolution;
E-U2 to factory admission; E-U3/E-U4 to the evolution playbook; E-U5 to the
evidence-cost note. Pack F's semantic amendment is reconciled with search policy,
not applied blindly or turned into a new framework. The source packs' integration
notes remain historical proposals; the current bodies and these two matrices
record their actual destinations.

A1 preserves Dot A's Vercel/OpenCode observations as supplied context only;
those clients were not installed, configured or independently runtime-tested.
Their version-specific APIs are not advertised as this CLI's behavior. No
third matrix or automatic discovery/update layer was added.

Direct wave-7 source readsets and restrictions:
[inputs B1–B3](../src/inferrsi/data/skill_library/methods/training-input-pipeline/references/sources.md),
[recovery C3–C4](../src/inferrsi/data/skill_library/methods/checkpoint-recovery-consistency/references/sources.md),
[cross-resource CR1/CR5/CR6](../src/inferrsi/data/skill_library/methods/training-resource-budget/references/sources.md).
CR6's adapted note retains named attribution and CC BY-SA 4.0 share-alike;
CR5 remains a historical documentation case with unresolved license/full pin.

DCP source/version reconciliation, exact links and tutorial snapshot hash:
[`dcp-async-save-performance/references/sources.md`](../src/inferrsi/data/skill_library/frameworks/pytorch/dcp-async-save-performance/references/sources.md).
The live tutorial and pinned implementation differ on caller-side state-dict
construction and cleanup details; claims follow the inspected implementation.
Approval is save-performance only, not the broader C1 recovery proposal.

Notes:

- Same-name repos are not the same project: InferMatrixLab/InferRSI (upstream
  scaffold) ≠ Dong1017/OmniRSI (sibling evaluation fork). The two local magpie
  checkouts share HEAD 77800032.
- Wave-5 additions (fastsafetensors, LMCache, llama.cpp) are systems sources
  and appear in §1 only, under their approved scopes.


## RFC 17 reconciliation: inspected main corpus

Local records below were inspected on 2026-10-16 after merging upstream main
`c13027983b853fee3700de6aabde52b72e61885a`. Their source inspections remain carried
at the dates/pins in each record; original repositories/papers were not reread.
This adds navigation to already imported mechanisms, not new candidate skills or
measured coverage. All catalog IDs, tiers, languages and licenses remain unchanged.

| Canonical source group | Locally inspected scope / extraction | Canonical material and limits |
|---|---|---|
| diffusers / dependency @ `efe46a5b177af67c64b3666da8ddddac7ee12163` | Group/leaf offload and asynchronous prefetch offer different memory-latency tradeoffs; hook compatibility and host allocation must be evaluated. | [diffusers.cuda.diffusion.group_offload_transfer_overlap](../src/inferrsi/data/knowledge_packs/dependency/diffusers/cuda/diffusion/group-offload-transfer-overlap.json); imported, locally_verified=false; preserve source readset and counter-signals |
| flashattention / dependency @ `1fc0221183e799363001394a12dd9e78e15f5dda` | Select an attention generation using its actual GPU, dtype and interface requirements; package names and installation paths are not interchangeable. | [flashattention.cuda.attention.generation_specific_dispatch](../src/inferrsi/data/knowledge_packs/dependency/flashattention/cuda/attention/generation-specific-dispatch.json); imported, locally_verified=false; preserve source readset and counter-signals |
| flashinfer / dependency @ `3637083a3a3d08538cce60937cd876b17779c6f0` | Paged attention separates planning from execution; auto dispatch and CUDA graph buffer ownership are part of the reproducibility boundary. | [flashinfer.cuda.llm.paged_decode_dispatch](../src/inferrsi/data/knowledge_packs/dependency/flashinfer/cuda/llm/paged-decode-dispatch.json); imported, locally_verified=false; preserve source readset and counter-signals |
| pytorch / dependency @ `f15b476814ebc5eade36fb40512e379ebf79dd60` | CUDA graph replay can reduce host launch overhead, but shape specialization, pointer stability and output lifetime remain independent constraints. | [pytorch.cuda.compiler.cudagraph_shapes_and_lifetimes](../src/inferrsi/data/knowledge_packs/dependency/pytorch/cuda/compiler/cudagraph-shapes-and-lifetimes.json); imported, locally_verified=false; preserve source readset and counter-signals |
| transformers / dependency @ `2126f65b0ab267e113e78a002447fc7094de83d5` | Dynamic, static, offloaded and quantized KV caches have different contracts; select by workload and API support rather than a universal ranking. | [transformers.common.llm.kv_cache_strategy_contracts](../src/inferrsi/data/knowledge_packs/dependency/transformers/common/llm/kv-cache-strategy-contracts.json); imported, locally_verified=false; preserve source readset and counter-signals |
| triton / dependency @ `4eda6cc91e86553a2517d1c764ea2967985553ad` | Fuse a bandwidth-bound reduction when its working set fits on chip; choose launch geometry using the compiled resource footprint. | [triton.common.kernel.bandwidth_fusion_resource_limits](../src/inferrsi/data/knowledge_packs/dependency/triton/common/kernel/bandwidth-fusion-resource-limits.json); imported, locally_verified=false; preserve source readset and counter-signals |
| cache_dit / peer @ `a57c826d3527736a0d1f1b0243d47568c350eb5f` | DBCache skips intermediate transformer work using residual similarity, with computed boundary blocks and warmup controlling approximation. | [cache_dit.common.diffusion.residual_cache_calibration](../src/inferrsi/data/knowledge_packs/peer/cache_dit/common/diffusion/residual-cache-calibration.json); imported, locally_verified=false; preserve source readset and counter-signals |
| lmdeploy / peer @ `822dddb8b3bc895eaf6cffb45a5514768e7ecb84` | KV compression can increase cache capacity yet reduce throughput; distinguish engine-specific quantizers and validate long-context quality. | [lmdeploy.cuda.llm.kv_quantization_capacity_cost](../src/inferrsi/data/knowledge_packs/peer/lmdeploy/cuda/llm/kv-quantization-capacity-cost.json); imported, locally_verified=false; preserve source readset and counter-signals |
| sglang / peer @ `f7ad4345b86d147a1c3095a3cebabca9a33ebaa1` | Move reusable prefix KV across device, host and storage tiers while accounting for sharing scope, layout conversion and prefetch policy. | [sglang.cuda.llm.hierarchical_prefix_cache](../src/inferrsi/data/knowledge_packs/peer/sglang/cuda/llm/hierarchical-prefix-cache.json); imported, locally_verified=false; preserve source readset and counter-signals |
| tensorrt_llm / peer @ `c9b18eefa731dc59b0091bdfff6d890aa9d1e98e` | Separate prefill and decode resources when workload interference dominates the added transfer, queueing and layout-conversion costs. | [tensorrt_llm.cuda.llm.prefill_decode_disaggregation](../src/inferrsi/data/knowledge_packs/peer/tensorrt_llm/cuda/llm/prefill-decode-disaggregation.json); imported, locally_verified=false; preserve source readset and counter-signals |
| xdit / peer @ `f7c16aa958379a9f0a0302350fe0e1bfcec5f23c` | USP, CFG splitting and PipeFusion have different topology, memory and quality tradeoffs; qualify each before combining them. | [xdit.cuda.diffusion.parallelism_freshness_and_topology](../src/inferrsi/data/knowledge_packs/peer/xdit/cuda/diffusion/parallelism-freshness-and-topology.json); imported, locally_verified=false; preserve source readset and counter-signals |
| strata / contribution @ `296b59d2f73c8f04a805df29c2fa97655adace78` | Family geometry, expert residency, CPU/PCIe balance and native engine gates; three existing abstracts inspected | [strata.common.llm.architecture_search_space](../src/inferrsi/data/repo_packs/strata/knowledge/common/llm/architecture-search-space.json); [strata.common.llm.controlled_execution_tuning](../src/inferrsi/data/repo_packs/strata/knowledge/common/llm/controlled-execution-tuning.json); [strata.common.llm.engine_validation_contract](../src/inferrsi/data/repo_packs/strata/knowledge/common/llm/engine-validation-contract.json); bilingual source documents retained, no device/service validation |
| vllm / contribution @ `2521446ac8c92937b5a32b7dc2a84ef7fa8e99c5` | V1 token/KV ownership, bounded serving measurements and extension gates; three existing abstracts inspected | [vllm.common.llm.bounded_serving_measurement](../src/inferrsi/data/repo_packs/vllm/knowledge/common/llm/bounded-serving-measurement.json); [vllm.common.llm.extension_correctness_gates](../src/inferrsi/data/repo_packs/vllm/knowledge/common/llm/extension-correctness-gates.json); [vllm.common.llm.runtime_and_kv_ownership](../src/inferrsi/data/repo_packs/vllm/knowledge/common/llm/runtime-and-kv-ownership.json); bilingual source documents retained, no device/service validation |
| sglang / contribution @ `16176278d0180f1a1a578e53e6eef432577876c2` | Radix/HiCache state, TP/DP/EP and controlled tuning; three existing abstracts inspected | [sglang.common.llm.parallelism_and_extension](../src/inferrsi/data/repo_packs/sglang/knowledge/common/llm/parallelism-and-extension.json); [sglang.common.llm.runtime_radix_hicache](../src/inferrsi/data/repo_packs/sglang/knowledge/common/llm/runtime-radix-hicache.json); [sglang.common.llm.tuning_and_validation](../src/inferrsi/data/repo_packs/sglang/knowledge/common/llm/tuning-and-validation.json); bilingual source documents retained, no device/service validation |
| sglang_omni / contribution @ `2cfb3b67becb437b70751defe37e63d3af4eedb0` | Stage DAG/process transport, preparation/abort lifecycle and audio quality; three existing abstracts inspected | [sglang_omni.common.audio.serving_and_streaming_quality](../src/inferrsi/data/repo_packs/sglang_omni/knowledge/common/audio/serving-and-streaming-quality.json); [sglang_omni.common.omni.extension_lifecycle_validation](../src/inferrsi/data/repo_packs/sglang_omni/knowledge/common/omni/extension-lifecycle-validation.json); [sglang_omni.common.omni.pipeline_state_and_transport](../src/inferrsi/data/repo_packs/sglang_omni/knowledge/common/omni/pipeline-state-and-transport.json); bilingual source documents retained, no device/service validation |
| vllm_omni / contribution @ `52194f24fa42e14d1c5e096f4bea4dc7f95cffa1` | Stage/replica ownership, diffusion state/output and streaming audio measurement; three existing abstracts inspected | [vllm_omni.common.audio.streaming_serving_measurement](../src/inferrsi/data/repo_packs/vllm_omni/knowledge/common/audio/streaming-serving-measurement.json); [vllm_omni.common.diffusion.step_state_and_output_validation](../src/inferrsi/data/repo_packs/vllm_omni/knowledge/common/diffusion/step-state-and-output-validation.json); [vllm_omni.common.omni.stage_ownership_and_search](../src/inferrsi/data/repo_packs/vllm_omni/knowledge/common/omni/stage-ownership-and-search.json); bilingual source documents retained, no device/service validation |
| Internal Drama3 issue #10 | Recorded continuous-admission versus drain occupancy; diagnostic section inspected, original trace not reread | [One reusable case](../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/admission-drain-occupancy.md); INCONCLUSIVE campaign, reported artifact hash, no new gain claim |
| Main audio source guidance | Scheduler-step, graph/state/stream ownership, actual dispatch and complete-service limits at the record's source pin | [Existing audio record](../src/inferrsi/data/repo_packs/vllm_omni/knowledge/cuda/audio/concurrency-scaling-state-and-overlap.json); imported guidance stays unverified |

Rejected-direction extraction reuses the same pinned main source summaries:
[Qwen B300](../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/qwen-b300-rejected-directions.md),
[Qwen Ascend](../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/qwen-ascend-rejected-directions.md)
and [Drama3 B300](../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/drama3-rejected-directions.md).
These are three additional Case bundles, not new source mechanisms, skills,
independent corroboration or hardware validation. Each separates recorded
disposition from a proposed diagnostic check and retains the source limits.

The [knowledge-base contract](knowledge-base.md) owns field and mode semantics.
Missing early six-paper input stays blocked. Historical reports and A–F readsets,
comparisons and cases remain preserved; catalog translation/import does not add
independent corroboration or a new source-mechanism count.

## Issue #27 reconciliation: Drama3 NPU readiness

Supplement scope only; **no new mined coverage or measured cell is credited**.
The [Drama3 NPU readiness supplement](drama3-npu-readiness.md) maps the
RFC-pinned GPU source and existing imported records to a stage/state execution
map, a state-correctness contract and a measurement/quality contract.

| Source group | Pin / scope | Lineage note |
|---|---|---|
| david6666666/drama-3-single-b300-inference | `58a1882a4d941f8d21bfce6be37d3d5e7c9fde80`; RFC-selected commits only (`a6e660cc`, `ec51ba1e`, `a7118fb7`, `6ff8d808`, `33f6d723`) and `benchmark.py`/results; no broad history scan | External GPU reference engine motivating NPU questions; shares the design family of the existing `vllm_omni.cuda.audio.concurrency_scaling_state_and_overlap` import (not independent corroboration) |

The supplement links the existing
[Drama3 B300 rejected-directions case](../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/drama3-rejected-directions.md)
rather than restating it; that case shares this campaign lineage.

The two primary matrices are unchanged in authority; this is a reconciliation
note, not a third inventory. All NPU status for Drama3 remains `unverified`.
