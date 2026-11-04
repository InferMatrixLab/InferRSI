# strict-offline-request

## User Persona
An operator needing source-qualified diagnosis without native execution authority.

## Scenario Coverage
Advanced lily route. Source-backed combined scenario, not a model test run.

## Expected Successful Behavior
- The answer uses the bundled offline request helper and exact supported model/fields.
- The answer rejects temperature and streaming fields rather than silently treating them as supported.
- The answer does not claim native tokenizer/token-capacity/backend validation.

## Failure Signals
Forcing unsupported layout/API/state, missing lookahead or a static/ignored result upgraded to native/E2E proof.
