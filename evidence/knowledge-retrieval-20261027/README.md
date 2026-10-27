# CPU knowledge retrieval evidence

Acceptance scope and ownership: [InferRSI #190](https://github.com/InferMatrixLab/InferRSI/issues/190).
This packet tests a manifest implementation that preserves retrieval behavior.
The frozen quality/parity and paired CPU performance gates passed. Campaign
acceptance, merge and issue closure remain with the authorized owner.

| Segment | Contents |
| --- | --- |
| `plan/` | Prospective protocol, current freeze, preserved first freeze and pre-measurement review amendment |
| `validator/` | Standard-library runner, 16 development and 8 withheld synthetic cases with source-grounded partial relevance labels |
| `results/` | Complete quality comparison, paired raw API/CLI measurements, baseline profile, #129 delivery trace, editable EN/ZH architecture artifacts and qualified local software/environment summaries |
| `patch/` | Fixed runtime candidate and exact source identity |

The current prospective freeze is
`a465367319f3058398eb1f8579ee5d4174b8cb90457793e90788fb5796151057`.
Independent review corrected completeness checks and removable assertions before
formal candidate measurement; `plan/amendment-1.md` records the change. The
withheld split was released only after the runtime candidate was fixed. Fixture
text and labels did not change between freezes. Root `.gitattributes` preserves
evidence bytes; copying or committing must retain the recorded hashes.

The full quality result has **96 outputs per revision, exact parity and unchanged
source/corpus identities**. For 20 labelled answerable cases, search/default
collect score Success@5/MRR@5 = 0.20/0.20; relevance/context-item ranking scores
1.00/0.9625. Four labelled negatives return empty items in 4/4 search/default
cases and 2/4 relevance/context cases. These are unchanged existing #129
behaviors, not a quality improvement from this runtime patch.

Context-item ranking does not establish correct body delivery. A post-hoc
inspection found the labelled owner's context delivered in **19/20** positive
cases. `withheld06` finds its correct item first but requires 170,782 context
bytes against a 65,536-byte budget, so that owner's context is omitted. This
diagnostic does not change the frozen quality gate. Synthetic, AI-authored,
partial source labels are not human gold judgements or complete Recall; no
agent-task efficacy or production-distribution claim follows.

The 20-pair CPU result observed **40.01%** hot-relevance paired-median latency
reduction, 95% interval **[38.38%, 41.06%]**, with all 400 output pairs and
80 CLI stdout pairs equal. [performance.md](results/performance.md) retains
all per-mode/query p50/p95 rows, including search regressions and CLI relevance
decode p95 **1.810 → 3.046 ms**. Independent read-only recomputation passed;
reviewer model/effort is unknown and no human/maintainer acceptance is recorded.

See the [audit](../../docs/knowledge-retrieval-audit.md) for source contracts,
per-query examples, failure qualifications and follow-up priorities. Local
software verification includes a failed whole-suite run whose initial failures
were reproduced on baseline, successful focused manifest checks and successful
isolated wheel/sdist construction; it must not be described as a green full
suite. No model, GPU or inference-service benchmark ran.
