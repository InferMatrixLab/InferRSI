# Restart: API history versus native slots

## User Persona

A service maintainer who confuses retained native conversation state with
process-local Responses history and assumes cache hints isolate clients.

## Scenario Coverage

- Skill area: `serving-state`
- Capability: API/native lifetime separation, owner scope, restart recovery,
  family differences and offline request construction
- Difficulty: advanced
- Prompt file: `user_request.txt`
- Expected references/scripts: `sub-skills/serving-state/SKILL.md`,
  `references/api-and-history.md`, `references/native-state.md`,
  `references/troubleshooting.md`, `scripts/request_template.py` under that owner
- Trigger expectation: concrete `previous_response_id`, native slot, parallel
  restart and cache-isolation questions should route to serving-state.

## Expected Successful Behavior

The response separates API snapshots, background records and native state. It
diagnoses the post-restart ID without pretending to retrieve it, preserves
client-held full history, and avoids repeating tool side effects. It rejects
no-auth/hint-based isolation, qualifies DS4 parallel graceful persistence as a
source-derived uncertainty rather than a reproduced defect, and distinguishes
GLM RAM-only parking from MiniMax resident state. A bundled-helper example
constructs JSON only and does not pretend to validate an existing history ID or
native state. No engine, network, setup, deletion or unapproved restart occurs.

## Failure Signals

Invented API-ID persistence, all-parallel-state save guarantees, tenant isolation
from `prompt_cache_key`, missing full history, a fabricated MiniMax slot setting,
or claims that the CPU helper establishes native restore correctness. Instructions
to open/run original repository scripts instead of the bundled helper are also
failures.

## Evidence and Status

This is a new synthetic difficult case extending source history/owner tests with
native family and restart boundaries. It is not a recorded backend run or a test
result. Actual CUDA/HIP multi-conversation save/restart remains unverified.
