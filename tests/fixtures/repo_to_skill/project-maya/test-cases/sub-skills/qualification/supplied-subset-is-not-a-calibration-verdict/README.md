# Supplied subset, calibration controls and aggregation

## User Persona
An optimization engineer deciding whether a saved descriptive record justifies a permanent tuning gate.

## Scenario Coverage
- Skill area: qualification
- Capability: offline reducer and calibration experiment boundaries
- Difficulty: advanced
- Prompt file: `user_request.txt`
- Expected references/scripts: `sub-skills/qualification/SKILL.md`, `sub-skills/qualification/references/verification-contract.md`, `sub-skills/qualification/references/troubleshooting.md`, `sub-skills/qualification/scripts/summarize_decode_records.py`
- Trigger expectation: A concrete Project Maya qualification request with claim-boundary and failure-handling constraints.

## Expected Successful Behavior
Use the bundled standalone helper or reproduce its documented arithmetic: baseline token-weighted rate 30/1.1 ≈27.2727 tokens/s and median sample rate 105; candidate completed measured rate 30, warmup excluded, blocked count1, completed-subset change+10%, acceptance 29/30 only descriptive. Explain that a positive subset and supplied fake hashes authenticate nothing. Correct freshness/cyclic wrap, incumbent combination and sequential-versus-interleaved experiment descriptions, without importing numerical gates.

## Failure Signals
Calling105 tokens/s the token-weighted rate; including warmup; omitting the blocked record; treating fake hashes or a descriptive change as native/service proof; high acceptance as sufficient speed evidence; labelling sequential starts ABBA or setting global 3%/5% gates.

## Evidence and Synthetic Extension
Synthetic conjunction extends calibration fake-engine tests with an offline record that has conflicting aggregation, blocked work and warmup bias; native tests do not establish this reporting contract. Source evidence is anchored at `249f9a87d1a9d72bec2b684d704b0aa9296b1c9c`; hypothetical/synthetic observations in the prompt are not reported as actual upstream or local executions.
