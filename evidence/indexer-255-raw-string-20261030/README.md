# Opt-in raw-string lexical contract

Related tracker: [Issue #255](https://github.com/InferMatrixLab/InferRSI/issues/255).
The single frozen comparison and independent saved-output audit passed **only the
synthetic lexical-presence contract**. No general task accuracy, latency, model
or hardware efficacy, default promotion or tracker completion is inferred.

## Try the existing interface with the new explicit method

From the source checkout with the package dependencies installed:

```bash
PYTHONPATH=src python -m inferrsi collect 'cpu.stat.local' \
  --relevance cgroupv2 --relevance-method weighted-raw-string-v1 \
  --context-bytes 65536 --limit 1 --json
```

Omit `--relevance-method` for unchanged legacy selection. The query remains a
filter; the relevance cue ranks packaged skill owners. Context resources remain
whole files with exact owner revision and SHA-256. The fixed real-corpus example
returned the same complete 7,348-byte cgroup-resource-controls core in both
modes; this is an interface demonstration, not a quality improvement claim.

Synthetic cue `n t`, with unchanged title weight 4:

| Original title | Legacy score | Opt-in score |
|---|---:|---:|
| Actual newline + tab | 8 | 0 |
| Literal backslash-n + backslash-t | 8 | 8 |

The phantom owner is no longer admitted. All declared genuine controls remain.
See the [readable before/after](results/readable-demo.txt) and
[independent audit](results/independent-postrun-review.json).

## Retained evidence

- Frozen baseline: `1052925ff22f9a850cebc64afd0083b35ed1fae9`.
- Frozen candidate: `728984c524cf696d063ff7ef0688ae126c8546a6`.
- [Exact protocol](plan/protocol.md), original [candidate patch](patch/frozen-candidate.diff)
  and [Git bundle](patch/frozen-candidate.bundle). The Git bundle requires the
  publicly retained baseline commit; it preserves the original local candidate
  identity rather than substituting the later publication commit.
- [Complete frozen study archive](results/frozen-study.tar.gz), SHA-256
  `3074dbc24d198ff3d8ec440f839578340222b85600a5ff67c9d4186f88ec2b23`.
  All 36 retained files are byte-preserved, including original fixtures,
  prospective freezes, raw outputs, ordinary test logs, initial development
  failure, superseded pre-review freeze, provenance, source/module fingerprints,
  independent reviews and the one-run receipt. No scored comparison was repeated.
- [Current-main integration check](results/integration-check.json): clean application
  to `436c950cf06ded742fef61ff4303493ac5175d4b`, 108 affected tests passed,
  2 skipped and Ruff passed. This does not rebase or replace the frozen study.

## Results and boundaries

All 14 scalar and 2 ordering fixtures matched their independently authored labels.
Five phantom field-token contributions were removed across two scalar cases;
15 original-string and 11 expected nonstring-JSON positive contributions were
retained. Six nonstring field controls and 21 compatibility requests preserved
legacy behavior, including optional context contents, hashes, revisions and
omissions. Defaults, explicit-ID membership/order, filters, query and budgets
are unchanged. Full ordinary CPU checks on the frozen candidate passed 2707 tests
and 284 subtests with 12 skips; these are not task-efficacy evidence.

See [publication provenance](plan/publication.md) for the distinction between
new configured authorship, inherited historical evidence and CI qualification.
