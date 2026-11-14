# Orca: iteration boundaries, selective batching, and conservative admission

Status: candidate. Empirical validation: not_run. **F** is a fact/author report from the pinned historical source. **P** is a proposed operational interpretation. No engine was run or inspected. [Exact readset and evidence](../references/orca-readset.md).

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
