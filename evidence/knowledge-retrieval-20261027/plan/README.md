# Frozen evaluation protocol

Governing acceptance: [InferRSI #190](https://github.com/InferMatrixLab/InferRSI/issues/190).
The machine-readable protocol is `protocol.json`; the freeze manifest commits
protocol, independently constructed inputs and validator bytes before candidate
measurement. This packet is authored by Codex `gpt-6.1-sol` / `xhigh`.

1. Read the shipped source content, construct 16 development and 8 withheld cases,
   and label defensible relevant package identities by original resource paths.
   Do not consult rankings while labelling. The partial labels are sufficient
   for Success@5/MRR@5, not complete Recall. The queries are synthetic and have
   no production-distribution claim.
2. Validate fixture references and freeze all authored inputs and scripts. Keep
   withheld queries/labels outside the runtime author's and orchestrator's view
   until the candidate revision and source digest are fixed.
3. Profile the read-only baseline separately. Run quality/parity and the frozen
   20 balanced paired groups with one interpreter and an equal complete corpus.
   Each process explicitly imports the selected checkout rather than a possibly
   unrelated editable install. Keep all raw timings and exact-output digests.
4. Report search and relevance retrieval separately at identical API scope
   (`repo=inferrsi`, `limit=5`). Report default collect, context delivery and CLI
   startup separately. The current collect CLI lacks repo/backend filters;
   its wider-scope startup cost is not an equivalent retrieval-quality result.
5. Apply frozen gates, self-check output integrity and submit artifacts for an
   independent review. This evaluation does not establish model task efficacy,
   full-library recall, service throughput or OS filesystem-cache-cold latency.

The primary performance statistic is the median of 20 paired reductions, each
formed from the median latency of four fixed hot relevance queries. The 95%
percentile bootstrap resamples complete paired groups with seed `19020261027`
for 10,000 iterations. The prospective issue bar requires at least 20% median
reduction and a lower confidence bound above zero. No trimming or post-hoc
choice of the fastest query, summary or run is allowed.

Exact parity covers the complete canonical serialization, with readable
projections for identity order, revisions, resource-hash inventories, omissions,
collision metadata, material bytes and context bytes/budget. The API timer
excludes the evaluator's serialization and hashing work. Full CLI timings
include process creation, imports, command work and stdout capture; decoding is
measured separately. Fresh-reader API calls include reader construction;
reused-reader calls follow one untimed pass across all four hot queries.

No candidate has been timed while this protocol is being authored. Missing or
incomplete evidence remains INCONCLUSIVE. Existing #128/#129 evidence stays
historical and is not relabelled as this campaign's measured result.
