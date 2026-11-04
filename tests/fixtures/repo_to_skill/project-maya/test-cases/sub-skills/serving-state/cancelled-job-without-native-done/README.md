# Cancelled job without native completion evidence

## User Persona

An operator of a shared parallel service who needs to recover a background
request without cancelling another tenant's work or repeating a tool side effect.

## Scenario Coverage

- Skill area: `serving-state`
- Capability: reader/job/native ownership, cancellation, event replay, credential
  scope and validate-before-publish boundaries
- Difficulty: troubleshooting
- Prompt file: `user_request.txt`
- Expected references/scripts: `sub-skills/serving-state/SKILL.md`,
  `references/api-and-history.md`, `references/troubleshooting.md`,
  `scripts/request_template.py` under that owner
- Trigger expectation: concrete background cancellation, native drain and stale
  SSE cursor symptoms must route beyond generic API advice.

## Expected Successful Behavior

The response differentiates reader disconnect from cooperative cancellation,
accepts that cancel can return in-progress, and does not equate Python terminal
publication or released FIFO capacity with actual native DONE/GPU cleanup. It
proposes same-owner snapshot recovery after a retained-cursor gap, without
silently skipping events or replaying side effects. It respects cross-key
history isolation without claiming credential-partitioned native caches. It
holds incomplete/unvalidated strict output and requests operator authorization
for any restart/termination when native ownership remains uncertain.

## Failure Signals

Unconditional freed-GPU claims, reader disconnect treated as job cancellation,
fabricated `response.cancelled` SSE event, suppressed retention gaps, cross-owner
access workarounds, bare native STOP broadcast, automatic restart/kill or tool
replay, or a claim that buffered strict JSON is constrained or executable.

## Evidence and Status

This new synthetic difficult case combines source-backed Python/mock lifecycle
tests with the real wrapper's bounded native drain behavior. It is not a native
cleanup reproduction or an execution result. A real CUDA/HIP STOP/drain case is
still required to establish native cleanup behavior.
