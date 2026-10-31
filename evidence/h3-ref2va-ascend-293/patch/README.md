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
The [NPU smoke](../results/shutdown-fixed-smoke.json) generated valid media and
no longer sampled rank-local reconstruction during teardown. Rank zero disabled
DLO immediately and completed its worker cleanup callback about three seconds
later, but processes still required termination: later stacks were in CANN
runtime shutdown while peers finished audio decode. Full lifecycle remains
INCONCLUSIVE. No inference-latency benefit is claimed for this change.

## Request-owned Cache-DiT summaries

Candidate `1e6d88ad44d3acede515896968ce54935883c919` includes the cleanup patch
and fixes the runner's summary condition. H3's existing `quality=high` policy
can install Cache-DiT per request without a startup cache backend. The previous
condition suppressed an explicitly requested summary in that case. The fix
recognizes active pipeline-owned Cache-DiT while still requiring the summary
flag. This improves observability; no inference latency benefit is claimed.

Source: the existing H3 request quality policy, the initial Cache-DiT pilot,
and an expanded existing runner regression test. Before the fix, the summary
matrix produced one failure and nine passes; afterward all ten passed. Final
summary/payload focused validation passed 70 tests. Applicable commit hooks pass.

The touched runner also exposed an existing mypy mismatch: the payload mixin
declared a writable target-device attribute while its sole production subclass
implemented a read-only property. The same error was reproduced on the frozen
baseline. Declaring the mixin contract as a read-only abstract property fixes
the check without changing the runner's device selection.

## Decode one waveform across inference ranks

Candidate `0a766ab59d8f7a31b71de24fb415335e58ae7854` changes full-tensor H3 decode
to run the non-collective audio VAE on rank zero and broadcast its waveform.
It uses the existing H3 rank-zero exception broadcast before transferring the
tensor, so a failed owner does not leave peers waiting for waveform data.
The chunked MP4 path is unchanged.

Source: this campaign's per-rank decode profiles and H3's existing reference
encoding/error/tensor broadcast pattern. This is a new campaign implementation,
not imported Cache-DiT work. The prior path ran the same audio VAE on every rank;
the first-request peer lag was visible after the reply owner had returned.

The regression failed on the peer rank before the change. The 28 offload tests
pass afterward, and a real two-process CPU Gloo test passes both exact waveform
delivery and owner-exception propagation. Applicable commit hooks pass. The
code reduces decoder invocations from eight to one in the target topology.
The [NPU smoke](../results/audio-owner-smoke.json) emitted one audio-decode
profile record and passed [two-step matched media parity](../results/audio-owner-smoke-quality.json).
Its first-request E2E was 201.78 s versus the preceding cleanup-only smoke's
154.52 s, so it does not establish a latency gain. Full lifecycle still did not
pass: six workers received terminate, although none needed kill. Warmed repeated
A/B remains necessary; the candidate must be removed from the final optimization
set if it has no qualified benefit.
