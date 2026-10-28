# Fixed-history Graph numerical diagnosis

Prospective scope: [Issue #67 comment](https://github.com/InferMatrixLab/InferRSI/issues/67#issuecomment-6347094636).
Harness-only observer, production unchanged. One H20, at most15 minutes from
the approved readiness stage. Historical case gsm8k/test/783,149 input tokens,
96 predicted positions (prefill plus95 decode), capacity1024. Force the prior
job1955 eager token history for all three arms: compact eager, capacity eager,
and the real prewarmed pooled Graph state. Compare full logits and all live
KV, conv and recurrent tensors. Reproduce the compact history and Graph prefix
through the previous first divergence at zero-based index81. No hooks, kernel
changes, quality scoring, performance search or acceptance gate changes.

The exact retained observer records fixture/history/source digests; its output
is a diagnostic INCONCLUSIVE regardless of exact comparisons. The source is
engine head80e5108e44c43f3f54fabb5723e6154d18088516, tree-equivalent to merged
3e918df2dd7b478d3d2985350bb5efb523ea4981. Checkpoint/config and fixture identities
reuse the authenticated intake; this does not claim a new full-shard rehash.
