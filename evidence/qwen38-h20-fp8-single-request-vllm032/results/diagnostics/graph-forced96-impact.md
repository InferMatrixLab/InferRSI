# Residual Graph divergence: fixed-history observations

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**Campaign INCONCLUSIVE. No engine change or new E2E gain.**

Job1957 completed with exit0 in65 allocated GPU seconds. All96 predicted
positions have exactly equal full logits and valid KV/conv/recurrent state
between capacity1024 eager and Graph. Compact logits first differ from those
arms at index23; only index81 changes greedy argmax within this fixed history.
The96 compact choices reproduce the original eager history, and Graph matches
the original Graph prefix through index81. The complete records and observer
are retained beside this report and under validator/diagnostics.

At index81 compact logits for tokens220 and264 are both25.625; argmax chooses220.
Capacity eager and Graph both give token26425.75 and token22025.625, choosing264.
This isolates the observed divergence to the compact-versus-capacity numerical
path in this trace. It provides no evidence of an additional Graph replay or
live-state corruption at these96 positions. It does not identify the exact
internal operator, prove all contexts/buckets correct, establish task accuracy,
or require future candidates to reproduce every greedy token bitwise.

The prior HTTP comparison remains3/5 full matching pairs; job1951 failure and
1955 repair outcomes are unchanged. Issue67 task-quality gates, including the
separate long-context retrieval gate, remain necessary. Historical Issue57
numerical failures are not rescored. No service timing is inferred from this
instrumented in-process diagnostic.

Readiness allocation total904/7200 GPU seconds (0.251111 GPU-hours), with6296
seconds remaining. The initial147-second diagnosis is separate. All relevant
allocations are released. Runtime/environment dependencies remain unchanged.

Independent reviewer Codex review_fp8_graph checked the exact observer,
all12 runtime source digests, tree equivalence to merged main, history inputs,
96 comparisons and index81. No blocking finding for retaining this diagnostic.
The reviewer confirmed the bounded numerical-path conclusion and explicitly
excluded general correctness, task-quality or performance acceptance.

KnowledgeStore candidate `case.qwen38-fixed-capacity-numerics-cand`, revision
`sha256:22d93a266b3eaec5a839f10a774dd88c81388be6df6d5a15f560750a88ee1331`,
was created and read back byte-for-byte; no protected library promotion.
