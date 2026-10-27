# Pre-measurement amendment 1

Independent review found two fail-closed defects after the first packet freeze
and before any formal candidate evaluation or timing:

- Positional `zip` comparisons could silently ignore missing output rows. A
  synthetic candidate with incomplete API/CLI measurements could satisfy the
  timing gate without complete evidence.
- Fixture and warmup checks used Python assertions, which optimized Python could
  disable.

The validator now requires the exact case-by-mode sets once per side, the full
pair-ID range and each prescribed AB/BA order. Missing, extra or duplicate rows
or pair IDs make the comparison INCONCLUSIVE and prevent a performance PASS.
Quality comparison explicitly checks its complete expected set, including all
96 rows per side for the full 24-case run. Keyed comparisons replace `zip`.
Critical checks raise explicit exceptions; child processes set PYTHONOPTIMIZE=0
and record optimization flags. Synthetic selfchecks cover incomplete/duplicate
quality rows, missing benchmark rows and duplicate paired groups.

The original `plan/freeze-v1.json` is preserved with content digest
`2a90de774129b06597c3c99e5b06d05bf735026829deb84376d06a985cdcc276`.
Before this supersession, only source-label/static validation and
baseline-v-baseline mechanics had run, never formal candidate measurement.
The revised `plan/freeze.json`
supersedes it prospectively. Fixture text, relevance labels, scoring rules,
query workloads, numeric gates and bootstrap method/seed are unchanged. The
runtime candidate was already fixed before the withheld fixture was released.
