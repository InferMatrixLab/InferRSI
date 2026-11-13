# Agentic Kernel Optimization: pinned original-source extraction

Status: candidate; empirical_validation: not_run.

## Result and scope

This paper is useful evidence for a correctness-gated, profiler-guided optimization campaign, workload-regime dispatch, and escalation from local tuning to structural redesign. It does **not** supply a quantitative physical lower-bound model, calibrated latency predictor, learned shortlist score, or controlled ablation of the agent workflow. Its numerical results are specific to CUDA kernels on a local NVIDIA B200 and the authors' contest evaluation. This extraction makes no portability, NPU, reproduction, or present implementation claim.

Labels: **F** = paper fact or author-reported observation; **F-hypothesis** = a future direction or interpretation explicitly proposed by the authors, not a demonstrated improvement; **P** = candidate operational rule proposed by this extraction. Analytical checks and reporting cautions are explicitly identified rather than attributed to the authors.

## Provenance and exact readset

- Verified requested ID/title match: **arXiv:2608.14560v1**, **Agentic Kernel Optimization: Generating State-of-the-Art GPU Kernels Without Hand-Written CUDA**.
- Authors: Mao Luo, Hongbin Li, Feng Lin, Hanling Yi, Zhe Huang; Intellifusion Inc.
- Original arXiv submission history displays **25 May 2026, 02:50:41 UTC**, v1 only. PDF and HTML display **25 May 2026**. Preserve this date as reported: it does not align with the August-style `2608` identifier; the discrepancy is unresolved, not silently repaired.
- Verified 2026-10-15 using [versioned abstract](https://arxiv.org/abs/2608.14560v1), [versioned HTML](https://arxiv.org/html/2608.14560v1), and [versioned PDF](https://arxiv.org/pdf/2608.14560v1). PDF is 12 pages.
- Original PDF/HTML, text extracts and figure renders were retained outside the deliverable tree; only this derivative extraction is delivered.
- PDF SHA-256: `d0f04ea7a63af331b1de4567c655e4ca88bdf0f9af8818aaf9edfd5a7c1ff991`.
- HTML SHA-256: `bceb7f6766f8c0456a387ebaab5e89929222267010f14cba79e307e3c3dcd83e`.
- Read all PDF text, pp. 1–12: Abstract; §1; §§2.1, 2.2, 2.3; §§3.1.1–3.1.3 and 3.2.1–3.2.3; both discussion subsections in §4; §5; Acknowledgments; reference list; Appendices A.1–A.4, including A.3.1–A.3.2; B.1–B.4, including B.3.1–B.3.2; C.1–C.4, including C.3.1–C.3.2.
- Read all **Tables 1–21**, including captions, units, and adjacent interpretation. Figures **1–4** were read visually from rendered PDF pages 2–4, including workflow arrows and trajectory annotations. Approximate annotations, rather than digitized curve positions, are used below.
- Read mathematical expressions: §3.1.2 sparse-attention logits `(q_nope K_c^T) + (q_pe K_p^T)` and attention-weighted output; §3.1.3 unnumbered TopK score `score(t) = sum_h ReLU(Q_h K_t^T) w_h`; C.3.1 unnumbered batch-indexed equivalent. There are **no numbered cost-model equations** in this version.
- Checked `prior-foundation-pack` and `supplier-research-cache/source-notes` for the title/ID: no existing coverage found. No repository was read or run; author-linked implementation is not needed to support the extraction.

## 1. What is actually modeled, shortlisted, measured, and redirected

### M1. Profile/history-driven candidate search

- **F objective:** Improve kernel speed subject to all benchmark correctness conditions.
- **F assumptions:** A fixed reference, workload definition, harness, configuration, and dataset are available; CUDA candidates can be built and tested in isolated GPU environments; NCU and run history are available to the planning role.
- **F decisions/constraints:** Only kernel implementation is editable. Numerical failures, runtime errors, and timeouts invalidate a candidate. The framework can coordinate heterogeneous CLI agents, but the actual campaign says its Houmao agents used Claude Code with Claude Opus 4.6 and isolated context windows; mentioning Codex as a supported CLI does not establish a controlled mixed-model comparison.
- **F mechanism:** Planner receives current incumbent, NCU reports, and records of kernels/metrics/decisions. Parallel coders implement and benchmark different proposals. Synthesizer selects and merges useful changes and validates the updated result. Profiler supplies bottleneck reports. Researcher supplies external examples on demand. Figure 1 explicitly feeds results, decisions, profiler output, and notes back into history and planning.
- **F resource benefit/cost:** Parallel exploration and reuse of profiling/history can reduce serial search and repeated mistakes, but the paper does not quantify either saving. Reported expenditure is approximately 1.9 billion agent tokens across the three campaigns; GPU-hours, monetary cost, wall time, role-level token attribution, and parallel coder count are not given.
- **F evidence:** Workflow description/diagram, cumulative trajectories, and final kernel performance. No controlled comparison to one agent, random search, no-profiler search, or a human-only campaign.
- **Limits/countersignals:** No mathematical acquisition function, uncertainty estimate, quantitative candidate-ranking criterion, exact candidate budget, exact stall threshold, or prediction error evaluation. The Synthesizer's selection is qualitative. Campaign success alone cannot identify the causal value of each role.
- **P candidate rule:** Maintain an experiment record with workload regime, correctness gate, incumbent, proposed bottleneck, measurable predicted direction, observed result, and retained/rejected decision; use that record plus fresh profiles to choose the next small candidate set. Treat any numeric ranking model as a separate proposal requiring validation, not a method recovered from this paper.
- Source: [§2.1](https://arxiv.org/html/2608.14560v1#S2.SS1), [Figure 1](https://arxiv.org/html/2608.14560v1#S1.F1), [§2.3](https://arxiv.org/html/2608.14560v1#S2.SS3).

### M2. Correctness and anti-exploitation gates

- **F objective:** Ensure speed gains represent a deployable computation rather than changes to the evaluation or reuse of test outputs.
- **F assumptions:** Repeated benchmark iterations can expose stable tensor identities; an ordinary output comparison alone may fail to detect identity-based output caching.
- **F decisions/constraints:** Freeze non-kernel surfaces. Reject sample-specific shortcuts, tensor-identity output caches, and cross-iteration buffer reuse. Require separate cold and warm measurements if a legitimate deployable cache is material.
- **F mechanism:** Apply all-correctness acceptance before speedup selection; provide anti-hacking rules in each agent's initial prompt. Tool/environment notes include tensor cloning, L2 flushing, cold-cache and no-CUDA-graph defaults.
- **F resource benefit/cost:** Avoid spending tokens optimizing invalid objectives and avoid selecting artificial speedups. No measured anti-hacking overhead or ablation is reported.
- **F evidence:** Early MoE candidates reportedly exceeded 1000× because the in-process harness reused tensor pointers and the generated program returned cached outputs after its first execution. The paper identifies those results as invalid, not achievements to include in the final campaign.
- **Limits/countersignals:** Prompt restrictions are described; the paper does not establish a formal proof or exhaustive adversarial test of the final candidates. General correctness tolerances are not fully enumerated in the paper. TopK has the explicit matched-index ratio of 1.0.
- **P candidate rule:** Before recording a new incumbent, preserve harness identity and validate behavior on fresh content/identities consistent with the authorized workload. Record cache state and graph mode with each timing. Huge gains trigger an evaluation-path audit before resource-model conclusions.
- Source: [§2.1](https://arxiv.org/html/2608.14560v1#S2.SS1), [Table 2](https://arxiv.org/html/2608.14560v1#S2.T2), [§4](https://arxiv.org/html/2608.14560v1#S4).

### M3. Stall-triggered research and human search correction

- **F objective:** Escape unproductive local optimization and avoid discarding useful ideas because an unrelated defect was blamed on them.
- **F assumptions:** Agents are competent at local implementation but can under-explore references, prefer small changes after a plateau, and misattribute a failure.
- **F decisions/constraints:** After several failures in one direction, consult the research role; after no improvement within an allotted time, return to the Planner. Humans supply references or redirect strategy; authors say humans neither reviewed nor edited kernel code.
- **F mechanism:** A structured escalation path changes the search direction rather than continuing near-identical local attempts. Supplied references include DeepGEMM, FlashInfer, and RadiK; reusable skills cover architecture, profiling, and independent review.
- **F resource benefit/cost:** Intended reduction of futile token/GPU exploration; no intervention-level cost or return is measured.
- **F evidence:** Three qualitative recurring failure modes in §2.2; trajectories show stepwise gains after increasingly specialized changes. No intervention log, frequency, counterfactual, or controlled human-removal ablation.
- **Limits/countersignals:** The paper's broad suggestion that limited domain knowledge may suffice is not demonstrated across users/tasks. No reproducible numerical threshold defines a plateau.
- **P candidate rule:** Escalate only after logging why repeated attempts failed; distinguish invalid implementation from a falsified optimization hypothesis. Supply a novel reference or structural alternative when evidence contradicts the current search direction. Define local attempt/time budgets explicitly for a new workflow; these would be proposed policy parameters, not paper facts.
- Source: [§2.2](https://arxiv.org/html/2608.14560v1#S2.SS2), [§4](https://arxiv.org/html/2608.14560v1#S4).

### M4. Workload-regime diagnosis instead of one global bottleneck label

- **F objective:** Explain speedups and choose specializations using a few distinct execution regimes.
- **F assumptions:** Shape/sequence metadata separates different launch, occupancy, arithmetic, and data-movement behavior. Authors choose one representative per regime.
- **F decisions/constraints:** MoE regimes are based on sequence length; attention on query-token count; TopK on maximum pages/length. All benchmark workloads still face correctness acceptance; representative profiling is not evidence that every workload has identical counters.
- **F mechanism:** Group cases, profile representative hot paths with NCU, connect measured limitations to dispatch boundaries, then retain workload-specific fast paths.
- **F resource benefit/cost:** Smaller profiling focus and better shape-specific decisions are plausible benefits, but profiling-cost reduction is not measured. Specialization increases implementation/dispatch complexity.
- **F evidence:** Tables 3–5 enumerate all 19/23/128 cases by regime; Appendices A–C provide detailed slow-case evidence.
- **Limits/countersignals:** No formal clustering algorithm, sampling adequacy test, held-out workload validation, or cross-hardware validation. See reported conflicts below between main-text representatives and appendices.
- **P candidate rule:** Keep regime-specific correctness and latency records. Do not use a single averaged speedup or one profile as a universal kernel cost model. Reprofile when the shape mix or hardware changes.
- Source: [§3.2](https://arxiv.org/html/2608.14560v1#S3.SS2).

## 2. Kernel mechanisms and their resource trade-offs

### M5. MoE: keep metadata on device, dispatch GEMM backends, inspect producer–consumer traffic

- **F objective:** Accelerate DeepSeek-V3-style MoE routing, activation gathering/quantization, two expert GEMMs with SwiGLU, and weighted scatter.
- **F assumptions/semantics:** Eight routing groups, group top-2, final top-8 experts; FP8 contiguous activation layout with FP32 block scales over 128 values; GEMM1 `[T,7168] → [T,4096]`, then SwiGLU and requantization; GEMM2 `[T,2048] → [T,7168]`.
- **F decisions/constraints:** Device-side metadata avoids hot-path `cudaStreamSynchronize`. One compiled module contains CUTLASS FP8 blockwise, a custom tcgen05 backend, and a cuBLAS FP16 fallback for very large T. Exact dispatch thresholds are not supplied. The text calls tcgen05 “hand-written” while globally claiming no human-written kernel code; this wording does not establish human authorship, and the inconsistency should not be silently resolved.
- **F mechanism:** Backend/tiling selection by workload, pipeline overlap, fused scan/scatter, static compilation, newer matrix instructions, and small-T routing changes accumulate improvements (Figure 2). For the long profiled case CUTLASS is selected because the authors report it is 2–7% faster than their tcgen05 implementation in long cases.
- **F resource benefit/cost:** Less host synchronization and interstage traffic; strong matrix throughput but high registers/shared memory. Appendix A gives 168 registers/thread and 201.22 KB dynamic shared memory/CTA, one resident CTA/SM, and 14.09% achieved occupancy.
- **F evidence:** Final local aggregate 92.68× relative to PyTorch for 1.05B tokens, with FlashInfer at 47.08× on the same reported local comparison. Long-case NCU has GEMM1 600.22 µs, GEMM2 383.26 µs, total iteration 1261.94 µs. Scatter is 81.31 µs and 62.92% of peak sustained DRAM throughput, making it the largest non-GEMM DRAM consumer.
- **F-hypothesis:** Fuse pull-scatter into the GEMM2 epilogue so producer/consumer values avoid a separate global-memory stage. Authors leave this undone because of an upstream CUTLASS API constraint.
- **Limits/countersignals:** Low occupancy alone does not prove low useful performance. Conversely, the main-text 97%/95% SM-utilization statement and appendix's 43.80–57.55% SM-throughput figures use unmatched metric definitions and possibly different collection windows. Their comparison remains unresolved, not a proven contradiction or evidence of physical saturation. Scatter's 6.4% of iteration time caps any benefit from removing only that measured cost; broader fusion interactions are not measured.
- **P candidate rule:** Retain per-regime backend comparisons instead of assuming a newer instruction path always wins. Prioritize interstage movement only after measuring its fraction and validating integration feasibility; do not convert proposed epilogue fusion into an achieved result.
- Sources: [§3.1.1](https://arxiv.org/html/2608.14560v1#S3.SS1.SSS1), [§3.2.1](https://arxiv.org/html/2608.14560v1#S3.SS2.SSS1), [Appendix A](https://arxiv.org/html/2608.14560v1#A1).

### M6. Sparse attention: trade Split-K parallelism against merge overhead and register pressure

- **F objective:** Compute paged decoding attention over 2048 selected KV entries, producing 512 output dimensions and LSE.
- **F assumptions/semantics:** Logits combine non-positional and positional dot products; base-2 softmax; output accumulates weights against K_c. Exact benchmark accuracy constraints limit lower precision.
- **F decisions/constraints:** Four heads per CTA; 128 threads/four warps, one warp per head. Use a two-stage asynchronous global-to-shared pipeline and double buffering. Single token takes a fused single-pass path; two tokens use templated Split-K=64; larger batches use Split-K=32. Merge divides output into four slices; BF16 partial results reduce merge traffic.
- **F mechanism:** Increase useful work parallelism when batch size is small while bypassing an unnecessary merge for a singleton. Register-resident query/output, branchless online softmax, and reordered blocks support the pipeline and locality.
- **F resource benefit/cost:** More Split-K CTAs can hide latency but add partial storage/reduction and launch cost. Registers and shared memory constrain residency; final eight-token partial kernel uses 192 registers/thread, 73.98 KB/CTA in Appendix B, and 10.07% achieved occupancy. Main text says about 50 KB; preserve that conflict.
- **F evidence:** Final local aggregate 181.35× PyTorch, FlashInfer 10.33×, 427M tokens. Final slow-case partial is 17.73 µs; merge 8.58 µs; total 26.31 µs. Partial has 17.68% SM throughput and 1.58% DRAM throughput; 1024 CTAs, 3.46 waves/SM. Merge has 128 CTAs, 0.17 waves/SM, 1.81% SM throughput, 0.77% DRAM throughput. Thus low memory utilization does not mean data access is irrelevant: poorly hidden gather/staging latency is the authors' explanation.
- **F-hypothesis:** Reduce register pressure or redesign around TMA/warpgroups/tcgen05. Additional local fusion is said to be unlikely to address the structural bottleneck. Lower precision is constrained by correctness, not a free optimization.
- **Limits/countersignals:** Authors use a single warmup and single NVTX-scoped measurement for this profiler capture. Phase timing is source-mapped PC-sampling attribution, not separately timed phases. No controlled Split-K sweep or precision-error curve is published. Main text calls merge partitioning the largest gain, while the cumulative annotations show larger absolute steps earlier; causal ranking is not established.
- **P candidate rule:** Classify latency/occupancy limits separately from bandwidth saturation. Adjust split/merge structure by regime, recording both stages. Any proposed register-reduction or tensor-core path must earn correctness and whole-iteration timing, not only a favorable occupancy estimate.
- Sources: [§3.1.2](https://arxiv.org/html/2608.14560v1#S3.SS1.SSS2), [§3.2.2](https://arxiv.org/html/2608.14560v1#S3.SS2.SSS2), [Appendix B](https://arxiv.org/html/2608.14560v1#A2).

### M7. TopK: semantic fast paths before arithmetic tuning

- **F objective:** Return the exact selected indices for weighted, rectified dot-product scores.
- **F assumptions/semantics:** FP8 Q has 64 heads × 128 dimensions; paged FP8 K has per-token FP32 scales; K=2048 selections. Required matched-index ratio is 1.0. When sequence length is at most K, every valid token is selected and score computation is unnecessary for this output contract. Pages contain 64 tokens, so max pages ≤32 implies the whole batch qualifies for this specialization.
- **F decisions/constraints:** Dispatch on each element's actual sequence length entirely on device. Preserve bit-exact dequantization and index semantics. For mixed batches only long elements calculate scores; short elements map block-table indices and pad remaining entries with -1.
- **F mechanism:** Bypass GEMM and selection for short sequences. Otherwise fuse dot products, ReLU, head weights, and reduction. Use padded shared layouts (key stride 129; cross-warp partials `[16][33]` rather than `[16][32]`) and a four-pass 8-bit radix selection using sortable float representations, early termination, subgroup histograms, suffix scanning, and ballot-based gather. Increase radix threads from 256 to 512 to reduce per-thread loop work.
- **F resource benefit/cost:** Eliminate unnecessary score/selection computation for eligible inputs; remove 32-way bank conflicts and serialized selection work. Exact-match requirements lead the slow-case score kernel to scalar FP32 dots rather than tensor cores. Extra fast/slow paths complicate scheduling and can leave many CTAs immediately returning.
- **F evidence:** Final local aggregate 1101.02× PyTorch, FlashInfer 52.03×, 414M tokens. Of 128 workloads, 69 are in the two all-short regimes and 59 in the long regime (this count addition is an extraction calculation from Table 5). Appendix C's worst-speedup case is 107.29× the mathematical reference. Only one of four batch elements exceeds K; score and radix stages total 24.86 µs, with low useful device coverage.
- **Limits/countersignals:** The huge PyTorch-relative average is strongly influenced by eliminating work that PyTorch still performs; it is not an across-the-board 1101× faster GEMM. Main text describes a three-kernel pipeline, but Appendix C explicitly invokes two kernels and handles remapping inline. Benchmark exact-match constraints are narrower than generic approximate TopK usefulness.
- **P candidate rule:** Prove a semantics-preserving shape/value-metadata shortcut before considering lower-level tuning. Report fast-path hit rate and slow-path performance separately; never generalize an aggregate shortcut-dominated result to larger sequences or a different output ordering/tie contract.
- Sources: [§3.1.3](https://arxiv.org/html/2608.14560v1#S3.SS1.SSS3), [§3.2.3](https://arxiv.org/html/2608.14560v1#S3.SS2.SSS3), [Appendix C](https://arxiv.org/html/2608.14560v1#A3).

### M8. TopK residual scheduling limitation and evidence granularity

- **F objective:** Explain the slow mixed-batch case after semantic work elimination and local shared-memory improvements.
- **F assumptions:** Small active batch count can limit whole-device coverage even when occupancy counters within active execution are nontrivial.
- **F decisions/constraints:** Keep exact scalar path where required; distinguish launched CTA count from CTAs doing score computation.
- **F mechanism/evidence:** Score grid is 288 CTAs but three of four batch elements exit early. Radix grid is four CTAs, one per element; only one performs all radix work over 2241 keys. Radix's reported 23.54% achieved occupancy coexists with just 0.01 waves over 148 SMs and 0.16% SM throughput. Those counters are not interchangeable notions of global utilization.
- **F resource benefit/cost:** Fast exits save work but leave scheduling/parallelism limits. Radix stage 13.18 µs is slightly larger than score stage 11.68 µs. The reported phase attribution says fast-path remapping for the three short elements is the largest radix component (3.14 µs), followed by ballot gather (2.30 µs) and histograms (1.98 µs).
- **F-hypothesis:** A persistent or globally scheduled combined fast/slow path could use more SMs; a tensor-core long-sequence path could coexist with scalar exact paths where needed. Neither is implemented/evaluated in the paper.
- **Limits/countersignals:** Four-CTA radix PC sampling is sparse. Its phase allocation uses executed warp instructions as a proxy; these estimated phase times cannot be treated as direct microbenchmarks or physical lower bounds.
- **P candidate rule:** For tiny or mixed grids, record useful CTAs, waves, active fractions, and launch count alongside occupancy. Require measurement of the full mixed batch before accepting persistent scheduling as better.
- Source: [C.2–C.4](https://arxiv.org/html/2608.14560v1#A3.SS2).

## 3. Evidence ledger: denominators, workloads, and trajectories

### F: final campaign results (Table 1)

All three local comparisons use **NVIDIA B200** and **PyTorch implementation latency as the speedup denominator**. Figure axes say average speedup; the exact arithmetic/geometric aggregation and workload weighting are not defined in this paper.

| Task | Cases (from §3.2) | FlashInfer/PyTorch speedup | Generated/PyTorch speedup | Agent tokens |
|---|---:|---:|---:|---:|
| Fused MoE | 19 | 47.08× | 92.68× | 1.05B |
| DSA Sparse Attention | 23 | 10.33× | 181.35× | 427M |
| DSA TopK Indexer | 128 | 52.03× | 1101.02× | 414M |

Token sum is 1.891B (extraction arithmetic), consistent with approximately 1.9B. Token accounting details (input/output, caching, failed attempts, role allocation) are unreported. No dollar conversion is justified.

Official contest claim is **MoE 1.71× relative to FlashInfer**, versus **1.68×** for the highest reported agent-assisted-track score. Acknowledgments attribute the result to an organizer email; the email itself was not inspected. This is a different evaluation statement and denominator from local Table 1. Do not label 1.71× as PyTorch-relative or treat the local Table 1 ratio as the official score. [Table 1](https://arxiv.org/html/2608.14560v1#S1.T1), [Acknowledgments](https://arxiv.org/html/2608.14560v1#Sx1).

### F: cumulative annotations, not controlled ablations

These are approximate labels in visually read Figures 2–4. Consecutive changes are campaign stages; differences do not isolate causal gains, and cumulative token totals are not deployment latency/cost models. Some plotted point positions do not align precisely with annotations (notably Figure 2 and early Figure 3); no interpolated curve or regression is warranted.

- **Figure 2, MoE:** PyTorch 0M/1×; cuBLAS FP16 with fast-16BF compute about 50M/26.8×; synchronization-free path about 100M/31×; CUTLASS FP8 grouped, 1-SM blockwise about 315M/43×; dual-tile dispatch about 420M/54×; pipeline overlap plus fused scan/scatter and uint4 scatter about 680M/78×; static compilation/embedded CUTLASS about 790M/85×; tcgen05 on GEMM1 about 880M/87×; tcgen05 on both GEMMs with two TMA descriptors about 940M/90×; small-T path, buckets, and parallel routing about 1050M/92.68×. Dashed FlashInfer line approximately 47×.
- **Figure 3, attention:** PyTorch 0M/1×; naive CUDA using one CTA per token/head and sequential gather about 30M/43.00× (annotation; marker appears lower); register-resident path about 85M/77.26×; adaptive Split-K about 195M/117.01×; multi-head pipelining about 248M/153.07×; workload-sensitive dispatch about 355M/160.56×; merge output partition about 393M/174.28×; templated Split-K about 427M/181.35×. FlashInfer line approximately 10.33×.
- **Figure 4, TopK:** PyTorch 0M/1×; hybrid CUDA plus PyTorch mm/topk about 180M/6.5×; fully CUDA fused stage with CPU batch dispatch about 220M/91×; on-device sequence-based dispatch/early exit about 340M/900×; cooperative 32-token K tile loaded once per CTA about 385M/942×; key shared stride 129 about 405M/971×; padded `[16][33]` partials and 16-warp radix about 414M/1101×. FlashInfer line approximately 52×.

Sources: [Figure 2](https://arxiv.org/html/2608.14560v1#S3.F2), [Figure 3](https://arxiv.org/html/2608.14560v1#S3.F3), [Figure 4](https://arxiv.org/html/2608.14560v1#S3.F4).

### F: regime table data

All regime speedups are in the paper's PyTorch-reference context; latency is for the listed representative, not every member of the group.

| Task/regime | Range | Count | Speedup range | Representative | Representative latency | Reported dominant issue |
|---|---|---:|---|---|---|---|
| MoE short | length 1–16 | 5 | 103–240× | length 7 | 0.099 ms | routing/launch overhead |
| MoE median | 32–80 | 11 | 75–93× | 54 | 0.205 ms | GEMM1+2 about 65% of iteration |
| MoE long | 901–14,107 | 3 | 38–74× | 14,107 | 1.229 ms | GEMM1 about 47%, GEMM2 about 30% |
| Attention short | 1 query token | 1 | 280× | 1 token | 0.005 ms | four CTAs, launch/underfill |
| Attention median | 2 query tokens | 8 | 125–148× | 2 tokens | 0.017 ms | Split-K latency and registers |
| Attention long | 6–8 query tokens | 14 | 108–228× | 8 tokens | 0.026 ms | registers and remaining bank conflicts |
| TopK short | max S≤1024; max P≤16 | 27 | 477–3732× | batch 29, max P=1, max S=64 | ~0.002 ms | remap launch/grid |
| TopK medium | 1088≤max S≤2048; 17≤max P≤32 | 42 | 816–5366× | batch 15, max P=31, max S=1984 | ~0.004 ms | remap proportional to batch and K |
| TopK long | max S>2048; max P>32 | 59 | 107–756× | batch 4, max P=36, S=[18,11,2161,20] | ~0.020 ms | active-CTA underfill and FP8 conversion stalls |

Sources: [Table 3](https://arxiv.org/html/2608.14560v1#S3.T3), [Table 4](https://arxiv.org/html/2608.14560v1#S3.T4), [Table 5](https://arxiv.org/html/2608.14560v1#S3.T5).

## 4. Detailed profiler evidence (reported measurements, not reproduced)

All captures identify **NVIDIA B200, SM100, compute capability 10.0**, NCU **2026.1.0.0**, full metric set and kernel replay. SM/DRAM/L1/L2 throughput percentages are NCU resource-throughput metrics; they are not latency savings, mathematical utilization bounds, or fraction of all chip time interchangeable with occupancy. Appendix tables retain profiled kernel-time totals separately from main-table representative benchmark latency.

### F: Appendix A, MoE

Provenance: `cuda-moe-tvm-v14`, workload `5e8dc11c`, sequence length 14,107; three warmups, five NVTX-scoped measurement iterations. Tables 6–9.

| Kernel | Invocations | Time per invocation or row mean (µs) | SM % | DRAM % | L1 % | L2 % | Achieved occupancy % | Registers/thread | Warp cycles/issued instruction |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CUTLASS FP8 grouped | 2 | 491.74 mean | 50.68 | 24.85 | 45.18 | 41.69 | 14.09 | 168 | 5.46 |
| routing | 1 | 108.22 | 62.37 | 1.74 | 67.96 | 1.65 | 65.08 | 32 | 17.71 |
| pull scatter BF16 | 1 | 81.31 | 23.52 | 62.92 | 33.87 | 30.90 | 43.50 | 61 | 26.82 |
| gather FP8/scales | 1 | 42.69 | 46.47 | 47.04 | 46.91 | 35.63 | 82.40 | 32 | 25.56 |
| SwiGLU→FP8 | 1 | 34.94 | 70.89 | 55.87 | 30.86 | 32.65 | 85.21 | 29 | 16.66 |
| scatter with scan | 1 | 11.30 | 2.31 | 0.53 | 1.80 | 1.47 | 24.03 | 18 | 198.69 |

Total 1261.94 µs; the grouped row must be multiplied by two, not counted once. Individual GEMMs: 600.22 µs (K=7168) and 383.26 µs (K=2048).

Table 7 min/max/average: SM clock 1.58/1.63/1.60 GHz; DRAM clock 4.00 GHz; memory throughput 37.52/50.70/44.11%; DRAM 23.99/25.71/24.85%; L1 38.02/52.34/45.18%; L2 37.68/45.71/41.69%; SM 43.80/57.55/50.68%. Table 8: 384 threads, 148 CTAs, 1.00 waves/SM, 201.22 KB dynamic shared memory/CTA, theoretical occupancy 18.75%, achieved 14.09%, active warps/SM 9.02, active threads/warp 31.85. Table 9 scatter: 14,107 CTAs, 23.83 waves/SM; clocks SM 1.94 GHz, DRAM 3.99 GHz; 62.92% memory throughput. The reported scatter fraction is about 6.4% of the profiled iteration.

### F: Appendix B, sparse attention

Provenance: `dsa-attn-v4`, workload `385742b2`, query tokens 8, pages 8462, K=2048; one warmup and one NVTX measurement iteration; imported source, line information enabled. Tables 10–15.

| Metric | partial<32> | merge<32> |
|---|---:|---:|
| Time (µs) | 17.73 | 8.58 |
| SM throughput % | 17.68 | 1.81 |
| Memory throughput % | 16.38 | 1.45 |
| DRAM throughput % | 1.58 | 0.77 |
| L1/TEX throughput % | 37.11 | 6.60 |
| L2 throughput % | 3.38 | 0.94 |
| SM frequency GHz | 1.94 | 1.95 |
| DRAM frequency GHz | 3.98 | 3.98 |
| Threads/CTA | 128 | 128 |
| CTAs | 1024 | 128 |
| Waves/SM | 3.46 | 0.17 |
| Registers/thread | 192 | 95 |
| Dynamic shared memory KB/CTA | 73.98 | 0.00 |
| Theoretical occupancy % | 12.50 | 31.25 |
| Achieved occupancy % | 10.07 | 6.16 |
| Active warps/SM | 6.45 | 3.94 |
| Warp cycles/issued instruction | 4.00 | 13.86 |
| Active threads/warp | 31.52 | 31.08 |

Total 26.31 µs; approximately 67% partial / 33% merge. Partial grid is 8 tokens × 4 head groups × 32 splits; each CTA handles 64 sparse entries. Merge consumes 32 BF16 partials and performs LSE-renormalized weighted accumulation; four output slices yield 128 CTAs. The 148-SM device is explicitly stated in the merge discussion.

Table 11 source-attributed phase times (µs): partial staging via cp.async 5.54; sparse index gather 5.34; dot/reduction 1.81; value accumulation 1.66; query/prologue 1.16; online softmax 0.96; shared KV loads 0.91; epilogue 0.35. Merge LSE/valid-split scan 3.11; weighted accumulation 2.58; helpers/scheduling 1.94; epilogue 0.95. The first two partial phases total 10.88 µs, reported as 41% of the complete iteration. These are sampled source attributions, not independent phase timers.

### F: Appendix C, TopK

Provenance: `dsa-topk-indexer-v6`, workload `4c7705ad`, batch 4, max pages 36, total pages 11,923, sequence lengths **[98,91,2241,100]**, only b=2 slow path; one warmup and one NVTX measurement; source import/line info enabled. This differs from Table 5's representative vector. Reported speedup 107.29× the mathematical reference, the lowest across 128 contest cases. Tables 16–21.

| Metric | FusedGemm | RadixSelect |
|---|---:|---:|
| Time (µs) | 11.68 | 13.18 |
| SM throughput % | 9.66 | 0.16 |
| Memory throughput % | 15.22 | 0.87 |
| DRAM throughput % | 0.37 | 0.03 |
| L1/TEX throughput % | 45.82 | 11.42 |
| L2 throughput % | 0.30 | 0.12 |
| SM frequency GHz | 1.94 | 1.95 |
| DRAM frequency GHz | 3.98 | 3.98 |
| Threads/CTA | 512 | 512 |
| CTAs | 288 | 4 |
| Waves/SM | 0.97 | 0.01 |
| Registers/thread | 64 | 40 |
| Dynamic shared memory KB/CTA | 48.13 | 38.15 |
| Theoretical occupancy % | 50.00 | 50.00 |
| Achieved occupancy % | 33.92 | 23.54 |
| Active warps/SM | 21.71 | 15.07 |
| Warp cycles/issued instruction | 21.64 | 17.79 |
| Active threads/warp | 31.30 | 30.85 |

Total 24.86 µs. No separate remapping kernel runs in this case. Score uses scalar FP32 for bit-exactness. Four CTAs cannot cover 148 SMs, irrespective of the active-execution occupancy metric.

Table 17 source-attributed/proxy phase times (µs): score setup 2.88; scalar dots 2.88; query dequantization 1.86; FP8 conversion helper 1.52; CUDA helper code 1.52; page table/key-scale loads 0.68; key dequantization/ReLU/reduction 0.34. Radix fast remap 3.14; ballot gather 2.30; histogram build 1.98; histogram initialization 1.27; suffix scan 1.05; selected bucket 0.83; score loading/encoding 0.59; subgroup histogram reduction 0.36; slow setup 0.31; other 1.35. The radix subdivision uses executed warp instructions as a proxy because its small grid yields sparse PC samples. Do not imply these are exact phase latency measurements.

Sources: [Appendix A](https://arxiv.org/html/2608.14560v1#A1), [Appendix B](https://arxiv.org/html/2608.14560v1#A2), [Appendix C](https://arxiv.org/html/2608.14560v1#A3).

## 5. Physical bounds versus empirical predictions: explicit answer

- **F:** Resource-feasibility constraints are discussed: registers/CTA, shared-memory footprint, resident blocks, occupancy ceilings, and CTA coverage. They help reject simplistic explanations such as bandwidth saturation when bandwidth counters are low.
- **F:** NCU's Speed-of-Light throughput counters compare observed hardware activity with profiler-defined throughput capacity. They are measurements/normalizations; the paper does not derive a universal lower bound on end-to-end latency from them.
- **F:** Main-text launch floors and structural bottleneck claims are interpretations of profiling, not mathematical proofs. The score equations define required computation, not a cost model.
- **F:** No explicit FLOP/byte model, arithmetic-intensity roofline, compulsory-traffic lower bound, overlap equation, launch-time bound, calibrated regression, surrogate model, or prediction-error statistics is reported. No formula maps tokens spent to expected speedup.
- **F:** Candidate shortlisting is Planner judgment based on incumbent/profile/history and external examples, followed by measurement; it is not a learned shortlist or validated analytical optimizer.
- **F:** Backend preferences and Split-K thresholds are empirical implementation choices. Proposed TMA/tcgen05/persistent/epilogue directions remain unmeasured hypotheses.
- **P:** Keep separate fields for (a) semantic feasibility/physical constraints, (b) measured counters, (c) empirical prediction, and (d) untested optimization hypothesis. This prevents a low-throughput diagnosis from being promoted into an achievable speedup promise.
- **P:** A future analytic bound can shortlist impossible or obviously poor candidates, but measured correctness and regime-level latency must decide acceptance; adding such a bound would be an extension beyond this source.

## 6. Important limitations and unreconciled signals

1. **Bibliographic date anomaly:** all inspected originals say 25 May 2026 with an ID beginning 2608. Record both; no conjectural repair.
2. **MoE metric comparison unresolved:** §3.2.1 says 97%/95% SM utilization for the long representative; Table 7's SM throughput is 43.80–57.55%, mean 50.68%. Metric definitions, denominators and capture windows have not been matched. This is not a proven contradiction or proof of saturation.
3. **Attention memory conflict:** main text ~50 KB versus Appendix B 73.98 KB dynamic shared memory/CTA. Use the appendix value only with its pinned version/capture.
4. **TopK workload conflict:** Table 5 [18,11,2161,20], ~20 µs; Appendix C [98,91,2241,100], 24.86 µs, though appendix calls it the corresponding long representative. Preserve distinct identities/timings.
5. **MoE timing context:** Table 3 1.229 ms vs Appendix A 1.26194 ms. Profiler capture and benchmark timing are different contexts; do not overwrite one with the other or call a regression from this alone.
6. **Trajectory interpretation:** cumulative campaign stages are not controlled ablations, and annotation/plot placement inconsistencies preclude a precise token-efficiency curve. Attention's “largest gain” attribution to merge partitioning is not established by the plotted stage values.
7. **Model/implementation wording:** framework examples include Codex but campaign specification says Claude Code/Opus 4.6. A custom backend is called hand-written despite the overall no-human-code claim. Preserve scope; do not invent a resolved authorship or mixed-model experiment.
8. **Statistical/cost incompleteness:** benchmark repetitions, variance, uncertainty, aggregation method, total GPU/wall-clock cost, model sampling settings, accepted/rejected run counts, intervention count, and full search logs are unreported in the paper. Profiling captures have their own stated 3+5 or 1+1 iterations.
9. **Transfer limits:** three selected task families, one GPU type, fixed benchmark shapes and strong correctness constraints. No held-out workload study, end-to-end serving throughput/energy result, or cross-architecture claim is supported.
10. **Implementation future directions:** epilogue fusion is blocked/unimplemented; TMA/tcgen05 attention and persistent TopK are proposals. The paper's title does not justify presenting these proposals as already achieved.

## 7. Leads for a separate next gate (unread, not admitted as evidence)

These are citations or author-supplied links found in the paper; their contents were **not** fetched/read for this extraction. No implementation action is proposed by listing them.

- Author-linked generated solutions: https://github.com/CodeGandee/flashinfer-bench-starter-kit/tree/main/solution/cuda
- Houmao orchestration: https://github.com/igamenovoer/houmao
- FlashInfer-Bench reference: arXiv:2601.00227, https://arxiv.org/abs/2601.00227
- TritonForge, arXiv:2512.09196, https://arxiv.org/abs/2512.09196
- CUDAForge, arXiv:2511.01884, https://arxiv.org/abs/2511.01884
- Astra, arXiv:2509.07506, https://arxiv.org/abs/2509.07506
- AKG Kernel Agent, arXiv:2512.23424, https://arxiv.org/abs/2512.23424
- Dr. Kernel, arXiv:2602.05885, https://arxiv.org/abs/2602.05885
- Paper-supplied architecture notes https://github.com/technillogue/ptx-isa-markdown and profiler skill https://github.com/maxiaosong1124/ncu-cuda-profiling-skill
- DeepGEMM and RadiK are named external-reference leads; no exact paper/repository identity was verified here.

## 8. Reuse delta against the supplied prior-reference inventory

The relevant rows of `supplier-research-cache/prior-readsets/reference-matrix.md` and Task 1 of `HANDOFF.md` were read after paper extraction. These inventory records already identify analytical and empirical roofline material; the parent also confirms existing Amdahl coverage. They are overlap evidence only, not newly verified current implementation state.

- **P `optimization-search-policy`:** Add profile/history-conditioned proposals, bounded unsuccessful-direction escalation, explicit separation of spurious implementation failures from failed optimization hypotheses, and the absence of controlled agent-role evidence.
- **P `inference-benchmark-design`:** Add the concrete tensor-identity cache failure, fixed editable surface, cold/warm split, exact TopK contract, separate benchmark/profiler contexts, and regime-dependent fast-path reporting.
- **P `kernel-writing-guide`:** Add shape-regime dispatch and semantic work elimination as candidate design rules, with numerical exactness and integration constraints; retain hardware-specific CUDA examples as examples only.
- **P `dense-performance-evidence`:** Add capture provenance, metric-denominator distinctions, phase-attribution/proxy labels, token-accounting limits, and unreconciled cross-section values.
- **P `inference-optimization-casebook`:** Add the three concrete before/after campaign narratives and residual-bottleneck cases, preserving cumulative rather than isolated attribution.
- **P `performance-ceiling-analysis`:** Cross-reference the existing analytical/empirical/Amdahl distinction. Do not create a duplicate ceiling method or claim this paper adds a physical-bound formula.

## Extraction completion

All requested original-paper methods, experimental trajectories, regime results, and profiler appendices were read. No separate controlled ablation section exists. No software installation, kernel reproduction, hardware access, repository inspection, PR, benchmark run, or implementation modification occurred. Original-source cache remains outside the deliverable tree; this derivative note is part of Pack A.
