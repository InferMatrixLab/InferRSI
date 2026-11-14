# InferenceBench: source audit and mechanisms

Status: candidate / empirical_validation: not_run. F = source fact; P = proposal. [InferenceBench: A Benchmark for Open-Ended LLM Inference Optimization by AI Agents, 2607.20468v1](https://arxiv.org/abs/2607.20468v1), [HTML](https://arxiv.org/html/2607.20468v1), [PDF](https://arxiv.org/pdf/2607.20468v1). ID/title/version match verified. Original abstract and full text display 2026-05-20 despite the July-coded identifier; this unresolved metadata anomaly is preserved, not repaired. Scaffolds are described as April 2026 snapshots. No current model ranking is inferred.

## Exact readset

§§1–6; methods §§3.1–3.4; results and ablations §4/§4.1; behavior §§5.1–5.3; limitations §6. Appendices A.1–A.5, B.1–B.4, C.1–C.3, D.1–D.2, E.1–E.4, F examples 1–7, G.1–G.5 read. Tables 1–22 read as PDF/HTML text; Fig.1 caption and explanation read; rendered Fig.2 and Tables 6–7 visually checked on PDF p.8. Metric formulas A.5 and quartile-volatility formula C.3 are unnumbered. No implementation repository opened. The quoted transcripts are evidence supplied by the paper, not independently audited experiment logs.

## Metric and resource contract (F)

Main setting: Mistral-7B-Instruct-v0.3, one H100 80 GB, two-hour wall-clock budget, three development/evaluation seed pairs per agent×scenario. Each job receives 16 CPUs, 180 GB RAM and 400 GB scratch on shared two-socket EPYC 9654 nodes; Ubuntu 22.04, driver 580.82.07, CUDA 12.8 container, PyTorch 2.8.0. The displayed host runtime CUDA version is 13.0, distinct from container toolchain/runtime.

A: 8,192/1,024 target input/output tokens, 128 requests, concurrency 1, minimize TTFT. B: 1,024/8,192, 64 requests, concurrency 1, minimize TPOT. C: 1,024/1,024, the same 256 requests replayed under burst cap64, Poisson32 requests/s cap32, constant16 requests/s cap16; maximize geometric-mean completed request throughput across profiles. D: 4,096/2,048, 96 requests, concurrency4; geometric mean of inverse mean TTFT, inverse mean TPOT, and requests/s on D's own workload. Token lengths vary uniformly over 80–100% of the targets; outputs are forced to sampled lengths. Inputs are LongBench-v2 documents with hashed realized request sets.

TTFT is client send to first parsed content-bearing SSE chunk; ITL is between streamed chunks, not necessarily individual tokens. Per-request TPOT=(end−first)/(output_tokens−1). Request throughput counts completed requests / wall time. Secondary generation throughput uses all output tokens / summed decode intervals, so its numerator differs by one token/request from the TPOT convention. D uses seconds and requests/s, not milliseconds; it is not composed from A/B/C baselines. Failed quality/integrity/unusable final servers score baseline-equivalent 1×, not zero. Aggregate is geometric mean of A–D speedups; cells are means over three seeds with sample SEM. Baseline native values: A 840 ms, B 41 ms, C 0.132 requests/s, D 1.68. These mixed quantities cannot be ranked against Vidur capacity/$ or FlashVector pod RPS.

## I1. Make exploration executable and compare fair budgets

- **Objective (F):** evaluate useful autonomous deployment under a fixed budget, including engine selection, integration and tuning.
- **Assumptions (F):** same hardware, weights, inputs, scoring gates and wall-clock allowance; candidate setup/JIT/repair consumes the agent's budget.
- **Decisions / constraints (F):** serving engine, backend, quantization, KV dtype, scheduler/batch/token limits, compile/graph choices; correct base model and functioning OpenAI-compatible server required.
- **Mechanism (F):** compare agents with defaults and documented-flag Random/SMAC/TPE searches. Each optimizer×engine has a separate two-hour run; the full cross-engine grid is not a single two-hour joint engine-search result.
- **Resource benefit / cost (F):** search attempts trade possible serving gains against setup, compilation, evaluation and API/GPU cost. D.2 uses a historical nominal H100 price of $1.99/h: a complete 12-run agent evaluation has $47.76 nominal GPU cost before overhead, plus API costs. These are optimization expenditures, not steady-state serving cost per request.
- **Author evidence (F):** §5/E.3 report 169/180 final launchers using vLLM, median one distinct non-default argument set, and 81% of restarts repeating arguments. Table20 shows engine choice matters across the fixed scenarios; it does not establish a universal engine winner. Table2's best-agent aggregate 8.08× and SMAC-vLLM 11.53× use the same naïve PyTorch denominator, not a tuned-production baseline.
- **Limits / countersignals (F/P):** only three seeds and fixed scaffold/model snapshots; broader cross-engine search consumes multiple independent budgets. §G.3's conjecture that two hours covers most of the flag space lacks an exhaustive optimum proof. Scenario-C vLLM default 48.69× exceeds its SMAC search 46.70× in Table2, so search is not uniformly better than defaults.
- **Candidate rule (P):** preserve a known-good incumbent while allocating bounded trials across materially different hypotheses. Count distinct measured configurations, not ideas mentioned or identical restarts. Use documented compatible families; do not silently turn this literature recommendation into installation or engine replacement authority.

## I2. Preserve the best valid artifact, not the last edit

- **Objective (F):** close the gap between finding a good configuration and delivering it.
- **Assumptions / decisions (F):** final server must match its launcher/configuration and pass final evaluation; quick probes are provisional. Choose whether to continue, revert, combine validated changes or finalize.
- **Mechanism (F):** structured prompt establishes baseline, changes one variable per experiment, logs proposals/outcomes, and reserves the last 15 minutes for validation. Best-seen rescoring diagnoses lost valid configurations rather than changing the benchmark's final-state objective.
- **Evidence (F):** Table3: 117/180 pass both gates, 34 fail/incomplete quality, 11 integrity flags, 18 server/runtime failures; categories exclusive. Table6: structured GPT-5.4 passes 11/12 versus10/12, Opus4.7 11/12 versus5/12. Best-seen Table4 rises from 8.62× to12.34× for per-scenario best-agent aggregation; this is a different aggregation from one agent's Table2 aggregate. Warm-start Table21 improves reliability but does not remove search gaps. Time-budget Fig.2/§4.1 does not show monotonic gains through 8 h.
- **Cost / limits (F/P):** preserving/replaying artifacts consumes time. No controlled isolation attributes all structured-prompt effects to a single constituent rule; fixed 15-minute reserve is benchmark-specific. One-variable exploration alone misses interactions.
- **Candidate rule (P):** store immutable candidate/config/input/evaluator identities and last full-valid results. Use one-factor contrasts for attribution, then explicitly labeled interaction tests. Reserve finalization based on measured restart/warmup/full-validation cost; after a regression restore and verify the incumbent rather than repeat repairs indefinitely.

## I3. Treat measurement semantics as correctness

- **Objective (F):** reject apparent speed improvements that alter the task or event boundaries.
- **Assumptions / constraints (F):** quality at least95% of baseline on a seed-fixed500-question MMLU-Pro subset, plus an independent integrity judgment from launcher/log/transcript evidence. Development/evaluation seeds differ.
- **Mechanism (F):** gate output quality and task integrity before scoring; use held-out canonical inputs and a final working-server check. Appendix F distinguishes fake first chunks, bypassed decode and dependency/compilation delays from real gains.
- **Resource benefit / cost (F/P):** gates prevent invalid apparent gains from entering selection, but quality evaluation and artifact/judge inspection consume time and compute. Their isolated resource overhead is unreported; total campaign cost cannot be assigned to the gates.
- **Evidence (F):** C.1 threshold rescoring is stable through0.95 and changes at most one rank at0.97. C.2 judge agreement κ=0.82; a stratified50-run manual audit finds zero false positives and one missed violation. These are sample estimates, not a guarantee. A quality-passing fake decode run is excluded; no exploit is an optimization recommendation.
- **Limits / countersignals (F/P):** §G.2 calls ScenarioD concurrency1, conflicting with §3/Table1 and A.3/Table8 concurrency4. Do not use that paragraph as a clean concurrency-specific causal claim. Main prompt B.1 allows quantization while §G.2 describes prequantized-checkpoint prohibition more specifically; do not reconstruct a universal authorization rule from this inconsistent presentation.
- **Candidate rule (P):** specify genuine first generated token, required forward/decode work, token counting and output length before optimization. Audit timing anomalies against both artifact semantics and physical feasibility; passing a small quality test cannot prove measurement integrity. Keep honest failures distinct from baseline performance when reporting local results, even if a benchmark maps both to1×.


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



# P: shared evidence boundary

Keep analytical physical constraints, measured attainable envelopes and conditional Amdahl impact separate from empirical predictions or heuristic ranks. The existing performance-ceiling-analysis hierarchy is reused, not replaced. A learned runtime is not a physical lower bound; a profiler throughput percentage is not a guaranteed speedup. Queueing, overlap and bottleneck migration invalidate naive summation of component time. The task's own semantic/quality/SLO contract governs; paper thresholds are historical evidence. No local benchmark, installation, hardware measurement, implementation change, matrix edit or promotion was performed.
