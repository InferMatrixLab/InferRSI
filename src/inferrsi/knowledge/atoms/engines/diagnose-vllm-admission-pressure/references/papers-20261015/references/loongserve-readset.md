# LoongServe pinned readset and source evidence

Status: candidate; empirical validation: not_run. Audit date: 2026-10-15 UTC. F = paper fact/author report; P = proposed interpretation. This is historical design extraction, with no repository, framework, kernel, or hardware changes and no current-code compatibility conclusions.

## Identity and provenance

- **F:** Bingyang Wu et al., *LoongServe: Efficiently Serving Long-Context Large Language Models with Elastic Sequence Parallelism*, **arXiv:2404.09526v2**. [Version/history record](https://arxiv.org/abs/2404.09526v2), [full PDF](https://arxiv.org/pdf/2404.09526v2), [full HTML](https://arxiv.org/html/2404.09526v2).
- arXiv history directly read: **v1, Mon 15 Apr 2024 07:45:04 UTC; v2, Tue 29 Oct 2024 13:04:42 UTC**. v2 was the last version listed at audit. PDF first-page stamp matches v2/29 October 2024. PDF SHA256: `d5ae35fa9a1645af42fd2760eb5ff423d5c994eed846e171602a5a14133e1401`.
- PDF/HTML/text/render caches remain outside the deliverable tree. No paper text, executable artifact, or reproduction script is bundled as new work.
- Existing scheduling/KV notes and source-notes were inspected first. This completes the LoongServe lead previously left unread by the Mooncake extraction; that earlier source was not re-extracted.

## Actual-read ledger

Read §§2.1–2.4 (PDF pp. 2–4); §3 (pp. 4–5); §§4.1–4.2 (pp. 5–7); §§5.1–5.5 (pp. 7–9), including all Equations 1–7; §6 (pp. 9–10); §§7.1–7.4 (pp. 10–13). Read §8's distinctions among serving/sequence-parallel/training mechanisms and accuracy-reducing approaches (p. 13). Abstract/introduction checked for scope, not as the evidence substitute. No second-paper expansions or repository inspections were performed.

Objects examined: Figs. 1–15 captions and accompanying methods/result prose; Equations 1–7, including both split-point inequalities in Eq. 6. There is no numbered algorithm/table providing additional empirical results in these sections. Visually inspected PDF p. 6 (proactive migration and buffer expression), p. 8 (Equations 1–4), p. 9 (Equations 5–7), p. 10 (Fig. 10 and testbed), p. 12 (Figs. 13–14), p. 13 (Fig. 15 and scaling/model-accuracy statements). Did not digitize chart coordinates. Fig. 12 ratios are retained only as author prose, with comparator ambiguity noted below.

## Exact mechanism locators and equation audit

- **G1:** [§4.1](https://arxiv.org/html/2404.09526v2#S4.SS1), PDF pp. 5–6/Fig. 7: proactive retention of KV during sequence-parallel prefill. Reactive placement needs per-instance intermediate KV capacity of order O(b·l·s·h/d), whereas the reused per-layer buffer is O(b·s·h/d). The first is persistent all-layer state, the second a transient layer buffer; do not claim all KV has been reduced to one layer.
- **G2:** [§4.2](https://arxiv.org/html/2404.09526v2#S4.SS2), pp. 6–7/Fig. 8: single-master then multi-master distributed decode. Queries/partial attention move; old KV need not. [§5.4](https://arxiv.org/html/2404.09526v2#S5.SS4), p. 9: fixed model-parallel base chosen at launch; smallest feasible decode ESP group after prefill; batch-size threshold for compute-driven expansion; multi-master assignment aims to balance new state.
- **G3:** [§5.1](https://arxiv.org/html/2404.09526v2#S5.SS1), pp. 7–8: FCFS candidate selection, user-maximum future KV check, profiled batch saturation, and possible prefill/decode interference.
  - [Eq. 1](https://arxiv.org/html/2404.09526v2#S5.E1): sum over affected decoding requests of predicted enlarged prefill runtime divided by that request's **existing generated output-token count**.
  - [Eq. 2](https://arxiv.org/html/2404.09526v2#S5.E2): sum over additional prefill requests of positive-part `(mean completed decode duration − minimum elapsed decode duration in affected batch)` divided by each input length. Gain exceeding cost permits extra dispatch.
  - **P caution:** These are approximate latency-normalized aggregate objectives, not exact completion predictions or deadline constraints. Zero-output-length handling is not specified in the equation presentation; no implementation bug is inferred.
- **G4:** [§5.2](https://arxiv.org/html/2404.09526v2#S5.SS2), p. 8: allocate idle instances, then potentially reclaim occupied ones while relocating old KV. [Eq. 3](https://arxiv.org/html/2404.09526v2#S5.E3) sums prefill-runtime savings divided by input length. [Eq. 4](https://arxiv.org/html/2404.09526v2#S5.E4) sums `resident_KV_bytes / (average_bandwidth × input_length)`. Receiver choice favors free slots. This optional decode shrink is not the no-extra-migration mechanism of §4.1.
- **G5:** [§5.3](https://arxiv.org/html/2404.09526v2#S5.SS3), pp. 8–9/Equations 5–6: length-sorted batching and instance partitions, fit constraints, DP split monotonicity. The paper calls T an iteration-time estimator in §5.1, but the DP's T over a partition is described as the **sum of input latencies** for requests in that partition. Preserve this distinction; the prose does not supply a complete reusable implementation contract for the transition/base cases.
  - [§5.5/Eq. 7](https://arxiv.org/html/2404.09526v2#S5.E7), p. 9: `T_p(R)=α_p+β_p Σ_r L_r+γ_p Σ_r L_r²`. Different parallelism choices have separately fitted coefficients. This is **sum of squared lengths**, not square of summed length.
- [§6](https://arxiv.org/html/2404.09526v2#S6), pp. 9–10: token-granularity PagedAttention-style GPU pool, adjusted StripedAttention/Flash-Decoding kernels, NCCL point-to-point groups and separate communicators/streams for TP and SP. This describes the historical implementation, not general evidence for today's NCCL behavior or NPU portability.

## Hardware, workloads, baseline identities, and metric denominators

**F, §7.1:** LWM-1M-Text, architecture matching **Llama-2-7B**. Each server: **8×A800 80GB**, 128 CPUs, 2048GB host RAM, four **200-Gbps InfiniBand NICs**; stated two-GPU NVLink bandwidth **400GB/s**. Most results use one server; §7.3 uses two. Historical stack: PyTorch 2.0.0, CUDA 12.2, Triton 2.1.0, tokenizers 0.15.2. These are evaluated settings, not installation recommendations.

Input/output lengths are sampled from real datasets; timestamps are synthesized with **Poisson arrivals**. Reported total sequence-length ranges: ShareGPT **4–2.3K**, L-Eval **2.7K–210.5K**, LV-Eval **15.1K–497.3K** tokens. Mixed samples the three datasets equally. Dataset realism does not establish real burstiness or production multi-tenant distribution.

Single-node configurations:
- LoongServe: **TP2, up to ESP4**, meaning four elastic instances with two GPUs each; each instance has its own model replica.
- vLLM: TP8; footnote 1 specifies 0.3.0 and commit `1af090b57d0e23d268e79941f8084bf0a8ad8621`.
- DeepSpeed-MII: TP8; footnote 2 `773b735d6294a98dd842d82ef024d0d9b050f66aa`; only ShareGPT because inputs above 32K hit an author-observed illegal-memory-access error.
- LightLLM SplitFuse: TP8; chunk size uses the dataset's calculated “ideal P:D ratio,” which authors acknowledge is unknown in practice. This gives the baseline oracle-like dataset tuning; it is not a tested Sarathi-Serve implementation.
- DistServe: four TP4 prefill GPUs and four TP4 decode GPUs, chosen by its simulator and validated on this testbed; authors obtained source from its authors. PDF footnote 3 is typographically placed by the LightLLM bullet but labels **DistServe** and gives `e2b5168a50f24d960ead314b0649428e35381f80`; do not misattribute that revision to LightLLM. No repository was fetched to resolve the marker mismatch.

Metrics (§7.1): **mean of request end-to-end latency / sequence length**, **mean prefill time / input length**, and **mean decode time / output length**. Compare maximum request rates meeting a latency SLO described as **25× inference latency**. The inspected text does not supply a complete per-workload absolute-seconds threshold table or an equivalent joint TTFT/P99-TBT objective. Figure 10 uses normalized axes and threshold lines. Do not label its throughput results as DistServe's original joint goodput metric. §7.4 separately evaluates **P90 goodput**, using SLO-attainment curves and 90% target.

## Numerical evidence register

**E1, §7.2/Fig. 10:** Eight GPUs each, same long-context model, dataset-specific load sweeps. Whole-system maxima: total/input throughput **4.64×/4.00× vs vLLM**, **3.85×/3.37× vs the tested chunked-prefill systems**, **5.81×/3.58× vs tested DistServe**. Prose states maxima across conditions; it does not identify one common workload/load point for all. Output-latency curves improve, but these throughput values are based on normalized metrics.

DistServe OOMs for the LV-Eval/Mixed experiments because each phase has only four GPUs, and is absent in those rows. This is a reported failed historical baseline condition, distinct from **unreported** performance elsewhere. DeepSpeed-MII's >32K failure is also limited to the tested version/configuration. Neither establishes today's compatibility.

**E2, §7.3/Fig. 11:** Two servers/16 A800s, Mixed workload. LoongServe keeps TP2 and extends ESP to eight instances. Baselines deploy their same single-node configuration per server. Max total/input throughput ratios: **1.86×/1.72× vs vLLM**, **3.37×/3.11× vs LightLLM SplitFuse**. This is not a one-node versus two-node scaling-efficiency ratio or a benchmark on weak network links.

**E3, §7.4/Fig. 12:** Mixed sampled with Zipf parameters **1.0/1.2/1.4**, capped at **200K total tokens** because replicated TP2 baseline cannot fit longer requests. Compare full LoongServe against TP8, static TP2+SP4, and four replicated TP2 instances. Prose reports P90-goodput improvements **2.33×/1.98×/1.53×** under the three distributions but does not explicitly map each ratio to a named static comparator. Do not assign an exact denominator without separately resolving chart intersections. This ablation changes the overall elastic strategy, not only G3/G4/G5 independently.

**E4, §7.4/Fig. 13:** ShareGPT, one node, elasticity-enabled versus **same LoongServe without elastic scale-up**: **2.87× P90 goodput**. At 25 req/s, average **7.12 scale-ups per 10 seconds** over plotted observation interval. These are two different denominators: SLO-constrained rate and event count per wall-clock time.

**E5, §7.4/Fig. 14:** Forward-time microbenchmarks; plotted `(batch size, length)` pairs are `(1024,10), (256,100), (64,1K), (16,10K), (4,50K), (2,100K), (1,200K)`. Prefill with/without proactive scale-down: author-reported overhead **<2%**. Decode with one/two/four masters: up to **2×** lower iteration latency at large batch, author-reported **<10%** overhead at small batch. These are normalized forwards, not end-to-end request tails, and do not show every possible batch/length Cartesian combination.

**E6, §7.4/Fig. 15:** Prefill analytical model, SP2TP4/SP4TP2/SP8TP1, batch sizes **1/2/4/8**, plotted long input lengths: authors report **<10% deviation**. Held-out split, full error distribution, uncertainty bounds, calibration drift, and congestion-conditioned accuracy are **unreported**. This is evidence of fit in the evaluated settings, not a guaranteed 10% error bound for scheduling decisions.

## Boundaries and negative-versus-unreported register

- **Measured counter-signals:** small-batch extra-master overhead; tested DistServe/MII OOM/kernel failures; phase allocations restrict some baselines. Preserve them with historical settings.
- **Unreported rather than negative:** formal fairness/starvation bounds; per-tenant priority guarantees; isolated admission/DP/shrink-policy ablations; real burst arrival traces; absolute token-tail SLO guarantees; quantitative end-to-end control-plane scheduling-time tails; cold-start costs; general congestion robustness; NPU tests.
- **P:** Source assertions that model accuracy is unchanged and that MQA/GQA/MoE are compatible are not per-architecture benchmark results. Dynamic model-weight repartitioning is not demonstrated; TP is fixed inside the elastic instance.
- **P:** Maintain separate budgets for target KV residency, per-layer temporary storage, extra migration, unavoidable SP communication, and scheduling time. Claims from G1/G2 cannot be generalized to every resize event. No new paper expansion is needed for this extraction; future current-code/portability work requires a separate scope and authorization gate.
