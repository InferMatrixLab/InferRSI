# CPU offline retrieval performance

The [frozen protocol](../plan/protocol.json)
used **20 paired groups**, ten AB and ten BA, over four fixed development cues:
`dev01`, `dev05`, `dev09` and `dev13`. Repeats do not add query types. Each side
ran in an isolated source-selected subprocess using CPython **3.12.6** with
site initializers disabled; import origins and complete source/corpus digests
were checked. The corpus contained **108 records**, including **60 generated
packaged skills**, within **458 evaluated corpus files / 2,883,003 bytes**.
The shared library accounted for **342 files / 2,294,958 bytes**. There were
**53 Python source files** in the source identity snapshot.

Hardware was an Intel Core i7-8565U, four physical/eight logical cores,
15.8 GiB RAM, Windows 10 Pro 10.0.19045. Clock/power state and unrelated
background load were uncontrolled; the CPU inventory's 1.80 GHz is not a
clock-lock observation. Fresh-reader calls include constructing a new reader;
hot calls reuse one reader after the fixed warmup. Neither establishes a cold
OS filesystem cache. CLI process/capture time and UTF-8 decode/JSON parse time
are measured separately. Collect CLI lacks the API's repo/backend filters, so
its wider-scope costs are diagnostics, not part of the fair scoped API gate.

For each pair, the estimator takes the median of its four hot-query latencies
on each revision and computes `1 - candidate_median / baseline_median`; the
primary estimate is the median of those 20 reductions. The frozen 10,000-draw
percentile bootstrap resamples complete paired groups with seed `19020261027`.
The observed reduction is **40.0068267%**, with 95% interval
**[38.3789227%, 41.0592071%]**. This satisfies the prospective issue bar of at
least 20% paired-median reduction and a lower 95% bound above zero. It is an
offline CPU retrieval result for this corpus, interpreter, machine and workload.

The measurement loop retained **640 API calls and 160 CLI processes** over
**836.162 seconds**; preflight/final inventory work is outside that elapsed
counter. All **400 cross-version output pairs**, including **80 exact CLI
stdout pairs**, preserved their digests. Complete measurement sets and final
source/corpus identities passed. Independent read-only review reproduced all
48 side-specific p50/p95 groups and the exact primary/bootstrap numbers from
the raw observations.

Regressions remain visible: API search `dev01` p50 rose **31.409 → 31.782 ms
(+1.19%)**, and CLI search `dev05` p50 rose **340.560 → 349.067 ms (+2.50%)**.
CLI relevance decode p95 rose **1.810 → 3.046 ms**, an absolute increase of
**1.236 ms (+68.31%)**. These observations do not establish a cause. Individual
rows are descriptive; no per-row significance gate was prespecified. Each p95
below is a sample quantile from **20 repeats per revision**, not a service tail
guarantee or evidence for additional query populations.

Every measured mode/query appears below. Values are milliseconds; positive
deltas mean the candidate was slower. The complete exact-nanosecond summaries
are in [latency-summary.json](latency-summary.json),
with all raw samples and output hashes in
[benchmark.json](benchmark.json).
The baseline [profile](baseline-profile.json)
and [#129 trace](baseline-trace-129.json)
are separate diagnostics excluded from the timing samples. No model, GPU,
inference-service or real-agent-task comparison ran.

### API call wall time

| Mode / case | Baseline p50 | Candidate p50 | Delta p50 | Baseline p95 | Candidate p95 | Delta p95 |
| --- | --- | --- | --- | --- | --- | --- |
| `cold_context_material` / `dev09` | 1060.606 | 686.352 | -35.29% | 1570.936 | 885.685 | -43.62% |
| `cold_default_diagnostic` / `dev05` | 999.688 | 614.151 | -38.57% | 1657.808 | 741.097 | -55.30% |
| `cold_relevance` / `dev01` | 1141.533 | 788.233 | -30.95% | 1427.484 | 1146.733 | -19.67% |
| `cold_relevance` / `dev05` | 1061.825 | 683.019 | -35.67% | 1247.372 | 817.370 | -34.47% |
| `cold_relevance` / `dev09` | 1083.634 | 680.551 | -37.20% | 1901.819 | 872.078 | -54.15% |
| `cold_relevance` / `dev13` | 1057.574 | 677.726 | -35.92% | 1766.674 | 844.748 | -52.18% |
| `hot_context_material` / `dev09` | 944.589 | 577.180 | -38.90% | 1495.627 | 780.720 | -47.80% |
| `hot_default_diagnostic` / `dev05` | 882.934 | 504.028 | -42.91% | 1529.218 | 640.953 | -58.09% |
| `hot_relevance` / `dev01` | 1021.204 | 663.073 | -35.07% | 1317.269 | 910.342 | -30.89% |
| `hot_relevance` / `dev05` | 938.521 | 579.671 | -38.24% | 1226.804 | 879.716 | -28.29% |
| `hot_relevance` / `dev09` | 957.842 | 577.391 | -39.72% | 1702.202 | 725.926 | -57.35% |
| `hot_relevance` / `dev13` | 949.685 | 566.260 | -40.37% | 1935.473 | 806.471 | -58.33% |
| `search` / `dev01` | 31.409 | 31.782 | +1.19% | 54.012 | 53.470 | -1.00% |
| `search` / `dev05` | 31.935 | 31.307 | -1.96% | 39.201 | 38.680 | -1.33% |
| `search` / `dev09` | 31.590 | 31.506 | -0.27% | 54.718 | 46.758 | -14.55% |
| `search` / `dev13` | 31.385 | 31.159 | -0.72% | 65.095 | 40.073 | -38.44% |

### Full CLI process plus stdout capture

| Mode / case | Baseline p50 | Candidate p50 | Delta p50 | Baseline p95 | Candidate p95 | Delta p95 |
| --- | --- | --- | --- | --- | --- | --- |
| `context_material` / `dev09` | 1413.646 | 1017.286 | -28.04% | 2644.763 | 1423.810 | -46.16% |
| `default_diagnostic` / `dev05` | 1613.022 | 1103.381 | -31.60% | 2133.128 | 1382.574 | -35.19% |
| `relevance` / `dev05` | 1413.156 | 998.828 | -29.32% | 1718.849 | 1369.453 | -20.33% |
| `search` / `dev05` | 340.560 | 349.067 | +2.50% | 487.368 | 451.238 | -7.41% |

### CLI UTF-8 decode and JSON parse

| Mode / case | Baseline p50 | Candidate p50 | Delta p50 | Baseline p95 | Candidate p95 | Delta p95 |
| --- | --- | --- | --- | --- | --- | --- |
| `context_material` / `dev09` | 3.289 | 3.296 | +0.19% | 5.639 | 4.242 | -24.78% |
| `default_diagnostic` / `dev05` | 0.022 | 0.022 | -0.45% | 0.030 | 0.032 | +6.81% |
| `relevance` / `dev05` | 1.532 | 1.537 | +0.34% | 1.810 | 3.046 | +68.31% |
| `search` / `dev05` | 0.012 | 0.013 | +2.42% | 0.016 | 0.014 | -11.16% |
