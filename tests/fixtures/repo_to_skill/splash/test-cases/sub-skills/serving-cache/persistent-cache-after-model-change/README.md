# Persistence after a model/layout change

## User Persona
A maintainer preparing a local model upgrade and investigating cold starts.

## Scenario Coverage
- Skill area: `serving-cache`.
- Capability: namespace identity, atomic state/KV recovery, write-behind durability and process-local API history.
- Difficulty: troubleshooting.
- Prompt file: `user_request.txt`.
- Expected resources: serving-cache router plus its state-and-api and troubleshooting references.
- Trigger expectation: concrete Splash flags and an actual API error require distinct disk/runtime/history lifetimes.
- Basis: synthetic integrated case extending persistent namespace/adoption and Responses-store contracts; no claim that a crash/model-upgrade experiment ran.

## Expected Successful Behavior
Explain why weights/state layout changes can select a cold namespace. Reject renaming namespaces, patching labels or replaying arbitrary old KV; continuation requires a compatible composite recurrent/draft state and complete KV chain. Separate the lost process-local Responses history store from disk-prefix persistence; resend complete history after the ID miss. Explain that publication/response completion is not immediate durability and only landed complete points survive a crash. Suggest inspecting namespace, effective formats, taken-back/write-behind/write-gate observations without mutating files or running inference. Keep native implementation verification unestablished.

## Failure Signals
A shared directory is treated as cross-model compatibility; response IDs are assumed persistent with KV; a disk slot is called durable before completion; failed labels/chains are patched to force a hit; proposed recovery is presented as executed native evidence.
