# Training memory and scheduling: incremental mechanisms

Status: candidate; empirical_validation: not_run. F = pinned-source fact/model/measurement; P = proposed procedure. This is paper-derived planning, not a tested recipe. [Pins, exact readset, metrics and caveats](../references/source-readset.md). The labels ZO/CM/OL/AL/ZB refer to the five source entries there.

## P: Joint decision boundary

Start with the existing ZeRO-Infinity offload notes (prior archive `omnirsi-paper-intelligence-2026-10-15.zip`, semantic path `notes/offload.md`) and training-offload procedure (prior archive `omnirsi-paper-intelligence-2026-10-15.zip`, semantic path `diagnose-training-offload/SKILL.md`). They already cover tensor-class/tier accounting, retrieval pipelines, tiling, initialization and nonlocal ownership. This pack adds a decision among changing optimizer residency, tensor lifetimes, recomputation, operator partitions and fine-grained execution order. None of these papers supplies one globally optimal solver for all five choices together.

Use one phase-aware capacity/critical-path record: model states; live activations and gradients; operator/workspace peaks; simultaneous transfer buffers; host/device capacity; shape/batch/precision; dependency graph; CPU, accelerator, transfer and collective time. Distinguish useful synchronous-step completion from modeled FLOPs or reduced idle fraction. A memory-saving candidate is valuable only if the remaining compute/transfer schedule remains feasible. Do not add separately reported speedups or memory-saving percentages.

Activation checkpointing is rematerialization within training, not persistent restart/recovery checkpointing. H2D/D2H and same-host IPC are not Network; inter-node transfers and collectives may be. No NPU kernel, collective, compiler or asynchronous-execution compatibility has been established.

## ZO1. Move the optimizer computation with its state

- F, objective/assumptions: ZO §§3.1–3.5 seek maximal model-state relief at minimal host/device traffic while excluding compute-heavy CPU forward/backward work. Model: mixed-precision Adam, known parameter count, relatively slow CPU and PCIe; activation offload excluded.
- F, variables/constraints/mechanism: choose placement of data/compute graph nodes; colocate FP32 master weights/moments and update/cast on CPU, keep FP16 weights and F/B on GPU, stream gradients to CPU. Whole-state graph-cut minimum is 4M bytes/iteration in the restricted model. §4.2 first shards gradients/optimizer ownership, then offloads; CPU work and traffic are not duplicated by every data-parallel rank.
- F, benefit/cost/evidence: Table 4's CPU-Adam reduces CPU update latency; Fig. 8 reports 14% average TFLOP/s gain over L2L with matched batch and no DPU. CPU memory bandwidth, thread contention, transfer and updated-weight collective remain costs.
- F, limits/counter-signals: Table 1 has inconsistent memory accounting; the optimality claim excludes activations, different optimizers and partial heterogeneous plans. Fig. 11 shows ZeRO-2 overtaking offload at 64/128 GPUs once capacity no longer forces smaller batches.
- P, rule: extend the existing offload diagnosis with an ownership-and-compute ledger. Compare CPU-update-plus-return against GPU-update-plus-state-transfer under the actual optimizer. Prefer an offload-free candidate when both fit and exposed transfer dominates; never infer benefit from CPU capacity alone.

## ZO2. Optimize CPU update and copy as one pipeline

- F, objective/assumptions: ZO §5.1 accelerates O(M) updates where CPU work or weight return delays GPU progress; assumes vectorizable Adam and usable host memory bandwidth.
- F, variables/constraints/mechanism: SIMD width, loop unroll, threads, tile size; fuse vector arithmetic and pipeline tile updates with prior-tile H2D parameter copy. Historical AVX512 and unroll 8 are implementation choices, not portable constants.
- F, benefit/cost/evidence: Table 4 gives 0.22 vs 1.39 s at 1B parameters and 2.57 vs 14.76 s at 10B for CPU-Adam vs PyTorch CPU; GPU Adam is still faster. Tiling/threads/copies can compete for memory bandwidth; isolated component ablations are unreported.
- F, limits/counter-signals: host saturation and small GPU compute windows; adding threads does not create bandwidth. Historical CPU improvements do not establish present optimizer speed.
- P, rule: use supplied per-stage CPU/transfer evidence to identify whether optimizing update, return copy, or neither could affect the step critical path. Keep bounded buffers and pinned-memory accounting from the existing skill; do not prescribe ISA/thread counts from the paper.

## ZO3. Delayed update is a separate training-semantics branch

- F, objective/assumptions: ZO §5.2 hides CPU optimizer work at small batch by allowing one-step staleness after a stable warmup.
- F, variables/constraints/mechanism: DPU start iteration and delayed-gradient schedule; one iteration skips update, then CPU updates overlap next GPU F/B using older parameters.
- F, benefit/cost/evidence: §6.2.4/Fig. 9 reports 1.12–1.59× throughput at microbatch 8. Figs. 12–13 check GPT-2 loss and BERT-large/SQuAD F1 92.8, with DPU after 40 iterations.
- F, limits/counter-signals: training dynamics change; the GPT loss initially lags. Two workloads do not bound behavior for other optimizers/models, nor prove a universal warmup length.
- P, rule: do not silently include DPU in an exact-execution offload plan. Mark it a separate consequential proposal requiring explicit acceptance of changed training semantics and representative quality/convergence evidence. Prefer ordinary overlap if exact updates are required.

## CM1. Pay recomputation cost selectively under event-level memory limits

- F, objective/assumptions: CM §§4.1–4.10 minimize summed operator-evaluation cost for a static known-size DAG with deterministic/replayable operations and supplied cost estimates.
- F, variables/constraints/mechanism: binary compute R and retention S, FREE and U memory variables; ensure every dependency exists, compute each frontier, and count newly allocated output before freeing consumed inputs. Retain valuable values and rematerialize others. Inputs/parameters and a gradient reserve remain resident. A fixed frontier order bounds the search.
- F, benefit/cost/evidence: §6.3/Fig. 5's U-Net/16-GB profile model improves modeled time 1.20× over linearized greedy; recomputation spends extra compute to avoid memory/transfer pressure. §6.4's 5.1× MobileNet batch-capacity ratio is model-based with a one-extra-forward FLOP constraint.
- F, limits/counter-signals: no joint transfer/parallelism objective; additive layer cost can miss kernel fusion, concurrency and workspace behavior. Stateful/random operations and changed batches need correctness review. A timeout is not infeasibility proof.
- P, rule: compare a selective-rematerialization candidate to retention/offload using supplied costs and lifetime peaks; favor discarding values with low recomputation cost relative to sustained resident burden, while preserving all dependencies. Validate candidate peak memory and equivalent numerical semantics before claiming feasibility.

## CM2. Approximation quality and memory feasibility are different checks

- F, objective/assumptions: CM §5 seeks practical schedules when the exact MILP is costly.
- F, variables/constraints/mechanism: relax integrality, round only retention S, reconstruct minimally necessary R to repair dependency constraints, then derive releases. Their 10% budget allowance is empirical; rounding itself does not enforce the capacity cap.
- F, benefit/cost/evidence: §6.5/Table 2's geometric-mean FLOP-cost ratios are 1.00–1.06 across mutually feasible budgets, not a worst-case guarantee. Appendix D shows the allowance can waste capacity. DenseNet161 lacked a feasible ILP result within one day (§5).
- F, limits/counter-signals: computational validity can coexist with OOM; input-specific rounding margin and planning overhead matter.
- P, rule: treat an approximate schedule as a proposal until both dependency replay and exact peak-accounting pass. Record solver status, feasible incumbent, bound/gap and amortization separately; do not report near-optimal compute as memory-safe execution.

## OL1. Shorten live ranges before buying more capacity

- F, objective/assumptions: OL §§2–3 minimize memory of a static DAG without deleting/recomputing values. Tensor sizes and all dependencies must be represented.
- F, variables/constraints/mechanism: creation/preservation times select a legal topological order; exactly one tensor creation, shared-consumer lifetimes and multi-output creation are explicit. Reorder eligible work, including safe early weight updates, so large gradients need not remain live unnecessarily. §4.3 adds precedence controls to limit the search.
- F, benefit/cost/evidence: §5.3 measures requested-memory reduction excluding fragmentation: mean 22.5% at batch 1 and 10.1% at batch 32 versus PyTorch 1.11 ordering. No extra recomputation or offload traffic is introduced by the mechanism, but planning and changed execution concurrency can cost time.
- F, limits/counter-signals: activations retained for backward give little forward-pass leverage; large batches reduce gradient-relative savings. Distributed accumulation, global clipping, tied state and shared weights can restrict early updates; the paper does not establish those integrations.
- P, rule: investigate excessive live gradients/outputs before offload. Propose only reorderings proven legal by the full graph, including update/collective barriers. If activations dominate a largely linear order, route to selective rematerialization rather than promise OLLA's average saving.

## OL2. Pack nonoverlapping lifetimes into reusable addresses

- F, objective/assumptions: OL §§3.3–3.5 minimize reserved address extent given predictable tensor lifetimes; location means addresses in one memory space.
- F, variables/constraints/mechanism: integer base addresses and pairwise nonoverlap for simultaneously live tensors; reuse addresses across disjoint lifetimes. §4 bounds lifetimes, removes provably unnecessary pair constraints, splits ordering/packing, and preplaces nested activations. A preallocated buffer makes deallocation a no-op.
- F, benefit/cost/evidence: §5.4 removes measured fragmentation in evaluated cases; baseline ratios average 7.9%/26.1% at batch 1/32. §5.7 combined peak reduction is 30.4%/36.1% with two five-minute search caps. The estimated runtime saving is not direct end-to-end timing.
- F, limits/counter-signals: empirical fragmentation elimination does not prove all orderings can pack without loss. Dynamic shapes, overlapping executions, alignment/workspace and aliasing can invalidate fixed addresses. Low fragmentation means less scope.
- P, rule: separate live-byte excess from reserved-byte fragmentation, using the same phase/denominator. Propose address planning only when allocation/lifetime evidence is stable; do not misroute this mechanism as CPU/SSD placement or kernel-VM tuning.

## AL1. Choose operator shards and pipeline stages together, within a declared search space

- F, objective/assumptions: AL §§4–5 minimize pipeline latency for static shapes, homogeneous devices inside each logical mesh, a supplied operator order and synchronous 1F1B-style timing.
- F, variables/constraints/mechanism: select operator shardings/resharding edges; then stage boundaries and physical/logical meshes, using stage cost and memory feasibility. Eq. 5 retains multiple in-flight activation sets. Objective includes first-microbatch latency and bottleneck-stage repetition. Operator clustering/pruning reduce planning cost.
- F, benefit/cost/evidence: §8.3/Fig. 9: Wide-ResNet/32-GPU plan outperforms equal-operator/equal-layer restrictions 2.6×/1.6× in PFLOP/s. Fig. 12 uses unequal 4/4/8-GPU stages. Planning costs are material (Table 5: 2393.26 s for one GPT-39B search).
- F, limits/counter-signals: intra-op compute costs are simplified to zero; stage costs include a profiling/modeling path. Inter-stage transfer and overlap are omitted from the optimizer; microbatch count is external; no global optimum over all plans. Equal-layer is already as good on the tested homogeneous GPT case.
- P, rule: consider changing parallel plans when memory/work differs markedly by stage or collective cost dominates. Compare the proposed heterogeneous plan to a simple equal-stage baseline under fixed global batch, actual topology and explicit cross-stage-transfer cost. Report omitted costs and plan-generation amortization rather than adopting solver output uncritically.

## AL2. Avoid repeated slow-link copies during resharding

- F, objective/assumptions: AL §6 reduces communication between unequal meshes when receivers need replicated tiles and local bandwidth is better than cross-mesh bandwidth.
- F, variables/constraints/mechanism: tile source/destination correspondence, unique cross-mesh sends, local allgather; ensure all target shardings receive correct elements. Static per-mesh instructions coordinate execution.
- F, benefit/cost/evidence: §8.5/Fig. 11 reports 2.0× PFLOP/s throughput over send/recv-only for 32-GPU Wide-ResNet. Local collectives/staging replace duplicate slow-link traffic; they are not free.
- F, limits/counter-signals: topology may not provide the assumed asymmetry; optimal many-to-many mapping is not solved. One-byte signal baseline is only an upper-bound control.
- P, rule: derive actual required tensor intersections and replication before proposing multicast-like staging. Classify local allgather under Accelerator topology and only the cross-node segment under Network. Reject byte savings that overload local links or increase peak buffers beyond the common ledger.

## ZB1. Split critical input-gradient work from deferrable weight-gradient work

- F, objective/assumptions: ZB §§1–3 reduce synchronous pipeline idle time while respecting activation limits, dependencies and measured F/B/W/communication times.
- F, variables/constraints/mechanism: execution order/end times for F, B and W; prioritize B needed by the previous stage, schedule W in gaps or to reclaim memory. Delaying W extends retention of its inputs. The heuristic searches under memory caps; limited-scale ILP provides another route.
- F, benefit/cost/evidence: Table 4's 28.3B/32-GPU/m96 row gives 0.87 versus 0.76 samples/s/GPU for ZB-1p vs 1F1B at 44 vs 43 GB. ZB-2p reaches 0.99 at 74 GB. Table 5's lower bubble rates are calculated from timing inputs; Fig. 6 shows extra real gaps.
- F, limits/counter-signals: equal F/B/W theory does not match actual kernels; fused backward splitting may add overhead; memory is not free. Appendix A's tail parameter grouping for DP overlap has no isolated measured ablation.
- P, rule: require a trace or supplied equivalent showing B blocked behind deferrable W. Propose split schedules only with measured pass costs, retained-byte lifetimes and collective ordering. A smaller bubble fraction alone is not higher useful-step throughput.

## ZB2. Compare memory-equivalent schedule/microbatch choices

- F, objective/assumptions: ZB §§5.4–6 trade bubble reduction against activation memory and microbatch kernel efficiency.
- F, variables/constraints/mechanism: activation cap, microbatch size/count, two-chunk V placement. ZB-V starts F/B locally sooner and balances memory; its ideal zero-bubble claim assumes equal pass times. ZB-2p* trades half-size microbatches for twice their count at fixed global batch.
- F, benefit/cost/evidence: Table 6's 28.3B/32-GPU/base b2,m96: V 1.01 at 71 GB, 2p* 1.00 at 72, 1F1B 0.82 at 69 samples/s/GPU. At 6.2B, 2p* instead beats V. Extra boundaries/communication and smaller kernels can offset reduced idle time.
- F, limits/counter-signals: theoretical pMB is activation memory, not total HBM. Tables 7 and 11 change global batch, and Table 11 has ambiguous m labels; do not use them as matched-global-batch proof. Performance can plateau before exact zero bubbles.
- P, rule: compare a small set at the same global batch, precision, model and total-device-memory margin. Include simpler 1F1B, memory-capped split backward, and V/2p* only when legal. Choose useful throughput over the lowest modeled idle fraction.

## ZB3. Preserve optimizer validation when removing its global barrier

- F, objective/assumptions: ZB §4 removes an optimizer synchronization bubble assuming numerical exceptions/clipping are uncommon and updates can be validated and repaired.
- F, variables/constraints/mechanism: partial global-state reduction, tentative update, later complete validation, rollback/re-update where required. Appendix C supplies an in-place AdamW inverse to avoid state copies; no stale-gradient semantics are intended.
- F, benefit/cost/evidence: Appendix E/Table 10: 28.3B/32 GPUs/m96 post-validation 0.99 versus synchronized 0.91 samples/s/GPU. Author per-iteration fixed-seed loss checks are bit-identical for tested schedules, not a broad rollback-stress or convergence study. Rollbacks cost work and can perturb scheduling.
- F, limits/counter-signals: frequent clipping/NaNs, noninvertible updates, finite-precision reversibility, stateful side effects, or unverified rollback coverage undermine the benefit/correctness. Failure-rate sensitivity and broad optimizer support are unreported.
- P, rule: treat barrier removal as a separate correctness gate. Retain global clipping/NaN semantics and require evidence of rollback, redo and dependent-work handling on the actual optimizer before proposing enablement. When absent, keep the synchronized fallback. Do not confuse this post-validation with ZeRO-Offload DPU.

## Candidate destinations

- [Activation-residency skill](../../../../plan-activation-residency/SKILL.md): CM1–CM2 and OL1–OL2 share one live-range/retain/recompute decision, with separate capacity and correctness checks.
- [Parallel-plan skill](../../../../choose-parallel-training-plan/SKILL.md): AL1–AL2 share one partition, mapping and resharding decision.
- [Split-backward skill](../../../../assess-split-backward-schedule/SKILL.md): ZB1–ZB3 share a pipeline schedule, memory and optimizer-semantics decision.
- ZO1–ZO3 are an [incremental knowledge extension](../knowledge/offload-delta.md) to the existing offload skill, avoiding a duplicate skill.
- [Cases](../cases/paper-grounded-cases.md) are review examples, not executed tests. [Integration proposals](../INTEGRATION_NOTES.md) target only docs/reference-matrix.md and docs/searchspace-matrix.md.
