# #255 source-conditioned cue feasibility — FAIL

## Decision
The one prospectively frozen paired run did not improve retrieval ranks: raw task and verbatim cue each achieve partial-label Hit@5 **6/6**, MRR@5 **29/36** (approximately0.805556), and complete relevant delivery **6/6**. The strict MRR improvement gate fails. No further wording changes or retries were made; no production change, promotion, or #255 closure follows.

All other evaluated gates pass: no labelled hits lost; identical-input controls produce identical serialized outputs; six unchanged-interface captures match; full required-resource integrity and budget accounting pass; frozen source remained unchanged; execution recorded no errors.

## What was actually tested
Six deliberately source-covered, synthetic tasks authored from reviewed source capsules. This is source-conditioned feasibility, not organic demand or unbiased general retrieval accuracy. Four cue edits mostly remove polite introductory framing and join retained spans with semicolons. Two controls are byte-identical. This narrow intervention does not establish broad narrative normalization, automatic rewriting, cheap human preparation, downstream agent benefit, or coverage of arbitrary repository tasks.

The previous blind-task preparation-INCONCLUSIVE (only three supported pairs below its four-case minimum) and prior performance/v2/v3 FAIL results remain separate and unchanged. The old sealed heldout was not accessed or evaluated.

## Frozen identity / execution
- Runtime/corpus baseline: `6e6ee245d9e92ee9365976f2e4e262304999f147`, production weighted-lexical-v1, unchanged in both arms.
- Accepted protocol: `4512e1ea3d56235b207e4926c0ed84e8eb3022a461830c919ad29810ee27b026`.
- Inputs: `24e822eaadcd4598435dac0e7cf77cc1dd73d8a6c50bc0f7c5982253b4a94fcc`.
- Input freeze: `305246e2c49ea47bea9dbe9dc412e5a8920acec735f01f445514938b8cf7b9c3`.
- Frozen runner: `566c9e2d3a63eb3d9b7e8f4b1e41ce1c5121e316c0ffa50ffc01fd0aca40c1af`; runner-freeze.json predates all retrieval.
- Exactly one capture per arm/case through production Collect with query empty, no filters, limit5, context budget262144. No new scorer, source edits, installations, models/services, hardware or timing campaign.

## Per-case table
| Case | Raw rank | Cue rank | Identity control | Raw/cue chars | Context bytes raw/cue | Output bytes raw/cue |
|---|---:|---:|---|---:|---:|---:|
| covered255-01 | 2 | 2 | False | 535/497 | 256659/256138 | 1083382/1081318 |
| covered255-02 | 3 | 3 | True | 299/299 | 234561/234561 | 1057891/1057891 |
| covered255-03 | 1 | 1 | True | 275/275 | 146747/146747 | 961583/961583 |
| covered255-04 | 1 | 1 | False | 558/532 | 144355/144355 | 961468/961442 |
| covered255-05 | 1 | 1 | False | 592/555 | 183756/183756 | 1006115/1006078 |
| covered255-06 | 1 | 1 | False | 521/487 | 143629/129803 | 961055/945736 |

Ranks are over partial positive IDs, not exhaustive precision/recall labels. Complete relevant delivery is audited separately from rank. Output byte differences may include selection cue metadata and do not imply rank or reasoning improvement. Full raw outputs preserve item order, resources and omissions.

## Independent supplemental audit
`independent-review.json` verifies all12 saved outputs, exact ranks/fractional arithmetic,29 emitted contexts per arm with full required sets/bytes/hash/revision/budget, unchanged frozen identities and control/default parity. No retrieval or heldout was rerun. Some unlabelled top-five items change, so this is neutral on labelled rank metrics, not a claim that all retrieval outputs are identical.

## Artifacts / replay
`results.json` contains exact fractional metrics, gate booleans, per-case summaries and errors. `partial-results.json` preserves incremental captures; final state is complete. Twelve lossless deterministic gzip JSON files retain complete outputs; their decompressed SHA256 and lengths appear in results.json. `default-captures.json` preserves the six unchanged-interface scenarios for each arm. `run.log` records terminal verdict. Protocol/input/source manifests remain in the separately frozen preparation directory.

For replay only under an authorized independent study, use existing Python/PyYAML: create a new output directory, then `python evaluate.py BASELINE_ROOT PREP_ROOT OUTPUT_DIR`. Do not overwrite frozen outputs or reinterpret a replay as a new successful experiment. No speed/nonregression claim follows from this untimed CPU-only trial.
