# Same key without a strict prefix

## User Persona
A maintainer debugging multi-turn cache misses in Lily's minimal server.

## Scenario Coverage
- Skill area: `serving-cache`.
- Capability: strict token-prefix eligibility, preferred-key ranking, two-entry LRU and actual state history.
- Difficulty: advanced.
- Prompt file: `user_request.txt`.
- Expected resources: serving-cache router and its API/session/troubleshooting references.
- Trigger expectation: concrete token arrays distinguish source predicates without inventing native tokenizer output.
- Synthetic basis: extends the source strict-prefix unit examples with key-preference and state-fed-accounting requirements; not a native implementation test.

## Expected Successful Behavior
Reject reuse for changed-token and equal-length histories even with the same key. Allow consideration of a different-key genuine strict prefix; keys prefer candidates but do not partition or authorize them. Describe filtering before `(key_match, prefix length)` ranking and the fixed two-entry LRU cold path. Preserve `DecodeState.pos == retained tokens.len()` and actual-fed-token accounting rather than caching all returned tokens. No native inference or unsupported verification claim.

## Failure Signals
Same key bypasses equality; an equal full prompt returns an empty suffix; different keys are described as isolated tenants; visible output is assumed identical to the fed state; a Python explanation is described as passing Rust/Metal tests.
