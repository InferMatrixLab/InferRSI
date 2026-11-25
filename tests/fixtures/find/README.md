# Externally labelled queries for `find`

`labelled-queries.json` holds 36 queries derived from the nine frozen decision
points of the material-discovery experiment
([#380](https://github.com/InferMatrixLab/InferRSI/issues/380)), three to five
per decision point.

## Why these labels are worth keeping

The earlier query set for this tool was written by whoever wrote the corpus
metadata, so it matched by construction and overstated retrieval quality. These
were produced by a separate model working only from the task descriptions, with
instructions not to open the corpus. It could not phrase a query around a
document it had seen, and it was told that "no knowledge base entry would help
here" is a real answer rather than a failure. Nineteen of the 36 came back that
way, which is the single most informative part of the set.

## Fields

Each query carries:

- `query` and `axis` — the wording, and which register it uses: `symptom`,
  `terminology`, `question`, `terse` or `chinese`. At least one query per
  decision point is `symptom` or `question`, and at least one is `chinese`.
- `expect` — `case`, `skill`, `record`, or `none` when the situation is already
  decidable from the stated facts.
- `expect_reason` and `must_surface` — why that kind, and what the ideal top
  result would tell the reader, in the labeller's own words rather than as a
  path or an ID.
- `confidence` — the labeller's own `high` / `medium` / `low`.

## What these numbers do and do not support

Scoring counts whether an entry of the expected kind appears in the top three.
That is a coarse proxy: it does not check that the particular entry returned is
the most useful one, and it says nothing about whether acting on it leads
anywhere. The `none` queries are reported separately and never folded into a
hit rate — they test restraint, which this tool does not currently have.

Known qualifications, retained rather than repaired after seeing results:

- All nine decision points come from one experiment, built to study material
  discovery. Day-to-day questions may be shaped differently.
- One query labelled `skill` is better served by a case: it asks how to measure
  admission and drain separately, and a casebook entry records exactly that
  observation. The label is kept as written.
- Labels are one model's judgement, unreviewed by a second. `confidence` is
  self-reported.

Reproduce with `tests/knowledge/test_knowledge_find.py::test_external_label_set_retrieval`.
