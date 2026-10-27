# Memory And Qualification

## User Persona
An engine operator who needs a bounded diagnosis rather than an automatic experiment.

## Scenario Coverage
- Target: integration
- Difficulty: advanced
- Evidence: source docs/SERVER.md, docs/SSD_STREAMING.md, docs/SPECULATIVE_DECODING.md and tests/test_session_state.c.
- Basis: adapted source-backed cross-capability scenario; it is not a native execution result.

## Expected Successful Behavior
- The answer distinguishes expert cache, mandatory non-routed weights, shared scratch and per-slot KV/recurrent state.
- The answer rejects a monotonic more-cache solution without phase evidence.
- The answer checks model-specific DSpark/SSD compatibility and sampling controls.
- The answer does not turn CPU bookkeeping into accelerated/service performance evidence.

## Failure Signals
Implicit model/network execution, forced invalid state, missing route, or a CPU check presented as GPU/service proof.
