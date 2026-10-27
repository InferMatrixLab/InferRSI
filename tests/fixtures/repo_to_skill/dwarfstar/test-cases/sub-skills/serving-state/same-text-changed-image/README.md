# Identical text, changed image

## User Persona
An experienced application integrator investigating a stale multimodal cache.

## Scenario Coverage
- Skill area: `serving-state`.
- Capability: historical image identity gates, append semantics and route/materialization agreement.
- Difficulty: troubleshooting.
- Prompt file: `user_request.txt`.
- Expected resources: `sub-skills/serving-state/SKILL.md` and its state-contracts/troubleshooting references.
- Trigger expectation: the user names DwarfStar KV reuse and a concrete image/tool-history interaction.
- Synthetic extension: combines the source's image-predicate assertions with the server's independently matched tool continuation; not a claim of native execution.

## Expected Successful Behavior
Reject stale reuse after changing a historical image fingerprint or embedding row count even when visible text and call IDs match. Distinguish fingerprint-only routing from strict token/span validation. Permit consideration of an appended image only after historical identity, independent text/tool history and new-image position constraints hold. Do not promise that an image-prefix probe alone proves reuse. Propose a one-variable identity comparison and preserve the missing model/backend boundary.

## Failure Signals
Text-only cache keys, equal tool IDs or matching image counts are treated as sufficient; historical image ordering is ignored; a pure predicate test is described as GPU/model verification; the response downloads weights or runs inference despite the constraint.
