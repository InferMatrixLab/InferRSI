# Asynchronous submission does not establish overlap

ID: `case.cuda-copy-overlap`. Owner: `optimization-search-policy`.
Axis: pipelining. Resources: host RAM, Accelerator copy/compute and host-device link.
Documentation-derived candidate; local validation not_run. No local campaign evidence.

## Source conditions

[NVIDIA CUDA C Best Practices Guide 11.8.0](https://docs.nvidia.com/cuda/archive/11.8.0/cuda-c-best-practices-guide/index.html),
§§9.1–9.1.2: minimize transfers first. Copy/compute overlap requires device
capability, pinned host memory and appropriately separate non-default streams.
Same-stream copy and dependent kernel remain ordered. Excessive pinned memory
can hurt the system. The staged-copy example is a mechanism illustration, not
an observed InferRSI service result or an Ascend portability claim.

## Proposed decision

Signal: a timeline shows exposed copies and independent work available to cover them.
Prerequisites: backend support, chunk independence and bounded host/device buffers.
Candidate: pipeline copies and eligible work with double buffering; keep serial
execution as the reference. Invariants: producer/consumer dependencies, completion
events before buffer reuse, ordering, cancellation and backpressure. Metrics:
critical-path elapsed time, exposed/hidden copy time, transfer bandwidth, launch
overhead, pinned/peak device memory and complete-output correctness.
Hypothetical counterexample: tiny chunks add more launches than overlap saves,
or compute and copies contend for memory bandwidth. If independence or completion
is unknown, request a dependency/lifetime trace before recommending more streams.
Rollback: join owned work before freeing buffers and restore serial submission.

Attribution and document version: [case record](cuda-copy-overlap.json).
