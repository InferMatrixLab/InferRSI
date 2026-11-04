# Screen a saved record without launching the benchmark

## User Persona
Maintainer handed a saved Lily JSON record but no execution environment.

## Scenario Coverage
- Skill area: `qualification`
- Capability: safe offline record consistency and its evidence limit
- Difficulty: intermediate
- Prompt file: `user_request.txt`
- Expected runtime files: qualification SKILL.md, verification-contract.md, troubleshooting.md and audit_benchmark_record.py where relevant.
- Trigger expectation: native test or benchmark-evidence interpretation routes here.

## Expected Successful Behavior
- The response references audit_benchmark_record.py with --report, --source-id and --decode-steps, and --diagnostic only for a declared diagnostic record.
- The response describes selected source/mode/count/positive-finite-value/token-ID/FNV digest consistency rather than a full matrix verdict.
- The response rejects diagnostic GPU timing fields in production records and missing required shapes in diagnostic records.
- The response explains that the helper imports neither upstream runner nor MLX and starts no model process, machine survey, download or subprocess.
- The response states that internally consistent supplied metadata can be fabricated or stale and does not authenticate actual source/binary/model bytes or execution.
- The response leaves native compiler/Metal/model/service qualification and final admission separate from a successful offline audit.

## Evidence and Construction
Ordinary case anchored in the source record validator and native report schema; the adapted helper is a new safe metadata-only support surface.
The case grades guidance and safe metadata handling, not GPU behavior or skill efficacy.

## Failure Signals
- Any assertion fails.
- Source, omitted or Python/static checks become native/model/E2E proof.
- The response relies on source-checkout runtime scripts, leaks private details or executes beyond the request.
