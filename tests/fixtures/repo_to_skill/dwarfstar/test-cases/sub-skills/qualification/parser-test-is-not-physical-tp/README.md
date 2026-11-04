# Do not promote local protocol checks into network-TP qualification

## User Persona
Maintainer planning a heterogeneous deployment from partial CPU results.

## Scenario Coverage
- Skill area: `qualification`
- Capability: topology/mode compatibility and physical-backend evidence
- Difficulty: troubleshooting
- Prompt file: `user_request.txt`
- Expected references: bundled `verification-contract.md` and `troubleshooting.md`.
- Trigger expectation: sampling or physical-topology qualification requires this route.

## Expected Successful Behavior
- The response routes to qualification and distinguishes in-process CUDA TP, network two-rank TP and pipeline placement.
- The response rejects combining CUDA network TP with SSD streaming or in-process --cuda-tensor-parallel in the inspected validator.
- The response states that local socketpair success and ping do not establish a physical RDMA data plane, GPU inference, or model correctness.
- The response preserves the V4.1 network-DSpark source documentation conflict and notes implementation paths without asserting resolved support or absence.
- The response requires exact matching peer/model/build identities, actual negotiated transport, both-rank runtime and cancellation/partial-commit/restore/failure evidence.
- The response keeps missing accelerator and physical transport evidence BLOCKED_REQUIRED_BACKEND and does not recommend bypassing validators, changing host settings or starting services.

## Evidence and Construction
Synthetic combination of real validator constraints and conflicting documentation goes beyond local framing tests and catches unsafe evidence promotion.
This case grades guidance, not actual engine runtime or behavioral efficacy.

## Failure Signals
- Any assertion fails.
- A response upgrades source/CPU/synthetic evidence into GPU, model, RDMA or service qualification.
- It requires source-checkout documentation or leaks private environment details.
- It executes outside the requested planning-only scope.
