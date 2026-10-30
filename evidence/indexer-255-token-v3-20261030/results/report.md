# Issue #255: structured string-value tokenization v3 — FAIL

## Decision
The single fixed v3 candidate fails the prospective development MRR gate. Stop: do not promote it, do not run heldout, and do not close #255. No tuning, additional candidate, morphology, model calls or timing campaign was performed. Historical v2 FAIL remains unchanged.

| Partial-positive DEV metric | Production baseline | Historical v2 (not rerun) | v3 |
|---|---:|---:|---:|
| Hit@5 | 4/6 | 5/6 | 5/6 |
| MRR@5 | 0.583333 | 0.541667 | 0.533333 |
| Complete relevant deliveries | 4 | 5 | 5 |

These six DEV cases are reused training diagnostics, not fresh validation. The six sealed heldout cases were not exposed to the implementer and were not evaluated; their original author/source reviewers necessarily accessed labels for preparation. No heldout content is included here.

## Frozen identity
- Production baseline: `b3549ce1aea1556f76de1d2e14a4240474947b6b`; source matches all813 entries in the prospective source manifest and is byte-identical to prior1147 production src.
- Candidate: `96788d26b57240e53c26fe5446b2062a62ee6d0e`; tree `5ae435fb5793b19f0de96ce74dd6ded9db3f3292`.
- Protocol SHA256: `2adf6a226b4c3763e52dec159aaae9ec4ea0824f2b0b0bd37a92799ef06bf94d`.
- Code and runner were frozen before semantic DEV evaluation: see pre-semantic-freeze.json. That receipt's semantic_runs_started=false describes the freeze instant, not final run status.
- Frozen evaluator SHA256: `47570bda5dd642c9a7170dcd24680806a007ecc88432569af9afa4867dbc7db8`.

## Single change tested
Explicit opt-in `weighted-token-v3` recursively unions tokens from scalar string VALUES within each weighted field. Dictionary keys and nonstring values contribute nothing; list/tuple/dict-values recurse. Strings are tokenized separately, not joined. Existing Unicode words regex/casefold and weights4/3/2/1 are unchanged. No stemming, synonyms, query/corpus/metadata changes. The optional-resource lexical scorer and default weighted-lexical-v1 remain unchanged. Key removal is an explicit policy consequence, not merely a newline repair.

## Per-case diagnostics
Partial positive labels do not judge every returned item. The two domain-negative cases are nongating and their unlabelled returns are not false-positive labels.

| Case | Production rank | Historical v2 rank | v3 rank | Relevant complete A/B | Context bytes A/B | Output bytes A/B |
|---|---:|---:|---:|---:|---:|---:|
| freshdev01 | miss/unlabelled | 4 | 5 | 0/1 | 209844/186748 | 1023627/997003 |
| freshdev02 | 1 | 1 | 1 | 1/1 | 192276/151271 | 995468/948177 |
| freshdev03 | 1 | 2 | 2 | 1/1 | 141145/183819 | 936745/984882 |
| freshdev04 | 2 | 2 | 2 | 1/1 | 186469/169204 | 991347/973224 |
| freshdev05 | 1 | 1 | 1 | 1/1 | 217296/254712 | 1024332/1064339 |
| freshdev06 | miss/unlabelled | miss/unlabelled | miss/unlabelled | 0/0 | 114329/257046 | 908046/1062990 |
| freshnegative01 | miss/unlabelled | miss/unlabelled | miss/unlabelled | 0/0 | 140102/166489 | 938511/965135 |
| freshnegative02 | miss/unlabelled | miss/unlabelled | miss/unlabelled | 0/0 | 163968/175888 | 968466/986613 |

Freshdev01 moves from production miss to rank5 (v2 rank4), while freshdev03 remains rank2 rather than production rank1. The rank5 gain contributes0.2 but rank1→2 costs0.5 in reciprocal-rank sum. This experiment does not establish general quality improvement or isolate which token-policy component caused each observed rank shift.

## Verification
- 51 focused tests passed in25.39s, including18 frozen synthetic contracts and existing/new compatibility tests. Ruff source/new-test check passed; not a full-suite claim.
- Six baseline/candidate default serialized captures match exactly, including default, relevance/context, substring query, filter, explicit ID and undersized budget scenarios.
- Frozen evaluator verifies complete indexed_skill required-resource sets and exact emitted bytes/hash with pinned revision reads for every emitted context. Relevant complete counts4→5 remain separate from retrieval misses/budget omissions. Full raw gzip outputs retain omissions and control metadata.
- Independent supplemental audit (`independent-review.json`) verifies38 emitted contexts per arm, complete required paths/bytes/hash/revision and context-budget accounting, all16 raw gzip/summary hashes, default parity and frozen code/runner identity. This post-run audit did not execute retrieval or heldout.
- No runtime code changed after pre-semantic freeze. Historical v2 scores are a separate diagnostic column from saved outputs, not pooled or rerun. Gate comparator remains production baseline.

## Replay / limits
Candidate.patch applies to pinned baseline; candidate.bundle retains exact candidate with baseline prerequisite. Use an existing Python/PyYAML environment, without new installation or paid calls. Set PREP_ROOT to inputs/, create OUTPUT_DIR with `mkdir -p "$OUTPUT_DIR"`, and execute frozen evaluate_development.py with BASELINE_ROOT PREP_ROOT OUTPUT_DIR baseline or CANDIDATE_ROOT PREP_ROOT OUTPUT_DIR token. Use a new output directory, not frozen results. compatibility_capture.py ROOT emits the retained parity capture. The frozen synthetic fixture lives in the retained candidate patch. Gzip results are lossless with mtime0.

Small diagnostic partial labels are not complete Recall/precision, population accuracy, downstream agent benefit or hardware efficacy. No speed/nonregression conclusion: this trial is untimed. Gate FAIL cannot be repaired by weakening the comparator or evaluating/tuning on heldout. Any further hypothesis requires a separate prospective decision.
