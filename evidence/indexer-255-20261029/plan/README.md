# Indexer #255: bounded CPU comparison and accuracy assessment

Owner: Dong1017. Scope and closure acceptance: [Issue #255](https://github.com/InferMatrixLab/InferRSI/issues/255). This is a harness-plane CPU retrieval campaign, not model or hardware efficacy evidence.

`protocol.json` is the frozen comparison contract. The exact baseline already includes the historical knowledge trim; this campaign does not repeat or claim that work. Candidate cap: one request-local resource-validation optimization. No paid services, new models, GPUs, synthetic corpus or ranking rewrite. Stop at one complete comparison; preserve any gate failures rather than revise gates to fit outcomes.

The source-only profile identified repeated Bundle resource validation and SHA-256 as the dominant controllable cost. A profiled reused-reader cgroup query took 1.767 seconds, with manifest 1.327 seconds, including approximately 47,278 SHA/path operations. Profile timings are diagnostic only, not the campaign result.

## Reproduce

First recover the preserved candidate commit using `../patch/README.md`. The final feature branch contains evidence only, not the optimized runtime. Use two clean worktrees at the baseline and candidate commits, the same Python executable, and dependencies recorded in `python-environment.txt`. Run sequentially without competing benchmark jobs:

```sh
python tools/evaluate_indexer.py \
  --baseline /path/to/baseline --candidate /path/to/candidate \
  --protocol evidence/indexer-255-20261029/plan/protocol.json \
  --cases tests/fixtures/indexer/development.json tests/fixtures/indexer/heldout.json \
  --output /path/to/new-results
```

A fresh reader is not a cold filesystem cache. Full CLI latency includes interpreter startup/output capture; JSON decoding is separately recorded. All 20 paired AB/BA groups and slow samples are retained. Bootstrap resamples the group statistic, not individual queries. Tail estimates from 20 samples are descriptive and noisy, not production SLOs.
