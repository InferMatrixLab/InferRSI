# Do not conflate BF16 KV, BF16 recurrent state and ANE prefill

## User Persona
Maintainer trying to reproduce an upstream numerical report on a different Mac.

## Scenario Coverage
- Skill area: `qualification`
- Capability: precision and actual ANE path qualification
- Difficulty: troubleshooting
- Prompt file: `user_request.txt`
- Expected runtime files: qualification SKILL.md, verification-contract.md, troubleshooting.md and summarize_rounds.py where relevant.
- Trigger expectation: speculative/precision/benchmark qualification routes here.

## Expected Successful Behavior
- The response refuses to call the author-reported measurements local reproduction or to transfer or combine speed ratios across machines and numerical settings.
- The response distinguishes KV storage, recurrent-state storage/rounding and weight precision; BF16 state still rounds stores despite FP32 compute.
- The response explains that eligible dense FFN prefill may split across Metal and W8A8 ANE, while MoE, mixers and decode remain GPU work in the inspected design.
- The response requires actual startup split/context/cache selection rather than assuming that ANE enabled means an active or faster split.
- The response controls verify_rows all where needed, isolated request/cache salt, cached prefix/chunk boundaries, concurrency, precision and matched target/draft bytes before judging repeatability.
- The response preserves missing Metal/ANE/model verification as BLOCKED_REQUIRED_BACKEND and gives no completed quality/performance claim or native execution.

## Evidence and Construction
Difficult synthetic case combines reported benchmark controls, orthogonal precision mechanisms, private-interface startup selection and reproducibility pitfalls.
This case grades source-grounded guidance, not actual backend execution or skill efficacy.

## Failure Signals
- Any assertion fails.
- Source or CPU evidence becomes a Metal/ANE/model/service claim.
- The answer needs original checkout docs/scripts or leaks private paths.
- The answer executes outside the planning-only request.
