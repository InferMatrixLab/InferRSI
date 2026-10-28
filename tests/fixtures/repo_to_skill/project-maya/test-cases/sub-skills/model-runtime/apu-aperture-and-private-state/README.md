# APU capacity, aliases and private concurrent state

## User Persona

Operator who understands model serving but has conflated logical device memory,
physical capacity, expert slots and per-conversation storage.

## Scenario Coverage

- Skill area: `model-runtime`.
- Capability: unified physical accounting, alias versus copy ownership,
  model-specific cache semantics and concurrency-dependent memory plans.
- Difficulty: advanced.
- Prompt file: `user_request.txt`.
- Fixture: `fixtures/unified-overcommit.json`, synthetic byte estimates only.
- Expected files: model-runtime model-and-memory and troubleshooting references,
  plus `audit_runtime_plan.py`.
- Trigger: shared physical memory, apparent aperture capacity, expert-cache
  count units and an MM3 single-session-to-parallel transfer.

## Expected Successful Behavior

Reject adding an aperture to physical memory. Treat the alias as zero extra
allocation but count four real sequence-state copies. The supplied simultaneous
allocations use 58 GiB; adding 16 GiB reserve exceeds 70 GiB by 4 GiB. The helper
should report a screening conflict with a negative estimated remainder, not a
native allocation failure or a fit certificate. Missing snapshots, scratch,
staging and measurement-boundary mistakes remain a separate completeness audit.

Explain GLM's largest-slot cap on the first part versus per-layer resident/
spare/lendable-tail slots. Do not transplant that knob into another engine.
Explain that MM3 parallel operation disables KV streaming and DSpark and has
private per-conversation device caches; the old estimate therefore does not
describe an equivalent four-session plan.

This difficult case is synthetic. It extends the upstream GLM pure-policy and
retention cases by combining alias/copy accounting, an audited measurement
boundary and a different family's parallel-mode change. It does not replace
the original native tests or actual backend verification.

## Failure Signals

Add host RAM and aperture, count a bound pointer twice, ignore real copies,
claim expert-cache is bytes/per-layer permanent residency, retain MM3 streamed
single-request settings under parallel mode, or equate arithmetic with verified
native fit/performance. Source-checkout-dependent runtime instructions fail.
