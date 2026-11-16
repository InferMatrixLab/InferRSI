# validator/ (template)

- Frozen validator definition and inputs (version-pinned)  
- Must be fixed **before** campaign runs; missing freeze → `INCONCLUSIVE`  

## Archive replay contract

Keep a reviewed recomputation entry point here or reference its immutable source
revision. Declare its command, input identities and numerical comparison rules
in `results/artifacts.json` (v2). The generic verifier never executes that command.

The entry point must independently enumerate every original trial from the
archived control records, including failed/interrupted and repeated attempts.
It writes `results/trials.jsonl` and `results/summary.json` to a new output
directory. Do not read retained summaries/indexes as inputs to regeneration.
Document each metric's source rows, formula, sample/failure counts and validator
identity. Review this derivation before accepting completeness.

1. Run the shared verifier with `--download` or a locally retrieved `--archive`.
2. Inspect and run the declared, identity-pinned replay command separately.
3. Run the shared verifier with the same archive and `--recomputed <output>`.

Structure, trial IDs, statuses, strings, integers and booleans compare exactly.
Only finite JSON floats use the predeclared absolute/relative tolerances. Freeze
those tolerances before archiving; never adjust them just to make replay pass.
Matching outputs do not prove the replay algorithm enumerated all control
records; the campaign review and adversarial coverage tests establish that.

Record commands, input digests, completeness checks, comparison results and gaps.
Download/hash success alone does not establish experiment reproducibility or
campaign acceptance. See [the shared tool](../../../tools/verify_evidence_archive.py).
