# Split-backward evidence and mechanism reference

Status: candidate; empirical_validation: not_run. F = historical source fact/model/result; P = unvalidated application. This file is self-contained when the skill folder is copied alone. It includes its original paper links, readset, numerical evidence, limitations and full mechanism cards. No current engine or NPU compatibility is established. Activation checkpoints refer to within-training rematerialization, not persistent recovery checkpoints.

## ZB: Zero Bubble Pipeline Parallelism

- Full title: Zero Bubble Pipeline Parallelism. Penghui Qi, Xinyi Wan, Guangxing Huang, Min Lin.
- [Original version record](https://arxiv.org/abs/2401.10241v1), [pinned v1 PDF](https://arxiv.org/pdf/2401.10241v1), [same-version HTML](https://arxiv.org/html/2401.10241v1). The original record and PDF both give v1 as 2023-11-30 10:40:34 UTC despite the 2401 identifier; retain that source metadata. 19 PDF pages. arXiv's link boilerplate says "and 2 other authors" while its author list and PDF contain four; use the actual list.
- Actual relevant readset: §§1–7 (all subsections), Tables 1–8/Figs. 1–9; Appendices A–H including Figs. 10–11, Appendix B Eqs. 1–2, Appendix C Algorithm 1 (AdamW rollback), Appendix G Eqs. 3–7, Tables 9–12. Visually checked PDF pp. 7, 11 and 18 for Tables 4,6–8,11 and associated plots/text. The v1 HTML served as an additional same-version methods check.
- SHA256: 0de7cd6efd52eaa3f216129cd186ab755b1045bca1f6ddc422216295a7e9fee9.

F, model and evidence:
- §§1–2: split backward into B (input gradient, critical across stages) and W (parameter gradient, movable after B). Delaying W retains its needed activations/gradients. Table 2's ideal comparison: 1F1B bubble (p−1)(TF+TB+TW), ZB-H1 (p−1)(TF+TB−TW), both peak activations pMB; ZB-H2 bubble (p−1)(TF+TB−2TW), peak (2p−1)MB. Zero-bubble equality depends on timing assumptions and removing the optimizer barrier; it is not a universal empirical zero-idle guarantee.
- §3/Appendix G: schedule ordering/end times with inter-stage F/B dependencies, device sequencing and cumulative activation-memory limits; input p,m, memory cap, profiled TF/TB/TW/Tcomm. Heuristic schedules W into gaps or when memory needs release; ILP is feasible only at limited problem scale. Appendix A proposes parameter-grouped tail W work for overlapping data-parallel allreduce; an isolated measured ablation of that proposal is unreported.
- §4/Appendix C: partial reductions followed by post-update validation; invalid speculative updates roll back and redo using global clipping/NaN state. AdamW arithmetic inverse is supplied to avoid a full historical state copy. This is not permission to omit clipping or accept stale-gradient training. Finite-precision rollback stability, rare-event failure frequency and broad optimizer support are not established by the reported throughput table.
- §5.1: Megatron-LM-based GPT-like models, up to 32 A100 SXM 80-GB GPUs on four RoCE RDMA nodes; sequence 1024; end stages have one fewer Transformer layer to offset embedding/loss work. Hardware bandwidth value is unreported. Table 3: 1.5B/6.2B/14.6B/28.3B on 8/8/16/32 pipeline GPUs, microbatch size 6/3/1/1 and microbatch counts 3p,4p,8p. 1F1B-I uses each Transformer layer as a chunk. Author correctness check uses identical fixed-seed per-iteration losses, without training to convergence; the reported number of correctness-check iterations is unreported.
- §5.2/Table 4, representative measured row: 28.3B, 32 GPUs, b=1,m=96: ZB-2p 0.99 samples/s/GPU at 74 GB, ZB-1p 0.87 at 44 GB, 1F1B 0.76 at 43 GB, 1F1B-I 0.82 at 58 GB. Doubling an activation budget does not double total memory. Same-activation-cap ZB-1p still has modestly higher measured total memory than 1F1B.
- §5.3/Table 5: bubble rates are schedule calculations using measured timing inputs, not directly measured idle percentages. For the above row: 1F1B 0.2646; ZB-H2 0.0641; ZB-1p 0.1421; ZB-2p 0.0038. Fig. 6 contrasts generated and profiled timelines and acknowledges extra real bubbles. Appendix D/Table 9 supplies timing inputs; its table does not explicitly label time units, so no unit is invented here.
- §5.4/Fig. 7/Appendix B: memory/idle tradeoff plateaus near 2pMB when TF≈TB and Tcomm is small. More memory can have diminishing returns; communication and first-B dependency chains remain.
- §6/Fig. 8: ZB-V maps two chunks/device in a forward-and-reverse V order, enabling earlier local backward and balanced activation demand. Ideal TF=TB=TW permits zero bubble at pMB; actual profiled schedules remain nonzero. Additional chunk boundaries introduce communication and computation-granularity tradeoffs.
- §6.1/Table 6 is the stronger approximately matched-memory/global-batch comparison: ZB-2p* halves b and doubles m, keeping global batch. 28.3B, 32 GPUs, base b=2,m=96: ZB-V 1.01 samples/s/GPU at 71 GB; ZB-2p* 1.00 at 72; ZB-1p 0.94 at 73; 1F1B 0.82 at 69. 6.2B/16 GPUs/base b=6,m=48: ZB-2p* 4.36 at 63 GB versus ZB-V 4.15 at 64; V is not universally fastest.
- Table 7 varies b with fixed m, changing global batch; the b=1→2 14.6B ZB-V row is 1.75→1.88 samples/s/GPU (7.43%). Do not present it as matched-global-batch isolation. Table 8's V bubble rates are calculated, like Table 5.
- Appendix E/Table 10: optimizer post-validation versus allreduce synchronization, samples/s/GPU: 1.5B/8 GPUs/m24 14.5 vs 13.11; 6.2B/8/m24 4.32 vs 4.00; 14.6B/16/m48 1.81 vs 1.68; 28.3B/32/m96 0.99 vs 0.91. No measured rollback-rate sensitivity curve is reported.
- Appendix F/Table 11 keeps listed m while changing b, so global batch differs. It also prints middle m=32 for the 14.6B and 28.3B blocks, inconsistent with the main setup's 64/128. Preserve as a source ambiguity; use Table 6 for fixed-global-batch evidence. Table 11 includes cases where larger-b ZB-1p exceeds ZB-2p, a useful counter-signal.
- Appendix H/Table 12: at m≤p benefits persist but bubbles remain. Example 14.6B,p16,m4,b1: 0.39→0.52 samples/s/GPU, 19→20 GB, 1F1B→ZB-2p. This is throughput at small microbatch count, not elimination of all bubbles.

# Candidate mechanism cards

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

# Integration boundary

P: Only propose links into repository docs/reference-matrix.md and docs/searchspace-matrix.md, using verified existing row IDs at integration time. No matrix was edited. Network coverage requires actual cross-node traffic; H2D/D2H, same-host IPC and local GPU links are not Network. Further full-step correctness/performance testing requires separate authorization; this paper-derived procedure is not empirically validated.
