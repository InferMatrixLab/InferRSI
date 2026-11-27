# FlashVector: source audit and mechanisms

Status: candidate / empirical_validation: not_run. F = paper fact; P = proposed use. [FlashVector: Agent for Hierarchical Model Serving Stack Optimization, 2609.17391v1](https://arxiv.org/abs/2609.17391v1), submitted 2026-09-15. [Pinned HTML](https://arxiv.org/html/2609.17391v1), [PDF](https://arxiv.org/pdf/2609.17391v1). Title/ID/version verified. Production case studies are author reports; no code or deployed system inspected.

## Exact readset

§§1–7, emphasizing §3 challenges, §§4.1–4.2 knowledge/loop, Algorithm1, §§5.1–5.4 methods/results. All Tables1–4 and figure captions/discussion1–6 read. PDF p.4 Fig.3, p.5 Algorithm1/correctness/noise prose, p.7 Figs.5–6/Table2, and p.8 Tables3–4 visually checked. Figures1–2/4 are caption/text-only reads. There are no numbered cost-model equations or appendix in this version. The noise reduction relation and hypothesis scoring are unnumbered. No controlled ablation isolating random layer sampling, knowledge refinement, human cookbook, or always-on triggering is reported.

## F1. Layer-local diagnosis with system-level acceptance

- **Objective (F):** improve serving-stack throughput/latency while preserving predictions and production constraints.
- **Assumptions (F):** appropriate profiling and semantic context exist for each layer: GPU/kernel, framework graph, model server, feature processing; recorded model inputs/weights/outputs represent the intended workload.
- **Decisions / constraints (F):** Algorithm1 randomly samples one layer per iteration, profiles it, ranks hypotheses within that layer by time share × expected gain, and rejects hypotheses whose best possible gain is below measurement noise. This is not demonstrated as globally optimal layer selection.
- **Mechanism (F):** Profile→Diagnose→Plan/Apply→Verify; candidates beating the local incumbent/noise gate receive a full-stack load test; regressions revert. Post-run refinement records accepted/rejected context without indefinitely appending every trace. Release/age triggers re-open optimization.
- **Resource benefit / cost (F/P):** focuses specialist tooling/context and avoids optimizing tiny time shares; full-stack replay and increased sampling consume resources. The expected-gain score is a heuristic, not a measured runtime predictor or hardware ceiling.
- **Author evidence (F):** production case studies find serialization, feature processing, graph and kernel opportunities. Table1 includes both latency and throughput changes, e.g. retrieval1.67×/1.10×, ranking-model2 1.98×/2.00×. Hardware, request mix and absolute latency are not uniformly supplied for those table rows, so they cannot be imported as general expectations.
- **Limits / countersignals (F/P):** knowledge-refinement and continual triggering benefits are asserted, not isolated experimentally. Intro/§6 describe E2E gain above noise; Algorithm1 explicitly gates local gain then full-stack non-regression. For a local procedure, choose and declare the stricter desired acceptance rule rather than treating these descriptions as identical.
- **Candidate rule (P):** retain layer-specific observables and ownership; evaluate impact on the actual critical path and full service objective. After an accepted change, re-profile before choosing the next target. Store rejection reasons scoped to model/workload/hardware versions, rather than permanent bans on whole techniques.

## F2. Noise-aware verification and typed correctness gates

- **Objective (F):** prevent noise or output changes from being promoted as performance progress.
- **Assumptions / constraints (F):** repeated unchanged-baseline runs estimate noise; weights/inputs/baseline predictions recorded before rewriting. Deterministic order/precision-preserving changes require exact elementwise equality. Reordered floating point uses task/dtype bounds; approximations use business metrics; configuration uses a shadow canary at fixed latency SLO.
- **Mechanism (F):** reported E2E baseline spread is ±6%; 2–6% candidate gains get up to8× samples, with claimed 1/sqrt(k) shrinkage to2.1%. Full-stack testing follows local validation.
- **Author evidence (F):** §4.2 describes the protocol; §5 gives accepted cases. Per-kernel bounds are 1e-3 FP32/1e-2 FP16, while end-to-end reorder checks describe 1e-3 absolute deviation (1e-4 FP32) and at most0.1% outside the1e-3 bound; nonfinite results fail. These are this paper's settings, not a universal tolerance prescription.
- **Resource benefit / cost (F/P):** reduced false promotion at added replay cost. No raw no-op distribution, sample counts, autocorrelation analysis, or confidence level for ±6% is reported.
- **Limits / countersignals (P):** 1/sqrt(k) reduction needs a justified noise model; drift and correlated traffic can invalidate it. The stated end-to-end tolerance text needs precise implementation interpretation, especially its threshold and allowed-outlier clauses. Never loosen a user's correctness contract to reproduce a paper threshold.
- **Candidate rule (P):** estimate local paired/repeated uncertainty, preserve run order/load/cache state, and separate indeterminate from rejected. Do not assume8× samples guarantees a2.1% detectable gain. Declare exact-equality, numerical tolerance, approximation-quality and SLO gates before trials.

## F3. Redirect from GPU work to host data movement

- **Objective (F):** remove exposed CPU-side request preparation rather than optimizing only model kernels.
- **Assumptions / decisions (F):** string-heavy Triton input conversion; CPU feature processing with one context row and up to2,000 candidate rows; one pod with12 Python backend processes over14 vCPUs. Features/data ownership must permit views or native lookup.
- **Mechanism (F):** §5.1 converts a Python deserialization path to C++; §5.3 exposes numeric tensors as read-only native views, scans strings in C++, bypasses Python materialization when vocabulary lookup is the only consumer, pre-resolves safe routing with decode fallback, uses Cython for irregular per-element work, and writes features directly into preallocated output slices.
- **Resource benefit / cost (F):** removes Python objects, copies, concatenations and redundant assembly; adds native code and ownership constraints. This is local CPU/memory activity, not evidence for NIC/network optimization merely because inputs came over gRPC.
- **Author evidence (F):** serialization step up to30×, not whole-server30×. Table2 gives call-site speedups, not pod throughput. Table3's cumulative pod throughput progresses940→about1,200→about1,500 requests/s at a fixed latency SLO, overall1.6×; native kernels+assembly are combined in one stage, then zero-copy I/O. Exact SLO value and isolated contribution of the combined pieces are unreported.
- **Limits / countersignals (P):** no independent generalization to arbitrary feature pipelines. Native views require buffer lifetime and immutability checks; shared-memory lookup requires stable vocabulary semantics. Benchmark proof of ownership correctness is not supplied by a high speedup alone.
- **Candidate rule (P):** before a new kernel experiment, inspect serialization/materialization/assembly time shares. Propose views or native preprocessing only when required semantics/lifetimes are established; measure both the component and request-level result with the same pod CPU budget.

## F4. Expose fusion opportunities, then retune serving configuration

- **Objective (F):** reduce redundant graph/kernel work and retune concurrency after bottlenecks move.
- **Assumptions / decisions (F):** §5.2 multi-task recommendation model, AOTInductor, FP16, RTX PRO6000 Blackwell,2,000 candidates/request. §5.4 one GPU partition per pod; sweeps vary model-instance count and dynamic batch size, while queue policy is derived from SLO, not independently searched.
- **Mechanism (F):** precompute candidate-only/position-only attention pieces, fuse six kernels with intermediates retained in registers; decompose opaque embedding-bag into fusion-visible primitives; reuse semantic embeddings across branches. Configuration search replays captured production tensors under held load and validates via shadow canary.
- **Resource benefit / cost (F):** attention traffic falls to roughly one-third; register pressure/fusion eligibility can trade against memory savings. More instances/bigger batches consume memory and can raise tail latency, so neither monotonically improves throughput-at-SLO.
- **Author evidence (F):** §5.2 attention996.5→279.8µs (3.56× module speedup), bit-identical under preserved order/precision. Combined embedding/reuse changes reduce total GPU kernel time33.4%, forward latency30.1%, dispatcher share44.8→28.5%; these are different denominators and the combined gain is not each component's isolated effect. The dominant profile shifts toward GEMM. §5.4 reports >2× throughput variation across configurations of one code-optimized model, not a final2× gain for every model.
- **Limits / countersignals (F/P):** Table4 gives selected trial RPS/p99 but no per-row baseline RPS, so tuning speedup cannot be calculated. ModelB explicitly shows SLO250ms and measured p99=271ms despite the caption saying throughput sustained at SLO; treat compliance as unresolved. Other rows' smaller p99 do not validate this row. No GPU partition dimensions or total fleet-resource normalization is given.
- **Candidate rule (P):** use model semantics to distinguish request-invariant from candidate-varying work. After changing code, reopen instance/batch tuning under unchanged absolute SLO, resource budget and quality constraints. Require every selected trial to pass its own inequalities; never infer SLO compliance from a caption or aggregate gain.


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



# P: shared evidence boundary

Keep analytical physical constraints, measured attainable envelopes and conditional Amdahl impact separate from empirical predictions or heuristic ranks. The existing performance-ceiling-analysis hierarchy is reused, not replaced. A learned runtime is not a physical lower bound; a profiler throughput percentage is not a guaranteed speedup. Queueing, overlap and bottleneck migration invalidate naive summation of component time. The task's own semantic/quality/SLO contract governs; paper thresholds are historical evidence. No local benchmark, installation, hardware measurement, implementation change, matrix edit or promotion was performed.
