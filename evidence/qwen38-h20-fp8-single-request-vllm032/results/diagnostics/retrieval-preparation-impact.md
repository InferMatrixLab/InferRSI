# Retrieval construction and review attempts

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE. Preparation only; no model answers or activated gates.**

CPU1964 prepared v1:30 exact-size inputs totaling2,048,000 tokens;28 seconds,
exit0, no GPU. Local hashes and positions verified. Independent review identified
a meaningful construct-validity defect: decoys had KEY_D/VAL_D prefixes and an
extra sentence, while targets did not; a128-record filler pool repeated. This
version is retained and rejected for freezing, not mislabeled a model failure.
The first scorer also conditioned every position on a fully valid JSON schema.
Its behavior was internally consistent but did not represent independent recall.

Before any model answers, v2 made identifier lengths/templates homogeneous and
used nonrepeating decoys. CPU1965 prepared the same30-case length/position matrix;
all generator assertions and local readback passed, with no GPU use. V2 extraction
separates exact whole-object success from independent available-key matches;
duplicate/invalid JSON still fails every position. Eight targeted local scorer
checks passed. These facts qualify input preparation only; independent v2 review,
baseline qualification and owner gate confirmation remain pending.

Both versions retain compressed inputs, manifest, generator and observer sources
in the campaign evidence tree. V1 observer was never GPU-executed. V2 observer
also corrects the baseline1961 one-token-per-choice assumption prospectively;
the old failed observer/records are unchanged. No production engine or gates
were changed, and no candidate was optimized against these final-set targets.

KnowledgeStore candidate `case.qwen38-retrieval-construction-cand`, revision
`sha256:f061eeb3c8c18d57eec16253fb990e42880483b3a9fad3f5beca2c9cf5b7a4fb`,
was created and read back byte-for-byte; no library promotion.
