# Indexer efficiency and retrieval accuracy — Issue #255

**Frozen comparison verdict: FAIL. Do not accept the runtime optimization on this evidence.**

The final feature branch is **evidence-only**: production runtime is restored to baseline; the rejected candidate and its tests are retained as a small exact-commit bundle/patch under `patch/`.

The primary request-local optimization is promising, but the unchanged acceptance contract includes a CLI-search tail guard that failed. This report preserves that failure; it is not an unconditional performance PASS or issue-closure decision. Retrieval results are identical before/after: this is an accuracy assessment, not an accuracy improvement.

## Headline table

| Dimension | Baseline → candidate | Disposition |
| --- | --- | --- |
| Primary paired reused-reader relevance latency | 58.61% reduction; group-bootstrap 95% CI 52.54–61.35% | Primary gate passes, **overall timing FAIL** |
| CLI catalog search p95, v1 | 450.21 → 687.56 ms (+52.72%; allowed ≤20%) | Guard fails; no sample removed |
| Separate CLI confirmation v2 | p50 +9.9734%; p95 −3.2103%, 120 pairs | Point gates pass; broad uncertainty, does not overwrite v1 FAIL |
| Frozen development partial-label Hit@5 / MRR@5 | 7/8 (87.5%) / 0.875 → identical | dev02 label ambiguous; not ground-truth full-query accuracy |
| Independently held-out partial-label Hit@5 / MRR@5 | 3/4 (75%) / 0.750 → identical | Unseen queries, not fully family-disjoint |
| Relevant-item emitted-byte fidelity/core delivery | dev 7/7, held-out 3/3 → identical | Conditional on retrieval; misses excluded and shown below |
| Supplemental all-required-resource audit | 58/58 emitted contexts per arm, exact bytes/hash/revision | Post-run independent audit, not frozen validation |
| Contract checks | 6/6 per arm, identical | No-match, incompatible filter, explicit ID, exact/undersized budget, stale projection |
| Output parity | Every one of 20 paired groups ×10 paths; all12 semantic cases | Exact serialized output equality |

## Reproducibility and interpretation

- Baseline: `ab03f3ffb8f2e5bc02c304828c5c41890eef673e`; candidate runtime: `6da28494891b21cdc89f632d84d763bc997b7d15`.
- Corpus: 751 packaged files, SHA-256 `411bd47a168f1549164f96fb3e4db4ba27e73edbb8d65b19d3bbc961897679c0`, identical before/after and across arms. Historical trim was already in baseline.
- Linux x86_64, Python3.12.14, reported CPU count9. Same interpreter and explicit source-root imports verified for both arms. Sanitized child environments; no model calls, hardware experiments or paid services.
- Frozen protocol: `plan/protocol.json`; commands and dependency versions: `plan/README.md` and `plan/python-environment.txt`. 20 alternating AB/BA groups, one warmup per reused-reader query/mode. Fresh reader ≠ cold filesystem cache. Full CLI includes interpreter startup and output capture.
- One runtime candidate; no tuning or rerun using held-out results. Small partial-positive labels do not establish complete Recall/Precision, downstream agent success or hardware efficacy. Peak memory was not measured; the per-request memo has nonzero retention overhead.

## All latency paths (milliseconds)

| Path | A p50 | B p50 | p50 change | A p95 | B p95 | p95 change | n/arm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hot_relevance/dev01 | 1370.08 | 484.44 | -64.64% | 2146.30 | 831.76 | -61.25% | 20 |
| hot_relevance/dev02 | 1400.00 | 551.04 | -60.64% | 2552.01 | 986.41 | -61.35% | 20 |
| hot_relevance/dev03 | 1183.81 | 563.73 | -52.38% | 2729.52 | 845.78 | -69.01% | 20 |
| hot_relevance/dev04 | 1150.67 | 567.04 | -50.72% | 2321.44 | 995.25 | -57.13% | 20 |
| fresh_relevance | 1193.42 | 702.32 | -41.15% | 2015.17 | 1263.89 | -37.28% | 20 |
| default | 1324.68 | 514.79 | -61.14% | 2378.70 | 1057.96 | -55.52% | 20 |
| context | 1068.10 | 574.24 | -46.24% | 1999.43 | 951.96 | -52.39% | 20 |
| search | 36.76 | 37.86 | +2.97% | 79.96 | 71.68 | -10.36% | 20 |
| cli_relevance | 1479.55 | 1016.48 | -31.30% | 2198.70 | 2634.82 | +19.84% | 20 |
| cli_search | 289.51 | 317.25 | +9.58% | 450.21 | 687.56 | +52.72% | 20 |

Negative change means faster. p95 is nearest rank from20 samples, a noisy descriptive tail—not a production SLO. Gates were not changed after measurement. The primary statistic is the median of within-group median four-query reductions, not a ratio of the table medians.

## Per-case retrieval results

| Case | Query intent | Known positive rank A/B | Required/core delivery among retrieved positives | Note |
| --- | --- | --- | --- | --- |
| dev01 | cgroupv2 cpu quota | 1 / 1 | 1/1 | partial positive label |
| dev02 | P2pNccl KV transfer completion | miss / miss | 0/0 | ambiguous mixed-intent label |
| dev03 | DLRover checkpoint replica recovery | 1 / 1 | 1/1 | partial positive label |
| dev04 | weight loading mmap checkpoint peak memory | 1 / 1 | 1/1 | partial positive label |
| dev05 | Ascend npu-smi device health before launch | 1 / 1 | 1/1 | partial positive label |
| dev06 | H3 MiniMax AdaLN SSD residency | 1 / 1 | 1/1 | partial positive label |
| dev07 | fixed workload throughput denominator timing claim | 1 / 1 | 1/1 | partial positive label |
| dev08 | storage fio direct IO page cache measurement | 1 / 1 | 1/1 | partial positive label |
| heldout01 | TorchNPU nonblocking transfer finished submitting but pinned RAM remains occupied; when may a CPU buffer be reused? | 1 / 1 | 1/1 | partial positive label |
| heldout02 | Checkpoint loading got faster on the second run. Does high disk utilization prove the SSD is the bottleneck, or could cached reads explain it? | miss / miss | 0/0 | natural-language positive missed; other returned items may still be relevant |
| heldout03 | After asynchronous training save staging completes, may the next checkpoint overwrite its cached CPU snapshot while the previous writer is still uploading? | 1 / 1 | 1/1 | partial positive label |
| heldout04 | SGLang video generation request timed out and its job record was deleted. How can I tell whether the worker stopped computing and released its resident components? | 1 / 1 | 1/1 | partial positive label |

The seven source-valid development cases have a separately labeled sensitivity subtotal Hit@5=7/7 and MRR@5=1.0; this does **not** replace the frozen8-case diagnostic. dev02 combines KV-transfer intent with an AFD hidden-state skill that explicitly excludes KV-block release. Heldout02 asks about repeated checkpoint-load speed/cache versus SSD bottlenecks and misses the labeled storage I/O skill despite the explicit `fio`/`page cache` development query succeeding. This is a useful lexical-versus-natural-query coverage gap, not evidence that every returned alternative was wrong. See `validator/label-review.md`.

## CLI tail diagnosis (observation, not a waiver)

- `catalog.search_knowledge` and its CLI search handler are unchanged and do not invoke Collect/Bundle manifests. The CLI imports the knowledge-operations module, but the optimized function is not executed on this search path. This narrows the plausible mechanism; it does not prove the observed regression is noise.
- Candidate CLI-search largest observations were group10 (AB) 1757.82ms, group16 (AB) 687.56ms, group18 (AB) 534.67ms. Baseline maximum452.44ms and p95 450.21ms. The p95 failure remains even though the maximum is not used as p95.
- CLI JSON decoding is measured separately and is sub-2ms; it does not explain the end-to-end tail. Catalog API p50 changes only+2.97%. Startup/import/scheduling/output capture were not separately instrumented, and host contention telemetry was not collected: attribution is unresolved.
- All raw samples and AB/BA order remain in `results/paired-run/timing.json`. A new confirmation study, if approved and prospectively frozen, must be a separate result and cannot replace this FAIL.

## Separate prospective confirmation v2

One focused replication was frozen in [Issue #255](https://github.com/InferMatrixLab/InferRSI/issues/255#issuecomment-6497690434) before execution. Same runtime candidate and exact v1 CLI invocation; 120 paired samples in balanced randomized AB/BA order (seed25502), then40 separate baseline/baseline diagnostic pairs (seed25503). All outputs and before/after source identities match. No samples or studies were pooled, dropped or repeated to obtain a pass.

| Study | n/arm | A p50 | B p50 | p50 change (paired95%CI) | A p95 | B p95 | p95 change (paired95%CI) |
| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| Confirmation v2 | 120 | 240.44 | 264.42 | +9.9734% (+1.20…+20.92%) | 599.97 | 580.71 | −3.21% (−22.23…+50.86%) |
| Baseline/baseline negative control | 40 | 228.23 | 226.30 | −0.85% (−9.18…+7.59%) | 336.39 | 364.26 | +8.29% (−5.98…+41.78%) |

Times are milliseconds. **v2's prespecified point gates pass**, narrowly at the10% median guard. Its uncertainty does not exclude a meaningful median or tail regression. The negative control illustrates variability but does not prove all candidate regression is environmental. v1 remains **FAIL** and runtime promotion is not justified by treating v2 as a replacement. These are separate studies, not an unconditional combined PASS. Raw chronology and bootstrap results: `results/confirmation-v2.json`; prospective protocol/wrapper hashes are recorded there.

## Software checks and remaining acceptance blocker

- Focused runtime/selection/knowledge tests:62 passed,2 Windows-only skips. New tests cover exact-byte/path reuse, changed owners/bytes, mutable metadata/dependencies, unsafe paths, non-byte content and no cross-request memo.
- Initial complete suite:2504 passed,9 failed,10 skipped; retained unchanged in `results/full-suite-initial.txt`. Eight failures were subprocess import errors from an uninstalled isolated environment; one was new evidence inventory registration/count. No full-suite PASS is claimed.
- After explicit source-path setup and inventory registration/count correction, unaffected inventory/module-boundary/server-process/summary tests:30 passed. This does not substitute for five outside-repository installed-package smoke tests.
- Repository CI lint command `ruff check src tests tools` and this campaign validator directory both pass. Broader `ruff check .` reports372 unchanged historical-evidence findings; baseline/final concise outputs are byte-identical and retained.
- The earlier focused source/harness/inventory/summary/module/server run recorded **89 passed,2 Windows-only skips** (`results/final-evidence-tree-tests.txt`), but it preceded inclusion of the final33-entry campaign integrity manifest. Despite that log filename, it did **not** prove the final published tree passed. Hosted CI then correctly exposed the stale inventory assertion (166 expected versus199 checked). The assertion is corrected to199; `results/post-manifest-verification.txt` records the affected test rerun after final manifest regeneration. This later software receipt is Git-versioned but deliberately excluded from the campaign integrity manifest to avoid a self-referential test-log/hash cycle. Original logs and benchmark data are retained unchanged. Production runtime equals baseline; candidate-only tests remain in the preserved patch.
- Editable package/build-dependency installation was denied by the execution approval gate; no retry or bypass. Installed-package smoke remains blocked pending specific authorization. Optional image dependencies and opt-in fresh-venv/Windows tests were not silently counted as passes.
- Runtime candidate is **not accepted** because the frozen CLI p95 guard failed. Evidence delivery is distinct from optimization acceptance and from closing the tracker.

## Raw evidence packaging

Large complete JSON outputs are losslessly gzip-compressed (`mtime=0`) and byte-identical A/B outputs share one object. `results/raw-archives.json` records every original path, original hash/byte count and compressed hash/byte count. This preserves full outputs without26MB of expanded duplicate text. `validator/verify_raw_archives.py` verifies and optionally restores them. Supplemental mandatory-resource audit is post-run and explicitly distinguished from the frozen runner.
