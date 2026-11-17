# Vidur: source audit and mechanisms

Status: candidate / empirical_validation: not_run. F = paper fact or author-reported evidence; P = proposed operational use. Source: [Vidur: A Large-Scale Simulation Framework For LLM Inference, 2405.05465v2](https://arxiv.org/abs/2405.05465v2), revised 2024-05-21. [Pinned full text](https://arxiv.org/html/2405.05465v2), [PDF](https://arxiv.org/pdf/2405.05465v2). ID/title/version match verified against arXiv abstract and full text. No implementation audit.

## Exact readset

Full methods §§3–6, including §§4.1–4.5 and §§5.1–5.2; evaluation §§7.1–7.3; Appendix A.1–A.2. Background §§1–2 and related-work/conclusion §§8–9 also read. Table 1 workload definitions and Table 2 cost accounting read in text. All figure captions/discussion 1–8 read; rendered PDF Figures 5–6 (p.11) and 7–8 (p.16) visually checked. Other figures are caption/text-only reads; no values inferred from their unseen pixels. The paper has no numbered cost equations; the quadratic prefill surrogate in §4.3 and the capacity/cost definitions in §6 are unnumbered. No RF-versus-MLP/polynomial ablation or isolated error attribution experiment is reported in the inspected paper.

## V1. Dependency-aware operator models

- **Objective (F):** estimate inference execution across batch composition and parallelization without profiling every sequence-length combination.
- **Assumptions (F):** shared transformer operator families; token-level work depends on current prefill+decode tokens; prefill attention has quadratic sequence-length cost; decode attention depends mainly on total KV reads when the kernel can parallelize across skewed sequences.
- **Decisions / constraints (F):** model shapes, sharded tensor shapes, current token count, per-request context lengths, phase, communication payload and topology. Profile sharded compute shapes on one GPU; communication requires separate topology-specific profiling.
- **Mechanism (F):** §4.3 replaces a prefill batch with an equivalent length sqrt(sum p_i²), models decode by aggregate KV traffic, and separates communication from model-dependent compute. §4.4 uses random-forest interpolation to capture tile/wave discontinuities with sparse profiles.
- **Resource benefit / cost (F):** less hardware profiling; CPU lookup/simulation replaces exhaustive deployment search. Profiling is still required. The random forest and length reduction are empirical approximations, not physical runtime lower bounds.
- **Author evidence (F):** end-to-end fidelity below is evidence for the composite simulator. It does not isolate the marginal accuracy or sample savings of each modeling choice.
- **Limits / countersignals (F/P):** exact training/held-out operator splits, RF uncertainty calibration and coverage boundaries are unreported. The skew-insensitivity argument specifically depends on sequence-parallel attention kernels. Unsupported kernels, model structures, dtypes, graph modes and topologies require new validation; do not extrapolate by model size alone.
- **Candidate rule (P):** attach an input-dependency signature and calibration domain to every predictor. Test unequal-context batches even when total KV bytes match. Mark interpolation, extrapolation and missing-profile states separately.

## V2. Stateful simulation plus constrained shortlist

- **Objective (F):** maximize sustainable QPS per hourly rental dollar subject to latency requirements.
- **Assumptions (F):** workload-specific request lengths/arrivals, modeled batching and memory policies, synchronous pipeline scheduling. Runtime error changes queueing and future batch composition.
- **Decisions / constraints (F):** GPU SKU, TP/PP degrees, replicas, scheduler, batch size and scheduler token budget. §6 defines capacity using P99 scheduling delay under 5 seconds; §7.3 imposes TTFT P90 <2 s and TBT P99 <200 ms. These are study choices, not universal SLOs.
- **Mechanism (F):** global routing → replica batching/KV planner → pipeline-stage scheduling; enumerate configurations and binary-search their sustainable arrival rate, then filter/select on joint SLO and cost. The cost denominator is the hourly rental cost of all GPUs used, not one GPU and not cost per generated token.
- **Resource benefit / cost (F):** simulations parallelize across CPU cores; avoid deploying every candidate. Appendix A.2 projects actual-execution cost for 35,565 search runs rather than reporting those GPU runs as performed. Simulated search took about 12.5 h on a 96-core CPU machine, about $125 under the authors' historical price assumptions. Projected deployment cost is about $1.14M, not a current price quote or measured bill.
- **Author evidence (F):** §7.3's search uses four models, three traces, A100/H100, at most 16 GPUs across replicas; TP and PP each 1/2/4; batch 32–512; vLLM, Orca+ and Sarathi-Serve. Fig.5 shows that the Pareto frontier of one latency metric can violate the other. Fig.1/§7.3 reports up to roughly 2× configuration-transfer cost across workloads.
- **Limits / countersignals (F/P):** default-vLLM fidelity tests do not independently validate every scheduler/PP configuration in the wider simulated search. Synchronous PP support does not establish asynchronous overlap support. Fig.5(b)'s label says Qwen-72B/Arxiv-4K, while §7.3's paragraph names BWB-4K; retain this discrepancy when citing that panel.
- **Candidate rule (P):** use predictions to create a diverse, jointly feasible shortlist and mark close ranks unresolved. Reevaluate after workload drift; measure finalists on the intended implementation and resource budget before promotion.

## V3. Validate at the queueing regime that matters

- **Objective (F/P):** prevent accurate local runtime estimates from creating overconfident service-level claims.
- **Assumptions / decisions (F):** compare four models (LLaMA2-7B/70B, InternLM-20B, Qwen-72B), three length traces capped at 4,096 total tokens, and static versus Poisson arrivals. Fidelity configurations use TP1/2/4 as appropriate and the default vLLM scheduler in an optimized vLLM fork with CUDA graphs and added scheduling/telemetry support.
- **Mechanism / metric (F):** dynamic normalized E2E latency = request latency / output-token count. Static normalized execution latency excludes scheduling delay. Median/P95 are evaluated separately; these are not TTFT or token-tail TBT accuracy claims.
- **Resource benefit / cost (F/P):** the proposed validation gate reduces the risk of selecting a falsely feasible deployment; the paper does not isolate the runtime/cost of this fidelity protocol from profiling and evaluation. This is a proposed risk benefit, not a measured speedup.
- **Resource context (F):** Azure A100 VMs contain four 80-GB GPUs with pairwise NVLink; the described H100 VMs likewise contain four 80-GB H100s with pairwise NVLink. The methods do not qualify an NPU stack.
- **Author evidence (F):** §7.2 reports static P95 error up to 3.33%; at 85% capacity error is below 5% in almost all scenarios. Appendix A.1/Fig.7(d) reports -12.65% P95 normalized E2E error for LLaMA2-7B on Arxiv-4K at 95% capacity. This qualifies the abstract's less-than-9% phrasing. Authors attribute the small-model error partly to CPU overhead, with queue amplification near capacity.
- **Limits (F/P):** component error attribution is an explanation, not an isolated ablation. The paper does not supply a universal safety margin or calibrated prediction interval.
- **Candidate rule (P):** validate operator, iteration, request and queue behavior separately; sample below and near the operating capacity boundary, include host overhead, and refuse SLO certification from an uncalibrated simulator alone.


# P: shared evidence boundary

Keep analytical physical constraints, measured attainable envelopes and conditional Amdahl impact separate from empirical predictions or heuristic ranks. The existing performance-ceiling-analysis hierarchy is reused, not replaced. A learned runtime is not a physical lower bound; a profiler throughput percentage is not a guaranteed speedup. Queueing, overlap and bottleneck migration invalidate naive summation of component time. The task's own semantic/quality/SLO contract governs; paper thresholds are historical evidence. No local benchmark, installation, hardware measurement, implementation change, matrix edit or promotion was performed.
