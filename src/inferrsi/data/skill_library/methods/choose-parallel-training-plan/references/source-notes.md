# Parallel-plan evidence and mechanism reference

Status: candidate; empirical_validation: not_run. F = historical source fact/model/result; P = unvalidated application. This file is self-contained when the skill folder is copied alone. It includes its original paper links, readset, numerical evidence, limitations and full mechanism cards. No current engine or NPU compatibility is established. Activation checkpoints refer to within-training rematerialization, not persistent recovery checkpoints.

## AL: Alpa

- Full title: Alpa: Automating Inter- and Intra-Operator Parallelism for Distributed Deep Learning. Lianmin Zheng, Zhuohan Li, Hao Zhang, Yonghao Zhuang, Zhifeng Chen, Yanping Huang, Yida Wang, Yuanzhong Xu, Danyang Zhuo, Eric P. Xing, Joseph E. Gonzalez, Ion Stoica.
- [Original metadata](https://arxiv.org/abs/2201.12023), [pinned v3 PDF](https://arxiv.org/pdf/2201.12023v3). v1 2022-01-28; v2 2022-06-03; read v3 2022-06-28 19:36:44 UTC. 20 PDF pages. A v1 PDF was fetched before metadata resolution but not used as evidence.
- Actual relevant readset: §§2–8.6 including every method, limitation and evaluation subsection; Eqs. 1–6, Algorithm 1, Tables 1–5, Figs. 1–12 and associated prose; Appendix A/Theorem 1/Eq. 7, Appendix B/Tables 6–8, Appendix C/Fig. 13. Visually checked PDF p. 13/Table 5/Figs. 10–11.
- SHA256: cd1dea70769571a5e9298ba0610e04cc514a06ab12018dd7f19a457fd00cd474.

F, model and evidence:
- §4/Eq. 1: choose one sharding algorithm per operator on a homogeneous 2-D logical device mesh, accounting for operator communication and edge resharding. The evaluated ILP estimates bytes/bandwidth and sets compute costs dv to zero, assuming equal arithmetic work among heavy-op shardings and negligible lightweight work. It does not show all equal-FLOP kernels run equally fast. Post-ILP reduce-scatter/allgather can reduce replicated optimizer work without changing total collective bytes.
- §5/Eqs. 2–5: stages are contiguous in a given operator ordering; corresponding forward/backward ops colocate. Objective sum(stage latency)+(B−1)×max(stage latency) for the chosen static GPipe/1F1B timing model. DP chooses stage boundaries and restricted physical submesh shapes; intra-op choices are evaluated per stage/mesh. 1F1B feasibility uses memstage+s×memact≤memdevice. Infeasible stage/mesh pairs get infinite cost. Shape restriction ensures device coverage, not global-optimal search over arbitrary partitions.
- §5.2 says compile/profile stage plans including fusion and memory planning; §8.4 describes accelerating profiling with a piecewise-linear XLA-operation cost model. Do not present all plan costs as directly timed full stages. Search also clusters operators and prunes DP choices.
- §6/Fig. 6: cross-mesh resharding sends each needed tile across slow links then locally allgathers replicated destinations, avoiding redundant slow transfers. Static per-mesh instruction lists avoid continuous driver coordination. Optimal cross-mesh resharding is left to future work.
- §7: no inter-stage communication cost in the plan objective; microbatch count is an external hyperparameter, not internally optimized; static shapes/graphs and linear schedules; no optimization of computation/communication overlap. Two-level solution is not guaranteed globally optimal.
- §8: eight AWS p3.16xlarge nodes, eight V100 16-GB GPUs/node, intra-node NVLink, 25-Gbps cross-node bandwidth; 64 vCPU and 488-GB host memory/node. Metric is aggregate PFLOP/s on warmed-up dummy-data batches; model size grows with GPU count (weak scaling). Global batches: GPT and MoE 1024/FP16; Wide-ResNet 1536/FP32. GPT/MoE sequence 1024; image input 224×224×3. Microbatch tuned per configuration.
- §8.1/Fig. 7: GPT roughly matches grid-searched Megatron-LM v2; MoE beats DeepSpeed 3.5× on 16 GPUs (10B model) and 9.7× on 32 GPUs (27B), where the historical DeepSpeed baseline has no inter-op pipeline and slow network communication dominates. Wide-ResNet achieves author-reported 80% linear-scaling efficiency on 32 GPUs. These are not time-to-quality or equal-model strong-scaling results.
- §8.2/Fig. 8: isolate intra-op search on one eight-GPU node, disabling pipeline and gradient accumulation, with altered model shapes/batches versus §8.1. ILP is compared with data parallel, ZeRO-2/3 and largest-axis sharding heuristic. It cannot be merged numerically with the end-to-end setup.
- §8.3/Fig. 9: at 32 GPUs, Wide-ResNet DP plan is 2.6×/1.6× faster in PFLOP/s than equal-operator/equal-layer restrictions; equal-layer equals DP on homogeneous GPT. §8.5/Fig. 11: local-allgather resharding gives 2.0× throughput over send/recv-only on 32-GPU Wide-ResNet. One-byte signal control is a synthetic upper bound, not executable model semantics.
- §8.4/Table 5: GPT-39B/64-GPU compilation 1582.66 s, profiling 804.48 s, stage DP 1.65 s, other 4.47 s, total 2393.26 s versus >40 h without optimizations. This is one supplied microbatch-count run, not cost of searching all B.
- §8.6/Fig. 12: Wide-ResNet/16 GPUs chooses three stages on 4/4/8 GPUs, with early activation-heavy layers preferring batch partitioning and later weight-heavy work different sharding. Table 4 rounds the 32-GPU Wide-ResNet model to 6.7B while Table 8 says 6.8B; do not silently reconcile.

# Candidate mechanism cards

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

# Integration boundary

P: Only propose links into repository docs/reference-matrix.md and docs/searchspace-matrix.md, using verified existing row IDs at integration time. No matrix was edited. Network coverage requires actual cross-node traffic; H2D/D2H, same-host IPC and local GPU links are not Network. Further full-step correctness/performance testing requires separate authorization; this paper-derived procedure is not empirically validated.
