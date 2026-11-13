# Mooncake: prefix reuse as a conditional cost comparison

Qin et al., *Mooncake: Trading More Storage for Less Computation — A
KVCache-centric Architecture for Serving LLM Chatbot*, FAST '25 proceedings, pp. 155-170
([publisher](https://www.usenix.org/conference/fast25/presentation/qin),
[paper](https://www.usenix.org/system/files/fast25-qin.pdf)). The fixed edition
and PDF digest are recorded in [the owner's paper source](../metadata.json).
This reference uses Section 2.2, Table 1 and Equations 1-2 (proceedings pp.
157-158; PDF pages 4-5). It does not substitute the later arXiv v5 edition.

Use this comparison when a valid cached input prefix is available remotely and
the question is whether loading it could cost less time than recomputing it.
It is an analytical screening step within performance-ceiling analysis. It
does not select a scheduler, validate a connector or establish service gains.

## Reconstruct the paper's comparison

The paper approximates full-prefill work and work saved by prefix reuse as:

```text
full_prefill_flops(n) = l * (a*n^2*d + b*n*d^2)                 (Equation 1)
saved_prefix_flops(p) ~= l * (a*p^2*d + b*p*d^2)
prefix_kv_bytes(p) = p * l * (2*d/gqa) * s

saved_compute_time = saved_prefix_flops / G
load_time = prefix_kv_bytes / B
B = min(B_h2d, B_nic)
```

For a nonempty matching prefix (`0 < p <= n`), comparing `load_time` with
`saved_compute_time` and cancelling common factors gives Equation 2:

```text
B/G > 2*d*s / (gqa * (a*p*d + b*d^2))
```

The strict inequality is the paper's conditional benefit criterion. Equality
leaves no modeled saving. When `p = 0`, there is no prefix to reuse; do not apply
the cancelled expression to infer a benefit. The saved-work expression is the
paper's approximation, not a measurement of the current engine's incremental
attention or batching costs.

| Symbol | Meaning | Table 1 example |
| --- | --- | --- |
| `n`, `p` | Input-token count and reusable-prefix-token count | Workload inputs |
| `l`, `d` | Layer count and model dimension | 80; 8192 |
| `a`, `b` | Architecture-dependent work coefficients in Equation 1 | 4; 22 |
| `gqa` | Query-head count divided by KV-head count | 8 |
| `s` | Bytes per KV tensor element | 2 B, BFloat16 |
| `G` | Average computation rate for the modeled GPU group | 8 × 312 TFLOP/s |
| `B_h2d` | Host-to-device bandwidth | 128 GB/s |
| `B_nic` | Network-interface bandwidth | 800 Gbit/s = 100 GB/s |

Table 1 describes LLaMA3-70B and an 8 × A800 machine. Use decimal bytes and
FLOP/s consistently; `B/G` has units of bytes/FLOP. Keep computation and
bandwidth at the same GPU-group scope. Table values are analytical example
inputs, not measurements of a new deployment. Changing the model, KV encoding
or sharding can change the work and byte counts; obtain those inputs before
using this formula for another system.

The `min` approximation assumes a pipelined loading path. Section 2.2 warns
that transfer stages do not overlap perfectly, increasing the actual bandwidth
requirement. It also omits request queueing, cache lookup/setup, contention and
other exposed transfer stages. A favorable inequality therefore leaves a
candidate to measure; it does not guarantee lower time to first token (TTFT).

## Illustrative decision using explicit inputs

Use the Table 1 model and compute rate with an assumed `p = 8192`:

```text
prefix_kv_bytes = 2,684,354,560 B
saved_prefix_flops ~= 1,143,492,092,887,040 FLOP
saved_compute_time ~= 458.13 ms
break_even_B = prefix_kv_bytes / saved_compute_time = 5.859375 GB/s
```

This reproduces the paper's rounded 6 GB/s A800 example. The following
bandwidths are illustrative supplied values, not measured rates:

| Assumed loading rate | Modeled loading time | Decision at this screening step |
| --- | --- | --- |
| 5 GB/s | 536.87 ms | Loading already exceeds saved compute; do not justify reuse with this model. |
| 10 GB/s | 268.44 ms | About 189.69 ms remains for additional exposed cost; investigate the actual path. |

For the favorable row, first establish cache validity and availability. Then
measure effective loading and compute rates under the intended workload, plus
the additional exposed queue/setup/staging time. If that added time consumes
the modeled margin, this comparison no longer supports a TTFT benefit. Unknown
inputs leave current feasibility `INSUFFICIENT_EVIDENCE`; retain the existing
execution path while resolving them. Before adopting a change, compare actual
request latency and joint service-level objectives (SLOs) at a fixed workload
and resource budget. This example provides neither those measurements nor an
implementation or execution authorization.

## Source and reuse boundaries

- The retained paper qualification covers all 17 PDF pages (including the
  publisher cover), all 15 figures, two tables, Algorithm 1 and Equation 2;
  there is no appendix. This amendment extracts only the Section 2.2 condition.
- Sections 3.1 and 5.3 bound storage interpretation: the overview names SSD,
  while the detailed request workflow and capacity study use CPU memory/DRAM.
  The equation supplies no SSD I/O, persistence or recovery model. This limit
  says nothing about SSD support in current Mooncake implementations.
- Earlier extraction history positively lists `evaluate-kv-cache-transfer-gates`
  for remote prefix reuse, phase-pool transfer and projected decode-load
  admission; see the [retained B integration notes](../../../repositories/vllm/diagnose-vllm-admission-pressure/references/papers-20261015/INTEGRATION_NOTES.md).
  Its original synthesis/archive remains unavailable. This separate public-paper
  reference does not recover it; novelty against its unseen text is `UNKNOWN`.
- The paper's historical capacity, transfer and GPU-time results are author
  reports with separate denominators. None is a local performance or monetary
  cost result here. Current model/KV representation, matching prefix, placement,
  effective rates, overlap, load and SLO measurements remain required inputs.
- Raw PDF, extracted text and images are excluded. Their third-party
  redistribution permission remains `UNKNOWN`; public access and current
  repository software licensing do not supply that permission.
