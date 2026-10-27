# GGUF role formats and target/draft compatibility

## User Persona
A maintainer transferring format-level acceptance and nominal dimensions into
an unsupported model/draft/streaming combination.

## Scenario Coverage
- Skill area: runtime-planning.
- Capability: loader screening, DFlash2 pairing and streaming-control semantics.
- Difficulty: advanced.
- Prompt file: `user_request.txt`.
- Expected references/scripts: runtime-planning, memory-and-formats,
  troubleshooting and offline budget parser.
- Trigger expectation: model representation must be established before serving.
- Synthetic extension: combines native configuration screening, GGUF screening
  and parser policy; no native fixture alone proves this complete scenario.

## Expected Successful Behavior
Reject the whole-unquantized target and arbitrary draft, distinguish per-role
tensor acceptance from entire-model support, preserve target/draft configuration
checks, reject incompatible streamed PLE and sparse-KV `off`, and explicitly
separate Linux syntax checks from Apple runtime availability.

## Failure Signals
Accepting the model by suffix/bit width, accepting the draft by hidden size alone,
assuming a rotated/rebuilt PLE table can stream, interpreting sparse-KV `off` as
valid, or presenting parser/header acceptance as native model qualification.
