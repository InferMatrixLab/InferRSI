# FastServe exact source and readset

Status: candidate. Empirical validation: not_run. Read date: 2026-10-15 UTC.

## Identity and version

Bingyang Wu, Yinmin Zhong, Zili Zhang, Shengyu Liu, Fangyue Liu, Yuanhang Sun, Gang Huang, Xuanzhe Liu, Xin Jin. *Fast Distributed Inference Serving for Large Language Models*.

- [Pinned arXiv record](https://arxiv.org/abs/2305.05920v3), [pinned PDF](https://arxiv.org/pdf/2305.05920v3), [HTML](https://arxiv.org/html/2305.05920v3).
- Original-source history checked: v1 10 May 2023; v2 21 Sep 2024; **v3 25 Sep 2024 05:57:51 UTC**. Extracted the v3 full PDF, not v1 or unversioned code.
- PDF SHA256: `f3cc10d868e0430bbabc063a9bec25ce5b826134ab876de14958a955c3bc7498`.

## Actual readset

Read §§1–3 (definitions/problem/objective), §§4.1–4.3 in full (policy, memory model, ENST equations, burst reservation, distributed coordination), §5 historical implementation, §§6.1–6.3 in full (methods/end-to-end/design ablations), and §7's relevant comparison/lead paragraphs. Read Algorithm 1, Tables 1–2, and all captions/associated text for Figures 1–15. Visually inspected PDF p. 8 (ENST equations/Figs. 9–10), p. 11 (Figs. 12–14), and p. 12 (Fig. 15). No coordinates were digitized. No author code was needed or inspected.

## Exact locators and interpretation

- F1: §2.3 pp. 4; §4.1 pp. 5–6, Figs. 5–7, Algorithm 1; §6.3 pp. 11–12/Fig. 14. Fig. 5 is a motivation microbenchmark, **OPT-2.7B on one A100**, not validation of the later OPT-13B profiler on arbitrary contexts. Minimum initial queue condition: `q_i >= t_init`.
- F2: §4.1 p. 6, Algorithm 1 lines 18–21; §6.2 p. 11/Fig. 12. Algorithm 1 mentions `alpha`; prose says threshold tuning follows the user-specified SLO, set to 300 ms by default. No formal starvation theorem or per-tenant fair-share objective is given.
- F3: §4.2 pp. 6–8, FP16 state bytes `4*l*h*(s+t)`, Fig. 8 (Gamma arrival process), three unnumbered ENST equations, Fig. 9; §6.3 p. 12/Fig. 15. The OPT-175B illustration quotes ~2.3 GB state, ~60-ms token time and ~36-ms PCIe swap time; these are paper examples with specific state/layout/assumptions, not a calibrated universal transfer model.
- F4: §4.3 pp. 8–9/Fig. 10; §6.1 pp. 9–10/Tables 1–2; §6.2 pp. 10–11/Figs. 11–13. The single-device ablation context must not inherit the 16-GPU end-to-end hardware.

## Cost-model caution

**F:** ENST selects the earlier of starvation-promotion time and estimated higher-priority service. The latter sums queue quanta and divides by maximum batch size. Higher-priority jobs are assumed not to finish before demotion to the target priority. It is a heuristic residency ranking, not a proof of completion latency or a tail admission guarantee.

**P reading caution:** The printed summation uses `i.priority < k <= j.priority` and `i.priority < j.priority` while §4.1 numbers Q1 as highest and describes demotion to larger queue indexes. The numeric priority/index convention is therefore not safe to transcribe literally. Algorithm 1 also switches input-set names (`Jnew` versus `Jin`) and does not fully define the demotion offset or every state transition. Preserve the prose policy; any future implementation needs current-code/semantic clarification. These observations are textual ambiguities, not measured implementation bugs.

## Evaluation ledger

**F hardware/model:** End-to-end (§6.2): two AWS p4d.24xlarge nodes, each eight A100-40GB GPUs with NVLink, 1152-GB host memory and PCIe 4.0×16. FP16 OPT-13B, 66B and 175B; Fig. 11/12 GPU counts 1/4/16. Design choices (§6.3): one A100-40GB in authors' own testbed. Cross-node bandwidth is not quantified in the inspected setup; do not fill it from vendor specifications.

**F workload/baselines:** ShareGPT and Alpaca lengths with synthesized Poisson arrivals; unlike Orca, input/output length distributions come from those datasets. FasterTransformer v5.3; vLLM v0.1.7; FastServe-FCFS uses FastServe's execution engine without proposed §4 techniques. Parallel/batch configurations are matched except vLLM's 175B case uses TP only because its then-tested version lacks PP. Exact TP/PP degree pairs are not reported in the inspected setup text; do not infer TP8/PP2 solely from node count.

**F metric:** Figures 11 and 12 use mean and P95, respectively, of request end-to-end latency divided by output tokens (s/token). A 0.3-s/token target is used, described as 10× a profiled decode iteration. This includes queueing and prefill; it is not raw decode iteration latency or token-tail TBT. Headline ratios compare maximum request rates meeting that target, not all-completion throughput without a latency constraint.

**F quantitative evidence kept with denominators:**
- Fig. 11/§6.2: ShareGPT throughput at target improves 2.3–18.3× versus vLLM and 2–4× versus FastServe-FCFS across model configurations. Alpaca corresponding ranges are 3–31.4× and 1.6–2×. Maxima across models are not additive or attributable solely to scheduling.
- Fig. 12/§6.2: P95 normalized target, ShareGPT, FastServe-FCFS comparison up to 1.5× for 175B/16 GPUs and 2–2.8× for 13B/66B. Up to 17.9× versus vLLM is a different baseline comparison.
- Fig. 13/§6.2: OPT-13B, joint initialization/decoding **95% request attainment** targets scaled 5×/10×/20× their respective light-load phase latencies. Labeled request/s at 95%: vLLM 0.63/0.64/0.76; FastServe-FCFS 1.77/1.83/2.05; FastServe 2.59/3.01/3.15. The paper does not explicitly restate the dataset for this figure in that paragraph, so do not silently supply it. Exact phase-latency threshold values and whether the decode constraint is mean TPOT versus another statistic are not fully specified there. Do not equate with DistServe's fully specified joint metric without clarification.
- Fig. 14/§6.3: ratio sensitivity, OPT-13B/one A100, ShareGPT-derived lengths. Text says normalized to the slowest system; axis still says s/token. Interpret bars as normalized comparisons, not absolute latency.
- Fig. 15/§6.3: OPT-13B/one A100, ShareGPT, proactive versus reactive/recompute. Author ratios 1.7×/2.7× lack a single specified comparison point in the prose. Blocked swapping <5% of end-to-end latency is author-reported; total transfer duration/bytes remain separate. Low-load policies are similar.

## Unreported versus negative

Profiling error, ENST error, reserve-slot sensitivity, isolated starvation-promotion ablation, per-tenant fairness, maximum waiting-time bounds, failure recovery and current implementation behavior are unreported in this read evaluation. The low-load no-advantage result for proactive swapping is reported. The strawman recompute/promotion ping-pong scenario is a design warning, not evidence that every recompute policy deadlocks.

## Unread next-gate lead

**Lead only, not opened/read:** Sheng et al., *Fairness in Serving Large Language Models* (VTC), OSDI 2024, FastServe §7/bibliography [52], PDF pp. 12 and 15. If a future authorized gate requires tenant/service fairness beyond starvation mitigation, inspect this source before proposing a fairness guarantee. No findings from it are included here.
