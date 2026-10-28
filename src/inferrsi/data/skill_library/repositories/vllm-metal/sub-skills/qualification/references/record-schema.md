# Offline record helper

`summarize_serving_records.py` adapts token accounting, not the engine/model
runner in source [avg_gen_length.py](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/tools/avg_gen_length.py).
It removes model loading, dataset/network access, MLX imports and measurement.
All input is caller-supplied and untrusted. Identity hashes are syntax-checked,
not authenticated against bytes. Metric scope labels are not verified.

```json
{
  "schema_version": 1,
  "source_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "controls_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "metric": "http-serving",
  "samples": [
    {"variant":"baseline","phase":"warmup","execution":"completed","output_tokens":8,"duration_ms":100},
    {"variant":"baseline","phase":"measured","execution":"completed","output_tokens":10,"duration_ms":1000},
    {"variant":"candidate","phase":"measured","execution":"blocked","output_tokens":null,"duration_ms":null}
  ]
}
```

Metric may be `http-serving`, `offline-generation` or `kernel`. Both baseline
and candidate require at least one measured record; warmup-only arms fail.
Each row has exactly the five shown keys. Execution is `completed`, `failed`,
`blocked` or `cancelled`. Completed rows require integer nonnegative token
counts and positive finite duration; incomplete rows require null measurements.
Booleans, NaN/infinity, unknown keys/classifications and oversized inputs fail.
The CLI reads at most1MiB and accepts at most10,000 records, exiting2 on invalid
input with an error that does not echo private input values.

Output retains per-arm failure/status counts and excluded warmup counts, sums
completed tokens/durations and reports a completed-subset rate. That sum is
not necessarily a valid wall-clock throughput under concurrent/overlapping
request windows. It never computes speedup, authenticates equal work, verifies
routes/quality or changes a campaign verdict; evidence remains INCONCLUSIVE.
Inspect original request/time-window records before interpreting any rate.
