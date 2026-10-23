# Self-contained source notes

Status: candidate. Empirical validation: not_run. These are the same authored historical-paper evidence notes supplied in the Pack B notes/readsets, included here so this skill can be consumed on its own. F facts and P proposals remain separately labeled. No paper source files or implementation artifacts are bundled.


# Orca: iteration boundaries, selective batching, and conservative admission

Status: candidate. Empirical validation: not_run. **F** is a fact/author report from the pinned historical source. **P** is a proposed operational interpretation. No engine was run or inspected. Exact readset and evidence (included below).

**F source:** Yu et al., *Orca: A Distributed Serving System for Transformer-Based Generative Models*, OSDI '22 proceedings, pp. 521–538. [USENIX record](https://www.usenix.org/conference/osdi22/presentation/yu), [proceedings PDF](https://www.usenix.org/system/files/osdi22-yu.pdf). This is the serving paper, not the unrelated ORCA accelerator paper.

## O1 Change batch membership at an iteration boundary

- **F objective → assumptions:** Reduce waiting behind a whole autoregressive request/batch and return completed requests promptly. Each output token requires another model iteration; requests can have different input/output lengths (§§2–3).
- **F decision variables/constraints → mechanism:** Select ready requests after each iteration, capped by request-count `max_bs` and KV reservation. Completed requests leave; arriving requests may join. The scheduler and execution engine communicate once per iteration, rather than only at whole-batch completion (§3, Fig. 4; §4.2, Algorithm 1).
- **F benefit/cost:** Avoids inactive-request work and full-batch join/leave delay; introduces repeated scheduling/control and does not make the first, whole-prompt iteration short. Selection remains arrival ordered: an earlier request has run at least as many iterations as a later one (§4.2). This is not FastServe's size/attained-service-based preemption policy.
- **F evidence:** End-to-end Fig. 10/§6.2, synthetic GPT-3-175B configuration on 16 A100-40GB GPUs (TP8/PP2), reports 6.81 versus 0.185 requests/s at about 190 ms/token **median of request end-to-end latency/output length**, hence 36.9× over FasterTransformer plus the authors' batching harness. The total system comparison includes engine, memory, batching, and pipelining changes; it is not an isolated scheduling ablation or TTFT/TBT goodput result.
- **F limits/countersignals:** The low-load 101B case is an exception to improved latency, because engine time dominates. With homogeneous requests, FasterTransformer benefits more from larger batches; Orca `max_bs=1` loses useful batching (Fig. 11). The authors explicitly say a larger maximum batch is not guaranteed to preserve latency for other models/hardware/workloads (§6.2).
- **P operational rule:** First distinguish fixed-batch admission delay from memory admission delay and prefill interference. Iteration-level eligibility alone does not demonstrate short-job priority, a token-latency bound, or sufficient room for a new request. Preserve the chosen service-order contract before proposing preemption.

## O2 Selectively batch tokens while retaining request-local attention state

- **F objective → assumptions:** Batch requests with different positions or phases without demanding identical attention tensor shapes. Non-attention operators can consume flattened token tensors; attention must respect request boundaries (§3, Fig. 5).
- **F decision variables/constraints → mechanism:** Concatenate ready tokens for linear, normalization and other non-attention operations; split by request for attention; merge afterward. Keep each request's KV until completion. The implementation also fuses separate request-attention kernels' thread blocks (§5).
- **F benefit/cost:** Amortizes model-weight reads across ready tokens without padding all requests into the same attention shape; costs split/merge logic, irregular attention work, and kernel/control overhead. It neither pages KV nor chunks long prefills.
- **F evidence:** Fig. 9a–b/§6.1 holds request lengths and start/finish points equal, disables scheduling, and finds comparable or slightly worse execution on 13B/one A100 and 101B/eight A100s. This is a useful kernel-level counter-signal to attributing all end-to-end benefit to a faster attention kernel. Inputs are 32 or 128 tokens, outputs 32, across tested batch sizes.
- **F limits:** Figure 9 does not separately ablate split/merge or the fused attention thread-block optimization. Current flash/paged attention performance is unreported.
- **P operational rule:** Keep the batch-membership capability and its kernel implementation separate. If the proposed benefit requires better KV packing, route to the existing PagedAttention-derived skill rather than crediting selective batching with that mechanism.

## O3 Reserve enough KV for each admitted request to finish

- **F objective → assumptions:** Prevent all active requests exhausting KV before another token can be allocated. Each request has a maximum total token count, `max_tokens = input tokens + max_gen_tokens`, respected by execution (§4.2 and footnote 6).
- **F decision variables/constraints → mechanism:** Choose `n_slots` and `max_bs`. On first scheduling, reserve that request's maximum total slots; stop arrival-ordered selection if the next request cannot fit. Release its reservation on completion. Intermediate reusable buffers are distinct from persistent KV (Algorithm 1, lines 13–14 and 23–26).
- **F benefit/cost:** Guarantees room for the admitted request's future KV within the model's bound; reserved-but-not-live capacity can restrict concurrency. Reservation is per-request maximum, less conservative than FasterTransformer's model-maximum sequence allocation but different from PagedAttention demand allocation.
- **F evidence:** §6.1/Fig. 9 reports FasterTransformer's tested 13B batch sizes ≥8 and 101B sizes ≥16 fail from model-maximum KV preallocation, whereas Orca can exploit the shorter request bounds. No isolated end-to-end reservation-versus-demand-allocation ablation is reported in Orca.
- **F limits:** Every synthetic request is forced to generate to its sampled maximum because the evaluation has no actual model checkpoint/input text (§6 setup). Therefore the experiment does not measure reservation waste from early EOS. There is no request migration, host swap policy, recomputation-recovery policy, or runtime TP/PP change in the read design.
- **P operational rule:** Measure reserved, allocated and live KV separately; do not call their difference fragmentation without checking semantics. A conservative reservation policy can be a deliberate forward-progress constraint. Any less-conservative admission proposal needs a supported recovery/overload policy and service-order accounting.

## O4 Pipeline independent batches and separate control/data channels

- **F objective → assumptions:** Keep distributed stages busy without sacrificing each batch's batching efficiency, and avoid CPU/GPU synchronization for CPU-consumed metadata (§4.1–4.2, Figs. 6–8).
- **F decision variables/constraints → mechanism:** TP/PP degrees are configured; schedule up to `n_workers` batches in flight, excluding currently running requests. A controller passes metadata/tokens through CPU-side gRPC while NCCL moves intermediate tensors. Requests retain stage-local KV; no KV migration is required just to pipeline them.
- **F benefit/cost:** Full batches can occupy successive stages; CPU metadata bypasses GPU synchronization. Costs include model partitioning, collective/stage communication and enough concurrent work/state. The paper does not change parallel degrees per request at runtime.
- **F evidence:** Fig. 9c, GPT-3-175B/16 A100s, fixed-length microbenchmark with pipeline execution disabled in both engines, reports up to 47% performance improvement attributed by the authors to control/data-plane separation. The microbenchmark does not isolate this change from all implementation differences. Fig. 10 is the combined pipeline/end-to-end result.
- **F limits:** Balanced worker occupancy is the design intuition, not a proof for arbitrarily variable stage times. No independent runtime-parallelism or migration evidence is supplied.
- **P operational rule:** Separate CPU scheduling/synchronization stalls from model communication and prefill/decode interference. Reuse the prior Sarathi/DistServe procedure for phase/parallel placement decisions; consider LoongServe only when changing sequence-parallel resource groups is the question.

## Increment over the earlier pack

**P:** Orca supplies the original eligibility/FCFS/reservation baseline behind the previous PagedAttention notes. It closes that notes' unread Orca lead without re-extracting PagedAttention. Sarathi's decode-first chunk budget is a later scheduling choice; DistServe's phase placement is a different architecture; Mooncake's future-load rejection is a separate admission objective. None follows from Orca's 36.9× result.


# Orca exact source and readset

Status: candidate. Empirical validation: not_run. Read date: 2026-10-15 UTC. Only the original proceedings full text was extracted for Orca.

## Identity and pin

- Gyeong-In Yu, Joo Seong Jeong, Geon-Woo Kim, Soojeong Kim, Byung-Gon Chun. *Orca: A Distributed Serving System for Transformer-Based Generative Models*. 16th USENIX Symposium on Operating Systems Design and Implementation (OSDI '22), July 2022, pp. 521–538.
- [Official record](https://www.usenix.org/conference/osdi22/presentation/yu); [official PDF](https://www.usenix.org/system/files/osdi22-yu.pdf).
- Proceedings edition, not an arXiv version. Download SHA256: `b8038438ad8ff99bb131c1a6e16f7df10cf2f962aeb1bf4f1c00cc37e70658ca`.
- The downloaded PDF has a cover; PDF page 2 corresponds to printed p. 521. Page links below use physical PDF numbering.

## Actual read set

Read abstract/introduction; §2's iteration/KV/batching definitions; §3 challenges and both solutions; §§4.1–4.2 in full; §5 implementation; §6 setup, §§6.1–6.2 in full; §7 discussion. Examined Figures 1–11 and Table 1 through extracted captions and surrounding text. Visually inspected [Algorithm 1, printed p. 528/PDF p. 9](https://www.usenix.org/system/files/osdi22-yu.pdf#page=9), [Figs. 9–10, printed p. 531/PDF p. 12](https://www.usenix.org/system/files/osdi22-yu.pdf#page=12), and [Fig. 11/result/caveat text, printed p. 532/PDF p. 13](https://www.usenix.org/system/files/osdi22-yu.pdf#page=13). Figures were not digitized. References were used only to identify the historical FasterTransformer source, not to expand into additional papers.

## Mechanism/evidence locators

- O1: §3 C1/S1, printed pp. 524–525, Fig. 4; §4.2, pp. 528–529, Algorithm 1; §6.2/Figs. 10–11, pp. 531–532.
- O2: §3 C2/S2, pp. 525–526, Fig. 5; §5, p. 529; §6.1/Fig. 9, pp. 530–531.
- O3: §4.2, p. 528, Algorithm 1 lines 13–14/23–26 and footnote 6; §6 setup, p. 530; §6.1/Fig. 9, pp. 530–531.
- O4: §4.1, p. 527/Figs. 6–7; §4.2, p. 529/Fig. 8 and Algorithm 1 lines 8–10/19; §6.1/Fig. 9c, pp. 530–531.
- No numbered analytical cost model is provided for optimization. The operative constraints are Algorithm 1's maximum request batch, finite KV slots, arrival order and in-flight pipeline count. Avoid fabricating a latency equation from qualitative arguments.

## Evaluation context and limitations

**F:** Azure ND96asr A100 v4 VMs; eight A100-40GB GPUs per VM with NVLink, eight 200-Gbps HDR InfiniBand adapters per VM (1.6-Tb/s aggregate quoted interconnect). Up to four VMs. FP16 weights/activations; maximum sequence 2048. Table 1: GPT-style 13B is one GPU, 101B TP8, 175B TP8/PP2, 341B TP8/PP4. The 101B/341B configurations are created by varying layers/hidden dimensions around GPT-3 configurations; this is not evaluation of named released pretrained checkpoints.

**F:** End-to-end input lengths sampled uniformly from 32–512 and generated lengths uniformly from 1–128, synthetic Poisson arrivals. EOS suppressed; all requests reach their sampled maximum. FasterTransformer receives a custom request-level dynamic batching harness. The bibliography records the FasterTransformer URL with retrieval date 13 Dec 2021; a tested commit/version is unreported in the inspected methods. Its present behavior is not established here.

**F:** Figure 10 compares throughput to median request end-to-end latency divided by generated tokens. Figure 11 uses unnormalized median request latency because lengths are homogeneous (32/32 or 256/256). Figure 9 measures time for the whole homogeneous batch without the scheduler. Those three denominators must remain separate.

**F:** 36.9× = reported 6.81/0.185 requests/s at approximately 190 ms/token median normalized latency for 175B. The text references “orca(128)” while describing this target's relationship to Fig. 9; Fig. 9's parentheses encode input length, unlike Fig. 10's `orca(max_bs)` notation. Do not interpret that parenthetical as a demonstrated max-batch-128 operating point.

**P:** Original Orca evidence should qualify the PagedAttention authors' reimplemented Orca baseline, not be silently substituted for that different code and evaluation. The paper's reservation and FCFS properties are historical source facts, not proof of any current serving engine's policy.

## Unreported evidence / no further source expansion

No direct TTFT/TBT or joint-SLO attainment curve, multi-tenant fairness bound, dynamic parallelism change, live migration, host swap/recompute crossover, or early-EOS reservation-waste ablation appears in the relevant read evaluation. This records the source boundary, not a measured failure. No new unread literature lead is needed from this paper; FastServe is in the present approved pack.


# FastServe: preemption must budget its suspended state

Status: candidate. Empirical validation: not_run. **F** labels historical paper facts or author-reported experiments. **P** labels proposed operational rules. Exact readset/evidence (included below).

**F source:** Wu et al., *Fast Distributed Inference Serving for Large Language Models*, [arXiv:2305.05920v3](https://arxiv.org/abs/2305.05920v3), 25 September 2024. The extracted design/results are v3, not silently attributed to the 2023 first version.

## F1 Skip-join MLFQ with token-boundary preemption

- **F objective → assumptions:** Reduce head-of-line waiting and maximize throughput under request-latency targets when input length is known but output length is unknown. A profiled first iteration depends on input length; later iteration time is treated as roughly constant for a fixed model/hardware (§§2.3, 4.1).
- **F decision variables/constraints → mechanism:** Predict first-iteration time, initially enter the highest-priority queue whose quantum can contain it, and skip shorter-quantum queues. After token-boundary service consumes a quantum, demote based on next-iteration time; form batches from ready jobs in priority order up to maximum batch size. The historical quanta double, starting from the minimum iteration time (Algorithm 1; Figs. 5–7).
- **F benefit/cost:** Newly arrived short work can preempt continuing long work; initial skip-join avoids repeated demotion or mid-prefill recomputation. It consumes more simultaneous unfinished-job KV and depends on profiling. Iteration-level preemption does not bound a long first iteration's interference as Sarathi's chunking does.
- **F evidence:** §6.3/Fig. 14 uses OPT-13B on one A100-40GB, ShareGPT-derived lengths with input/output ratio changed from 0.25 to 256. Author-reported improvement maxima over FCFS/naive MLFQ/fixed input-length priority are 8.9×/1.87×/13.9×. Values are normalized to the slowest system at each ratio; these are not absolute s/token despite the plotted unit label. The ranking changes in the naive/fixed-priority alternatives as phase dominance changes.
- **F limits:** This is not SRPT with known remaining output length, nor a formal optimality guarantee. Full target-workload profiler residuals and long-context calibration are unreported. Algorithm notation has ambiguities; do not translate it directly into code (readset).
- **P operational rule:** Consider preemption only when observed queueing from heterogeneous service lengths is important after preserving a matched engine baseline. Require first-iteration calibration, the actual safe preemption boundary, and a suspended-state budget; do not use input length alone as total work.

## F2 Promote starved jobs, but distinguish mitigation from fairness guarantees

- **F objective → assumptions:** Prevent long input/output jobs staying indefinitely in low-priority queues while shorter jobs arrive.
- **F decision variables/constraints → mechanism:** Periodically promote a job waiting past a starvation threshold to the highest-priority queue, resetting its starvation time. The paper ties threshold tuning to the user SLO and mentions a 300-ms default (§4.1, Algorithm 1 lines 18–21).
- **F benefit/cost:** Gives long jobs service opportunities, at the cost of changing priorities and likely next-use times of KV. Promotion must therefore affect cache prefetch/eviction order, not only the job queue (§4.2).
- **F evidence:** §6.2/Fig. 12 measures P95 normalized request latency on ShareGPT. Against FastServe-FCFS, throughput at the 0.3-s/token target improves up to 1.5× for OPT-175B (16 A100s), and 2–2.8× for OPT-13B/66B (one/four A100s). This evaluates the combined policy, not an isolated promotion-on/off comparison.
- **F limits:** Per-user/tenant service fairness, starvation worst-case bounds, and an isolated promotion/threshold sweep are unreported. Aggregate P95 cannot establish that every long request meets a deadline. The paper's “does not hurt tail latency” conclusion is limited to the evaluated aggregate curves.
- **P operational rule:** Require maximum wait, age/length/priority-cohort latency and token service shares alongside global P95. Keep a declared service-order/fairness contract; a throughput gain is insufficient if a protected cohort or TBT target regresses.

## F3 Proactively swap KV by estimated next scheduled time

- **F objective → assumptions:** Allow preempted state to outlive scarce device residency, while hiding local transfer behind useful computation. A destination host-memory tier and sufficient copy/compute overlap exist (§4.2).
- **F decision variables/constraints → mechanism:** Evict the job with latest estimated next scheduled time (ENST), fetch earliest. ENST is the minimum of time until starvation promotion and estimated preceding higher-priority service; the latter assumes those jobs do not finish before demotion and divides aggregate service by maximum batch size. Reserve some idle KV slots from historical burst behavior. Use asynchronous H2D/D2H, with capacity for prefetched state (unnumbered §4.2 equations, Figs. 8–9).
- **F benefit/cost:** Exchanges device KV occupancy and recomputation for host capacity, PCIe traffic, prediction error and possible thrashing. The FP16 conventional-attention state formula is `4*l*h*(s+t)` bytes per request. Fig. 8's OPT-2.7B Gamma(rate=64, CV=4), output cap 20 example shows peak KV up to 7× FCFS. This is a warning about active-plus-suspended state, not a universal multiplier.
- **F evidence:** §6.3/Fig. 15, OPT-13B on one A100-40GB and ShareGPT-derived Poisson workload: proactive swapping has author-reported 2.7× improvement over recomputation and 1.7× over reactive swap. The prose does not specify the exact comparison point/latency target for these ratios; retain them as author-reported curve comparisons, not a precise crossover. The reported blocked-swapping share is <5% of end-to-end latency in Fig. 15b; this is **exposed wait**, not all transfer service time or bandwidth consumption.
- **F limits/countersignals:** At low arrival rates, proactive/reactive/recompute perform similarly because KV fits. Bursts can force reactive eviction despite prediction. Reserved idle slots trade productive capacity for burst headroom; a separate reserve-policy ablation and quantified ENST prediction accuracy are unreported. FastServe's killed-job ping-pong/deadlock concern is its strawman scenario, not a universal statement that recomputation cannot progress.
- **P operational rule:** Compare host swap and recomputation using matched workload/state bytes and useful compute opportunity cost. Measure exposed copy waits, total bytes, copy concurrency, host pressure, futile prefetched bytes and repeat evictions separately. No nominal PCIe threshold or universal swap preference follows from this paper; H2D/D2H is Accelerator/RAM, not Network.

## F4 Keep preemption and swapping coherent across static TP/PP partitions

- **F objective → assumptions:** Serve models beyond one GPU without losing scheduling semantics or stalling every stage on swapping (§4.3).
- **F decision variables/constraints → mechanism:** Keep in-flight jobs in priority queues but schedule the highest-priority pending job; KV remains partitioned to the GPU/stage that consumes it. A central first-stage manager coordinates tensor-parallel KV actions, and subsequent stages apply corresponding swap actions while receiving intermediate results (Fig. 10).
- **F benefit/cost:** Multiple batches fill the pipeline and local swap overlaps stage activation movement. Costs include coordination, stage communication and per-stage device/host headroom. These are configured TP/PP partitions, not online changes of degree or migration among serving replicas.
- **F evidence:** Main end-to-end tests include OPT-175B on two eight-A100-40GB EC2 p4d nodes, but no standalone distributed-swap-coordination ablation is reported. The same-engine FCFS comparator is stronger attribution evidence than raw vLLM comparisons (§6.2).
- **F limits:** FastServe's tested vLLM v0.1.7 comparator has only TP for 175B, whereas other baselines match FastServe TP/PP/batch sizes. C++ and fused-kernel implementation differences also contribute. The 31.4×/17.9× headline is not scheduler-only speedup, current-vLLM evidence, or per-GPU joint-TTFT/TPOT goodput.
- **P operational rule:** Require identical resource count, current engine capability and matched partitioning for an operational comparison. Charge activation transport and local KV swapping to their actual separate paths; do not label all distributed state actions network transfers.

## Increment over the earlier pack

**P:** This closes the explicit FastServe lead in the prior DistServe scheduling notes. PagedAttention previously framed device allocation and recovery; FastServe adds next-service-aware residency because choosing short jobs changes the number/lifetime of suspended states. Sarathi controls within-iteration prefill interference; FastServe controls between-iteration service ordering. Mooncake's projected decode-load rejection controls whether to admit work, not how to preempt accepted jobs. No measured combination benefit is inferred.


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
