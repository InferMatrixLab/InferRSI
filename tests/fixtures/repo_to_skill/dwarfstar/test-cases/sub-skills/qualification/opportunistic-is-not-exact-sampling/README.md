# Separate distribution preservation from seeded output identity

## User Persona
Experienced inference user comparing algorithms, not yet familiar with DwarfStar sampling semantics.

## Scenario Coverage
- Skill area: `qualification`
- Capability: opportunistic versus exact speculative sampling
- Difficulty: advanced
- Prompt file: `user_request.txt`
- Expected references: bundled `verification-contract.md` and `troubleshooting.md`.
- Trigger expectation: sampling or physical-topology qualification requires this route.

## Expected Successful Behavior
- The response routes to qualification and reads the bundled verification contract.
- The response states that default nonzero-temperature opportunistic greedy-draft acceptance is not a target-distribution preservation guarantee.
- The response identifies --mtp-exact-sampling as the selected exact path where implemented and describes acceptance/correction rather than only argmax agreement.
- The response does not promise identical seeded token sequences across ordinary and exact speculative algorithms because additional random draws and batched arithmetic differ.
- The response keeps CPU synthetic-logit sampling checks separate from actual accelerator state, matched-model quality and service verification.
- The response freezes mode, checkpoint hashes, sampling filters, workload and quality/performance gates before comparison and refuses to execute or download.

## Evidence and Construction
Synthetic case extends the native histogram test by combining a misleading default-mode conclusion, exact-mode RNG expectations and an unavailable backend.
This case grades guidance, not actual engine runtime or behavioral efficacy.

## Failure Signals
- Any assertion fails.
- A response upgrades source/CPU/synthetic evidence into GPU, model, RDMA or service qualification.
- It requires source-checkout documentation or leaks private environment details.
- It executes outside the requested planning-only scope.
