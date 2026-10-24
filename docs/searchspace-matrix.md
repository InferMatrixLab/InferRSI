# InferRSI SearchSpace Matrix

**Branch:** `opus/meta-skill-bootstrap` | **Integration date:** 2026-10-16 | **Comparison anchor:** `d96ff8d3`

Current skill links resolve to the complete categorized
[skill library](../src/inferrsi/data/skill_library/README.md). Hardware-specific
procedures live under their hardware owner; this relocation does not change
the source-inspection or maturity claims below.

Top-level rows are hardware resource layers.  
Second-level optimization targets (Kernel, Operator, KV Cache, Attention, Runtime, Distributed, Serving, VAE/Codec) live **inside** the row that owns their bottleneck.

**Maturity key:** 🟢 covered (candidate skill + source evidence — candidate intelligence with source support, **not proven gains**) · 🟡 partial (source read, no dedicated skill) · 🔴 gap (no source, no skill)

Per decision D05 (2026-10-15): approval, extraction, coverage, and empirical
validation are distinct. Green here means extracted candidate intelligence
with source support; no cell claims a measured improvement. Provenance and
inspected scope belong in the [Reference Matrix](reference-matrix.md), covering
repositories, papers, official documentation, PRs and expert material.

---

## 1 · Graphics Card / Accelerator

The primary compute and HBM resource. Most current work lives here.

| Lifecycle step | What it covers | Candidate Skills | Cases / Experience | Evidence | Maturity |
|---|---|---|---|---|---|
| **Diagnose / Configure / Verify** | CUDA eager dense-FFN Attention/FFN rank namespaces and per-stage/per-peer hidden-state ownership | [audit-afd-p2p-exchanges](../src/inferrsi/data/skill_library/repositories/afd-plugin/audit-afd-p2p-exchanges/SKILL.md) | A=3,F=2 control sender differs from data peer; matching total tokens does not preserve peer rows | afd-plugin @ df8d6a0c403c3ca1b4ed9cf1687e7204908bebec; [source ledger](../src/inferrsi/data/skill_library/repositories/afd-plugin/audit-afd-p2p-exchanges/references/source-notes.md), [proposed cases](reviews/issue91-afd-p2p.md) | 🟢 (source-derived candidate; native/model/efficacy not_run; no Network qualification) |
| **Observe / Diagnose / Verify** | MiniMax-H3 joint audio/video AdaLN schedule/row-map validity, Metal BF16 rounding and actual int8 dispatch versus approximate controls | [audit-h3-runtime-residency](../src/inferrsi/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/SKILL.md) | Fifty layers/reuse 1 does not disable M5 int8 or BF16 head; test-source parity is not full media quality | h3.c @ 8974cc055ea9c02fcd14cc27dfda3e1027c05153; [precision contracts](../src/inferrsi/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/references/precision-and-streaming.md) | 🟢 (source-derived candidate; native/quality/performance not_run) |
| **Diagnose / Configure / Verify** | Workflow model-weight residency, partial unload versus wrapper removal, patch identity and static/dynamic backend dispatch | [comfy-ui](../src/inferrsi/data/skill_library/repositories/comfy-ui/SKILL.md) | CPU dynamic construction reroutes to the static patcher; wrapper/free-byte bookkeeping is not physical allocator release | ComfyUI @ b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c; [model ownership](../src/inferrsi/data/skill_library/repositories/comfy-ui/references/model-residency.md) | 🟢 (source-derived audit; device/native allocator unverified) |
| **Observe / Diagnose / Verify** | Native diffusion managed budget versus device headroom, graph-segment weight protection and optional prefetch completion | [audit-sd-cpp-residency](../src/inferrsi/data/skill_library/repositories/stable-diffusion-cpp/audit-sd-cpp-residency/SKILL.md) | CPU bypasses accelerator capacity and segmentation gates; pin release is not physical free; backend capability does not prove overlap | stable-diffusion.cpp @ b13a48219d5cdf408edcb93da6cd69b612ed03d3; [phase residency](../src/inferrsi/data/skill_library/repositories/stable-diffusion-cpp/audit-sd-cpp-residency/references/phase-residency.md) | 🟢 (source-derived audit; native/device/model unverified) |
| **Observe / Profile** | System-level GPU/NPU timeline, per-kernel stats, SOL%, AI Core utilization ratios, step-trace four-tuple | `ascend-performance-analysis`, `dense-performance-evidence` (L2) | CANN CSV pipeline, MindIE-SD profiling-analyze lessons | MindIE-SD @ 8481d39b; TRT-LLM nsys/ncu @ f33e0e5f | 🟢 |
| **Observe / Profile** | Single-operator benchmark (msprof op, 8 CSV metrics, per-core occupancy) | `ascend-operator-profiling` | ops-profiling loop | awesome-ascend-skills @ 75ec89ce | 🟢 |
| **Observe / Profile** | Trace-to-source attribution: representative-step selection, kernel→source-module ownership via code_ref, compact vs full detail views | `cann-attribution-overlap` | Selection reason + shapes + streams + code_ref retained per kernel owner | cann/oam-tools @ 8440935f (pack-mediated, wave 6) | 🟢 |
| **Diagnose** | Bottleneck classification: compute-bound vs memory-bound vs AI-CPU fallback vs comm-exposed | `ascend-performance-analysis` (5-layer pipeline), `performance-ceiling-analysis` (L1–L3), `cann-attribution-overlap` (attribution-aware) | SOL% / mte2-ratio / mac-ratio heuristic | MindIE-SD; TRT-LLM roofline @ f33e0e5f; LLM-Viewer @ 1893e4b5 | 🟢 |
| **Diagnose** | Roofline model, arithmetic intensity, hardware table entry for new accelerator | `performance-ceiling-analysis` (L1) | FLOPs formulas per layer type | LLM-Viewer `roofline_model.py`, `hardware_params.py` | 🟢 |
| **Configure** | Graph mode (npugraph_ex / ACLGraph): capture-replay, FX pass, memory reuse, static kernel compile | `ascend-graph-mode` | TorchAir document-first discipline | awesome-ascend-skills torch-npugraph-ex-knowledge @ 75ec89ce | 🟢 |
| **Configure** | Parallelism strategy (USP/CP/TP/PP), topology-aware card-group selection | `ascend-distributed-parallel` | USP activation requirement, masking upper-bound formula, AlltoAllV workaround | MindIE-SD dit-parallel-opt @ 8481d39b (9 reference files) | 🟢 |
| **Configure** | Model adapter: FP8 dequantization, KV-head replication, multimodal feature validation order | `ascend-model-adaptation` | vllm-ascend FP8/multimodal lessons; [separate runtime-wrapper route](../src/inferrsi/data/skill_library/README.md#vllm-ascend-version-and-responsibility-routing) | vllm-ascend @ bc8115ed | 🟢 |
| **Optimize** | Kernel-level: Triton/CuTe/TileIR writing, kernel tuning, fusion scope analysis | `kernel-writing-guide` | Framework routing (Triton vs CuTe vs AscendC), 6 universal correctness rules, verify-before-benchmark workflow | TRT-LLM kernel-triton-writing + kernel-cute-writing @ f33e0e5f | 🟢 |
| **Diagnose / Configure / Verify** | AKG static CUDA Affine loop tails: effective target/option gates, full point-loop bounds and protected input/output accesses | [kernel-writing-guide](../src/inferrsi/data/skill_library/methods/kernel-writing-guide/SKILL.md) | [Tail-guard reference](../src/inferrsi/data/skill_library/methods/kernel-writing-guide/references/akg-affine-tail-guards.md): separation precedence, non-divisible fixture and diagnostic boundary | AKG @ 5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff; source + FileCheck expectations only | Candidate; compiler/IR command, CUDA runtime and agent efficacy not run; no new measured coverage |
| **Optimize** | Operator-level: staged accuracy-gated tuning campaign (code-level → scheduling → instruction-level), metric→action routing; AscendC tiling design per operator class (reduction/broadcast/elewise/matmul/conversion) | `ascend-operator-tuning`, `ascendc-tiling-design` | PyPTO frontend/swimlane/incore playbooks; fullload-vs-split, four-element tiling template, chip-generation (DAV_2201/3510) routing | awesome-ascend-skills pypto-op-perf-tune + ascendc-tiling-design @ 75ec89c | 🟢 |
| **Optimize** | Casebook of past NPU optimization decisions: AI-CPU fallback, memory-bound, comm-exposed, graph-compilation, scheduling idle gaps | `ascend-optimization-casebook`, `inference-optimization-casebook` | Five bottleneck classes with symptom→diagnosis→action→evidence schema | MindIE-SD profiling-analyze + dit-perf-opt + perf-gate + dit-parallel-opt @ 8481d39b | 🟢 |
| **Optimize** | Bounded experiment selection, distinct mechanism hypotheses, incumbent preservation and final-artifact integrity | `optimization-search-policy` | Methodology provenance stays in Reference Matrix §2; no hardware coverage from agent-paper scores | vllm-evolve @ 43cc82c; scoped A/F paper amendments | 🟢 (procedure only) |
| **Optimize** | Bounded multistream overlap: dependency-DAG constrained (data/state/event/collective_order edges; shared input ≠ dependency), minimal-first, execution-mode sync contract (eager streams vs TorchAir) | `cann-attribution-overlap` | Metric separation (wall / union-of-busy / summed durations / summed duration+wait; repeated-instance product = estimate); device-memory domain qualification; formula conflicts carried unresolved | cann/oam-tools @ 8440935f (pack-mediated, wave 6) | 🟢 |
| **Verify** | Evidence taxonomy (L0 correctness → L5 production), claim-evidence matching | `dense-performance-evidence`, `rsi-evidence`, `claim-contract` | InferRSI PASS/FAIL/INCONCLUSIVE protocol | InferRSI @ 4c8e1285 | 🟢 |
| **Diagnose / Verify** | Fixed-stage PyTorch/Ascend model report: bind current stage and actually loaded candidate to quality-validator output and comparable baseline | [ascend-performance-analysis](../src/inferrsi/data/skill_library/hardware/ascend/ascend-performance-analysis/SKILL.md) | [Stage-evidence rule](../src/inferrsi/data/skill_library/hardware/ascend/ascend-performance-analysis/references/cannbot-stage-evidence.md): workflow instructions versus registered marker/keyword checks; completion is not numerical validation | canonical cann/cannbot @ c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110; selected CANN-2.0 scope | Candidate procedure only; host/model/backend not_run, agent efficacy not evaluated; no new measured coverage |
| **Verify** | Same-window A/B protocol, noise floor, acceptance-state discipline; correctness-first overlap acceptance (fallback works, no KV/state reorder, actual overlap, no outside-module regression) | `ascend-optimization-casebook` (evidence-required section per case), `dense-performance-evidence`, `rsi-evidence`, `cann-attribution-overlap` | MindIE-SD perf-gate protocol: exploration vs acceptance state, three-proof requirement | MindIE-SD perf-gate @ 8481d39b; cann/oam-tools @ 8440935f | 🟢 |
| **Observe / Configure / Optimize** | DALI CPU/GPU queue overlap and operator buffer sizing under explicit executor-mode gates | `training-input-pipeline` | Separated queues require async+pipelined and non-dynamic mode; output synchronization retained | Reference B1, DALI @ 6fe47c48d3b0 | 🟢 (Python API evidence, not C++/device validation) |
| **Diagnose / Configure / Optimize** | Training capacity versus throughput, parameter/optimizer tier budgets, recomputation/offload choices; DCP exposed staging pause | `training-resource-budget`, `dcp-async-save-performance` | DeepSpeed stage gates; expert MFU/HFU denominator discipline; historical MindSpeed case only | Reference CR1, CR6, CR5, C1 async-only | 🟢 (MindSpeed implementation/current support unresolved) |
| **Observe / Diagnose / Configure / Optimize / Verify** | vLLM V1 token/input/active-request budgets, allocation/preemption gates and async-KV admission; cap changes are conditional hypotheses | `diagnose-vllm-admission-pressure` | Queue length and KV usage do not establish allocation pressure; stats are gated and incomplete; verification proposed only | vLLM @ 7f730b4cea9a, Dot bundle; pinned scheduler/connector source ledger | 🟢 (candidate diagnosis; no runtime or gain validation) |
| **Diagnose / Verify** | Context partial-ubatch progress, topology/input graph reuse and backend copy/event readiness | [audit-llama-runtime-state](../src/inferrsi/data/skill_library/repositories/llama-cpp/audit-llama-runtime-state/SKILL.md); [owner map](../src/inferrsi/data/skill_library/repositories/llama-cpp/audit-llama-runtime-state/SKILL.md#choose-the-scope) | Retained completed ubatches differ from whole-batch rollback; frontend reuse differs from backend captured graphs | llama.cpp @ `707616feb5f379e99ff7442680a55b4a1704c7c9`; runtime/source notes and native test assertions; static inspection 2026-10-21 carried | 🟢 (source-derived candidate; native/backend execution not run) |
| **Observe / Diagnose / Verify** | KV receive/save completion, delayed-free ownership, in-flight-write fences and failure reporting | `audit-vllm-kv-lifetimes` | Event ledger is proposed, not a telemetry exporter; abstract obligations require concrete connector/caller evidence | vLLM @ 7f730b4cea9a, Dot bundle | 🟢 (contract intelligence; concrete backend unverified) |
| **Diagnose / Configure / Optimize / Verify** | Runtime ACLGraph dispatch, stable input addresses, capture-resource limits and branch-specific replay/update ordering | `ascend-aclgraph-capture-replay` | Caller owns persistent buffers; DEBUG checks positional tensors only; reduced capture sets trade coverage for resources; [version/responsibility routing](../src/inferrsi/data/skill_library/README.md#vllm-ascend-version-and-responsibility-routing) | vllm-ascend @ 8a8e1e05ecb6, Dot bundle; wrapper/guide/tests inspected by supplier | 🟢 (conditional proposals; tests not run) |
| **Diagnose / Configure / Optimize / Verify** | Device-HBM stream-use lifetime, fragmentation/counter interpretation and gated allocator controls | `torchnpu-device-memory-lifecycle` | Lifetime recording does not insert data dependencies; expandable segments change counters/control legality; GC synchronization/comment conflict retained | TorchNPU @ 67511c53cd4c, Dot bundle; device allocator ledger | 🟢 (source-supported procedure; NPU execution not run) |
| **Diagnose / Verify** | Serving model: operator/context dependencies, calibration/load domain and joint-SLO prediction uncertainty | [calibrate-serving-simulation](../src/inferrsi/data/skill_library/methods/calibrate-serving-simulation/SKILL.md), `performance-ceiling-analysis` | Vidur near-capacity CPU-overhead counterexample; simulator output is not a bound | Vidur v2; Reference Matrix systems-paper row | 🟢 (prediction guidance; calibration not run) |
| **Diagnose / Configure / Optimize / Verify** | Serving service order versus HBM admission and suspended-KV recovery; replica migration versus elastic sequence groups | [assess-serving-preemption](../src/inferrsi/data/skill_library/methods/assess-serving-preemption/SKILL.md), [evaluate-elastic-serving-placement](../src/inferrsi/data/skill_library/methods/evaluate-elastic-serving-placement/SKILL.md) | [Hypothetical pressure/migration cases](../src/inferrsi/data/skill_library/repositories/vllm/diagnose-vllm-admission-pressure/references/papers-20261015/knowledge/scheduling-state-boundaries.md); cohort/fairness and destination-reservation costs | Orca proceedings, FastServe v3, Llumnix v1, LoongServe v2; implementation pins remain separate | 🟢 (conditional paper-derived plans) |
| **Diagnose / Optimize / Verify** | Training activation lifetime, rematerialization and reserved-address packing | [plan-activation-residency](../src/inferrsi/data/skill_library/methods/plan-activation-residency/SKILL.md) | Dependency repair and capacity feasibility checked separately; no recovery-checkpoint coverage | Checkmate v3, OLLA v2; [C readset](../src/inferrsi/data/skill_library/methods/training-resource-budget/references/papers-20261015/references/source-readset.md) | 🟢 (planning, not solver/runtime validation) |
| **Diagnose / Configure / Optimize / Verify** | Training stage/mesh/sharding feasibility and split F/B/W execution under total-HBM and optimizer-semantics constraints | [choose-parallel-training-plan](../src/inferrsi/data/skill_library/methods/choose-parallel-training-plan/SKILL.md), [assess-split-backward-schedule](../src/inferrsi/data/skill_library/methods/assess-split-backward-schedule/SKILL.md) | Alpa conditional plans; Zero Bubble activation caps versus total memory; rollback versus stale updates | Alpa v3, Zero Bubble v1 | 🟢 (author evidence, no current stack validation) |
| **Diagnose / Optimize / Verify** | Attention IO, operation-class ceilings, output ownership, work supply, async dependencies and FP8 layout/accuracy | [diagnose-attention-bottlenecks](../src/inferrsi/data/skill_library/hardware/cuda/diagnose-attention-bottlenecks/SKILL.md), `kernel-writing-guide` | [Author-reported attention cases](../src/inferrsi/data/skill_library/hardware/cuda/diagnose-attention-bottlenecks/references/papers-20261015/cases/overlap-and-fp8-counter-signals.md); compiler/register and precision counter-signals | FlashAttention v2 / FA2 v1 / FA3 v2 | 🟢 (Accelerator only; no Ascend implementation claim) |
| **Diagnose / Verify** | Diffusion stage/component-use readiness, retention and mutable request-scheduler aliases; client timeout/deletion versus worker/device completion | [audit-sglang-diffusion-lifetimes](../src/inferrsi/data/skill_library/repositories/sglang/audit-sglang-diffusion-lifetimes/SKILL.md) | Default ParallelExecutor and concrete rank/strategy must be traced; closing a use does not imply eviction or device cancellation | SGLang @ df13d5dce31a; bounded multimodal_gen source readset, separate from LLM/HiCache | 🟢 (candidate diagnosis; native/quality/performance not run) |

**Second-level targets in this row:** Kernel, Operator, KV Cache, Attention, Diffusion denoising steps, VAE/Codec, Graph compilation, Serving/Runtime admission, device-HBM allocator lifecycle, Training activation residency and pipeline scheduling

---

## 2 · RAM / Host Memory

Host-side memory: CPU DRAM, pinned memory, page tables, PyTorch tensor lifecycle.

| Lifecycle step | What it covers | Candidate Skills | Cases / Experience | Evidence | Maturity |
|---|---|---|---|---|---|
| **Observe / Diagnose / Verify** | MiniMax-H3 TE/vision/input-output VAE phase lifetime, prepared DiT/decoder retention, shared/mapped weight and host media/output residency | [audit-h3-runtime-residency](../src/inferrsi/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/SKILL.md) | Preview/cache changes overlap; output tiling retains full RGB; checkpoint bytes and tracked tensors do not establish total RAM fit | h3.c @ 8974cc055ea9c02fcd14cc27dfda3e1027c05153; [phase ledger](../src/inferrsi/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/references/phase-residency.md) | 🟢 (source-derived candidate; physical/compressed/swap peaks unmeasured) |
| **Diagnose / Configure / Verify** | Workflow-output signatures and object identity, ancestor/fingerprint validity versus retention, lazy consumer references and host/pinned state | [comfy-ui](../src/inferrsi/data/skill_library/repositories/comfy-ui/SKILL.md) | A fixed JSON filename is not an external-state fingerprint; NOT_IDEMPOTENT node identity does not force every-run invalidation | ComfyUI @ b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c; [cache ledger](../src/inferrsi/data/skill_library/repositories/comfy-ui/references/graph-cache-invalidation.md) | 🟢 (source-derived procedure; executor cache suite not run) |
| **Observe / Diagnose / Verify** | Native diffusion parameter storage, compute staging and retained runtime buffers across conditioning/denoise/VAE phases | [audit-sd-cpp-residency](../src/inferrsi/data/skill_library/repositories/stable-diffusion-cpp/audit-sd-cpp-residency/SKILL.md) | Device fit does not establish sufficient host RAM; initial host preparation may precede async transfer; track host/device peaks separately | stable-diffusion.cpp @ b13a48219d5cdf408edcb93da6cd69b612ed03d3; [validation](../src/inferrsi/data/skill_library/repositories/stable-diffusion-cpp/audit-sd-cpp-residency/references/validation-boundaries.md) | 🟢 (source-derived ownership audit; host peaks unmeasured) |
| **Observe / Profile** | Host overhead in nsys: GPU idle ratio (>0.30 aggregate/>0.15 generation), host-prep exposed ratio (M3b>0.05), NVTX breakdown, inter-kernel gaps; cgroup memory pressure (PSI) and event counters | `host-overhead-profiling`, `cgroup-resource-controls` (pressure/events observation) | GPU idle + host-prep verdict metrics; NVTX root-cause breakdown; regression comparison across two traces | TRT-LLM perf-host-analysis @ f33e0e5f; kernel cgroup-v2 docs (pack-mediated) | 🟢 |
| **Diagnose** | YES/NO bottleneck verdict; multi-rank straggler detection; NVTX-to-source function mapping | `host-overhead-profiling` | M3b>0.05 AND M3c>0.50 together confirm host-prep bottleneck | TRT-LLM perf-host-analysis @ f33e0e5f | 🟢 |
| **Configure** | Pinned memory for fast H2D (>1MB tensors where transfer is measured bottleneck), async H2D via non_blocking=True + stream + explicit synchronize(), Python GIL avoidance (ProcessPoolExecutor, Python 3.13 free-threading PEP 703), NUMA-aware allocation (numactl); memory limits and protection (memory.high/low/max); versioned Ascend native CPU descriptor-pool ownership | `host-memory-management`, `kv-tier-management` (L1 tier sizing, multi-L1 composition), `cgroup-resource-controls` (memory controls) | Historical guide: APIs attributed to PyTorch/Python docs and numactl (not revalidated here); Ascend source case: successful head end-event query gates normal reuse, tracked wait does not recycle | PyTorch docs, Python docs, PEP 703, numactl manpage; LMCache @ c3b875a; kernel cgroup-v2 docs (pack-mediated); vllm-ascend @ 8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf ([native case](../src/inferrsi/data/skill_library/hardware/host/host-memory-management/references/vllm-ascend-native-offload.md)) | 🟢 (Ascend extension: source-derived candidate; native not run) |
| **Optimize** | line_profiler loop targeting `_prepare_tp_inputs`; NVTX regression triage to alternative targets (`_fetch_new_requests` +643%, `broadcast_requests`, `_update_requests` +75%); runtime KV tier management (store/retain/prefetch/evict policies, concurrency-vs-RAM admission dial) | `host-overhead-optimization`, `kv-tier-management` | Iterative profile→identify→optimize→verify loop; RAM-release lever ranking | TRT-LLM perf-host-optimization @ f33e0e5f; LMCache MP mode @ c3b875a | 🟢 |
| **Verify** | Memory-event verification: matched baseline/outcome windows, PSI + event deltas, configuration provenance, rollback contract | `dense-performance-evidence` (evidence levels apply), `cgroup-resource-controls` (verification contract) | Application outcomes + sibling pressure tracked together; raw counter deltas retained | kernel cgroup-v2 docs (pack-mediated, wave 6) | 🟢 (proposed procedure, unvalidated) |
| **Observe / Profile** | Per-host checkpoint snapshot/pinned-memory residency, copy and staging-worker pressure | `dcp-async-save-performance` | Sum local-rank state plus cache and input/offload overhead; no global-rank-to-single-host RAM assumption | PyTorch DCP @ 7d239835e773 | 🟢 (source-supported estimate/measurement plan) |
| **Configure / Optimize / Verify** | CPU snapshot lifetime: source mutation after staging, cached storage reuse after upload, caller-owned cleanup | `dcp-async-save-performance` | D2H and same-host IPC remain host resources, not network cells | DCP `DefaultStager`, `StateDictStager` @ 7d239835e773 | 🟢 (unvalidated candidate procedure) |
| **Observe / Diagnose / Configure / Optimize** | Input queue/cached-shard working-set budgets; offload CPU/pinned-memory costs and locality | `training-input-pipeline`, `training-resource-budget` | Per-worker samples differ from bytes; host budget includes input/checkpoint/offload together | Reference B1/B2/B3, CR1/CR6/CR5 | 🟢 (candidate decisions, no measurements) |
| **Configure / Verify** | Shared-memory snapshot readiness, positive-step agreement, replica/staging lifetime | `checkpoint-recovery-consistency` | Worker survival differs from host survival; state completeness remains separate | Reference C3/C4 | 🟢 (source contracts; recovery untested) |
| **Diagnose / Configure / Optimize / Verify** | TorchNPU pinned-host ownership, pending-copy reuse, host-specific byte accounting and default/expandable cache controls | `torchnpu-pinned-host-memory-lifecycle` | External registration ownership and ATen internals unresolved; per-block threshold is not a total-cache cap; version-warning conflict retained | TorchNPU @ 67511c53cd4c, Dot bundle; host allocator/copy/config ledger | 🟢 (conditional procedure; no runtime validation) |
| **Diagnose / Configure / Optimize / Verify** | Suspended KV host residency, predicted recovery and migration staging under actual host capacity/bandwidth | [assess-serving-preemption](../src/inferrsi/data/skill_library/methods/assess-serving-preemption/SKILL.md), [evaluate-elastic-serving-placement](../src/inferrsi/data/skill_library/methods/evaluate-elastic-serving-placement/SKILL.md) | Running-batch bytes exclude other unfinished state; device space is also required for restoration | FastServe v3, Llumnix v1; hypothetical cases, not observed failures | 🟢 (conditional host mechanism) |
| **Diagnose / Optimize / Verify** | CPU optimizer state/compute ownership and tiled update/return cost | [training-resource-budget](../src/inferrsi/data/skill_library/methods/training-resource-budget/SKILL.md) | [ZeRO-Offload delta](../src/inferrsi/data/skill_library/methods/training-resource-budget/references/papers-20261015/knowledge/offload-delta.md); staleness requires a separate semantic decision | ZeRO-Offload v1, distinct from the existing DeepSpeed config pin | 🟢 (author evidence, unmeasured locally) |
| **Diagnose / Optimize / Verify** | Host feature materialization, invariant reuse and assembly lifetime | [host-overhead-optimization](../src/inferrsi/data/skill_library/hardware/host/host-overhead-optimization/SKILL.md) | [Cross-layer procedure](../src/inferrsi/data/skill_library/methods/performance-ceiling-analysis/references/papers-20261015/redirect-cross-layer-optimization/procedure.md); local gain requires full-stack SLO verification | FlashVector v1, same source identity as Reference Matrix §2 | 🟢 (scoped host mechanism, not service gain) |
| **Diagnose / Verify** | Host-side request/job records, scheduler-object sharing and output-finalizer task lifetime | [audit-sglang-diffusion-lifetimes](../src/inferrsi/data/skill_library/repositories/sglang/audit-sglang-diffusion-lifetimes/SKILL.md) | Req field is not proof of object isolation; socket close and store deletion do not establish worker termination; device HBM excluded | SGLang @ df13d5dce31a; same bounded source identity | 🟢 (source-derived candidate, no measured memory saving) |
| **Diagnose / Verify** | Host-owned reader/task/result and slot prompt-token lifecycle under cancellation | `audit-llama-runtime-state` | Waiter removal, queued-work cleanup and slot release are distinct; stateful prompts may remain; no host byte-saving claim | llama.cpp @ 707616feb5f3; server queue/context source and cancellation test assertion | 🟢 (candidate lifecycle diagnosis; native server case not run) |

**Second-level targets:** PyTorch tensor lifecycle, request scheduling, KV cache CPU offload, TorchNPU pinned-host allocator lifecycle, CPU optimizer ownership and host feature assembly

---

## 3 · SSD / Storage

Storage I/O: model weight loading, checkpoint save/restore, profiling artifact I/O, dataset prefetch.

| Lifecycle step | What it covers | Candidate Skills | Cases / Experience | Evidence | Maturity |
|---|---|---|---|---|---|
| **Diagnose / Configure / Verify** | Raw tensor-schema compatibility, file-backed DiT versus two-slot BF16 SSD streaming, Qwen read-worker/ring-depth distinction and submit/join completion | [audit-h3-runtime-residency](../src/inferrsi/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/SKILL.md) | SSD mode disables runtime int8; compare matching BF16 paths. F_NOCACHE request and zero join wait do not prove bypass or free I/O | h3.c @ 8974cc055ea9c02fcd14cc27dfda3e1027c05153; [I/O tradeoffs](../src/inferrsi/data/skill_library/repositories/h3-c/audit-h3-runtime-residency/references/precision-and-streaming.md#three-different-ioresidency-paths) | 🟢 (source-derived candidate; native I/O/overlap/performance not_run) |
| **Observe / Profile** | Workload-matched block-device measurement (fio methodology: signature recording, requested-vs-achieved depth, cache-state ledger, run-shape classification), per-device attribution (iostat), per-process attribution (pidstat) | `storage-io-measurement`, `weight-loading-optimization` (§7 phase timers) | Bounded observation templates; unit/latency-provenance schema; logical-vs-physical I/O distinction | fio @ acb7a302 + sysstat @ efd0c445 (pack-mediated, wave 6); fastsafetensors perf.py @ 219e256; mindie-agent docs @ 6a81b41 | 🟢 (methodology only — running benchmarks or manipulating caches requires separate authorization) |
| **Diagnose** | Slow startup (graph capture + weight loading dominating): distinguish compile warmup from I/O | `ascend-graph-mode` (mentions slow startup), `ascend-model-adaptation` (dummy→real sequence) | ACLGraph startup cost is compile + capture, not I/O bound; FP8 weight loading pitfalls | MindIE-SD; vllm-ascend | 🟡 (incidental coverage only) |
| **Diagnose** | Device saturation and attribution: workload matching, achieved-depth validation, %util/%iowait saturation guards, per-process I/O vs CPU-scheduling-pressure separation | `storage-io-measurement` | No universal percent threshold; corroboration required before naming a storage bottleneck | fio/sysstat pack (wave 6) | 🟢 |
| **Diagnose** | Load-path judgment (source/format/placement/duplication) and startup fixed-overhead accounting (bytes+counts lines, hit-criteria warmup validation) | `weight-loading-optimization` | Four-dimension load-path judgment; fixed-vs-per-request split; 7 accounting errors | MindIE-SD host-opt + host-overhead-account @ 8481d39b | 🟢 |
| **Configure** | Checkpoint format for fast loading (FP8 paired tensors, shard loading order) | `ascend-model-adaptation` | FP8 paired-tensor loading pattern | vllm-ascend @ bc8115ed | 🟡 |
| **Optimize** | Serving-level load path: device-side weight prefetch (switch-gated, 50%-of-theoretical start), CPU-tier offload ordering by change surface, duplication removal | `weight-loading-optimization` | `npu_prefetch` decision rules; OOM fallback tiers; construction vs inference OOM | cannbot model-infer-prefetch + diffusers memory-optimization @ 75ec89c; MindIE-SD resource-fallback-tiers @ 8481d39b | 🟢 (serving level) |
| **Optimize** | Disk-level loading mechanics: mmap/mlock/dio/lazy loading modes, pinned bounce-buffer parallel reads, GDS direct-to-device, byte-range/shard-parallel loading, incremental mlock growth | [weight-loading-optimization](../src/inferrsi/data/skill_library/methods/weight-loading-optimization/SKILL.md) (§6-7); [llama.cpp owner map](../src/inferrsi/data/skill_library/repositories/llama-cpp/audit-llama-runtime-state/SKILL.md#choose-the-scope) | Mode trade-off table; NUMA-disables-prefetch coupling; block-size formula; readiness overlap; static fit planner | ggml-org/llama.cpp @ `3e390af18de1131dda27913c00511725b4274c8a` (MIT; static inspection 2026-10-22 carried); foundation-model-stack/fastsafetensors @ 219e256 (Apache-2.0) | 🟢 (wave 5; CUDA/ROCm/POSIX-bound — no Ascend path in these sources) |
| **Optimize** | Runtime KV-to-disk tier: L2 local adapters (fs/nixl/raw_block/dax), persist/recover, per-adapter serde capacity lever | `kv-tier-management` | Adapter selection table; persist/recover semantics | LMCache MP mode @ c3b875a (Apache-2.0) | 🟢 |
| **Optimize** | Checkpoint save/restore: synchronous sharded writes, per-file atomic publish, opt-in fsync, reload via existing loader; whole-set atomicity / async / distributed / crash durability explicitly unsupported | `weight-loading-optimization` (§8) | Supported-vs-unknown table; mixed-set rename-failure risk as caller obligation | fastsafetensors saver.py @ 219e256 | 🟡 (fastsafetensors-specific semantics extracted; its save-performance optimization remains unsourced — no perf harness or documented tuning levers) |
| **Verify** | Load-path measurement protocol (phase timers, fadvise cold-cache, baseline comparison); storage-side verification: unit/latency-provenance-aware schema, two-layer evidence gate (device metric + application outcome) | `weight-loading-optimization` (§7), `storage-io-measurement` (prime rule, §5) | Author-reported numbers labeled as such; device metrics never merged with application outcomes | fastsafetensors perf.py @ 219e256; fio/sysstat pack (wave 6) | 🟢 (methodology; no empirical validation) |
| **Observe / Profile** | Checkpoint caller pause, staging elapsed, upload elapsed and exposed training waits; first-use versus cached-buffer steady state | `dcp-async-save-performance` | Distinct timing boundaries; asynchronous return is not write completion | DCP async recipe + PyTorch @ 7d239835e773 (wave 7) | 🟢 (proposed measurement, not executed) |
| **Configure** | Async save mode, one outstanding save policy, staging cache/writer ownership and completion gates | `dcp-async-save-performance` | Tutorial/API reconciliation; explicit caller-owned cleanup | PyTorch DCP @ 7d239835e773 | 🟢 (DCP-only; backend qualification outstanding) |
| **Optimize** | Training-visible pause reduction via asynchronous staging and cached pinned buffers; CPU/RAM/I/O contention limits | `dcp-async-save-performance` | Wait for staging before source mutation; wait for upload before cached snapshot reuse | PyTorch DCP @ 7d239835e773; live recipe inspected 2026-10-15 | 🟢 (source-supported intelligence, no gains measured) |
| **Verify** | Observe final upload errors and step-time impact separately from backend durability and distributed recovery validity | `dcp-async-save-performance` | Async completion is not crash-durability evidence | PyTorch DCP save/stager/thread-writer paths @ 7d239835e773 | 🟢 (verification procedure only) |
| **Diagnose / Configure / Optimize** | Dataset shard residency, compressed/raw admission, cache churn, FFCV mmap/process cache and traversal order | `training-input-pipeline` | Mosaic minimum-cache implementation gate; distributed QUASI_RANDOM excluded | Reference B2/B3 | 🟢 (sample correctness and throughput untested) |
| **Configure / Optimize** | DeepSpeed NVMe parameter/optimizer buffer pools and tile read/compute/write overlap intent | `training-resource-budget` | Parameter and optimizer budgets distinct; buffer_size unit/dispatch not verified | Reference CR1 | 🟢 (configuration evidence only) |
| **Configure / Verify** | Complete-generation selection; NVIDIA dirty-to-final publication; DLRover queued/shard/done/tracker boundaries | `checkpoint-recovery-consistency` | DLRover common commit counts done files; payload serialization and POSIX synchronization require separate durability evidence. Rank coverage does not prove state completeness | Reference C3/C4; [DLRover persistence](../src/inferrsi/data/skill_library/methods/checkpoint-recovery-consistency/references/dlrover-persistence-replicas.md) | 🟢 (source-derived recovery procedure; recovery/durability untested) |

**Second-level targets:** Model weight sharding, checkpoint I/O, profiling output archival

---

## 4 · Communication Card / Network

Inter-device and inter-node communication: HCCL (Ascend), NCCL (CUDA), InfiniBand, RoCE.

| Lifecycle step | What it covers | Candidate Skills | Cases / Experience | Evidence | Maturity |
|---|---|---|---|---|---|
| **Observe / Profile** | Communication time in step-trace four-tuple, HCCL per-collective timing, `communication.json` | `ascend-performance-analysis` (Layer 4) | HCCL single-collective latency varies ~2× across devices | MindIE-SD profiling-analyze @ 8481d39b | 🟢 |
| **Diagnose** | Exposed communication: `effective_comm = Communication - Overlapped`; communication-bottleneck class; wait-aware diagnosis (wait pollution, transport/rank metrics, device imbalance) | `ascend-performance-analysis` (L1 step-trace derivation), `cann-attribution-overlap` (wait-aware) | Overlapping vs exposed comm in step_trace_time.csv; zero/missing bandwidth = unavailable evidence, single-rank data cannot establish cross-rank balance | MindIE-SD; cann/oam-tools @ 8440935f (pack-mediated) | 🟢 |
| **Diagnose** | Topology-aware card group validation: intra-domain (UB/HCCS) vs inter-domain (PCIe/SYS) | `ascend-distributed-parallel`, `ascend-device-health` | npu-smi topo output; legal card-group rules; Health=OK not sufficient | MindIE-SD dit-parallel-opt @ 8481d39b | 🟢 |
| **Configure** | Collective-in-graph capture (HCCL graph mode), comm-stream masking; masking formula `1-1/n` when F≥C | `ascend-distributed-parallel` | Masking upper bound derivation; AlltoAllV defect workaround | MindIE-SD @ 8481d39b | 🟢 |
| **Optimize** | USP activation requirement (ParallelConfig wrapping), strategy selection, AlltoAllV workaround; evidence-gated compute/communication overlap of independently-ready work | `ascend-distributed-parallel`, `cann-attribution-overlap` | USP must set ParallelConfig; verify allToAll appears not just allGather; overlap preserves ordering and joins, no comm recommendation without comm evidence | MindIE-SD dit-parallel-opt @ 8481d39b (9 ref files); cann/oam-tools @ 8440935f | 🟢 |
| **Verify** | Masking ratio measurement, before/after comm-fraction comparison; strategy activation attribution | `ascend-distributed-parallel` (attribution method), `ascend-performance-analysis`, `dense-performance-evidence`, `cann-attribution-overlap` (overlap acceptance) | Step-trace four-tuple as ground truth; scope-effectiveness-check.md | MindIE-SD perf-gate + dit-parallel-opt; cann/oam-tools @ 8440935f | 🟢 |
| **Observe / Diagnose / Verify** | Native HCCL-test versus PyTorch/HCCL wrapper selection; per-operation tensor-byte meaning, completed-call timing, rank-local reports and actual oracle coverage | `ascend-distributed-parallel` ([test acceptance](../src/inferrsi/data/skill_library/hardware/ascend/ascend-distributed-parallel/references/awesome-ascend-communication-tests.md)) | Unchecked operations can print PASS; subgroup tags and P2P peer schedules need separate references; async timing does not prove overlap | awesome-ascend-skills @ `75ec89ce9d401be8ac95980e1c3f42f8d4315057`, wrapper code and source docs | 🟢 (candidate evidence procedure; native collective/transport, backend and agent efficacy not_run; host-KV deferred, no RAM increment) |
| **Configure / Optimize** | Remote dataset shard download look-ahead versus cache churn | `training-input-pipeline` | Network bytes/readiness are distinct from local-cache footprint | Reference B2 | 🟢 (candidate mechanism; no network measurements) |
| **Configure / Optimize / Verify** | File-owner whole-tensor broadcast versus TP scatter; adjacent whole-tensor broadcast coalescing | `weight-loading-optimization` (§9) | Group-rank order, coalescing eligibility, source readiness, run-storage retention and early close; local clones/H2D excluded | fastsafetensors @ 219e256, [full-pin delivery readset](../src/inferrsi/data/skill_library/methods/weight-loading-optimization/references/fastsafetensors-transfer-readset.md) | 🟢 (source-derived candidate procedure; no runtime, transport, NPU or gain qualification) |
| **Diagnose / Configure / Verify** | Saver/loader agreement, complete-iteration coverage and DLRover full/sharded Gloo byte/metadata transport | `checkpoint-recovery-consistency` | Same-host shared memory is excluded; replica group/placement and restore consumer need payload checks. CPU/Gloo source is not HCCL/NPU qualification | Reference C3/C4; [DLRover replica boundaries](../src/inferrsi/data/skill_library/methods/checkpoint-recovery-consistency/references/dlrover-persistence-replicas.md#replica-transport-and-its-consumer) | 🟢 (source-derived transport procedure; distributed restore untested) |
| **Observe / Diagnose / Verify** | Collective kind/payload/ranks, algbw versus busbw, rank-side GC stalls versus fabric stalls | `training-resource-budget` (attributed expert note) | No network-script execution or universal bandwidth/gain claim | Reference CR6 | 🟢 (expert methodology) |
| **Diagnose / Configure / Optimize / Verify** | Cross-node request-state pre-copy/catch-up, migration versus ongoing sequence-attention traffic | [evaluate-elastic-serving-placement](../src/inferrsi/data/skill_library/methods/evaluate-elastic-serving-placement/SKILL.md) | Total bytes, duration and final downtime differ; charge congestion and protected-class regressions | Llumnix v1, LoongServe v2; actual inter-node placement required | 🟢 (paper decision contract; transport unvalidated) |
| **Diagnose / Configure / Optimize / Verify** | Cross-mesh shard intersections, required slow-link sends and local allgather replacement cost | [choose-parallel-training-plan](../src/inferrsi/data/skill_library/methods/choose-parallel-training-plan/SKILL.md) | Separate inter-node traffic from local accelerator collectives; include staging and per-rank memory | Alpa v3 AL2; no current compiler or transport qualification | 🟢 (conditional communication mechanism) |

Host/device transfers and same-host IPC are excluded from this row. Network
coverage above comes only from remote downloads, distributed agreement/replicas
and collective-specific evidence.

**Second-level targets:** AllReduce, AllGather, AllToAll, P2P ring; TP/SP/PP/EP collective patterns

---

## 5 · OS / System

System-level: scheduler, DVFS, process isolation, environment variables, driver state.

| Lifecycle step | What it covers | Candidate Skills | Cases / Experience | Evidence | Maturity |
|---|---|---|---|---|---|
| **Observe / Profile** | DVFS effect on first-run timing, process-level NPU ownership (proc-mem via npu-smi); cgroup CPU bandwidth counters (cpu.stat vs cpu.stat.local for ancestor throttling), hierarchy state | `ascend-operator-profiling` (--warm-up rationale), `ascend-device-health` (proc-mem check), `cgroup-resource-controls` | DVFS: always warm up before measuring; proc-mem occupancy check | awesome-ascend-skills ops-profiling; MindIE-SD dit-parallel-opt @ 8481d39b; kernel cgroup-v2 docs (pack-mediated) | 🟢 |
| **Diagnose** | Shared-machine contamination: neighbor load, inter-window drift, temperature variation | `ascend-performance-analysis` (measurement discipline section) | Same-window A/B required; cross-window delta ≈ real gain magnitude | MindIE-SD perf-gate @ 8481d39b | 🟢 |
| **Diagnose** | Quota versus contention: cpu.stat vs cpu.stat.local (ancestor-caused throttling), memory PSI + event deltas, requested-versus-effective cpuset | `cgroup-resource-controls` | Allocation-is-not-efficiency prime rule; pressure alone is not causal proof | kernel cgroup-v2 docs (live 2026-10-15 + v6.12, pack-mediated, wave 6) | 🟢 (proposed procedure, unvalidated) |
| **Diagnose** | SIGKILL residual state: per-step time uniformly elevated by ~1 order of magnitude | `ascend-device-health` | npu-smi Health=OK does not prove card is clean; 4-step smoke required | MindIE-SD dit-parallel-opt @ 8481d39b | 🟢 |
| **Configure** | Card-group selection, env variables (`HCCL_OP_EXPANSION_MODE=AIV`), proc-mem occupancy check; cgroup quota/weight/cpuset configuration with hierarchy/delegation/permission preflight | `ascend-device-health`, `cgroup-resource-controls` | Card-group change = contract change; all baselines must be re-measured on new group; identify the authorized owner before proposing changes | MindIE-SD dit-parallel-opt + perf-gate @ 8481d39b; kernel cgroup-v2 docs (pack-mediated) | 🟢 |
| **Configure** | Env-preflight: verify device availability, driver health, Python env before measurement | `performance-ceiling-analysis` (env-preflight references TRT-LLM exec-env-check) | TRT-LLM exec-env-check pattern | TRT-LLM @ f33e0e5f | 🟡 |
| **Optimize** | CPU affinity check-then-pin (accelerator-local NUMA node, cross-round consistency), NUMA placement mode semantics (distribute/isolate/numactl) with page-cache-drop and numa_balancing rules, generation-vs-batch thread/affinity splits, thread-count env discipline, device-busy preflight with graceful-to-force PID escalation, structured ERROR/WARNING env checks, container flags and ulimits; cgroup resource reallocation as capacity spend (quota/weight/headroom reviews gated on observed stalls) | [os-process-placement](../src/inferrsi/data/skill_library/hardware/host/os-process-placement/SKILL.md), `cgroup-resource-controls`; [llama.cpp owner map](../src/inferrsi/data/skill_library/repositories/llama-cpp/audit-llama-runtime-state/SKILL.md#choose-the-scope) | OMP_NUM_THREADS/PROC_BIND per scenario; `CPU_AFFINITY_CONF`; npu-smi usages preflight; `ASCEND_HOME_PATH` named-var correctness; rollback manifest before any change | TRT-LLM perf-host-optimization @ f33e0e5f; awesome-ascend-skills @ 75ec89c; ggml-org/llama.cpp @ `3e390af18de1131dda27913c00511725b4274c8a` (MIT; static inspection 2026-10-22 carried); kernel cgroup-v2 docs (pack-mediated); historical vllm-ascend Dockerfile/thread-env shipping defaults @ bc8115ed (Reference Matrix); ACLGraph @ 8a8e1e05ecb6 adds no OS-control evidence | 🟢 (isolcpus and scheduler priorities nice/ionice/SCHED_FIFO/RR remain unsourced) |
| **Verify** | Card health check sequence: npu-smi Health, 4-step smoke verify, proc-mem occupancy; cgroup change verification (matched windows, application metrics, counter deltas, provenance, rollback) | `ascend-device-health`, `cgroup-resource-controls` | Health=OK ≠ card usable; SIGKILL residual state only detectable via smoke run | MindIE-SD @ 8481d39b; kernel cgroup-v2 docs (pack-mediated) | 🟢 |
| **Diagnose / Configure** | CPU optimizer share, NUMA locality and per-rank garbage-collection stalls; training/helper lifetime in recovery | `training-resource-budget`, `checkpoint-recovery-consistency` | Gate CPUAdam cores to stage-3 super_offload; fallback saver lifetime matters | Reference CR1/CR6, C3; historical CR5 prerequisites only | 🟢 (no scheduling or privileged changes) |
| **Configure / Optimize** | FFCV OS-managed versus process-managed dataset caching | `training-input-pipeline` | Cache ownership is independent of nice/ionice/realtime scheduling | Reference B3 | 🟢 (configuration decision, not runtime result) |

**Second-level targets:** NPU driver, CANN runtime, container/process isolation

---

## Gap Summary

| Gap | Row | Priority | Next action |
|-----|-----|----------|-------------|
| Earlier six-paper foundation archive unavailable | Uncredited paper mechanisms | Input blocked | Supply the approved archive/readsets before importing ZeRO-Infinity, FlexGen, Sarathi-Serve, DistServe, PagedAttention or Mooncake paper candidates; do not substitute config/discovery evidence |
| Reviewed A–F qualification | Scoped Accelerator / Host / Network rows above | Separate future task | Candidates and author evidence do not establish runtime compatibility, measured gains or NPU support; no reproduction authorized |
| Save-path performance qualification (checkpoint) | SSD / Optimize + Verify | Low | DCP asynchronous staging, pinned-buffer reuse and completion gates are now sourced in `dcp-async-save-performance`; no local gains, NPU compatibility or backend durability verified. fastsafetensors-specific performance remains unsourced; no repeat mining authorized |
| Wave-7 input pipeline qualification | Accelerator / RAM / SSD / Network | Low | Mode-specific DALI behavior, FFCV current toolchain/distributed limits, Mosaic cache-churn and sample correctness remain unmeasured; no hardware run approved |
| Distributed recovery qualification | RAM / SSD / Network / Verify | Low | C3/C4 contracts extracted; replica transport, whole-state completeness, world-size changes and actual failure recovery remain unvalidated |
| Cross-resource applicability and historical evidence | Accelerator / RAM / OS | Low | DeepSpeed buffer_size units/dispatch outside inspected config; MindSpeed full pin/license/implementation/current compatibility unresolved; CR6 is expert methodology, not measured gains |
| OS/System isolcpus and scheduler priorities (nice / ionice / SCHED_FIFO / RR) | OS / Optimize | Low | cgroup v2 controls are now sourced (`cgroup-resource-controls`); the scheduler-priority class remains without a source and deferred |
| vLLM-RLT recurrent-depth KV finalization | Accelerator / KV correctness / Verify | Intake only; not coverage | `vllm_rlt` remains descriptor-only; canonical owner corrected. Follow the [bounded early-exit intake](reviews/issue91-vllm-rlt-intake.md) before extraction; tensor copying, written-position bookkeeping and device completion remain distinct, with no runtime qualification |
| AFD P2pNccl completion, graph and transport qualification | Accelerator / Communication / Verify | Candidate audit delivered; native qualification gap remains | [audit-afd-p2p-exchanges](../src/inferrsi/data/skill_library/repositories/afd-plugin/audit-afd-p2p-exchanges/SKILL.md) covers rank and peer/stage ownership at its pin. The `afd_plugin` runtime descriptor remains unverified; underlying completion, DBO/graph and physical/multi-host transport are unqualified. Historical [intake](reviews/issue91-afd-plugin-intake.md) retained; no new Network coverage |

**Resolved gaps since initial matrix (all high/medium priority cleared):**
- ~~Host overhead profiling + optimization skills~~ → `host-overhead-profiling`, `host-overhead-optimization` ✅
- ~~Parallelism strategy skill~~ → `ascend-distributed-parallel` ✅
- ~~NPU optimization casebook~~ → `ascend-optimization-casebook` ✅
- ~~SIGKILL / card-health recovery~~ → `ascend-device-health` ✅
- ~~Same-window A/B acceptance skill~~ → covered in `ascend-optimization-casebook` (per-case evidence schema) ✅
- ~~Kernel writing skill (Triton-Ascend / AscendC TileIR / CuTe)~~ → `kernel-writing-guide` ✅
- ~~Host memory lifecycle (pinned memory / GIL / H2D async)~~ → `host-memory-management` ✅
- ~~Operator-level tuning (pypto-op-perf-tune, AscendC tiling)~~ → `ascend-operator-tuning`, `ascendc-tiling-design` ✅
- ~~Serving-level weight loading / startup overhead~~ → `weight-loading-optimization` ✅
- ~~OS/System Optimize (CPU affinity, NUMA process placement, env discipline)~~ → `os-process-placement` ✅ (cgroups/scheduler priorities remain open, see gap table)
- ~~Disk-level loading mechanics (mmap/mlock/dio/lazy, pinned staging, parallel reads)~~ → `weight-loading-optimization` §6-7 ✅ (wave 5: llama.cpp, fastsafetensors)
- ~~Runtime KV-to-disk tiering~~ → `kv-tier-management` ✅ (wave 5: LMCache)
- ~~Load-path measurement protocol (SSD Verify)~~ → `weight-loading-optimization` §7 ✅ (wave 5: fastsafetensors)
- ~~Checkpoint save/restore semantics~~ → `weight-loading-optimization` §8 ✅ (wave 6: fastsafetensors saver, pack-approved scope)
- ~~Standalone block-device measurement methodology (fio-class)~~ → `storage-io-measurement` ✅ (wave 6: fio + sysstat pack)
- ~~DCP save-path performance mechanisms~~ → `dcp-async-save-performance` ✅ (wave 7; staging/pause/reuse/CPU-RAM-I/O trade-offs sourced, no measured gains)
- ~~cgroup v2 resource controls~~ → `cgroup-resource-controls` ✅ (wave 6: kernel docs pack)

---

## PR coverage table

Use this table in the PR description for `opus/meta-skill-bootstrap`.

| Search Space | Observe / Profile | Diagnose | Configure | Optimize | Verify |
|---|---|---|---|---|---|
| **Accelerator** | 🟢 `ascend-performance-analysis`, `ascend-operator-profiling`, `dense-performance-evidence`, `cann-attribution-overlap` (code_ref attribution), `diagnose-vllm-admission-pressure`, `audit-vllm-kv-lifetimes` (event-ledger requirement) | 🟢 `ascend-performance-analysis`, `performance-ceiling-analysis`, `cann-attribution-overlap`, `diagnose-vllm-admission-pressure`, `audit-vllm-kv-lifetimes`, `ascend-aclgraph-capture-replay`, `torchnpu-device-memory-lifecycle`, `audit-llama-runtime-state` (source candidate; native not run), `audit-sglang-diffusion-lifetimes` (source candidate; native not run) | 🟢 `ascend-graph-mode`, `ascend-model-adaptation`, `ascend-distributed-parallel`, `diagnose-vllm-admission-pressure`, `ascend-aclgraph-capture-replay`, `torchnpu-device-memory-lifecycle` (conditional proposals) | 🟢 `ascend-optimization-casebook`, `optimization-search-policy`, `kernel-writing-guide`, `ascend-operator-tuning`, `ascendc-tiling-design`, `cann-attribution-overlap` (bounded overlap), `diagnose-vllm-admission-pressure`, `ascend-aclgraph-capture-replay`, `torchnpu-device-memory-lifecycle` (unmeasured proposals) | 🟢 `dense-performance-evidence`, `rsi-evidence`, `claim-contract`, `cann-attribution-overlap` (overlap acceptance), `diagnose-vllm-admission-pressure`, `audit-vllm-kv-lifetimes`, `ascend-aclgraph-capture-replay`, `torchnpu-device-memory-lifecycle` (proposed checks), `audit-llama-runtime-state` (source candidate; native not run), `audit-sglang-diffusion-lifetimes` (source candidate; native not run) |
| **RAM / Host** | 🟢 `host-overhead-profiling`, `cgroup-resource-controls` (PSI/events) | 🟢 `host-overhead-profiling`, `torchnpu-pinned-host-memory-lifecycle`, `audit-llama-runtime-state` (source candidate; native not run), `audit-sglang-diffusion-lifetimes` (source candidate; native not run) | 🟢 `host-memory-management`, `kv-tier-management`, `cgroup-resource-controls` (memory limits), `torchnpu-pinned-host-memory-lifecycle` (version/path-gated) | 🟢 `host-overhead-optimization`, `kv-tier-management`, `torchnpu-pinned-host-memory-lifecycle` (unmeasured proposals) | 🟢 `cgroup-resource-controls` (verification contract), `dense-performance-evidence`, `torchnpu-pinned-host-memory-lifecycle` (proposed checks), `audit-llama-runtime-state` (source candidate; native not run), `audit-sglang-diffusion-lifetimes` (source candidate; native not run) |
| **SSD / Storage** | 🟢 `storage-io-measurement`, `dcp-async-save-performance` (phase boundaries) | 🟢 `weight-loading-optimization`, `storage-io-measurement`, `training-input-pipeline`; 🟡 startup incidental | 🟢 `training-input-pipeline`, `training-resource-budget`, `dcp-async-save-performance`, `checkpoint-recovery-consistency`; 🟡 FP8 loading | 🟢 `weight-loading-optimization`, `kv-tier-management`, `training-input-pipeline`, `training-resource-budget`, `dcp-async-save-performance` (gains unmeasured) | 🟢 `weight-loading-optimization`, `storage-io-measurement`, `dcp-async-save-performance`, `checkpoint-recovery-consistency` (procedures only) |
| **Communication** | 🟢 `ascend-performance-analysis` | 🟢 `ascend-performance-analysis`, `ascend-distributed-parallel`, `cann-attribution-overlap` (wait-aware) | 🟢 `ascend-distributed-parallel` | 🟢 `ascend-distributed-parallel`, `cann-attribution-overlap` (evidence-gated overlap) | 🟢 `ascend-distributed-parallel`, `ascend-performance-analysis`, `cann-attribution-overlap` |
| **OS / System** | 🟢 `ascend-operator-profiling` (DVFS), `ascend-device-health` (proc-mem), `cgroup-resource-controls` (cpu.stat/local) | 🟢 `ascend-device-health`, `ascend-performance-analysis`, `cgroup-resource-controls` (quota-vs-contention) | 🟢 `ascend-device-health`, `cgroup-resource-controls` (quota/weight/cpuset) | 🟢 `os-process-placement` (affinity/NUMA/threads/env), `cgroup-resource-controls` (capacity-spend reallocation) | 🟢 `ascend-device-health`, `cgroup-resource-controls` (verification contract) |

**Wave-7 additions to the coverage summary above:**

| Search Space | Observe / Profile | Diagnose | Configure | Optimize | Verify |
|---|---|---|---|---|---|
| Accelerator | `training-input-pipeline` | `training-resource-budget`, `dcp-async-save-performance` | `training-input-pipeline`, `training-resource-budget` | `training-input-pipeline`, `training-resource-budget` | No new device validation |
| RAM / Host | `training-input-pipeline`, `dcp-async-save-performance` | `training-input-pipeline`, `training-resource-budget` | All four wave-7 skills | Input/budget/DCP candidates | DCP lifetime + recovery contracts only |
| Communication / Network | `training-resource-budget` expert note | Expert collective diagnosis + recovery agreement | Remote input downloads + recovery replicas | Remote input predownload only | Expert measurement + recovery agreement procedures |
| OS / System | No new observation tool | `training-resource-budget`, `checkpoint-recovery-consistency` | Budget/locality/lifetime + FFCV cache ownership | FFCV cache ownership only | No new OS runtime validation |

**Reviewed-paper additions:** the individual rows in §§1, 2 and 4 bind each
mechanism to its named target and stage. A–F add no SSD or OS mechanism here.
E/F are methodology references only, and Magpie coordination remains pending;
none fills a Network cell. The summary tables immediately above retain the earlier
coverage as a baseline; the detailed rows in §§1, 2 and 4 include the paper additions.

**Skill-consumption integration:** Reference A1 → existing CLI metadata catalog,
explicit named instructions and on-demand resource-path resolution. This is a
cross-cutting consumption connection, not a new hardware performance cell or a
third authoritative matrix. Narrow offline checks do not promote skills.

**Optimization targets added in this branch:**
- Kernel profiling (CANN CSV pipeline, 5-layer analysis, operator-level msprof loop)
- Graph compilation (npugraph_ex capture-replay, FX passes, memory reuse)
- Model adapter (FP8, KV replication, multimodal)
- Distributed parallelism (USP/CP strategy, topology rules, masking formula, attribution)
- Host overhead (GPU idle / host-prep verdict, NVTX root-cause, line_profiler loop)
- Host memory (pinned memory, async H2D, GIL avoidance, NUMA allocation)
- Device health (topology validation, SIGKILL detection, 4-step smoke)
- NPU optimization casebook (5 bottleneck classes: AI-CPU fallback, memory-bound, comm-exposed, graph-compile, scheduling)
- Kernel writing (Triton/CuTe/AscendC routing, 6 correctness rules, verify-before-benchmark workflow)
- Search policy (phase-locked round, RRSI constraints, CRISP critical-step)
- Skill evolution (Trace2Skill pool consolidation, SkillOpt bounded edit)
- Benchmark design (goodput, three-regime, InferRSI evidence trail)
- Repository intelligence (LTC temporal split, Magpie patterns, Change2Task, Chronos)
- Operator tuning campaign (accuracy gate, staged escalation, metric contract, routing tables)
- AscendC tiling design (four-element template, fullload-vs-split, per-class routing, chip-generation tables)
- Weight load path and startup overhead (fixed-overhead accounting, sharded verification, prefetch rules, offload tiers)
- OS-level process placement (affinity pinning, NUMA mode semantics, thread env discipline, device-busy preflight, env checks)
- Loading modes and high-throughput loading (mmap/mlock/dio/lazy, bounce-buffer readers, GDS direct reads, readiness overlap, static fit planner, phase-timer measurement)
- KV cache tiering (L1/L2 hierarchy, store/retain/prefetch/evict policies, concurrency-vs-RAM admission, local adapters, serde)
- Checkpoint save/restore semantics (sync sharded writes, per-file atomic publish, opt-in fsync, explicit unsupported list)
- Storage I/O measurement (workload matching, requested-vs-achieved depth, cache-state ledger, device/process attribution, saturation guards, two-layer evidence gate)
- Cgroup v2 resource controls (quota-vs-contention, requested/effective cpuset, memory pressure+events, io caps, delegation preflight, rollback contract)
- CANN attribution and overlap (code_ref ownership, dependency DAG, bounded multistream, metric separation, lineage discipline)

- Training input pipelines (executor-gated queue/buffer sizing, bounded sample look-ahead, shard cache churn, OS/process cache ownership)
- Checkpoint recovery consistency (readiness/step gates, complete iteration selection, helper/replica failure domains)
- Cross-resource training budgets (ZeRO offload constraints, attributed compute/collective/NUMA/GC diagnosis, historical NPU adaptive-memory case)
- DCP asynchronous save performance (caller pause, staging/upload distinction, cache reuse, bounded in-flight saves and contention)

- vLLM admission and KV lifetime diagnosis (independent budgets, async readiness, completion/retention/failure ownership; concrete backend unverified)
- vLLM-Ascend ACLGraph runtime (effective dispatch, caller-owned replay buffers, branch-specific ordering and capture-resource proposals)
- TorchNPU device/host allocator lifecycles (separate memory domains/counters, stream-use versus ordering, feature gates and unresolved conflicts)

**Skill count:** 36 branch-added candidate skills + 5 inherited skills = 41 skill directories. All branch-added skills remain `status: candidate`; inherited skills retain their original metadata. None promoted.

The five wave-8 additions are Dot bundle-mediated code/docs intelligence, not
paper extraction or measured gains. Their source pins are independent; no
combined stack compatibility is established. No new SSD, Network or OS-priority
coverage is claimed; device HBM remains separate from host RAM.


## RFC 17: existing main knowledge mapped to resources

These are locally inspected **existing imported records**, not new skills or
new measured effectiveness. The [Reference Matrix reconciliation](reference-matrix.md#rfc-17-reconciliation-inspected-main-corpus)
links their exact IDs/pins/readsets and the [ownership contract](knowledge-base.md).
The five resource rows above remain authoritative; no new coverage is credited
for translation, filename, package installation or an unexamined trace.

| Resource | Stage / named subtargets | Existing canonical support | Boundary |
|---|---|---|---|
| Accelerator | Diagnose/Configure/Verify: attention-generation dispatch, paged-decode planning, compiler guards, KV strategies, fusion resource limits | [Dependency records](../src/inferrsi/data/knowledge_packs/README.md); FlashAttention, FlashInfer, PyTorch, Transformers, Triton | Source guidance only; selected backend, pointer lifetime, precision and resource envelope require target validation |
| Accelerator | Configure/Optimize/Verify: residual reuse, KV compression, sequence partition and pipeline freshness | [Peer records](../src/inferrsi/data/knowledge_packs/README.md); Cache-DiT, LMDeploy, xDiT | Approximation/capacity gains do not establish latency or quality gains; preserved LMDeploy regression |
| RAM / Host | Diagnose/Configure: group offload staging, CPU expert work, host prefix residency | Diffusers dependency card; [Strata tuning](../src/inferrsi/data/repo_packs/strata/knowledge/common/llm/controlled-execution-tuning.json); SGLang HiCache peer card | Host budget and transfer/recompute cost remain distinct from device HBM |
| SSD / Storage | Configure/Verify: prefix L3 sharing, prefetch/layout/eviction and hit-state comparisons | [SGLang HiCache](../src/inferrsi/data/knowledge_packs/peer/sglang/cuda/llm/hierarchical-prefix-cache.json) | Storage backend qualification pending; larger private host cache is not cross-instance sharing |
| Communication / Network | Diagnose/Configure/Verify: disaggregated KV transfer, topology-dependent sequence parallelism | [TRT-LLM disaggregation](../src/inferrsi/data/knowledge_packs/peer/tensorrt_llm/cuda/llm/prefill-decode-disaggregation.json); [xDiT](../src/inferrsi/data/knowledge_packs/peer/xdit/cuda/diffusion/parallelism-freshness-and-topology.json) | Interconnect/layout/queue cost, backpressure and recovery; H2D/IPC are not counted here |
| OS / System | No new OS-control mechanism credited | Existing OS-specific rows retained | Process/stage ownership and installed access are not scheduler-priority or cgroup evidence |
| Accelerator / Host | Observe/Verify: actual active batch, admission/drain scope and state lifetime | [Shared internal case](../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/admission-drain-occupancy.md); [main audio guidance](../src/inferrsi/data/repo_packs/vllm_omni/knowledge/cuda/audio/concurrency-scaling-state-and-overlap.json) | Recorded observation versus interpretation; frozen evidence preserved, no new service gain |

The existing casebook/search-policy path now also exposes rejected directions
for [Qwen B300](../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/qwen-b300-rejected-directions.md),
[Qwen Ascend](../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/qwen-ascend-rejected-directions.md)
and [Drama3](../src/inferrsi/data/skill_library/methods/inference-optimization-casebook/cases/drama3-rejected-directions.md).
They inform Observe/Diagnose/Verify under their recorded Accelerator/Host scope;
no new green coverage, Network/OS capability or measured gain is credited.
Current applicability and a changed condition must be established before retry.

The 15 contribution abstracts for Strata, vLLM, SGLang, SGLang-Omni and vLLM-Omni
supply scoped architecture, tuning and validation navigation, including their
English procedures. They do not qualify every backend listed by their upstream
projects. Main-only contribution, dependency and peer material remains at its
original owners rather than duplicated under local skills.

## Issue #27: Drama3 NPU readiness (guidance only, no new coverage)

The [Drama3 NPU readiness supplement](drama3-npu-readiness.md) is a scoped task
artifact: a stage/state execution map, a state-correctness contract (with a
CPU-only reference fixture) and a measurement/quality contract reusing the pinned
GPU `benchmark.py` and only the `load_runtime` record/summary checks of the frozen
`evidence/drama3-b300-scale150` validator; a target plan/verdict remains a gap. It
adds **no 🟢 cell and no measured NPU coverage**; every Drama3 NPU status is
`unverified`, and target qualification is pending the owner-resolved
hardware/software/model/service/evaluation/authority tuple. The five resource
rows above remain authoritative; the two-matrix contract is unchanged.

## MLX framework guidance (source-derived)

| Resource | Stage / named mechanism | Canonical owner | Evidence boundary |
|---|---|---|---|
| Accelerator | Observe / Diagnose / Verify: submission versus completion, fence/event dependency ordering and selected backend dispatch | [lazy-evaluation-stream-lifetimes](../src/inferrsi/data/skill_library/frameworks/mlx/lazy-evaluation-stream-lifetimes/SKILL.md) | Pinned CPU/Metal/CUDA source paths; no native device execution or measured gain |
| RAM / Host | Observe / Diagnose / Verify: graph-reference detachment versus in-flight Data retention and result availability | [execution/lifetime contract](../src/inferrsi/data/skill_library/frameworks/mlx/lazy-evaluation-stream-lifetimes/references/execution-lifetime.md) | Backend-specific retention mechanisms; allocator eviction and physical-memory release remain outside the readset |

No new measured or green coverage is credited. Stream dependency guidance does
not add a Communication/Network capability; no SSD or OS control is introduced.
`common` indexing categorizes framework guidance and certifies no backend.

## vLLM-Omni incremental abort guidance

| Resource | Stage / named mechanism | Canonical owner | Evidence boundary |
|---|---|---|---|
| Accelerator / RAM / Host | Diagnose / Verify: abort submission, logical acknowledgment, partial AR output and separately queued transfer reclamation | [Abort acknowledgment reference](../src/inferrsi/data/skill_library/repositories/vllm-omni/sub-skills/omni-validation/references/abort-acknowledgment.md) under the existing validation skill | Source control-flow and queue ownership, not native device synchronization or measured release completion |
| RAM / Host | Observe / Diagnose / Verify: correlated waiter lifetime, blocking submission, wait-only timeout and late result routing | Same canonical reference, source `18c3bd5d2d4323bc7adca1ac3c465c4a53bbfb6e` | Queue timeout does not certify engine cancellation; actual API/backend/next-request validation not_run |

These extend source-derived guidance without a new measured/green cell. No new
SSD, Network or OS-control coverage is credited by local RPC or release-task code.

## MLX-LM application guidance (source-derived)

| Resource | Stage / named mechanism | Canonical owner | Evidence boundary |
|---|---|---|---|
| RAM / Host | Observe / Diagnose / Configure / Verify: request UID/stage/cache-row alignment, prefix identity/copy/trim/eviction and cooperative stop | [generation-cache-lifecycle](../src/inferrsi/data/skill_library/repositories/mlx-lm/generation-cache-lifecycle/SKILL.md) | Logical cache state and allocated storage differ; native model/row/stop behavior unrun |
| Accelerator | Observe / Diagnose / Verify: prefill cache evaluation and asynchronous decode submission/read boundary | [generation/batch contract](../src/inferrsi/data/skill_library/repositories/mlx-lm/generation-cache-lifecycle/references/generation-batch.md) | Application calls MLX primitives; CPU checks cannot certify Metal/CUDA dispatch, quality or serving performance |

No measured or green coverage is credited. Application batching is not a new
Network/OS capability; no SSD mechanism is added. `common` indexes guidance and
does not certify backend compatibility.

## Diffusers invocation guidance (source-derived)

| Resource | Stage / named mechanism | Canonical owner | Evidence boundary |
|---|---|---|---|
| RAM / Host | Observe / Diagnose / Configure / Verify: wrapper versus reused component identity, per-invocation scheduler schedule/index ownership | [diffusers-invocation-state](../src/inferrsi/data/skill_library/frameworks/diffusers/diffusers-invocation-state/SKILL.md) | Configuration means selecting the existing invocation/scheduler owner; no new manager. Real caller admission and runtime overlap are unverified. |
| Accelerator | Observe / Diagnose / Verify: post-step callback, next-iteration interrupt observation and normal output/cleanup tail | [invocation ownership path](../src/inferrsi/data/skill_library/frameworks/diffusers/diffusers-invocation-state/references/ownership.md) | Cooperative loop skipping does not revoke submitted kernels; model/device/quality, exception cleanup and performance remain unrun. |

No measured or green coverage is credited. This adds no SSD, Network or OS
capability and does not retest the existing offload mechanism. `common` indexes
framework guidance without certifying backend compatibility.

## DeepInfer bounded source guidance

| Resource | Stage / named mechanism | Canonical owner | Evidence boundary |
|---|---|---|---|
| Accelerator | Diagnose / Configure / Verify: configured-width DFlash drafts versus budgeted verification rows; lagged CPU totals and GPU ZOS per-request metadata correction | [budget-speculative-verification](../src/inferrsi/data/skill_library/repositories/deepinfer/budget-speculative-verification/SKILL.md) | Source constraints and cost objective, not sampling-distribution proof, dispatch qualification or measured gain |
| Accelerator / RAM / Host | Diagnose / Configure / Verify: retained query dependency closure, separately preserved full-layout KV, SWA valid-state bounds and nested ring-sizing gates | [bound-windowed-attention-replay](../src/inferrsi/data/skill_library/repositories/deepinfer/bound-windowed-attention-replay/SKILL.md) | Model-specific boundary/rollback/cache contract; native equivalence and resource measurements unrun |
| RAM / Host | Observe / Diagnose / Verify: host work overlap, one-step retained state, repair and drain obligations | [Existing host-overhead owner case](../src/inferrsi/data/skill_library/hardware/host/host-overhead-optimization/references/deepinfer-zero-overhead-scheduling.md) | Source-level schedule, no reproduced host-gap reduction or complete-service latency result |

These rows add source-derived procedure guidance; native execution and measured
gains remain unverified. They do not add measured resource coverage:
local host scheduling and source references to collectives do not establish new
SSD, Network or OS-control coverage. Backend and production-service scope remain
separate from the public release's inspected code paths.

## Task-specific evaluation coverage (issue #60)

| Resource | Stage / named mechanism | Canonical owner | Evidence boundary |
| --- | --- | --- | --- |
| Accelerator / Host / service boundary | Observe / Verify: select task quality and reference parity; freeze workload, timing, SLOs, units and failure accounting; distinguish agent replay from live task success | [inference-benchmark-design task reference](../src/inferrsi/data/skill_library/methods/inference-benchmark-design/references/task-benchmark-selection.md) and [commands](../src/inferrsi/data/skill_library/methods/inference-benchmark-design/references/benchmark-commands.md) | Cross-task measurement guidance, not new measured hardware coverage. A text HTTP smoke cannot validate TTS, duplex, image/video quality, repeated A/B or production capacity. No runtime adapter or automatic evaluator is added. |

## SGLang scope selection

Use the [versioned entry comparison](../src/inferrsi/data/skill_library/repositories/sglang/SKILL.md#choose-among-source-pins)
to distinguish LLM engine/Radix ownership, the separate CUDA HiCache peer's
prefix-KV host/storage policy, and multimodal_gen diffusion stage/instance,
component-use and timeout/job-finalizer lifetimes. This adds routing only.
Common indexing is not CUDA/NPU qualification; process transport/IPC is not new
Network coverage. Existing resource cells and maturity boundaries remain unchanged.
