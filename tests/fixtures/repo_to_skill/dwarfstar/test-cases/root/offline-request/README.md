# Offline Request Preparation

## User Persona
An engine operator who needs a bounded diagnosis rather than an automatic experiment.

## Scenario Coverage
- Target: dwarfstar
- Difficulty: advanced
- Evidence: source docs/SERVER.md, docs/SSD_STREAMING.md, docs/SPECULATIVE_DECODING.md and tests/test_session_state.c.
- Basis: adapted source-backed cross-capability scenario; it is not a native execution result.

## Expected Successful Behavior
- The answer uses the bundled offline request helper and does not send a request.
- The answer distinguishes API alias from startup GGUF selection.
- The answer keeps network/model execution under separate authorization.

## Failure Signals
Implicit model/network execution, forced invalid state, missing route, or a CPU check presented as GPU/service proof.
