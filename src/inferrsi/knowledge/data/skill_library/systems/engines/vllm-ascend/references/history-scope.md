# History scope and verification

The source boundary is the complete ancestor graph of v0.27.1rc1, resolved to `3b31886237ed65c435e0965b10e8002ff5769766`. The local repository was checked as non-shallow. The inventory enumerates **5029 reachable commits** and retains **1381 candidates** using full commit messages, changed paths and a separate fusion-pattern diff search across runtime and C++ sources.

| Topic | Candidate count |
| --- | --- |
| deepseek-v4-dspark | 275 |
| communication | 148 |
| priority-models | 251 |
| fusion | 973 |

Counts overlap. DeepSeek/DSpark matching also includes IndexCache, IndexShare and HcPre shared dependencies. “Fusion” is deliberately broad because changes to fused-MoE files can be fixes, refactors or deletions. GLM model matching focuses on the GLM5 family. Older model changes may still appear as general fusion history. A match is a discovery lead and carries no optimization or performance verdict.

The [archived machine-readable inventory](https://github.com/InferMatrixLab/InferRSI/blob/9fd6fd1ed68f063cc47ec230eae040b153a83a23/docs/reviews/vllm-ascend-0271rc1/history-inventory.json) retains full SHAs, subjects, changed paths, matched topics and runtime-diff matches. The complete inventory is retained under repository review artifacts. Runtime readers load the compact reviewed records and the reproducible screening script. Review-specific records are in [history-reviewed.json](history-reviewed.json). The latter distinguishes selected-path reading from whole-commit reading where recorded. It links the focused mechanisms in the four performance procedures. Their immutable source links identify the actual supporting consumers and tests.

## Reproduce the candidate inventory

Run against a local repository with complete reachable history.

```bash
python scripts/screen_history.py --repo <local-vllm-ascend-repo> --revision v0.27.1rc1
```

The script reads Git objects and prints JSON. It rejects shallow history and performs no fetch. Compare the resolved SHA before comparing output. Candidate discovery covers the entire reachable graph; focused semantic inspection covers the commits and paths named in the procedures and review records. Keyword selection can miss a differently named mechanism, so source consumers and reversals are also followed explicitly.

## Construction and validation boundary

- Source checks resolve every cited commit and blob against the local repository, require commit ancestry under the tag, and validate line bounds. The dedicated source-anchor check additionally compares the two configuration field links with their exact pinned definitions.
- Host tests exercise discovery, resource reading and inventory classification. Three isolated MiniMax configuration checks execute tagged functions with substituted hardware/profile dependencies.
- Local forward-testing uses the packaged guidance on a MiniMax-M3/950DT fused-MC2 launch and a Kimi K3 A3 copy-removal proposal. It checks that guidance recovers effective dispatch and the retained revert. This is a bounded authoring check.
- No NPU runs, measured optimization gain or held-out agent-efficacy comparison were performed for this extraction. Historical benchmark numbers remain attributed upstream reports. Native test commands in procedures are future verification candidates.

For a real performance comparison, preserve model/checkpoint and quantization identity, software/device build, parallel topology, phase, tokens, concurrency, prefix-hit and KV-pool state. Capture correctness, operator time and end-to-end service time separately. The complete candidate inventory remains available for deeper investigation beyond the focused mechanisms.

See the [pinned source readset](sources.md) for source identity and verification limits.

From an InferRSI source checkout, run `python tools/check_vllm_ascend_source_anchors.py --repo /path/to/vllm-ascend` to check the configuration anchors against local Git objects. This targeted check requires Git with `--no-lazy-fetch` support and does not validate every historical citation.
