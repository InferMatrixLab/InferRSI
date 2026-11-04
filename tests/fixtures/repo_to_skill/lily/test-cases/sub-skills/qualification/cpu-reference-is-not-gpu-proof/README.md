# Do not convert a CPU oracle or omitted tests into native proof

## User Persona
Contributor reviewing a green Linux check without native Apple hardware.

## Scenario Coverage
- Skill area: `qualification`
- Capability: test cfg, CPU oracle, ignored golden and native execution boundaries
- Difficulty: troubleshooting
- Prompt file: `user_request.txt`
- Expected runtime files: qualification SKILL.md, verification-contract.md, troubleshooting.md and audit_benchmark_record.py where relevant.
- Trigger expectation: native test or benchmark-evidence interpretation routes here.

## Expected Successful Behavior
- The response routes to qualification and distinguishes non-macOS library-only compilation from all-target compilation or a CPU inference backend.
- The response explains that CPU-reference algorithms are numerical oracles and selected matches_cpu tests create a Metal context, dispatch and read back GPU results.
- The response reports cfg-omitted, ignored, filtered, completed and not-run checks separately and does not treat a green summary or short duration as native proof.
- The response separates shader function/pipeline construction from numerical, route-selection, recurrent-state, matched-model and service correctness.
- The response requires the route predicate and actual numerical GPU checks on both sides, including packing/tails/views and stack-versus-slice reduction consistency.
- The response keeps absent Rust/compiler/M5/macOS/model evidence blocked and does not install, execute a model, rewrite a golden or claim Metal PASS.

## Evidence and Construction
Difficult synthetic case combines actual cfg/ignored mechanisms with CPU-oracle naming and route fallback, beyond a single native numeric test.
The case grades guidance and safe metadata handling, not GPU behavior or skill efficacy.

## Failure Signals
- Any assertion fails.
- Source, omitted or Python/static checks become native/model/E2E proof.
- The response relies on source-checkout runtime scripts, leaks private details or executes beyond the request.
