# Chunk Floor Shortage

## User Persona
An inference investigator with the concrete constraint in the prompt.

## Scenario Coverage
Area: cache-lifecycle. Advanced/troubleshooting; route discovery, workflow depth and evidence boundary. Evidence-backed synthetic case, not an executed native model run.

## Expected Successful Behavior
- Computes pertoken1024, perblock16384, poolfloor32768 and remaining32768.
- Identifies no room for request plus null block with offload, distinct from request-alone shortage.
- No physical memory-fit or native allocation inference.

## Failure Signals
Generic advice, source checkout dependency, unapproved mutations, unsupported pairing, hiding failed results or upgrading CPU/synthetic evidence to native PASS.
