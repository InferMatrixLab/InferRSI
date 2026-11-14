# FlexGen: conditional feasibility of throughput-oriented offload

Use this reference when an offline inference proposal frees accelerator memory
by moving state to CPU memory or disk. Check whether the complete placement,
working storage and exposed execution cost fit the workload's resource and
latency objective before treating it as a throughput candidate. This is
source-derived candidate guidance; empirical validation is `not_run` and
efficacy is `not_evaluated`.

## Source identity and inspected scope

Sheng et al., *FlexGen: High-Throughput Generative Inference of Large Language
Models with a Single GPU*, ICML 2023, PMLR 202:31094–31116
([proceedings](https://proceedings.mlr.press/v202/sheng23a.html),
[paper](https://proceedings.mlr.press/v202/sheng23a/sheng23a.pdf)). The
[owner's paper source](../metadata.json) records the fixed edition and digest:
the official ten-author edition, 23 PDF pages, SHA-256
`7cd9673c37640011d38ef4b8595f5e1e09a85b1f803a3734f19c97ca66c75b9e`.
The extended-author arXiv v2 edition is not the extraction source.

The scoped qualification on 2026-10-31 inspected:

- Section 1's offline objective and limitations, Section 3's memory and metric
  definitions, Sections 4.1–4.3's validity constraints, scheduling, placement and
  cost model, and Section 4.4 only to bound the multi-GPU extension.
- Sections 6 and 6.1 for the evaluation denominator and ablation discussion;
  Appendix A.3's selected timing and peak-memory formulas on PDF pages 15–17;
  the ending of Appendix A.2 only to bound Theorem 4.1, without a full proof audit.
- Rendered PDF pages 1, 4, 5, 6 and 8: Figures 1–3, Algorithm 1, Equation 1,
  Tables 2–3 and their surrounding definitions. Rendering page 7 alone is not
  credited as visual inspection. This is not an all-page or released-engine audit.

PMLR's [publication agreement](https://proceedings.mlr.press/pmlr-license-agreement.html),
clauses 2–3, specifies CC BY 4.0 and attribution to the original publication.
This resource is an attributed synthesis; it includes no raw PDF, figure or
extended quotation. The archived official repository
[FMInference/FlexLLMGen](https://github.com/FMInference/FlexLLMGen/tree/004ffef82b46e8dc8685c55d0cdda650bdaf1269)
was inspected only for README identity and its Apache-2.0 LICENSE, not runtime
behavior. Repository licensing does not establish code/paper-version equivalence.

## Reconstruct the source condition

Section 3 defines block latency `T` as the time to process the prompts and
generate all `bls * n` output tokens, including prefill. Its generation
throughput is `bls * n / T`, where `n` is output length. Table 3's decoding
throughput excludes prefill; keep that denominator separate. The paper targets
latency-insensitive batched work, where more block latency may be acceptable.
That objective does not establish an interactive latency SLO.

Section 4.2 defines effective batch size (block size) as:

```text
bls = gbs * number_of_GPU_batches_in_a_block
```

`gbs` is the GPU batch size. A larger block reuses a layer's weights across
more GPU batches, but the block's KV cache and activations must remain stored
for their required lifetimes. GPU batch size and effective batch size therefore
charge different resident and working-storage terms; they are not interchangeable.

The policy jointly places weights (`wg`, `wc`, `wd`), KV cache (`cg`, `cc`,
`cd`) and activations (`hg`, `hc`, `hd`) on GPU, CPU and disk. Each triple sums
to one in Equation 1. Freeing GPU weight storage alone does not establish that
the complete policy fits. Section 4.1 requires inputs on the computing device,
preserves activation/KV lifetimes, and limits total storage at every point.
Appendix A.3 makes the following charges explicit:

| Resource | Capacity condition to inspect |
|---|---|
| GPU | Home weights, activations and KV plus working memory at prefill and decode peaks, including staged weights and operation intermediates |
| CPU RAM | Home weights, activations and KV plus working memory at prefill and decode peaks, including staging and CPU-attention storage |
| Disk / NVMe | Placed weights, activations and KV within available storage; the separate disk↔CPU transfers still enter the timing model |

For fixed workload lengths, Equation 1 minimizes `T / bls` subject to the GPU,
CPU and disk peak-capacity constraints and the three placement sums. The timing
model uses:

```text
T_model = l * T_pre + (n - 1) * l * T_gen
T_pre, T_gen = max(CPU_to_GPU, GPU_to_CPU, disk_to_CPU, CPU_to_disk, compute)
```

Each `max` uses that phase's per-layer costs, not a maximum across the whole
run. The model assumes perfect overlap, fits hardware parameters from profiling,
and includes CPU and GPU computation. Moving attention work to CPU can reduce
KV transfer, but its CPU work still costs time. Appendix A.3 notes that effective
rates vary with load; its simplified constants are not universal hardware rates.

The source-derived decision condition is to retain an offload proposal only as
a candidate when all three state placements and phase-specific peaks fit, and
its complete block latency is compatible with the stated offline objective.
Evaluate exposed transfer and CPU costs with rates and overlap evidence for
that workload before recommending a throughput change. Missing capacity,
placement, working-memory, rate or latency inputs leave current feasibility
`INSUFFICIENT_EVIDENCE`. The fitted model is a conditional prediction, separate
from the owner's L1 bound and its single-device, single-traffic-tier helper.

Section 4.3 explicitly warns that relaxed fractional placements and imperfect
peak-memory modeling, including fragmentation, can produce out-of-memory
policies requiring manual adjustment. A predicted policy is neither a fit
guarantee nor a measured speedup. Theorem 4.1 concerns I/O complexity under the
paper's assumptions; it does not prove a global latency or performance optimum.

## Two qualitative reasoning counterexamples

These are source-grounded hypothetical checks, not observed experiments.

1. **More weight reuse exceeds the state budget.** Keep `gbs` fixed and increase
   the number of GPU batches in a block. Weight loading may be amortized across
   more prompts, while the block's retained KV and activations increase. If the
   resulting home plus working storage exceeds GPU/CPU capacity, or the placed
   state exceeds disk capacity, reject that placement as infeasible. Checking
   only GPU weights or the unchanged `gbs` misses the violated condition.
2. **A fitting placement misses the execution objective.** Suppose all resource
   peaks fit after state moves to CPU/disk. Disk↔CPU or CPU↔GPU traffic, CPU
   attention work, or incomplete overlap can remain exposed; a larger block can
   also exceed the allowed block latency. Capacity feasibility alone therefore
   cannot justify a throughput recommendation. Compare complete generation time
   under the same workload and resource budget, with the actual latency objective.

## Unresolved wording and reuse limits

- The printed Section 4.3 says `bls < 20`, while Section 6.1 reports a block of
  `32 × 8`. This remains unresolved. Do not reinterpret the former as a count of
  GPU batches or turn either value into a runtime default or universal limit.
- Approximation and 4-bit settings, model quality, current engine/backend
  compatibility, device execution, service SLO qualification and efficacy are
  outside this extraction. Author results are not current-stack measurements.
- The earlier `omnirsi-paper-intelligence-2026-10-15.zip` and its supplier
  synthesis remain unavailable. Existing extraction history does not reveal its
  exact FlexGen text or reuse rights. Public-paper and repository licenses do
  not recover or license that synthesis; historical novelty remains `UNKNOWN`.
- Loading/readiness, training offload, host transfer lifetimes and KV-only runtime
  tiers retain their existing owners. This resource adds one inference-policy
  feasibility comparison, with no solver, runtime, registration or helper change.
