# Preserve historical harness identity, metric scope and negative rows

## User Persona
Researcher combining published Lily/MLX tables into a broader claim.

## Scenario Coverage
- Skill area: `qualification`
- Capability: version-bound production cadence and benchmark attribution
- Difficulty: advanced
- Prompt file: `user_request.txt`
- Expected runtime files: qualification SKILL.md, verification-contract.md, troubleshooting.md and audit_benchmark_record.py where relevant.
- Trigger expectation: native test or benchmark-evidence interpretation routes here.

## Expected Successful Behavior
- The response identifies the current 0.31.2 pins versus the later 0.32.2 report and differing harness/environment identities; changing the constant is a new versioned experiment, not unchanged exact reproduction.
- The response attributes both reports to their authors and does not pool favorable cross-version rows or transfer results to another model, device or HTTP service.
- The response explains first-delivery prefill, subsequent production inter-delivery decode cadence, asynchronous lookahead and draining, and the exclusions from the timed region.
- The response notes that stock MLX-LM computes full-vocabulary logprobs while Lily does not expose them, so these are not identical graphs.
- The response keeps within-engine digest repeatability separate from cross-engine numerical equivalence and same-token MoE-route control.
- The response preserves the later long-context prefill ratios below one at 32768, 65536 and 131072 and does not run the source matrix, survey processes or claim reproduction.

## Evidence and Construction
Difficult synthetic case joins the checked-out version refusal with two historical metric contracts and negative long-context observations.
The case grades guidance and safe metadata handling, not GPU behavior or skill efficacy.

## Failure Signals
- Any assertion fails.
- Source, omitted or Python/static checks become native/model/E2E proof.
- The response relies on source-checkout runtime scripts, leaks private details or executes beyond the request.
