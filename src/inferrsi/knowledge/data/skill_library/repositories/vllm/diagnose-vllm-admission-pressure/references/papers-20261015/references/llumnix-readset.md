# Llumnix pinned readset and source evidence

Status: candidate; empirical validation: not_run. Audit date: 2026-10-15 UTC. F = paper fact/author report; P = proposed interpretation. No code, repository, kernel, framework, or current hardware compatibility was investigated.

## Identity and provenance

- **F:** Biao Sun et al., *Llumnix: Dynamic Scheduling for Large Language Model Serving*, **arXiv:2406.03243v1**. [Version/history record](https://arxiv.org/abs/2406.03243v1), [full PDF](https://arxiv.org/pdf/2406.03243v1), [full HTML](https://arxiv.org/html/2406.03243v1).
- arXiv submission history read directly: **v1, Wed 5 Jun 2024 13:20:18 UTC**. This was the only version listed at audit. PDF first-page version stamp independently matches v1/5 June 2024. PDF SHA256: `c76d726aced3e5d24920b10259938922d37ebcb3b8d80b89d9bb9550e4bdf97a`.
- Source PDF/HTML/plaintext and page-render caches are held outside the deliverable tree. They are not bundled as authored work.
- Existing scheduling and KV synthesis plus their source-notes were read first to identify the new cross-instance decision boundary. Prior Sarathi-Serve, DistServe, PagedAttention, and Mooncake papers were not re-extracted.

## Actual-read ledger

Read full relevant text of §§2–3 (background and motivation, PDF pp. 3–4); §§4.1–4.4.3 (pp. 5–8); §5 (pp. 8–9); §§6.1–6.6 (pp. 9–13). Read §7's discussion of local preemptive/fair scheduling and multiple-model future work (pp. 13–14), and Appendix A's artifact/release distinction (p. 19). The abstract/introduction was consulted for identity and scope, not used to replace method/evaluation reading. Only targeted bibliography entries were checked.

Specific objects read: Algorithm 1; unnumbered freeness formula in §4.4.3; Table 1; Figs. 2–16 captions and accompanying explanations. Visually inspected PDF p. 8 (Algorithm 1 and scheduling policy), p. 10 (Fig. 10 and numerical migration discussion). Chart coordinates were **not digitized**. Large figure-page text was read through extracted text and result prose; claims below use author-reported numbers. No appendix reproduction commands were executed.

## Mechanism locators

- **L1:** [§4.2](https://arxiv.org/html/2406.03243v1#S4.SS2), PDF pp. 5–6, Figs. 6–7. Pre-copy immutable KV while decode proceeds; per-stage destination allocation; abort on full destination/completion/preemption/failure; final stop and commit. [§5](https://arxiv.org/html/2406.03243v1#S5), pp. 8–9: host-buffer block fusion and Gloo transport. [§6.2](https://arxiv.org/html/2406.03243v1#S6.SS2), p. 10/Fig. 10: migration microbenchmark.
- **L2:** [§4.4.2](https://arxiv.org/html/2406.03243v1#S4.SS4.SSS2), p. 7, and [Algorithm 1](https://arxiv.org/html/2406.03243v1#algorithm1), p. 8: physical-plus-virtual usage, head-of-line demand, freeness. [§4.4.3](https://arxiv.org/html/2406.03243v1#S4.SS4.SSS3): dispatch/pair/select/stop policy. [§6.3](https://arxiv.org/html/2406.03243v1#S6.SS3), pp. 10–12/Figs. 11–12: results and fragmentation case study.
- **L3:** §4.4.1's separate scheduling/execution priorities; §4.4.2 headroom; Algorithm 1 lines 8–10. [§6.4](https://arxiv.org/html/2406.03243v1#S6.SS4), p. 12/Fig. 13: high/normal-class tradeoff.
- **L4:** §4.4.2 fake infinite-usage request and §4.4.3 scaling policy; [§6.5](https://arxiv.org/html/2406.03243v1#S6.SS5), pp. 12–13/Figs. 14–15: instance-cost/latency tradeoff.
- **Coordination:** [§4.3](https://arxiv.org/html/2406.03243v1#S4.SS3), p. 6/Fig. 8: global scheduler manages instance-level loads/pairs, local llumlets select requests and execute migrations. [§6.6](https://arxiv.org/html/2406.03243v1#S6.SS6), p. 13/Fig. 16 is a separate **simulated GPU-execution scheduling stress test**, not a measured 64-GPU serving deployment.

## Evaluation setup and denominators

**F, §6.1/Table 1:** Four Alibaba Cloud machines, each four **A10 24GB** GPUs connected through **PCIe 4.0**, 128 vCPUs, 752GB host RAM, **64 Gb/s network**. FP16 LLaMA-7B uses one GPU; LLaMA-30B uses TP4 within one machine. Main serving is sixteen 7B instances; 30B is used in the migration study. All compared schedulers share the historical vLLM engine.

The baseline is **INFaaS++**, modified by these authors to use GPU-memory load including waiting prompt demand; it is not simply stock INFaaS. Llumnix-base retains migration but removes priority differentiation. Round-robin is reported on real length distributions and omitted on generated distributions after very poor observed behavior.

Traces have **10,000 requests** with synthetic Poisson or Gamma arrivals. ShareGPT/BurstGPT supply length distributions, not the arrival timestamps. Synthetic S/M/L lengths have means 128/256/512 and maximum 6K per input/output draw. The paper acknowledges its historical backend's original-LLaMA 2K-position support while arguing systems representativeness for longer-context variants. This is an author extrapolation, not a demonstrated long-context quality/compatibility result.

Metrics: mean and P99 **request end-to-end**, **prefill/first-generated-token**, and **request-average decode** latency. Decode time is from first to last generated token, averaged over generated tokens. P99 is a percentile of this per-request average, **not P99 inter-token latency**. Preemption loss includes extra queuing plus recomputation. No joint TTFT/token-tail goodput objective is established.

### E1 State movement

§6.2/Fig. 10: two instances on different machines; equal total batch length 8K on each side, one request moved; request sequence sweep 256/512/1K/2K/4K/8K. The 20–30 ms is **migrated-request downtime**, not total copy duration. Comparators: recompute and Gloo stop-and-copy, the latter nonblocking for unrelated requests. Authors report up to 111× lower downtime and 3.5 s 8K/30B recompute. All measured migrations required exactly two stages. Source decode overhead ≤1%; destination “mostly similar” is prose, not a separate plotted series. Serving runs have migration active roughly 10% of each instance's time on average; do not multiply this into an unreported universal overhead guarantee.

### E2 Load/fragmentation

§6.3/Fig. 11: on real datasets versus INFaaS++, maximum mean/P99 prefill improvements **2.2×/5.5×**, P99 decode **1.3×**. Generated distributions: mean/P99 end-to-end **1.5×/1.6×**, mean/P99 prefill **7.7×/14.8×**, P99 decode **2×**. These are maxima across experiments, not a single matched operating point. Preemption loss reduction **70.4% average** (about **1.3 seconds** average request-latency contribution) compares against INFaaS++; separate **84%** average on real traces compares against round-robin.

Fig. 12's M-M at 7.5 req/s case defines fragmented bytes as free cluster bytes that could satisfy whole blocked head-of-line demands if pooled; divides by cluster total memory. Busy-window averages **0.7% Llumnix, 7.9% INFaaS++**, labeled **92% reduction** by authors (rounded inputs need not reproduce the percentage). This is not physical allocator internal-fragmentation rate, and it is not an all-run mean.

### E3 Priority, cost, scalability

§6.4/Fig. 13: 10% random high-priority fraction, S-S lengths, Gamma burstiness CV sweep; headroom chosen to target 1,600-token memory load. High-class mean request improves 1.2–1.5×; mean/P99 prefill 2.9–8.6×/3.6–10×; mean/P99 request-average decode 1.2–1.5×/1.3–2.2×. Comparator Llumnix-base uses the same migration infrastructure. Measured normal-class mean penalties reach **4.5% end-to-end, 13% prefill, 2% decode**.

§6.5/Figs. 14–15: L-L lengths, maximum 16 instances, default freeness thresholds [10,60], same scaling strategy for INFaaS++. Fixed policy gives up to 16% (Poisson-rate sweep)/18% (Gamma CV, rate 2) reduction in **average active instance count**. Sweeping thresholds [t,t+50] gives roughly 5 s P99 prefill at **36% cost saving**; Fig. 15 labels **36.49%**. Avoid claiming GPU-hour dollar savings with billing/startup details absent.

§6.6/Fig. 16: simulated 64-instance test replaces GPU execution with sleeps from offline A10 profiles; requests have input/output lengths 64. Centralized vLLM-derived scheduler stalls up to 40 ms/iteration, 1.7× slowdown; Llumnix's stalls described as near-zero. This supports the scheduler decomposition only under the simulator's scope.

## Limits and proposal boundaries

- **F:** Appendix A distinguishes the evaluated vLLM-based, **not fault-tolerant** artifact from the standalone/fault-tolerant release described in §5. Never attach evaluated fault-tolerance evidence to §5 solely because it appears in the same paper.
- **F:** §7 explicitly leaves combination with local preemptive/fair scheduling and support for multiple model types for future work.
- **Unreported:** starvation bounds, tenant-weighted service accounting, migration concurrency/catch-up across arbitrary networks, quantitative recovery testing, source/destination reservation worst cases, empty-instance B=0 semantics in the paper pseudocode, and present-day accelerator/NPU support.
- **P:** Turn L1–L4 into measured go/no-go gates, not automatic mutations. Read current implementation/configuration only under a separate task. Memory-load symmetry, acceptance thresholds, operational SLOs, and fairness budgets are deployment choices, not paper-certified defaults.
