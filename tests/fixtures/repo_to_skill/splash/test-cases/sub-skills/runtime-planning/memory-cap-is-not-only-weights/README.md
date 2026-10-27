# Memory cap is not weights or process RSS

## User Persona
A local operator who knows exposed flags but not native/host accounting or
recurrent-state rounding boundaries.

## Scenario Coverage
- Skill area: runtime-planning.
- Capability: memory ceiling, streamed PLE ownership, context/concurrency and precision.
- Difficulty: troubleshooting.
- Prompt file: `user_request.txt`.
- Expected references/scripts: runtime-planning, memory-and-formats,
  troubleshooting and `scripts/parse_budget.py`.
- Trigger expectation: memory planning is the correct owner before runtime tuning.
- Synthetic extension: combines parser and PLE budgeting/audit source anchors
  with a precision misconception; it is not an observed native run.

## Expected Successful Behavior
Explain that the configured cap can only lower the automatic safe ceiling and
does not cap combined RSS; account for PLE host rows, other host overhead,
weights, draft/vision, arenas, reserves, state staging, ANE and dynamic KV/state.
Clarify that PLE `off` loads the whole table and BF16 storage rounds at meaningful
boundaries. Demonstrate offline syntax normalization only and propose an
authorized future comparison without executing it.

## Failure Signals
Raising OS/Metal limits, calling PLE `off` a disabled table, equating FP32 compute
with exact FP32 state, promising fit from a parsed byte value, starting the
server/downloading files, or classifying source/parser checks as Metal validation.
