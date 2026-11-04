# Issue #255 — avoid redundant size serialization after the item limit

[Result table and limits](results/report.md) · [Frozen protocol](plan/protocol.md) · [Independent audit](results/independent-review.json)

This distinct five-line runtime optimization passes its bounded CPU-retrieval campaign. It is not acceptance of the earlier resource-cache candidate, a retrieval-accuracy gain, or closure of #255. Historical FAIL/INCONCLUSIVE evidence remains unchanged.

## Replay and inspection

The candidate snapshot and tests are retained under [patch/](patch/README.md). The [frozen runner](validator/evaluate.py) and its adjacent [freeze receipt](validator/candidate-runner-freeze.json) describe exact baseline/candidate pins. `plan/protocol.md` preserves the original `proposed-protocol.md` bytes; that original filename appears in the freeze receipt.

Inspect the archived evidence without executing retrieval:

```bash
python evidence/indexer-255-limit-sizing-20261030/validator/verify_raw.py
```

The deterministic gzip/tar archive retains every original raw file, including240 completed-arm receipts,120 paired groups, original output captures, source identities, run order, environment and summary. [Raw-file manifest](results/raw-files.json) records decompressed exact byte counts and hashes. The verifier does not extract or execute archive members. The independent audit is a post-run supplement, not the prospective validator; its original local helper was not portable and is not represented as a reusable production tool.

To reproduce the experiment only with appropriate CPU-execution authorization, reconstruct the two pinned worktrees, use the same recorded Python/dependencies, and invoke:

```bash
python evidence/indexer-255-limit-sizing-20261030/validator/evaluate.py \
  --baseline "$BASELINE_ROOT" --candidate "$CANDIDATE_ROOT" --output "$NEW_OUTPUT_DIR"
```

`NEW_OUTPUT_DIR` must not exist. Keep the frozen receipt adjacent to the runner. Worktrees must be at the exact recorded commits; the runner asserts pins, source/corpus equality, output equality and unchanged source. The original run is complete; this command is reproducibility documentation, not permission to repeat until PASS. No source/control defaults carry campaign thresholds.

The runner's generic exception wrapper records `INCONCLUSIVE`; an output-parity assertion failure must instead be interpreted as a correctness **FAIL/blocker**, not measurement noise. No exception or mismatch occurred in the retained run.
