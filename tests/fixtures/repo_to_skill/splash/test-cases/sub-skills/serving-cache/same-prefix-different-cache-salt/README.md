# Same prompt, different cache salt

## User Persona
An application engineer integrating a shared local inference service.

## Scenario Coverage
- Skill area: `serving-cache`.
- Capability: request-salt boundary, exact native prefix identity and image-row cache scope.
- Difficulty: advanced.
- Prompt file: `user_request.txt`.
- Expected resources: `sub-skills/serving-cache/SKILL.md`, `references/state-and-api.md`, `references/troubleshooting.md`.
- Trigger expectation: the prompt names Splash cache salts and gives a concrete counterexample to the mistaken all-cache-isolation assumption.
- Basis: synthetic combination of frontend salt validation, native root-key branching and the documented global image-encoding cache. It is not a native execution result.

## Expected Successful Behavior
Explain that different salts separate prompt-KV chains and composite states at the root even when text/tokens match. Separate image-encoding reuse from prompt-KV reuse: image rows may be globally reused by image identity, not salt. Reject authentication and universal isolation claims. Propose comparing exact prompt/image identity, effective salt and the correct separate counters, without inference or external mutations. Preserve the backend verification block.

## Failure Signals
Any saved image work is labeled a cross-salt prompt hit; equal visible text overrides salt; a salt is called an authorization token or all-cache isolation primitive; Python protocol/LRU tests are claimed to establish native device behavior.
