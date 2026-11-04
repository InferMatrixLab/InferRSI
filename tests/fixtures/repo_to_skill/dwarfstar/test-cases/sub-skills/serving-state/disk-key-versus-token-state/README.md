# Disk lookup is not backend state

## User Persona
A maintainer diagnosing a post-restart tool-continuation rebuild.

## Scenario Coverage
- Skill area: `serving-state`.
- Capability: rendered-byte keys, exact-token payload, tool replay and distributed restore.
- Difficulty: advanced.
- Prompt file: `user_request.txt`.
- Expected resources: `sub-skills/serving-state/SKILL.md` and bundled state-contracts/troubleshooting references.
- Trigger expectation: the prompt combines persistent DwarfStar KV with a concrete BPE mismatch and TP deployment.
- Synthetic extension: combines independently sourced byte-prefix loading, canonical-tail safety and TP rebuild behavior; source native candidates do not by themselves verify this integrated deployment.

## Expected Successful Behavior
Treat the filename match as a lookup candidate, not payload validation. Preserve the exact saved token history and tokenize only the new text suffix on a successful compatible load. Check model ID, saved context versus current capacity, optional same-quant policy and payload version/layout. Reject token-vector-only replacement behind the live frontier. Explain missing/mixed tool-map fallback and that a live ID binding is not durable remote conversation storage. TP reload rebuilds both ranks from exact tokens; it does not directly restore a second GPU. Preserve failures and avoid service mutation/cache deletion.

## Failure Signals
Equal bytes are assumed to prove token/backend equality; canonical tokens are spliced into old KV; larger saved context is forced into a smaller runtime; tool IDs are assumed durable; a local file is claimed to restore all ranks instantly; a proposed recovery is mislabeled as an executed native result.
