# Publication-head HTTP readiness protocol

Governing acceptance: https://github.com/InferMatrixLab/InferRSI/issues/67
Protocol declared before allocation in issue comment 6345756537.
This file records that declaration; it does not activate an acceptance freeze.

Purpose: validate the independently published prefill repair through the actual
HTTP service, including startup prewarm, pooled Graph reuse and state cleanup.
One GPU, at most 15 minutes, charged to the owner-approved 2 GPU-hour readiness
stage within the 44 GPU-hour phased ceiling. No performance candidate search.

Source arms run sequentially on the same allocated GPU:

1. Original main, Graph enabled.
2. Publication repair, Graph enabled.
3. Publication repair, eager.

Source revisions and actual source hashes are in results/diagnostics/http-summary.json
and http-readiness.jsonl. Hardware is NVIDIA H20-3e, driver 580.105.08; private
device identity is retained in controlled operational logs. Runtime remains
Python 3.12.13, torch 2.14.1+cu130, Triton 3.8.0, Transformers 5.20.2, official
FP8 checkpoint and Triton block-FP8 implementation. FlashInfer is not installed.
Model bytes reuse the earlier authenticated intake; no fresh full-shard scan.

Inputs: historical GSM8K cases 783, 1 and 424, token lengths 149, 70 and 106.
Each arm performs two repetitions in that case order. Greedy, natural EOS,
16-token maximum, concurrency 1, context bound 2048. Input hashes are retained.
Graph startup captures all existing buckets; these requests use bucket 1024.
No additional warmup request or capacity-transition probe is included.

The exact retained client measures token-ID SSE events, with first-token delay,
mean interval between the first and last returned token, and complete HTTP
request latency. It retains every token, timestamp, terminal marker and cleanup
record. These semantics are **not the official vLLM benchmark client**. Main's
unsupported benchmark fields remain a separate prerequisite.

Startup is bounded at 180 seconds per service; requests at 120 seconds; server
shutdown at 20 seconds followed by owned-PID kill if necessary. The job has an
850-second command timeout and 900-second Slurm limit. Slurm device visibility
is preserved. No server is externally exposed. All mutable paths and caches
remain within the task's authorized root.

Startup and first-use effects are reported separately from request samples.
The fixed arm order, different generated sequences on the failing base case,
short caps and lack of an acceptance freeze preclude causal speedup, quality,
long-context or vLLM-parity claims. Verdict remains INCONCLUSIVE.
