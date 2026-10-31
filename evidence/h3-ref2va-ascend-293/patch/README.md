# Candidate changes

All downstream engine changes are consolidated in
[vLLM-Omni PR #9698](https://github.com/vllm-project/vllm-omni/pull/9698).
The PR is a draft; no candidate performance result is accepted yet.

## Terminal DLO cleanup

Executable candidate `3c4d5f8f1` skips rank-local and resident weight reconstruction
when the worker disposes of its pipeline. Ordinary disable and startup rollback
still restore reusable weights. Synchronization failure retains backing storage
for cleanup retry, and a terminally discarded backend rejects reuse.

Source: the current `OffloadBackend.shutdown` contract, DLO's existing terminal
AllGather optimization, and this campaign's NPU stacks showing rank-local
`restore_tensor_storage` after response completion. The stack was sampled after
timing; it is not a profiler-derived inference speedup.

Validation: 116 DLO CPU tests and all applicable pre-commit hooks passed. The
separate NPU smoke uses a detached worktree at the executable candidate revision.
Actual NPU lifecycle validation is pending. No inference-latency benefit is
claimed for this change.
