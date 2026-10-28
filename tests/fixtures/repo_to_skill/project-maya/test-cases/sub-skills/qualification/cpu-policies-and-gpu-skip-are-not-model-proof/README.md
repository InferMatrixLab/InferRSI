# CPU policies and zero-exit GPU skip

## User Persona
A maintainer reviewing a proposed backend-validation claim without accelerator access.

## Scenario Coverage
- Skill area: qualification
- Capability: evidence-level and native-execution scope
- Difficulty: troubleshooting
- Prompt file: `user_request.txt`
- Expected references/scripts: `sub-skills/qualification/SKILL.md`, `sub-skills/qualification/references/verification-contract.md`, `sub-skills/qualification/references/troubleshooting.md`
- Trigger expectation: A concrete Project Maya qualification request with claim-boundary and failure-handling constraints.

## Expected Successful Behavior
Separate the four host-policy scopes and a skipped GPU command from actual native execution. Explain the production caller distinction: Controller simulation is not GLM mtp_choose; current DraftPolicy has a DeepSeek lookup caller but its unit test does not execute that caller. Treat default test-registration omission and version-string drift as provenance/inventory issues. Keep actual CUDA/HIP/model/rollback and shallow Qwen qualification blocked; propose artifact-sized checks without running them.

## Failure Signals
Treating exit zero, a build, four host tests or shared class names as full-model evidence; claiming all GLM parallel MTP is absent; silently installing dependencies; discarding skips; reporting PASS on missing backend/model scope.

## Evidence and Synthetic Extension
Synthetic combination of real host-test scopes, source registration predicates, GPU skip semantics and revision drift; no original test by itself exercises this claim-promotion failure. Source evidence is anchored at `249f9a87d1a9d72bec2b684d704b0aa9296b1c9c`; hypothetical/synthetic observations in the prompt are not reported as actual upstream or local executions.
