# Plan an ordinary target-only control before a DSpark comparison

## User Persona
New DwarfStar user with authorized local model files but requesting a plan only.

## Scenario Coverage
- Skill area: `qualification`
- Capability: correctness-first single-host comparison planning
- Difficulty: intermediate
- Prompt file: `user_request.txt`
- Expected references: bundled `verification-contract.md` and `troubleshooting.md`.
- Trigger expectation: sampling or physical-topology qualification requires this route.

## Expected Successful Behavior
- The response provides a target-only command template and a candidate adding --dspark --mtp-model with placeholder model/support paths.
- The response freezes same target/support hashes, backend/build, prompt/context/output length, greedy sampling, repetition and cache policy before running.
- The response records accepted-prefix correctness, first divergence/quality, draft/verify/replay costs and actual path activation instead of ranking acceptance alone.
- The response explains that batched verifier arithmetic may differ from serial greedy decoding, so the frozen correctness standard must be explicit.
- The response distinguishes single-host diagnostic evidence from service latency, physical TP/RDMA, other models and backend qualification.
- The response does not execute a command, download a model or claim a completed result.

## Evidence and Construction
Ordinary task anchors command generation and the experiment worksheet to the documented matched-checkpoint comparison, complementing the two difficult synthetic cases.
This case grades guidance, not actual engine runtime or behavioral efficacy.

## Failure Signals
- Any assertion fails.
- A response upgrades source/CPU/synthetic evidence into GPU, model, RDMA or service qualification.
- It requires source-checkout documentation or leaks private environment details.
- It executes outside the requested planning-only scope.
