# Qualification troubleshooting

| Symptom | Likely boundary | Recovery or stop condition |
| --- | --- | --- |
| Four CPU slices succeed, so someone proposes a GPU/model certificate | Arithmetic and simulation are being promoted beyond their consumers | Name each slice's scope from the verification contract. Require real backend/model evidence; retain `BLOCKED_REQUIRED_BACKEND` and `INCONCLUSIVE` when absent. |
| GPU test exits zero but says `no GPU, skipped` or tensor-core `SKIP` | Upstream skip convention is not an assertion pass | Retain exact skip/work counts. Do not run more GPU commands without the required backend; record the unavailable route separately. |
| Default build appears green with no model tests | Test-registration predicate is false or required files/artifacts are absent | Inspect configured test inventory, not just build status. Do not install/fetch missing components or enable model work automatically. |
| GLM `MTP_DECODE=1` still does not select the path | Single-part, sequences, no-MTP/no-spec, cap or DFlash gate | Resolve the exact model-runtime route. One-GPU enablement cannot override every prerequisite; parallel MTP has a different opt-in/row route. |
| DeepSeek requests a long lookup window but caller uses DSpark instead | First proposal disagreement, sampled drafts or measured policy economics | Check actual caller mode and effective window. Do not transplant a simulator's preferred window into production. |
| Greedy output agrees for a window then diverges later | Recurrent replay, NextN repair, speculative cache visibility, counter or tier arithmetic | Compare first/middle rejection, full acceptance and the following continuation with frozen state/tier controls. Stop speed claims until this correctness seam is qualified. |
| MM3 same seed changes after drafting or tier/parallel changes | Distribution-exact algorithm can consume RNG differently; CPU/GPU rounding and routes differ | Separate repeatability within one frozen configuration from cross-algorithm token identity. Use the frozen quality protocol appropriate to the claim. |
| High acceptance but worse decode | Verification/commit/cache costs or RAM/SSD misses outweigh saved rounds | Preserve wall-time components and complete tokens/time. A lower draft cap or no drafting is a candidate to measure, not a guaranteed remedy. |
| GLM calibration reports unusually high VRAM hits on a few questions | Repeated prompts trained expert placement toward the benchmark | Use fresh groups until wrap, record wrap/reuse and warmup, preserve copied usage and no-write controls. Reconfirm defaults and incumbent combinations interleaved. |
| DFlash/DSpark sequential comparison is noisy | Independent starts and placement/OS drift | Preserve order and every side; design separately frozen repeated/order-balanced controls if authorized. Do not describe the source sequence as ABBA. |
| Requested TP changes but effective grouping stays the same/unknown | Runtime fallback or incomplete telemetry | Treat duplicates as one effective configuration; unknown grouping is not a new ranked result. Preserve incumbent and missing telemetry. |
| Larger MM3 prefill chunk wins, decode worsens | Chunk buffers displace expert capacity | Keep the decode-side control and actual tune-record identity. Prefill-only wins do not clear a combined campaign. |
| Benchmark mean changes with short answers | Current source has answer-membership filtering and all-short fallback | Report actual token lengths, included count and raw rates; do not compare to a token-weighted reducer without labelling the changed aggregation. |
| Offline reducer rejects a record | Wrong schema/identity, booleans, duplicate keys, nonfinite duration or invalid count relationship | Normalize from original records explicitly. Do not edit the claimed source, hide failures, or fabricate missing times. Input is not a source-runner report. |
| Offline reducer emits a positive rate change despite blocked samples | It describes the completed subset only | Cite incomplete execution counts; do not convert the arithmetic to a native/model/service verdict. |
| Quant report shows high recovery, so a proposal says lossless | Task recovery and token/distribution agreement are different metrics | Preserve model/recipe/reference/held-out conditions and negative quality observations. Speculative exactness is against the selected target, not FP8 restoration. |

Before sharing, redact private model paths, machine names, process arguments and
service endpoints while preserving source revision, settings, failures and
measurement identity. Missing indispensable originals remain explicit gaps.
