# Historical source-scan inventory

The complete generated inventory is retained at its [exact source revision](https://github.com/InferMatrixLab/InferRSI/blob/a590ccb25596396a592f237105166ade4aedeaaa/docs/reviews/vllm-ascend-0271rc1/history-inventory.json).
It is omitted from the current tree under the [archiving contract](../../evidence-archiving.md).
Runtime knowledge readers use the compact reviewed records and screening script;
they do not consume this full scan.

- Original bytes: 1,401,157
- SHA-256: `5df28360760a6d5cb513b7a4627eeb5a365d2d557b0fc2ff3d5c84cff925b72c`
- Upstream repository: https://github.com/vllm-project/vllm-ascend
- Upstream revision: `3b31886237ed65c435e0965b10e8002ff5769766`
- Reachable commits: 5,029
- Keyword/path/diff candidates: 1,381
- Topic counts (overlapping): {"communication": 148, "deepseek-v4-dspark": 275, "fusion": 973, "priority-models": 251}

Before removal, the pinned copy was compared byte-for-byte; unique candidate
count, topic totals and inclusion of the separately reviewed commits were
checked. These are historical screening observations, not whole-commit semantic
review or native validation. The immutable source remains available in history.
This cleanup removes a generated file from the current tree only, not Git history.

For local retrieval from a checkout containing that revision:

```bash
git show a590ccb25596396a592f237105166ade4aedeaaa:docs/reviews/vllm-ascend-0271rc1/history-inventory.json > <local-inventory.json>
```

Check its byte count and SHA-256 above before use. Re-run the published screening
script against the pinned upstream revision for an independent reconstruction;
behavioral regression tests use a small synthetic Git history, not this scan.
