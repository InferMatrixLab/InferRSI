# Shape screen, sequence ceiling and pending ownership

## User Persona
A maintainer connecting static metadata screening to sequence allocation and
asynchronous shared-buffer reuse.

## Scenario Coverage
- Skill area: model-runtime.
- Capability: screen limits, checkpoint-clamped sequence and buffer frontiers.
- Difficulty: advanced.
- Prompt file: `user_request.txt`.
- Expected resources: model-runtime, model-and-memory, troubleshooting and
  the offline screen helper.
- Trigger expectation: capacity and tensor lifetime belong to model-runtime.
- Synthetic extension: combines checkpoint shape predicates, server extra-slot
  budget assertion and Metal pending-pass ownership. This tests guidance rather
  than reproducing a native run.
- Fixture: `fixtures/config-screen-only.json` intentionally passes the helper's
  selected rules but omits other required native fields and all tensor payloads.

## Expected Successful Behavior
Report only selected-rule screening; retain compiler/backend/weights checks.
Clamp 4096 to 2048 and calculate 1900 + 148 + 1 = 2049, so the request does not
fit. Explain clone/view aliasing, offsets and idle-GPU reset requirements. Do not
execute or turn component formulas into a physical-memory fit claim.

## Failure Signals
Calling the fixture fully compatible, omitting the extra slot, using the
unclamped ceiling, treating clone as data copy, resetting while pending, or
promising memory fit from weight size alone.
