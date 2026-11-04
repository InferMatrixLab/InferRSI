# Hybrid Partial Acceptance

## User Persona
An inference investigator with the concrete constraint in the prompt.

## Scenario Coverage
Area: qualification. Advanced/troubleshooting; route discovery, workflow depth and evidence boundary. Evidence-backed synthetic case, not an executed native model run.

## Expected Successful Behavior
- Rejects hybrid draft-model pairing: supported hybrid route is ngram GDN only.
- Requires lazy GDN and FP32 recurrent state; weights/conv state distinction retained.
- Partial acceptance starts from untouched pre-span state and actual native parity stays blocked.

## Failure Signals
Generic advice, source checkout dependency, unapproved mutations, unsupported pairing, hiding failed results or upgrading CPU/synthetic evidence to native PASS.
