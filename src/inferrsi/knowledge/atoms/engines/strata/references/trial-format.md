# Trial data contract

Run the bundled helper with Python 3.10+ (standard library only):

```text
python <skill-root>/scripts/summarize_trials.py trials.csv
```

Required CSV header:

```csv
trial_id,config_id,experiment_id,hardware_id,workload_id,baseline_id,ttft_ms,decode_tps,peak_vram_mib,peak_ram_mib,quality_ok,valid
```

Define the four comparison IDs in a separate experiment manifest. Keep model and pack hashes, source/build/toolchain, tokenizer, sampling, actual input/output tokens, concurrency, cache/warmup protocol, quality reference and resource limits fixed behind those IDs. All rows must have the same nonempty comparison IDs; mixed conditions reject the whole file, even when the mixed row fails quality.

Each row is one measured run. Use unique trial IDs and a configuration ID tied to a saved config or patch. Any duplicate nonempty trial ID rejects the whole file before filtering, regardless of row order. `quality_ok` means the declared correctness/quality checks actually passed. `valid` means the run completed under the required context/output/concurrency and every resource bound. Only literal `true` (case-insensitive) passes. Never mark these fields based on speed alone.

TTFT is client first-token latency in milliseconds. Decode throughput is model tokens per second with the same timing definition in every row; do not mix stream chunks, client estimates and engine-reported tokens. Memory values are per-run peaks in MiB. Numeric metrics must be finite; TTFT and throughput must be positive, memory nonnegative.

The helper reports descriptive medians, accepted sample counts and rejection reasons. A configuration with any rejected row is excluded from the Pareto set even if other rows passed. The Pareto objectives are lower TTFT and higher decode throughput; neither may worsen and one must improve for domination. Memory is reported but is not a Pareto objective. Enforce every per-run memory limit in `valid` before summarizing; a median cannot prove a peak bound.

These summaries do not compute confidence intervals, quality scores, power, p95 latency or significance. Preserve raw logs and perform those analyses separately. An empty eligible set is not a successful optimization. The helper was authored for this skill, not copied from Strata.
