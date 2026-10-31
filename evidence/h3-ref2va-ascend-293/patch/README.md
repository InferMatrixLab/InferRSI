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

## Bounded NPU native-runtime finalization

Candidate `ff6ac7b3fc242c9a2b1b3bed3e4cb6fa5ebdd9ba` supplies a 60-second graceful
worker-exit deadline on NPU; other platforms retain 15 seconds. The deadline is
shared across all workers, joins return as soon as workers exit, and the existing
bounded terminate/kill fallback remains. This does not alter request timing.

Source: the retained CANN native-shutdown stack and the
[MC2 diagnostic receipt](../results/cache2-screening.json), which observed no
forced signals with a 60-second override and 27.24 seconds total teardown.
That receipt does not include individual worker exit codes, so production-path
qualification is still required. The [queued code A/B plan](../plan/audio-qualification.json)
adds per-worker exit receipts and uses the production NPU path for the candidate.

All 86 executor concurrency tests passed. Editing the files exposed eight mypy
errors also reproduced on the frozen baseline. Narrow type annotations/casts
and distinct future-loop variables correct these without changing result
handling. Applicable commit hooks pass. No inference speedup is claimed for
cleanup, and no final lifecycle PASS is inferred from the diagnostic run.

### Audio ownership across DP replicas

Self-review found that the reused H3 broadcast helpers use the global DiT group.
Different DP replicas can own different requests, so broadcasting rank zero's
waveform across DP would be incorrect. Follow-up
`833bf9b07395734237f16bddf50109d32bb93312` retains the original independent audio
decode when DP is not exactly one. It does not alter the frozen DP1 pilot path.

The regression produced two DP2 failures and two DP1 passes before the guard.
Afterward all 31 related tests passed, including a real two-process Gloo check
that gives the two DP replicas distinct waveforms, plus owner failure and DP1
broadcast cases. Commit hooks pass. This validates the audio ownership boundary,
not full DP2 model serving or an inference speedup. The queued DP1 pilot remains
pinned to `ff6ac7b3f`; final qualification must use the final accepted revision.

## Optional device-resident reference KV

Candidate `4fc121ff3d6e7ccb1d3e35582fddf509e010dfa9` adds opt-in
`kv_cache_residency=device` to the existing reference-KV configuration. Default
host staging is unchanged. Device residency stores each layer's reference K/V
in a contiguous device pool and avoids host capture and H2D staging; refresh
interval semantics and returned-payload ownership remain the same. Host KV
quantization cannot be combined with this option. Pool bytes and transfer
counters are logged explicitly.

Source: [reference-KV PR #8072](https://github.com/vllm-project/vllm-omni/pull/8072)
and this campaign's retained KV2 counters. The failed host-KV2 attempt transferred
167.09 GB per rank over 25 reuse steps; this motivates an isolated transfer
hypothesis, not a measured causal attribution or predicted speedup.

[Thirteen CPU tests pass](../results/reference-kv-residency-cpu.json), including
exact host/device payload parity, refresh, ownership, block-cache skips and
cleanup. All applicable pre-commit checks pass. The
[frozen NPU pilot](../plan/kv-residency-pilot.json) compares host/device at interval
2, then device interval 8, within one reservation after earlier CPU scoring ends.
NPU speed, actual HBM and output quality remain unverified; no benefit is accepted.
