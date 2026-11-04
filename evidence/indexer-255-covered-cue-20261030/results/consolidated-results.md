# #255 consolidated results

Evidence delivery is not accepted efficiency/accuracy gain. Keep #255 open. This table consolidates existing artifacts only; no new experiment was run for packaging. Historical outcomes and distinct baselines remain intact.

| Study | Samples | Result | Evidence |
|---|---|---|---|
| Efficiency v1 | 20 paired AB/BA groups ×10 paths; primary4 queries; accuracy8DEV+4heldout;6contracts | FAIL: primary median reduction58.6105% (95%CI52.5395–61.3458%); CLIsearchp95+52.7193% exceeds20%guard | [Report](../../../evidence/indexer-255-20261029/results/report.md) |
| Efficiency confirmation v2 (not accuracy v2) | 120pairedCLIsearch samples;40separatebaseline/baselinecontrolpairs | PointgatesPASS only: p50+9.9734%, p95−3.2103%;95%CIp50+1.2014…+20.9187%,p95−22.2255…+50.8618%; v1FAILunchanged, no promotion | [Report](../../../evidence/indexer-255-20261029/results/report.md) |
| Accuracy whole-token v2 | 6DEV+2nongatingdomaincases;8synthetic;6sealedheldoutNOTRUN | FAIL: Hit4/6→5/6;MRR7/12(.583333)→13/24(.541667);complete4→5;38contexts/arm fidelityPASS | [Report](../../../evidence/indexer-255-token-v2-20261030/results/report.md) |
| Accuracy structured-string v3 | 6reusedtrainingDEV+2domaincases;18synthetic;6sealedheldoutNOTRUN | FAIL: Hit4/6→5/6;MRR7/12→8/15(.533333);complete4→5;51testsPASS;38contexts/arm fidelityPASS | [Report](../../../evidence/indexer-255-token-v3-20261030/results/report.md) |
| Blind-cue preparation | 6authoredraw/cuepairs;3source-supported <4minimum;0pairedretrievalruns | PREPARATION INCONCLUSIVE: intent reviewpassed but coveragegatefailed; no replacements or effect claim | [Report](../../../evidence/indexer-255-blind-cue-20261030/results/source-label-review.json) |
| Source-conditioned covered-cue | 6coveredsyntheticpairs/12captures;2byteidenticalcontrols;4mostlyframingedits | Neutral FAIL: Hit6/6→6/6;MRR29/36→29/36;complete6→6;strictMRRgainfalse;29contexts/arm fidelityPASS | [Report](../../../evidence/indexer-255-covered-cue-20261030/results/report.md) |

Exact baselines, candidate revisions, protocol/report repository paths and SHA256 are in [consolidated-results.json](consolidated-results.json). Timing confirmation v2 is distinct from accuracy v2: its point-gate pass and broad uncertainty never replace timingv1FAIL. Accuracyv3 DEV is known training diagnostics, not independent validation. The newer sealed six-case heldout was never evaluated or exposed to the implementer; its authors/source reviewers necessarily accessed it for preparation. It differs from the historical four-case heldout used in the initial efficiency assessment. No sealed content is included here.

Published campaigns #256/#259 are linked, not modified. This follow-up archives v3FAIL, blind-cue preparationINCONCLUSIVE and covered-cue neutralFAIL together. No production source change, runtime promotion, new algorithm, cost or issue-closure claim. Partial positives do not establish complete Recall/precision, population accuracy, speed nonregression, or downstream-agent benefit. Any further hypothesis is a separate prospective decision.
