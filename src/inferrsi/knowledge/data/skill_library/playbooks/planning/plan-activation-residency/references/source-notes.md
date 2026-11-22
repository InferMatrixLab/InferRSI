# Activation-residency evidence and mechanism reference

Status: candidate; empirical_validation: not_run. F = historical source fact/model/result; P = unvalidated application. This file is self-contained when the skill folder is copied alone. It includes its original paper links, readset, numerical evidence, limitations and full mechanism cards. No current engine or NPU compatibility is established. Activation checkpoints refer to within-training rematerialization, not persistent recovery checkpoints.

## CM: Checkmate

- Full title: Checkmate: Breaking the Memory Wall with Optimal Tensor Rematerialization. Paras Jain, Ajay Jain, Aniruddha Nrusimha, Amir Gholami, Pieter Abbeel, Kurt Keutzer, Ion Stoica, Joseph E. Gonzalez.
- [Original metadata](https://arxiv.org/abs/1910.02653), [pinned v3 PDF](https://arxiv.org/pdf/1910.02653v3). v1 2019-10-07; v2 2020-03-12; read v3 2020-05-14 17:46:43 UTC. 15 PDF pages. No revision mixing.
- Actual relevant readset: §§4.1–4.10, Eqs. 1–9, Theorem 4.1 and Lemmas 4.1–4.2; §§5.1–5.3 and Algorithms 1–2; §§6.1–6.5, Eq. 10, Tables 1–2, Figs. 5–6; Appendices A–D, Figs. 7–8. Visually checked PDF pp. 9–10 for Figs. 5–6/Table 2. PDF p. 2 contains a figure with embedded manuscript text; its obsolete equation/section snippets were not used in place of the body formulation.
- SHA256: 8355cc2ecac072863fde2542585f8da0be30924e6181d9b05a36a63b22a1f694.

F, model and evidence:
- §§4.1–4.10: static DAG; each value has memory Mv and per-evaluation cost Cv. Binary R[t,i] selects evaluation, S[t,i] retention. U[t,k] accounts for memory just after an output exists and before dependencies are freed. Inputs/parameters and parameter-gradient reserve remain resident (Eq. 2). FREE variables require no later user and no retained checkpoint. Objective minimizes summed evaluation costs under per-event memory budget, not transfer time.
- §4.6/Eq. 8 restricts to a supplied topological order and frontier-advancing stages. This narrows the feasible set; optimality is within this formulation, not all possible reordered/parallel executions. Example: an eight-layer linear graph with unit costs and memory budget 4 solves in 0.23 seconds versus 9.4 hours unpartitioned, to the same objective. Appendix A's corresponding integrality-gap example is 1.18 versus 21.56. These are optimization examples, not training throughput.
- §4.10: additive timings from layer profiling on target hardware, shapes and batch; dense tensors use four-byte floats in the evaluated model. §6 implementation is TensorFlow 2.0/Keras/Gurobi. Most ordinary solves use 3600-second limit on at least 24 CPU cores. §5 reports no feasible solution for a DenseNet161 instance within one day; solver timeouts do not prove infeasibility.
- §6.3/Fig. 5: overhead is profile-model time relative to no-rematerialization ideal, using one NVIDIA V100. U-Net batch 32, 416×608 images, 16-GB budget: reported 1.20× speedup over linearized greedy and 1.38× over linearized sqrt(n). This is not directly measured whole-training speedup. VGG16 batch 256 and MobileNet batch 512 use 224×224.
- §6.4/Eq. 10/Fig. 6: maximize feasible batch subject to 16 GB and at most one extra forward pass in statically computed FLOPs. The nonlinear formulation gets a one-day limit; returned batch is a lower bound if optimality is unproved. MobileNet 224×224: 1105 versus 215 checkpoint-all and 640 linearized-greedy; author reports 5.1× and 1.73× respectively. U-Net 416×608: 61 versus 16 checkpoint-all and 35 best plotted heuristic. These are theoretical feasible-batch results, not observed time-to-quality or a guarantee that enlarged batch preserves training behavior.
- §§5.1–5.3/Algorithm 2: round S, then restore minimal necessary R to satisfy computation dependencies. Capacity is not guaranteed by this procedure. The authors empirically use 10% memory allowance; Appendix D says that allowance is overly conservative for MobileNet.
- §6.5/Table 2: two-phase approximation COSTapprox/COSTopt, geometric mean across mutually feasible budgets, in FLOPs: MobileNet 1.06, VGG16 1.01, VGG19 1.00, U-Net 1.03, ResNet50 1.05. It is neither a worst-case 1.06 approximation guarantee nor a whole-job speed ratio. Appendix D/Fig. 8 compares randomized versus deterministic two-phase rounding with profile-cost milliseconds.

## OL: OLLA

- Full title: OLLA: Optimizing the Lifetime and Location of Arrays to Reduce the Memory Usage of Neural Networks. Benoit Steiner, Mostafa Elhoushi, Jacob Kahn, James Hegarty.
- [Original metadata](https://arxiv.org/abs/2210.12924), [pinned v2 PDF](https://arxiv.org/pdf/2210.12924v2). v1 2022-10-24; read v2 2022-11-02 19:22:24 UTC. 14 PDF pages.
- Actual relevant readset: §§2.1–2.3/Figs. 3–4; §§3.1–3.5, Eqs. 1–9/Function 1; §§4.1–4.5, Eqs. 10–15/Functions 2–5/Figs. 5–6; §§5.1–5.7/Figs. 7–14; §6's placement/lifetime comparison. Visually checked PDF p. 10 (Figs. 11–14 and §5.7). Individual bar values were not digitized.
- SHA256: 69aebb2c874871e363ccec93e2ea15891e91c793153cde37004d17ea12ddef0b.

F, model and evidence:
- §3: DAG tensors are edges (possibly multiple consumers), with known sizes. Binary creation C[e,t] and preservation P[e,t] enforce exactly one creation, availability of all inputs, contiguous retention and simultaneous sibling outputs. Integer A[e] is a base address in one preallocated buffer, not GPU/CPU/SSD tier placement. Concurrent live tensors cannot overlap addresses. Objective minimizes maximum A[e]+size[e]. It neither offloads nor recomputes tensors.
- §§4.1–4.5: bound variable ranges using earliest/latest schedules and useful lifetimes; drop pairwise constraints for proven nonoverlapping tensors; add control edges to force safe early weight updates; split lifetime optimization (Eq. 14) from address optimization (Eq. 15); preplace nested activation lifetimes. The split relies on their empirical ability to remove fragmentation, not a universal proof that independently optimized lifetimes always admit ideal packing.
- §§5.1–5.2: PyTorch 1.11, torchtext/torchvision 0.12, torch.FX and Gurobi 9.1.1; Xeon Gold 6138 at 2.0 GHz plus A100 40 GB. Eleven families: AlexNet, EfficientNet, GoogleNet, MNASNet, MobileNet, ResNet, ResNet3D, Transformer, VGG, ViT, XLM-R, at batches 1/32. Graph size ranges from AlexNet 118 to XLM-R 2007 operators.
- §5.3/Fig. 7: node-reordering comparison excludes fragmentation, measuring peak requested operator memory/resident demand rather than allocator-reserved bytes. Maximum reduction 38%; mean 22.5% at batch 1, 10.1% at batch 32. Less leverage at large batch is attributed to forward activations dominating gradients.
- §5.4/Fig. 8: fragmentation defined (MR−RS)/MR at peak reserved memory MR. PyTorch mean fragmentation 7.9% at batch 1, 26.1% at batch 32; OLLA fully removes it in evaluated scenarios. Do not add these percentages to lifetime percentages: denominators differ.
- §§5.5–5.6/Figs. 9–12: median ordering solve 1.4±0.2 s, address generation 5.7±0.6 s; difficult EfficientNet ordering takes 2 min for batch-1 optimum, 5 min to within 1% at batch 32. GoogleNet/EfficientNet packing reaches <1% fragmentation within 5 min. The text's uncertainty notation is retained; no unreported confidence interpretation is added.
- §5.7/Fig. 13: cap each of the two optimizations at five minutes; overall memory reduction averages 30.4% at batch 1 and 36.1% at batch 32 versus PyTorch. §5.7/Fig. 14 estimates about five minutes runtime saved over one million batch-32 iterations by comparing allocator costs with upfront optimization. Total training time under the two schemes was explicitly not directly measured; batch-1 runtime estimate is unreported.
- Isolated ablations of every pruning/early-update/preplacement optimization and distributed-training interactions are unreported. No conclusion about current PyTorch allocator behavior follows from the 1.11 comparison.

# Candidate mechanism cards

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

# Integration boundary

P: Only propose links into repository docs/reference-matrix.md and docs/searchspace-matrix.md, using verified existing row IDs at integration time. No matrix was edited. Network coverage requires actual cross-node traffic; H2D/D2H, same-host IPC and local GPU links are not Network. Further full-step correctness/performance testing requires separate authorization; this paper-derived procedure is not empirically validated.
