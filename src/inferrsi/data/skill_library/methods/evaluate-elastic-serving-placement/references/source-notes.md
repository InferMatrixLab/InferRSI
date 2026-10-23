# Self-contained source notes

Status: candidate. Empirical validation: not_run. These are the same authored historical-paper evidence notes supplied in the Pack B notes/readsets, included here so this skill can be consumed on its own. F facts and P proposals remain separately labeled. No paper source files or implementation artifacts are bundled.


# Llumnix: migration is a scheduling primitive, not free capacity

Status: candidate paper synthesis; empirical validation: not_run. **F** = historical paper fact or author-reported measurement. **P** = proposed operational interpretation requiring separate validation. Source: Sun et al., *Llumnix: Dynamic Scheduling for Large Language Model Serving*, [arXiv:2406.03243v1](https://arxiv.org/abs/2406.03243v1), 5 June 2024. Exact methods, read coverage, metric definitions, and context are in the readset (included below).

## New decision boundary relative to the existing material

**F:** Llumnix retains continuous batching and device-block allocation, but adds request movement between already-deployed instances of the same model. Its principal new choices are **where a running request resides**, **whose memory pressure to relieve**, and **when to drain/activate an instance**. It does not dynamically repartition model weights or introduce LoongServe-style sequence-parallel groups.

**P:** Add a migration gate after diagnosing whether unused capacity exists elsewhere. This fills a cross-instance scheduling gap without repeating the prior chunked-prefill, phase-separation, or PagedAttention explanations. Do not use the OS analogy as evidence for operating-system tuning. A memory reservation below is virtual accounting, not an independent physical memory pool.

## L1 Live transfer instead of stop-and-copy or recomputation

- **F objective → assumptions:** Reduce service interruption during relocation. Earlier KV is immutable and append-only; a compatible destination already has the model; transfer must catch up with newly generated state.
- **F variables/constraints → mechanism:** Choose source/destination/request and migration stages. Copy completed-token KV while source decode continues; copy the small newly appended suffix in subsequent stages; suspend only for the final outstanding block. Before every stage, reserve destination blocks. Abort/clean up on failed allocation, completion, preemption, or peer failure; release source state and commit destination execution only after completion. §§4.2–4.3, Figs. 6–8.
- **F resource benefit/cost:** Avoids rebuilding the entire prefix and hides most transfer time from the migrated request. It still consumes full KV-copy traffic, temporary source/destination memory, and coordination. The historical transport stages fused blocks through host RAM/Gloo with asynchronous CPU↔GPU copies; this adds host memory/bandwidth and device-link costs as well as inter-machine network traffic (§5).
- **F evidence:** §6.2/Fig. 10: two machines, 1-A10 LLaMA-7B instances or 4-A10 TP LLaMA-30B instances, each batch totaling 8K tokens. Moving one request at sequence lengths 256–8K gives approximately **20–30 ms downtime**, versus **3.5 s** to recompute the 8K LLaMA-30B case. Source decode-time differences during transfer are **up to 1%**; all measured migrations use two stages.
- **F limits/countersignals:** Constant downtime does not mean constant total transfer time or zero resource cost. The result depends on copy speed exceeding append rate in this test. Slow-link convergence, concurrent-migration congestion, and general tail-disruption bounds are **unreported**, not negative results. §5's described fault tolerance differs from the evaluated research artifact, explicitly documented in Appendix A.
- **P operational rule:** Gate migration on destination reservation, state identity, measured effective copy/append rates, total bytes, and final interruption. Compare with recomputation using actual state size and GPU opportunity cost. Measure H2D/D2H separately from inter-node traffic; never replace the entire transfer budget with the 20–30 ms downtime number.

## L2 Virtual pressure combines placement, preemption relief, and admission space

- **F objective → assumptions:** Reduce memory preemptions/decode interference while freeing enough memory on one instance for a waiting prompt. Output lengths remain unknown; free memory can be fragmented across instances despite adequate aggregate capacity.
- **F variables/constraints → mechanism:** For ordinary running requests, virtual usage equals physical usage. Assign the head-of-line queued request its prompt-memory demand, while other queued requests contribute zero. Compute freeness **F=(M−ΣV)/B**, where B is batch size; it approximates iterations of remaining growth. Dispatch to the freest instance, pair low-/high-freeness instances periodically, and prefer lower-priority/shorter requests for relocation. This deliberately favors clearing the head-of-line memory demand. Algorithm 1 and §4.4.
- **F resource benefit/cost:** Moves usable slack to the needed instance without changing total installed capacity; fewer preemptions can save both requeueing and prefix recomputation. Costs migration and can conflict with even load spreading. New request processing still inherits local engine memory/batch constraints; this is not a rejection/overload admission policy.
- **F evidence:** §6.3/Figs. 11–12, sixteen 1-A10 LLaMA-7B instances and authors' memory-aware **INFaaS++** comparator: generated long-tail traces show up to **14.8× P99 prefill** improvement and **2× P99 request-average decode** improvement. In the M-M, **7.5 req/s** case's plotted busy interval, the authors' cluster-fragmentation statistic averages **0.7% versus 7.9%**. Across the reported comparison experiments, preemption loss falls **70.4% on average**, equivalent to **1.3 s** mean end-to-end reduction. This is whole-policy evidence, not a clean per-component ablation.
- **F limits/countersignals:** No capacity is created when every destination is full; §4.4.1 explicitly notes rescheduling has limited benefit at very high or low load. The queue-demand heuristic is not a future-output predictor. Empty-batch division and exact freeness threshold tuning are not an executable contract in Algorithm 1. The large generated-trace prefill maximum must not be attributed to ShareGPT/BurstGPT, where the reported P99 gain versus INFaaS++ is up to **5.5×**.
- **P operational rule:** Diagnose cluster fragmentation as blocked prompt demand versus destination-accessible slack, separately from internal KV-block waste. Require reduced requeue/recompute time to exceed migration and displaced-work costs. Track waiting-age and long-request outcomes; a head-of-line heuristic is not proof of starvation freedom.

## L3 Priority headroom differentiates latency but spends other requests' slack

- **F objective → assumptions:** Lower urgent-request queueing and decode interference. Applications specify scheduling and execution priorities; the evaluated policy has high and normal classes and profiled memory-to-decode-speed behavior.
- **F variables/constraints → mechanism:** Schedule higher priorities first, FCFS within each class. Add profiled headroom to virtual load for high execution priority, dividing that headroom among same-class requests on the instance rather than multiplying it per request. Pressure causes other normal requests to migrate away. §§4.4.1–4.4.3/Algorithm 1.
- **F resource benefit/cost:** Dynamically creates lower-load execution without permanently dedicated machines, but may delay/move normal work and reduce its batching opportunities.
- **F evidence:** §6.4/Fig. 13, same 16-A10 serving setup, synthetic Short-Short lengths, Gamma arrivals, **10% randomly selected high-priority requests**, target load **1,600 tokens**: high-priority mean request latency improves **1.2–1.5×** over priority-agnostic Llumnix-base. Normal-request mean end-to-end, prefill, and decode latencies **increase by up to 4.5%, 13%, and 2%**, respectively.
- **F limits/countersignals:** The normal-class cost is a measured counter-signal, not zero overhead. No per-tenant service guarantee, starvation bound, or weighted-fairness evaluation is reported. Priority differentiation and request-average latency gains are not hard TTFT/TBT SLO enforcement.
- **P operational rule:** Admit a priority/headroom proposal only with an explicit acceptable normal-class regression and class-specific tail/wait-age checks. Profile the target headroom; do not transplant 1,600 tokens or infer fairness from FCFS within classes.

## L4 Draining and filling instances improves autoscaling efficiency

- **F objective → assumptions:** Reduce active-instance cost while preserving latency under varying load; model replicas and scale actions are available.
- **F variables/constraints → mechanism:** Scale using sustained average normal-priority freeness outside a range. Prefer the instance with fewest running requests for termination; add an infinite-virtual-usage fake request to force draining. Load balancing fills a newly started instance. §4.4.3.
- **F resource benefit/cost/evidence:** Transfers reduce stranded running work during scale-down and accelerate use of added capacity. §6.5/Figs. 14–15, Long-Long traces, at most sixteen A10/LLaMA-7B instances, identical scaling strategy for INFaaS++: threshold sweeps achieve about **5 s P99 prefill latency** with **36% fewer average active instances**. Fixed-threshold rate/burstiness sweeps report up to 16%/18% lower average instances. The cost denominator is average instances, not a measured cloud invoice or energy consumption.
- **F limits/countersignals:** Depends on spare receiving capacity and excludes a general cold-start, billing-minimum, or model-loading cost model. No dynamic model-TP/PP change is established.
- **P operational rule:** Compare total replica-time and scale-event transfer costs at matched latency targets. Do not start real scaling or migration from this research artifact without separate operational authorization.

## Tiny unread next gate

Only if formal multi-user fairness becomes a requirement: Llumnix §7 explicitly leaves interaction with fair local scheduling to future work and cites **Sheng et al., “Fairness in serving large language models”**, [reference 55](https://arxiv.org/html/2406.03243v1#bib.bib55). Its full text was **not opened** in this pass. No other papers were expanded.


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


# LoongServe: elasticity requires separate admission, placement, and communication gates

Status: candidate paper synthesis; empirical validation: not_run. **F** = historical paper fact/author report. **P** = proposed operational interpretation requiring separate validation. Source: Wu et al., *LoongServe: Efficiently Serving Long-Context Large Language Models with Elastic Sequence Parallelism*, [arXiv:2404.09526v2](https://arxiv.org/abs/2404.09526v2), 29 October 2024. Exact equations, read coverage, metrics, and baseline caveats are in the readset (included below).

## Added decision boundary

**F:** An elastic instance contains a model replica with a fixed model-parallel configuration. LoongServe changes **groups of instances along the sequence dimension**, per iteration, without repartitioning model weights. The choice is how many instances a batch uses in each phase, which requests share that batch, and where their KV tokens reside. The same request's state may span instances. Its distributed KV pool is **GPU memory**, not a Mooncake-style host-cache reuse pool.

**P:** Reconsider the earlier “migrate or recompute” decision when distributed attention can use KV where it already resides. This does not eliminate communication: prefill circulates KV; decode exchanges queries and partial attention results. Separate incremental migration traffic from the collective traffic already required by the algorithm. LoongServe resolves the prior Mooncake source-notes' unread elasticity lead; it does not justify replacing chunked pipelines without a matched workload/topology comparison.

## G1 Choose post-prefill residency during computation

- **F objective → assumptions:** Use a wide group to accelerate long prefill, then release compute resources for other work without a second full-cache copy. Sequence-parallel attention already circulates KV among participating instances; the target decode group and token placement can be chosen before prefill completes.
- **F variables/constraints → mechanism:** Choose prefill and post-prefill groups, degree of parallelism, and token-level target placement. Each target retains selected KV when it passes through the existing attention communication path. Uniform input-token work can coexist with nonuniform retained-state placement. Reuse a per-layer buffer of order **O(b·s·h/d)** instead of requiring each prefill instance to retain all of its produced layers' KV before a later migration. §§4.1, 5.4/Fig. 7.
- **F benefit/cost:** Removes an **additional reactive KV migration** and the requirement for equal intermediate residency on every instance. Still pays replicated model weights, normal sequence-parallel communication, buffer capacity, and placement bookkeeping.
- **F evidence:** §7.4/Fig. 14(a), LWM-1M-Text/Llama-2-7B architecture on the single-node eight-A800-80GB testbed: authors report **<2% extra prefill forward time** with proactive scale-down versus without it across plotted batch/length pairs. This is a direct mechanism microbenchmark; the whole-system throughput maxima are not its isolated effect.
- **F limits/countersignals:** “Zero overhead” refers to no extra full-state migration, not zero elapsed-time overhead. Optional scale-down of an already-running decode group is a different path and can migrate existing state (§5.2). No numerical end-to-end ablation isolates memory-pool placement from all scheduler/ESP changes.
- **P operational rule:** Propose proactive placement only if the state can be captured during an existing communication path and every target/buffer fits. Compare whole forward time and resident bytes, not only extra transfer bytes. Treat a mid-decode shrink as a paid migration decision.

## G2 Expand decoding without moving existing KV

- **F objective → assumptions:** Avoid memory-driven eviction/recomputation and accelerate large decode batches as outputs grow. Distributed attention can evaluate each existing KV shard locally; a master need only create/store the new-token state.
- **F variables/constraints → mechanism:** Add instances to a sequence-parallel group and choose one or multiple request masters. A master computes new queries/KV and local layers; all state-holding instances compute partial attention and return results. New masters store new-token KV locally. Multiple masters divide requests/FFN work and overlap some query communication with local attention. Existing KV stays where it is. §§4.2, 5.4/Fig. 8.
- **F benefit/cost:** Adds accessible capacity and may parallelize a compute-bound decode batch without whole-prefix relocation. Costs extra communication/synchronization and weight replicas; adding a master is useful only when local-layer work or storage benefits exceed that cost.
- **F evidence:** §7.4/Fig. 13(a), ShareGPT/Poisson arrivals, same eight-A800 setup: P90 goodput is **2.87×** the same system **without elastic scale-up**. Fig. 13(b), offered rate **25 req/s**, records **7.12 scale-up events per 10 s** on average. Fig. 14(b) reports up to **2× better per-iteration latency** for large batches but **<10% overhead** for small batches compared with the single-master case.
- **F limits/countersignals:** Small-batch communication regressions are measured, not merely hypothetical. Scale-up frequency is workload-specific. The ablation does not prove that arbitrary added instances or networks improve latency, nor that client-token tails are bounded.
- **P operational rule:** Separate a capacity-needed scale-up from a speed-needed scale-up. Require free new-token slots, a supported state distribution, and measured communication-adjusted decode time. Do not require copying all old KV when the algorithm consumes it in place; do not call the resulting distributed attention traffic free.

## G3 Admission balances worst-case KV reservation and prefill/decode opportunity cost

- **F objective → assumptions:** Avoid expensive long-sequence eviction while admitting useful prefill work and limiting harm to ongoing decode. User maximum sequence lengths, current state, finished-request decode times, and profiled prefill duration are available.
- **F variables/constraints → mechanism:** FCFS scan of pending work; require enough KV slots and reject the current dispatch choice if maximum possible future KV demand may cause eviction. Stop enlarging a prefill batch once its profiled memory-to-compute-bound transition is exceeded. If it would occupy a decode group's instances, compare estimated normalized input waiting-time reduction with normalized output-token delay under pessimistic preemption. Equations 1–2/§5.1.
- **F benefit/cost:** May save recomputation and improve aggregate latency, but conservative maximum-length accounting can leave memory unused, and admitting prefill can delay existing decode. This is a local dispatch decision, not a paper-established global overload rejection policy.
- **F evidence:** The mechanism is explicit in §5.1. Fig. 12 compares full dynamic ESP scheduling with three static parallelism arrangements under Mixed/Zipf workloads and reports higher P90 goodput. **Unreported:** isolated benefit of the maximum-length admission rule, its wasted-reservation cost, and a calibration/error breakdown for the remaining-decode-time estimate. Absence of ablation is not a failed result.
- **F limits/countersignals:** Eq. 1 divides by **already-generated output length**, not an oracle future output length. Eq. 2 estimates remaining waiting using average completed decode duration minus the minimum elapsed decode time, clipped at zero. Neither encodes each user's deadline or a fairness entitlement. FCFS dispatch is followed by length-based batching; it is not a complete fairness proof.
- **P operational rule:** Keep capacity and latency admission gates separate. Require trustworthy maximum-length limits and accounting for conservative reservation. Test long waits, class tails, and near-zero output-length edge handling before treating the heuristic as an executable scheduler or a user-SLO guarantee.

## G4 Pay for shrinking decode only when released prefill capacity is worth it

- **F objective → assumptions:** Make useful instances available to prefill without unnecessarily stopping entire decode batches. Existing KV can fit on remaining active decode instances, and effective link bandwidth can be estimated.
- **F variables/constraints → mechanism:** Start from idle instances. If more memory is needed, consider occupied instances with free slots, trying to migrate their existing KV elsewhere. For additional compute, examine the instance with least resident KV; compare the sum of normalized prefill-latency reductions from adding it against resident-byte transfer time **V/average_bandwidth**, normalized by each new request's input length. Continue while gain exceeds cost. Equations 3–4/§5.2.
- **F benefit/cost/evidence:** Converts underused decode compute into useful prefill capacity but consumes actual KV migration, destination memory, and transfer time. Whole-system single-node results (§7.2/Fig. 10) report up to **3.85×** SLO-constrained throughput versus the tested chunked-prefill systems and **5.81×** versus the tested DistServe configuration. These maxima combine mechanisms and do **not** isolate this optional shrink policy. No shrink-only performance ablation is reported.
- **F limits/countersignals:** Mean bandwidth does not represent burst contention or tail delays. DistServe uses four prefill and four decode GPUs here; it OOMs on LV-Eval/Mixed and is omitted there. The quoted multiplier is from remaining evaluated configurations, not an OOM-to-finite ratio or a universal disaggregation verdict.
- **P operational rule:** Estimate exposed transfer time under concurrent load, reserve receivers, and include opportunity costs to both phases. Require a benefit margin larger than prediction uncertainty. A no-extra-migration claim for G1/G2 must not erase this path's real transfer cost.

## G5 Length-aware batching and calibrated parallel-degree selection

- **F objective → assumptions:** Reduce total prefill input latency while allocating scarce instances to requests with different scaling behavior. Similar lengths have similar execution characteristics; sufficient profiled examples exist for each fixed model-parallel/ESP configuration.
- **F variables/constraints → mechanism:** Sort requests by descending length and instances by topology/free slots. Dynamic programming chooses contiguous request/instance partitions and DoP, subject to summed token demand fitting available slots. The paper claims quadrangle-inequality properties reduce complexity from O(n²m²) to **O((n+m)²)**. Per-configuration prefill predictor is **α + βΣL + γΣL²**, with least-squares fitted coefficients; ΣL² means sum of individual squared lengths. Equations 5–7/§§5.3–5.5.
- **F benefit/cost/evidence:** Better resource matching and reduced scheduler search space cost profiling, model maintenance, and iteration-level control. §7.4/Fig. 15 reports **<10% prediction deviation** for plotted batches 1/2/4/8 under SP2TP4, SP4TP2, SP8TP1. Fig. 12 supports the combined dynamic strategy versus static alternatives; no separate measured tail distribution of scheduler decision time is reported.
- **F limits/countersignals:** The model is calibrated to this implementation/topology/model. The paper asserts the DP split properties but does not supply a general proof for arbitrary profiled cost surfaces. Overall metrics normalize latency by token lengths; optimizing them does not automatically optimize absolute TTFT or individual TBT.
- **P operational rule:** Preserve the ΣL² feature, validate on held-out mixed-length batches and actual topology, and measure decision overhead. Treat a DP outline and reported fit as design evidence, not permission to install a scheduler or a proof of real-time feasibility everywhere.

## Scope and stopping boundary

**F:** Main evidence is one Llama-2-7B-architecture long-context model on one or two eight-A800 nodes, not NPUs. Claimed algorithmic compatibility with MQA/GQA/MoE is not an evaluation of every architecture/current implementation. **P:** No additional unread paper is required to conclude this two-paper extraction. Hardware portability, target serving-stack feasibility, and formal fairness remain separate evidence gates.


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
