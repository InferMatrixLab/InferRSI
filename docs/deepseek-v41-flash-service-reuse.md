# DeepSeek V4.1 Flash on Ascend 910C

In an independent service restart, four retained changes reduced TPOT from **39.6646 to 37.1970 ms/token at C1**, **44.6316 to 40.9078 at C4**, and **57.4303 to 50.8701 at C16**. The final GSM8K score was **292/300** and the relative InferRSI gate passed. **Overall acceptance was FAIL** because all three workloads exceeded the frozen 25 ms/token target.

This case covers the DeepSeek V4.1 Flash 1017 W8A8 checkpoint served by vLLM-Ascend on one Ascend 910C node with 8 cards and 16 dies, TP4 / DP4 / EP16, mixed prefill and decode, and DSpark. The retained stack removed eager prefill mask expansion, changed two bounded index operations, and fused HC post-processing. All baselines and candidates were measured in the fresh campaign. [Issue #524](https://github.com/InferMatrixLab/InferRSI/issues/524) · [Archive manifest](../evidence/deepseek-v41-flash-service-reuse-20261120/results/archive-manifest.json) · [Result summary](../evidence/deepseek-v41-flash-service-reuse-20261120/results/summary.json) · [Retained patch](../evidence/deepseek-v41-flash-service-reuse-20261120/patch/selected-baseline.patch)

[Final results](#final-results-by-workload) · [Reproduction](#fixed-workload-and-reproduction) · [Offline dashboard replay](#offline-dashboard-replay)

## Final results by workload

The tables compare the fixed baseline `9be3c22a` and an independent restart of the selected R8 revision `25fa4660`. Each value is the median of two wave means. Change is signed, calculated as `(final − baseline) / baseline × 100%`. The span is the absolute difference between the two wave means. [Wave results and attempt IDs](../evidence/deepseek-v41-flash-service-reuse-20261120/results/summary.json)

### 8192/1024 C1

| Metric | Direction | Baseline | Final | Change | Absolute gate |
| --- | --- | ---: | ---: | ---: | --- |
| TPOT (ms/token) | Lower | 39.6646 | 37.1970 | −6.22% | FAIL (≤25) |

Baseline wave means 39.6888 / 39.6403 (span 0.0486). Final wave means 37.2723 / 37.1218 (span 0.1505). Both attempts completed 2/2 requests at this load.

### 8192/1024 C4

| Metric | Direction | Baseline | Final | Change | Absolute gate |
| --- | --- | ---: | ---: | ---: | --- |
| TPOT (ms/token) | Lower | 44.6316 | 40.9078 | −8.34% | FAIL (≤25) |

Baseline wave means 44.5240 / 44.7392 (span 0.2152). Final wave means 41.0189 / 40.7967 (span 0.2221). Both attempts completed 8/8 requests at this load.

### 8192/1024 C16

| Metric | Direction | Baseline | Final | Change | Absolute gate |
| --- | --- | ---: | ---: | ---: | --- |
| TPOT (ms/token) | Lower | 57.4303 | 50.8701 | −11.42% | FAIL (≤25) |

Baseline wave means 57.7178 / 57.1427 (span 0.5752). Final wave means 51.3689 / 50.3713 (span 0.9976). Both attempts completed 32/32 requests at this load.

The independent final was **−0.91% / −2.42% / −1.75%** against R8's acceptance parent R3 at C1 / C4 / C16. C4 met the ≥2% parent gain requirement. All three stayed within the ≤1% regression caps against both references. The baseline and final each scored 292/300 on the fixed GSM8K test, meeting the quality gate. Final readiness, formal timings, GSM8K and verified cleanup all bind to the same new service. [Parent and final trial records](../evidence/deepseek-v41-flash-service-reuse-20261120/results/summary.json)

## Fixed workload and reproduction

- **Serving stack.** vLLM-Ascend baseline `9be3c22ab5dade39c0d33d49540ae021ff74bbd1`, vLLM `6e448d0ea9bf3d88d898b65449ca6dc2aec170ac`, CANN 9.1.0, driver 25.5.1.1, Python 3.12.13, Torch 2.10.0+cpu and torch-npu 2.10.0.post4. The served model alias was `dsv41-0day`. The matching checkpoint requires authorized access. The archive includes the RunSpec in `plan/runspec.md` and the exact serving command in `validator/serve.sh`.
- **Performance.** Each of 12 service lifecycles ran a 21-request warmup at 8192/32, then two formal 8192/1024 waves in C1 → C4 → C16 order, 42 requests total. Two frozen raw-token banks supplied the inputs. Routing was `slot % 4`, with per-attempt cache isolation. All 504 formal requests succeeded, with exact lengths and zero matched prefix tokens. Per-request TPOT is elapsed client monotonic time from the first complete SSE frame with a generated token ID to HTTP EOF, divided by generated tokens minus one. TPOT was the sole performance objective. The repeats measure within-service variation. The archive contains the stage receipts and `plan/evaluation-settings.redacted.json`.
- **Quality.** Fixed 300 GSM8K test questions (seed 42 over the original 1,319), scored with the pinned AISBench `Gsm8kEvaluator` using the frozen zero-shot CoT chat template. C32, 4096 maximum output tokens, and one request per question. Truncations are scored. The candidate quality stage runs after the relative performance gate.
- **Codex and InferRSI.** Run the recorded prompt in a Codex session with the InferRSI plugin enabled, in the target vLLM-Ascend checkout. This campaign used plugin `0.1.0` and runtime `0+unknown`, pinned by source `b5756cd561e8b12b68899d9dfa6411feab4669f5` and content hash. The task used a new directory and a one-time allowlisted copy of benchmark and validator inputs. All new performance results and optimization hypotheses came from this campaign and its pinned knowledge library. The archive preserves `plan/prompt.md` and `plan/frozen-sources.json`. [Plugin guide](codex-plugin.md)

## Optimization rounds

Four rounds passed the relative performance, GSM8K, and cleanup checks. Every PASS became the next comparison parent and direct Git parent. In R2 the C16-first ranking initially favored R1, and the run wrapper advanced R2 under the user's parent rule. R8 was both the last accepted revision and the best accepted candidate in the frozen C16 → C4 → C1 ranking. The independent final used a new service for R8. [Trial index](../evidence/deepseek-v41-flash-service-reuse-20261120/results/summary.json)

The table reports screening TPOT in C1 / C4 / C16 order, in ms/token. Percentages in the decision column refer to each round's comparison parent. Rejected rounds retain their timings and record GSM8K as `NOT_RUN`. Individual patches are under `patch/round-NN.patch` in the archive.

| Round | Parent → candidate | Profiling cue and change | TPOT (C1 / C4 / C16) | GSM8K | Decision |
| --- | --- | --- | --- | ---: | --- |
| 1 | `9be3c22a` → `f9958ee4` | `RepeatInterleave` expanded masks during overlapping prefill. Keep eager prefill masks at block granularity. | 39.7812 / 44.0778 / 55.8778 | 293/300 | PASS, C16 −2.70%. |
| 2 | `f9958ee4` → `86650a73` | INT64 Ascend AI_CPU Sort on selected indices. Sort in FP32 where the input indices are exactly representable, then restore INT64. | 38.9813 / 43.1903 / 55.9452 | 293/300 | PASS, C1 −2.01%, C4 −2.01%, C16 +0.12%. |
| 3 | `86650a73` → `03ec787b` | INT32 AI_CPU TopK on cutoff ties. Use exact FP32 only for the tie-column TopK input. | 37.5395 / 41.9223 / 51.7785 | 295/300 | PASS, C16 −7.45%. |
| 4 | `03ec787b` → `86e223e7` | Separate clip and gate ops in grouped W8A8. Reuse native clipped SwiGLU. | 37.3227 / 41.7537 / 51.3998 | NOT_RUN | FAIL, largest gain 0.73%. |
| 5 | `03ec787b` → `111e06dd` | AI_CPU `Cumsum` on bounded prefixes. Use INT32 accumulation for the tie and sparse-slot masks. | 37.0640 / 40.9601 / 52.7793 | NOT_RUN | FAIL, C16 +1.93%. |
| 6 | `03ec787b` → `5d466b55` | Multi-op E4M3 prefill quantization. Extend the A3 single-pass kernel to the full output-projection tile. | 37.7317 / 42.2988 / 51.3760 | NOT_RUN | FAIL, largest gain 0.78%. |
| 7 | `03ec787b` → `c42e663e` | Scalar scan for the first negative sparse index. Check aligned rows eight entries at a time with scalar tail and fallback. | 37.6142 / 41.4772 / 54.3910 | NOT_RUN | FAIL, C16 +5.05%. |
| 8 | `03ec787b` → `25fa4660` | Large HC post broadcast and reduction intermediates. Reuse A3 `npu_hc_post` for guarded BF16 residual and FP32 gate layouts. | 37.3197 / 41.4501 / 50.6157 | 294/300 | PASS, C16 −2.25%. Selected. |
| 9 | `25fa4660` → `d20a49b5` | Frequent small gates and affine ops. Merge HC affine with Sinkhorn and share the native Sigmoid. | 36.6631 / 40.7400 / 51.0305 | NOT_RUN | FAIL, largest gain 1.76%. |
| 10 | `25fa4660` → `7221866e` | Frequent small FP32 reductions in V4.1 RMSNorm. Reuse A3 RMSNorm for the model's contiguous BF16 input layouts. | 43.0684 / 39.5682 / 48.5355 | NOT_RUN | FAIL, C1 +15.40%. |

The run retained verbatim candidate hypotheses, the delivered context filenames, and the cited applicability rules. R1 used the materialization rule in [performance ceiling analysis](../src/inferrsi/knowledge/data/skill_library/playbooks/measurement/performance-ceiling-analysis/SKILL.md). R2 used the dtype and fallback checks in [Ascend performance analysis](../src/inferrsi/knowledge/data/skill_library/systems/platforms/ascend/ascend-performance-analysis/SKILL.md). R5 consulted the [Ascend optimization casebook](../src/inferrsi/knowledge/data/skill_library/casebooks/ascend/ascend-optimization-casebook/SKILL.md). The other rounds referenced the same-card and same-shape checks in [Ascend operator tuning](../src/inferrsi/knowledge/data/skill_library/systems/platforms/ascend/ascend-operator-tuning/SKILL.md). The delivery records mark the contexts as prepared. The authored hypotheses identify the specific rules applied. The full round ledger and parent-adoption helper are in the archive.

### Profiling and rejected changes

The profiler used a separate 8192/32 C16 diagnostic wave. The baseline and R1 exported all 16 ranks. R2 through R10 kept all 16 raw captures and exported the same randomly drawn cross-DP pair, EP5 (DP1/TP1) and EP12 (DP3/TP0). The live worker could capture, and the daemon's inline parser failed. Offline parsing after cleanup recovered the windows used to plan the next round. Per-stream measurements cover overlap with outstanding prefills, full-concurrency decode, and the final decode tail. The archive records the random draw and window summaries in `results/profiles.json`.

- R8 ran `HcPost` 400 times per sampled EP in the full-concurrency decode window. For a 2040-row probe, fusion changed 1,347 out of 41,779,200 BF16 outputs through rounding, with maximum absolute difference 0.015625. The guarded path passed the numeric probe and same-service GSM8K.
- R5 removed AI_CPU `Cumsum` from the sampled decode stream and the microbenchmark improved from 185.14 to 34.65 μs at `[64,512]`. The formal C16 regression still rejected the candidate.
- R10 reduced the 6×5120 BF16-weight RMSNorm probe from 76.65 to 23.30 μs. Both formal C1 waves regressed. The generated sequences changed and observed DSpark acceptance moved from 730/1490 (49.0%) to 658/1830 (36.0%), with 298 versus 366 proposal steps. The run establishes an association with the C1 regression. A causal split between rounding, draft behavior, and other execution effects remains unresolved.

## Offline dashboard replay

The review archive is `deepseek-v41-flash-service-reuse-20261120-evidence-v1.tar.gz`. It contains the dashboard, samples, per-round patches, run configuration, replay script, screenshots and original browser receipt. The archive was verified from a local copy. A versioned download URL is pending. [Archive manifest](../evidence/deepseek-v41-flash-service-reuse-20261120/results/archive-manifest.json)

From the InferRSI checkout, set `DSV41_ARCHIVE` to the absolute path of the archive. Verify its SHA-256, then extract it to a temporary directory and recompute the timings.

```bash
manifest=evidence/deepseek-v41-flash-service-reuse-20261120/results/archive-manifest.json
expected_sha=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["sha256"])' "$manifest")
printf '%s  %s\n' "$expected_sha" "$DSV41_ARCHIVE" | sha256sum --check - &&
  replay_dir=$(mktemp -d) &&
  tar -xzf "$DSV41_ARCHIVE" -C "$replay_dir" &&
  python3 "$replay_dir/deepseek-v41-flash-service-reuse-20261120/validator/replay.py"
```

Open `$replay_dir/deepseek-v41-flash-service-reuse-20261120/results/dashboard.html` over `file://`. The **Independent final** and **Rejected round 10** links lead to each attempt's **Timing and stage receipts** with the original run and attempt IDs. Review screenshots and the original browser receipt under `results/screenshots/` and `results/browser-replay.json` inside the archive.

A fresh offline Chromium profile reopened the extracted dashboard and recomputed final C16 **50.8700750465237 ms/token** and rejected R10 C1 **43.06836537194526 ms/token** from the linked samples. It also followed R10's parent link and confirmed the **+15.4038%** regression. The archive's Python validator checked all 504 formal requests across 12 attempts. [Replay result and trace IDs](../evidence/deepseek-v41-flash-service-reuse-20261120/results/summary.json)

Weights, input tokens, GSM8K answers, full device validators and raw traces require authorized access. A separate Campaign acceptance issue and independent acceptance owner have yet to be identified.
