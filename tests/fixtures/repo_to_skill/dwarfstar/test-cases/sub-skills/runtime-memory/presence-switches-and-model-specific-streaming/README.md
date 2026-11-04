# Presence switches and model-specific streaming

## User Persona
An experienced CUDA operator transferring familiar boolean environment settings
and generic GGUF assumptions into a specialized runtime.

## Scenario Coverage
- Skill area: runtime-memory.
- Capability: expert-cache units, read-policy controls and compatibility triage.
- Difficulty: advanced.
- Prompt file: `user_request.txt`.
- Expected skill resources: runtime-memory, memory-ledger and troubleshooting.
- Trigger expectation: CUDA SSD read-policy comparison belongs to this route.
- Synthetic extension: combines parser and CUDA call-site facts into a
  contradictory configuration that a simple native parser test does not cover.
  This case tests advice only, not CUDA execution.

## Expected Successful Behavior
Explain presence semantics and disable precedence, unset all relevant policy
overrides to restore defaults, distinguish bare slots from integer-GB budgets,
separate selected-read prefill ordering from next-layer prefetch and ordinary
decode, and reject an unsupported GGUF/model/backend tuple. Propose a frozen
comparison record, not an unrequested run.

## Failure Signals
Treating `=0` as absent, suggesting only the enable switch needs unsetting while
leaving the disable override present, accepting arbitrary GGUF formats, equating
slots with GiB, promising speedups, or calling source inspection GPU validation.
