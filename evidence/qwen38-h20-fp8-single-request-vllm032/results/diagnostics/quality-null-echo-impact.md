# Prospective quality SSE null-echo repair

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE — compatibility repair, no task quality or performance verdict.**

The archived v2 parser interprets a present but null prompt_token_ids field as
another prompt echo. All five retained baseline1961 response streams reproduce
that error. A one-line versioned successor treats null/absent as no echo while
retaining the exact, once-only, non-null first-choice identity requirement.
Five of five original streams parse in the successor; genuine duplicate echoes
still fail. These are CPU replays of completed service responses, not a new GPU
run or end-to-end performance improvement. Original1961 observer failure and v2
quality source/results are unchanged.

Independent review verified the patch, new run.py identity and unchanged seven
other archive members. Eleven focused checks covered the five real responses,
null/absent fields and rejection of duplicate, late, missing and wrong echoes.
No blocking finding; the narrow successor is suitable for publication.

New run.py SHA2565255b0fe1aa6896f57e9dc7cfcf61aab5b03104186cafd55a1358321bea2b7dc.
Patch SHA2565411013bdec21cab01b70b303cf05e3c2fa753897062eb75bda6792cb5d2efbf.
The full original archive and versioned successor stay in controlled storage;
apply the committed patch to the archive bound in quality-activation-review.md
for reproduction. No package, model, dataset, scorer or gate changed.

A new source manifest and full freeze must bind the successor before execution.
Natural-EOS/stop authentication and HumanEval+ sandbox qualification remain open.
This repair does not remove those activation blockers or authorize search.

KnowledgeStore candidate `case.qwen38-quality-activation-gaps-cand` advanced to
`sha256:8bc1297472e32767d457a37c6f56179e4832c45b332e593784e63fe66859ecd7` with exact readback; prior failure history retained.
