# MiniMax-H3 Ref2VA historical Ascend 950PR record

This bundle is the compact, reviewable projection for the historical experiment
record tracked in Issue #520. It preserves searchable configuration, trial,
summary, and recomputation data while the privacy-reviewed raw material remains
in a versioned external archive.

The record covers MiniMax-H3 Ref2VA experiments collected between 2026-10-20
and 2026-11-18 on Atlas 150 / Ascend 950PR systems. The retained observations
include dense step sweeps, Cache-DiT, RainFusion, quantization, communication
probes, failures, retries, and partial VBench results.

## Verdict and interpretation

The overall performance and quality verdict is `INCONCLUSIVE`.

- Historical `PASS` strings are retained only as source observations; they are
  not current InferRSI acceptance decisions.
- The 4.2242x 50-step engine-stack observation and the 7.3747x 10-step plus
  Cache-DiT observation are separate comparisons and are not cumulative.
- Some VBench dimensions had one prompt per seed, source/runtime identities are
  incomplete, no validator was frozen before search, and the original
  containers are unavailable.
- The 448 index rows are source-derived observations, not 448 independent
  trials.

## Retained core

- `plan/effective.json` records the bounded historical scope and environment.
- `results/trials.jsonl` indexes all 448 structured observations, including
  failed and inconclusive records.
- `results/summary.json` preserves recorded ratios and limitations.
- `results/external_optimization_record.json` exposes the compact external
  record without promoting it into gain ranking.
- `validator/recompute.py` checks only the arithmetic stated in the summary. It
  does not rerun the model, VBench, or establish acceptance.
- `results/artifacts.json` is the authority for the external archive.

## Archive verification

Offline metadata and repository inventory checks do not download the archive:

```bash
python tools/verify_evidence_archive.py evidence/h3-ref2va-ascend-history-20261118/results/artifacts.json
python tools/validate_evidence.py
```

Explicit archive verification authenticates the compressed bytes and bounded
members before any replay comparison:

```bash
python tools/verify_evidence_archive.py \
  evidence/h3-ref2va-ascend-history-20261118/results/artifacts.json \
  --download
```

The public archive excludes media, model/cache payloads, the complete VBench
workspace, and unavailable live container state. Hash verification establishes
which redacted bytes were retained; it does not establish historical execution
correctness, model-quality equivalence, or a campaign `PASS`.
