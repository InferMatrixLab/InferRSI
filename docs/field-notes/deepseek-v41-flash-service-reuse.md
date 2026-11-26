# DeepSeek V4.1 Flash on Ascend 910C

A fresh-service retest of the selected R16 patch reduced client-visible time
per output token (TPOT) by **22.84–24.22%** across C1, C4, and C16 versus
the fixed baseline. The patch targets hyperconnections (HC), DeepSeek Sparse
Attention (DSA), and KV staging in DeepSeek V4.1 Flash W8A8. This independent
InferRSI `service_reuse` run does not constitute formal #602 acceptance.

[Technical protocol (#602)](https://github.com/InferMatrixLab/InferRSI/issues/602) ·
[Public evidence archive](https://github.com/user-attachments/files/35452881/issue-602-offline-evidence-public-v1.tar.gz)

## Results and scope

| Concurrency (8192 in / 1024 out) | Baseline (ms/token) | Final (ms/token) | TPOT change |
| --- | ---: | ---: | ---: |
| C1 | 40.0760 | 30.9226 | −22.84% |
| C4 | 44.7217 | 33.8909 | −24.22% |
| C16 | 57.8936 | 43.9464 | −24.09% |

TPOT change is `(final − baseline) / baseline × 100%`. Each workload cleared
the **>10% reduction** target before rounding. Final GSM8K met the **292/300**
floor, down from **294/300** at baseline. Timing, GSM8K, and verified cleanup
refer to the same final service. The case makes no end-to-end latency or
throughput claim.

The [cumulative patch](../../evidence/deepseek-v41-flash-service-reuse-20261124/patch/selected-baseline.patch)
compares baseline `9be3c22ab5dade39c0d33d49540ae021ff74bbd1` with R16
`fff7b712ad3747ac924e92c6502a71034890f65d`.

Three fresh A/A launches informed the round margins, with TPOT spreads of
0.19%, 0.94%, and 2.48% in C1 / C4 / C16 order. Search used a separate fixed
baseline whose C1 and C4 were 1.36% and 0.14% above their A/A maxima. The
A/A readiness verdict remains `INCONCLUSIVE`.

## Fixed workload and method

| Control | Setting |
| --- | --- |
| Engine | vLLM-Ascend with DSpark |
| Hardware | 8 Ascend 910C cards / 16 dies, TP4 / DP4 / EP16, colocated prefill and decode |
| Timing | 8192/32 warmup, then two timed 8192/1024 waves per service in C1 → C4 → C16 order, with synchronized requests at each load |
| Quality | Pinned AISBench evaluator on a fixed 300-item GSM8K subset |
| Profiling | Separate 8192/32 waves at C1 and C4, 8192/64 at C16. One EP from the active DP at C1 and one EP per DP at C4 and C16. |
| Search | C16 → C4 → C1 ranking. A winning PASS became the next parent. No target-triggered early stop. |
| Budget | 24 hours including A/A and cleanup, with an hour reserved for final. About 19 hours used. |

Per request, TPOT is the client elapsed time from the first complete SSE frame
carrying a generated token ID to HTTP EOF, divided by the output token count
minus one. Each evaluation used 42 timed requests, aggregated as the median
of two wave means at each concurrency.

The launch prompt below is an English translation of the actual request, with
the private task and local skill link removed. A follow-up confirmed that the
run would use the same technical RunSpec and report its results separately.

> Use service reuse in the authorized environment. Collect profiling data and
> export one EP per DP. Follow the RunSpec and enable knowledge retrieval from
> the repository, MindIE, and CANNBot. For each candidate, pursue substantive
> optimizations by combining changes across bottlenecks.

The agent used those sources alongside the profiles to plan candidates.
For a new run, follow the [Codex plugin guide](../guides/plugins/codex-plugin.md) and the
[optimization workflow](../guides/optimization-workflow-unification.md).

## Optimization rounds

The [trial summary](../../evidence/deepseek-v41-flash-service-reuse-20261124/results/summary.json)
indexes all 20 candidates, including 13 failures. The seven promotions below
show screening TPOT in C1 / C4 / C16 order.

| Round | Comparison parent | Retained change | TPOT (ms/token) | GSM8K |
| --- | --- | --- | ---: | ---: |
| R02 | Baseline | Fuse four-way HC input mixing and residual combination in separate Triton kernels, keeping the FP32 operation order. | 38.30 / 42.44 / 54.59 | 294/300 |
| R03 | R02 | Keep ordered INT32 physical KV slots through target decode and DSpark draft attention. | 36.45 / 40.48 / 52.04 | 294/300 |
| R04 | R03 | Scan DSA Top-K cutoff ties within bounds and fill in original column order. | 34.76 / 38.10 / 50.28 | 293/300 |
| R06 | R04 | Use exact FP32 sorting for the bounded candidate IDs and remove redundant valid-length masking in paged scoring. | 33.70 / 37.32 / 49.90 | 293/300 |
| R09 | R06 | Fuse HC casting, squaring, and gate affine work. Prepare BF16 target and DSpark LM heads at weight load. | 33.24 / 36.58 / 47.12 | 293/300 |
| R14 | R09 | Delay prefill DSA block masks to avoid expansion. Fuse decode row masks into HC and RMSNorm. | 31.78 / 35.41 / 44.88 | 293/300 |
| R16 | R14 | Tile selected-KV by row, reuse its metadata, and skip the unused cache source for homogeneous tiles. | 31.19 / 34.67 / 43.07 | 293/300 |

R16 advanced on C16 with a **4.0241%** reduction against R14 (4% required).
The fresh retest cleared the parent-relative gate on C1 and C4. Its C16 TPOT
was higher than in screening.

R01 improved C16 by 7.75% but failed C1's regression cap. R20's combined W8A8
prefill routing and grouped epilogue passed a targeted probe but did not
meet a promotion threshold on any workload. Neither round ran GSM8K.

## Offline evidence replay

From the InferRSI checkout, verify the saved archive against the
[pinned hashes](../../evidence/deepseek-v41-flash-service-reuse-20261124/results/artifacts.json)
before extracting it. Replay uses only Python's standard library.

```bash
DSV41_ARCHIVE=/path/to/issue-602-offline-evidence-public-v1.tar.gz
manifest=evidence/deepseek-v41-flash-service-reuse-20261124/results/artifacts.json
python3 tools/verify_evidence_archive.py "$manifest" --archive "$DSV41_ARCHIVE" &&
  replay_dir=$(mktemp -d) &&
  tar -xzf "$DSV41_ARCHIVE" -C "$replay_dir" &&
  (cd "$replay_dir" && python3 validator/replay.py)
```

Replay covers 1,050 timing rows (924 evaluation and 126 calibration), all 20
round decisions, and GSM8K totals from 2,700 item outcomes. Use the run IDs
below to find the wave samples in the archive's `results/trials.jsonl`.

| Trial | Run ID | Attempt ID | Expected replay check |
| --- | --- | --- | --- |
| Independent final | `30ead6bdd21f4605a7549fb1b19af8fd` | `4a09ee03cd6d4ba89c0e19e253092183` | C16 43.946426114827716 ms/token, final PASS |
| Rejected R01 | `728df2be453b451b86aa8317902ee89d` | `0a06a9debaa6421891d4445c36018400` | C1 44.9694 ms/token, +12.21% vs. parent, performance-gate FAIL |

The public archive omits raw responses, request banks, traces, the HTML
dashboard, and per-round patches. It supports offline replay, not re-grading
answers or reproducing device execution. The running image digest was unavailable.
