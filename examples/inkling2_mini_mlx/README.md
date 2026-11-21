# Inkling 2 Mini on MLX: benchmark and RSI round scripts

Scripts and records behind [Inkling 2 Mini on Apple silicon](../../docs/inkling2-mini-apple-silicon.md).
They are maintainer tools, not part of the `inferrsi` package, and need an
Apple-silicon Mac with mlx-lm from ml-explore/mlx-lm#2086 (`0c4c991`).

| File | Purpose |
| --- | --- |
| `bench_mlx.py` | One code-generation request on MLX: TTFT, prefill/decode tok/s, peak memory, full output |
| `chat_bench.py` | The same request through llama-server's streaming OpenAI API |
| `bench_llama.sh` | `llama-bench` 512/128 × 3 with `/usr/bin/time -l` |
| `rsi_mlx.py` | One search round: load once, alternate each candidate with the default path, paired scoring, token-identity gate, evolve/holdout split |
| `mechanism.py` | Per-step graph-building and step time, default vs one candidate |
| `rounds/r1`, `rounds/r2` | Candidates (`cands/*.py`) and the JSONL/JSON records each round wrote |

```bash
python rsi_mlx.py <mlx-model-dir> rounds/r2 --split evolve  --max-tokens 256 --reps 3
python rsi_mlx.py <mlx-model-dir> rounds/r2 --split holdout --max-tokens 256 --reps 3
python mechanism.py <mlx-model-dir> rounds/r2/cands/r2d_fused_half_gates.py
```

Round 1 records predate adjacent pairing; its paired ratios in the doc were
recomputed from the logged run order (default run `1 + 3k + i` precedes
repetition `i` of candidate `k`). Workload prompts are kept verbatim,
including the Chinese ones. Run one runtime at a time; another GPU job on the
machine invalidates the round.
