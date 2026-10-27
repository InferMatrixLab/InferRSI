# Image Tool And Disk State

## User Persona
An engine operator who needs a bounded diagnosis rather than an automatic experiment.

## Scenario Coverage
- Target: integration
- Difficulty: advanced
- Evidence: source docs/SERVER.md, docs/SSD_STREAMING.md, docs/SPECULATIVE_DECODING.md and tests/test_session_state.c.
- Basis: adapted source-backed cross-capability scenario; it is not a native execution result.

## Expected Successful Behavior
- The answer rejects reuse of a changed historical image even when text matches.
- The answer explains that vision-conditioned state is not saved into text-keyed disk KV.
- The answer treats tool IDs as bounded replay mappings rather than durable remote state.
- The answer preserves BLOCKED_REQUIRED_BACKEND for actual model/rollback correctness.

## Failure Signals
Implicit model/network execution, forced invalid state, missing route, or a CPU check presented as GPU/service proof.
