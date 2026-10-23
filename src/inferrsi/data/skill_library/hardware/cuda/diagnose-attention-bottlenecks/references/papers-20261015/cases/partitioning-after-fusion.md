# Case D-C2: Fusion leaves parallelism and output ownership to solve

Status: candidate; empirical_validation: not_run. Historical paper evidence only.

## F: mechanism and experiment boundaries

[D2 §3.1–3.3, pp. 5–9](https://arxiv.org/pdf/2307.08691v1#page=5) combines three changes: less non-matmul normalization, more sequence-tile workers, and less inter-warp reduction traffic. Query-row ownership makes the forward output independently computable; backward key-column ownership still shares dQ and uses atomic additions. A no-communication forward diagram is not a no-communication backward algorithm.

The attention benchmark in §4.1 uses A100 80GB SXM4, lengths 512 through 16k, total tokens fixed at 16k by changing batch, hidden dimension 2048 and d=64 or 128, with and without causal mask. Its figures distinguish forward, backward and combined throughput. The exact benchmark dtype/library pins are not fully stated in the inspected §4.1 text; do not fill them from current library defaults. The operation-count convention uses the two forward matmuls, halves for causal masking, and assigns backward 2.5 times forward due to five matmuls including recomputation.

## F: application benefit is a separate denominator

[D2 Table 1, p. 12 and §4.2, p. 11](https://arxiv.org/pdf/2307.08691v1#page=12) report training speed in TFLOP/s per GPU on 8×A100 80GB SXM, with different GPT-style workloads:

| Workload | Without FA | FA | FA2 |
|---|---:|---:|---:|
| GPT3-1.3B, 2k context | 142 | 189 | 196 |
| GPT3-1.3B, 8k context | 72 | 170 | 220 |
| GPT3-2.7B, 2k context | 149 | 189 | 205 |
| GPT3-2.7B, 8k context | 80 | 175 | 225 |

The model-FLOP convention is 6*N*parameter_count + 12*layer_count*hidden_dim*N² per sequence; unlike the attention-kernel convention, the attention term is **not halved for causal masking**, for consistency with prior model-throughput reporting. These values and the reported 72% model FLOP utilization are not directly comparable to FA3's attention-only percentage of device peak.

The row differences also show why an attention-only speedup is not the same as a whole-training speedup. Do not interpret the comparison between 2k and 8k rows as a controlled kernel change; those are different workloads. D2 provides no isolated ablation that assigns a unique fraction of these gains to scalar work, sequence parallelism or split-Q.

## P: proposed decision

For a fused attention kernel with low utilization, inspect whether batch*heads*query_tiles supplies enough work and whether each owner finishes an output or produces a partial requiring reduction. Select the candidate that matches the observed gap, and measure output/gradient correctness, reduction/atomic waits and resource pressure. Do not automatically introduce more workers if resource occupancy or shared-gradient contention is already limiting.

Reject “use larger tiles and more parallelism simultaneously” without a register/SMEM budget: the two can conflict. Treat the paper's 4/8 warps, {64,128} tile choices and approximate 80-worker heuristic as historical settings. See [F3–F5](../../mechanisms.md).
