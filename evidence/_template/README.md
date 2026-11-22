# <campaign-id>

Copy this directory for a new campaign, then replace all placeholders. The
`*.example.json` files describe fields; they are not runnable evidence.
Follow the [archiving contract](../../docs/evidence-archiving.md).

- Acceptance issue and owner: <issue-url>, <owner>
- Goal, compared variants and execution conditions: <description>
- Source/configuration/input/validator identities: [plan/](plan/)
- Conclusion and limitations: <PASS / FAIL / INCONCLUSIVE with rationale>
- Performance and quality: [results/summary.json](results/summary.json)
- Every attempted trial: [results/trials.jsonl](results/trials.jsonl)
- Archive authority: [results/artifacts.json](results/artifacts.json)
- Verification commands, identity pins and comparison rules: [validator/](validator/)

State sample/failure counts, repetitions and variability, not only best results.
Generate the trial index from the existing controller or frozen source records;
retain failed, regressing, interrupted and repeated attempts with distinct IDs.
Do not create a second controller state. Explain unavailable/private originals
and the resulting verification limits. Archive availability is separate from
the historical experiment verdict.
