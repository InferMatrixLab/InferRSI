# Expert-cache budget is not total memory

## User Persona
An operator familiar with the command line but not the engine's ownership and
planned-session bookkeeping.

## Scenario Coverage
- Skill area: runtime-memory.
- Capability: SSD model fit, shared prefill and per-session capacity.
- Difficulty: troubleshooting.
- Prompt file: `user_request.txt`.
- Expected skill resources: the runtime-memory skill and its memory-ledger and
  troubleshooting references.
- Trigger expectation: direct mention of SSD cache, multiple slots and a
  failed allocation should select runtime-memory.
- Synthetic extension: combines the documented cache controls with the
  model-free `test_session_memory` assertions; it is not a report of a real Mac
  execution and extends those assertions into an operational diagnosis.

## Expected Successful Behavior
Distinguish requested and effective expert cache, count non-routed weights,
shared prefill storage, private KV/recurrent state and planned slots, preserve
the guard, and propose one controlled context/slot/cache comparison without
executing it. Keep observed values separate from missing physical-memory data.

## Failure Signals
Calling 32GB a process cap, asserting all slots share KV, disabling the guard,
inventing a safe slot count, launching tests/downloads, reopening original source
docs instead of using the bundled references, or clearing accelerator evidence
with CPU bookkeeping.
