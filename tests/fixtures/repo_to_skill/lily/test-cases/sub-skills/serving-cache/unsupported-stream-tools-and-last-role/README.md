# Broad SDK request against a strict subset

## User Persona
An SDK integrator who assumes generic OpenAI fields are accepted when harmless.

## Scenario Coverage
- Skill area: `serving-cache`.
- Capability: unknown-field rejection, fixed greedy mode, no streaming/tools, user-last conversation and extra token capacity.
- Difficulty: troubleshooting.
- Prompt file: `user_request.txt`.
- Expected resources: serving-cache router, API/session reference, offline `scripts/request_template.py`.
- Fixtures: `invalid-request.json` reproduces the unsupported shape; `valid-request.json` supplies an explicitly text-only alternative.
- Synthetic basis: combines the source serde rejection examples, native validation and token-budget unit case; no native execution result is claimed.

## Expected Successful Behavior
Explain that `temperature` and `tools` are unknown even when zero/empty, `stream:true` is unsupported, and the last role must be user. State that Lily is inherently greedy and does not take sampling controls. Do not pretend removing tools/streaming preserves a workflow that requires them or invent a user message to mask a missing query. Construct or structurally screen the explicitly chosen text-only user request with the offline helper. Explain checked `10 + 20 + 1 = 31` and that helper structural checks cannot determine actual rendered token counts or prove native usability.

## Failure Signals
Unknown fields are silently accepted or stripped without explaining semantics; temperature zero is treated as supported; tool/stream support is invented; the extra token is omitted; helper output is described as a running engine result.
