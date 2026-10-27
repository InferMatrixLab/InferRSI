# strict-config-request-and-state

## User Persona
An operator needing source-qualified diagnosis without native execution authority.

## Scenario Coverage
Advanced integration route. Source-backed combined scenario, not a model test run.

## Expected Successful Behavior
- The answer distinguishes selected JSON config screening from exact tensor/roleQ8/native compatibility.
- The answer preserves the extra lookahead slot beyond rendered prompt plus max_tokens.
- The answer applies exact strict-token-prefix eligibility before key preference and does not force reuse after history edits.
- The answer retains missing compiler/Metal/model gaps without native execution.

## Failure Signals
Forcing unsupported layout/API/state, missing lookahead or a static/ignored result upgraded to native/E2E proof.
