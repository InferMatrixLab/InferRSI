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
| `count_ops2.py` | Ops in one decode step's graph (total and non-view), default or one candidate |
| `route/` | Raw outputs of the MLX / llama.cpp route comparison (`mlx_lm.benchmark` log, `llama-bench` JSON, per-run chat timings) |
| `rounds/r1` … `rounds/r4` | Candidates (`cands/*.py`) and the JSONL/JSON records each round wrote |

```bash
python rsi_mlx.py <mlx-model-dir> rounds/r2 --split evolve  --max-tokens 256 --reps 3
python rsi_mlx.py <mlx-model-dir> rounds/r2 --split holdout --max-tokens 256 --reps 3
python mechanism.py <mlx-model-dir> rounds/r4/cands/r4a_conv_kernel.py
python count_ops2.py <mlx-model-dir> rounds/r4/cands/r4a_conv_kernel.py
```

`rsi_mlx.py` prints "speed screen passed, pending mechanism check" for a
complete, token-identical candidate at least 5% faster, and INCONCLUSIVE for
one with an error, fewer pairs than `--reps` or a failed revert. The verdict
strings in the committed `score-*.json` files ("keep", "留") come from earlier
scorer versions and are superseded. Round 1 records predate adjacent pairing; its paired ratios in the doc were
recomputed from the logged run order (default run `1 + 3k + i` precedes
repetition `i` of candidate `k`). Workload prompts are kept verbatim,
including the Chinese ones. Run one runtime at a time; another GPU job on the
machine invalidates the round. These records are exploratory and
unverified (no acceptance issue). The round-4 candidate is packaged as
[zuiho-kai/inkling2-mlx-fastpath](https://github.com/zuiho-kai/inkling2-mlx-fastpath).
