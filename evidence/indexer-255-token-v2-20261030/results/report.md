# Issue #255: one fixed opt-in whole-token candidate — FAIL

## Decision
Do not promote this candidate. Development Hit@5 improves 4/6 to 5/6, but MRR@5 decreases 0.583333 to 0.541667, violating the prospectively frozen nondecreasing-MRR gate. Complete relevant deliveries increase 4 to 5. No tuning or second candidate was attempted. The coordinator stopped at this development failure: the six held-out cases remain sealed from the candidate implementer and **NOT RUN by decision**, not an execution gap to retry. Issue #255 is not closed by this evidence.

## Identity and protocol
- Baseline: `1147c5bb41724826b64ad13cebc8a4dce5cc278b`.
- Candidate: `55a458328195335586eb6c6c1301ba34a8218e63`; tree `005fd1e3d48de52bc288a521033e5fc94b4ee298`.
- Accepted protocol SHA256: `6e72cf159003a1e85b0b4cdc42beee895494da294162e19adecfe963613de517`.
- Independent semantic input commitment: `a4d6d0d18c3bdb4fbbed887a33fe6cbc07ca1b705650018e8ef13a27d527dd81`.
- Sealed heldout commitment: `ac54bd7b55687bce8d7c6727e3d63b7fe184f5de84b3300bb4f1f9e49baa9500` (not exposed to the candidate implementer or evaluated; the case author and independent source reviewer necessarily accessed it to prepare and validate labels).
- Candidate uses existing Unicode `words()` casefold/regex on cue and serialized fields, weighted set intersection at unchanged 4/3/2/1 weights. No stopwords, synonyms, stemming, corpus edits or query tuning.
- Experimental API `relevance_method="weighted-token-v2"`, CLI `--relevance-method weighted-token-v2`; requires a relevance cue. Existing default remains weighted-lexical-v1, and the optional-resource scorer is unchanged.

## Development and diagnostic results
Ranks are over partial source-reviewed positives, not complete relevance truth. The two negative cases are nongating out-of-domain diagnostics: their unlabelled outputs are not counted as false positives.

| Case | Baseline rank | Token rank | Complete relevant A/B | Output bytes A/B | Context bytes A/B |
|---|---:|---:|---:|---:|---:|
| freshdev01 | miss/unlabelled | 4 | 0/1 | 1023627/997003 | 209844/186748 |
| freshdev02 | 1 | 1 | 1/1 | 995468/954601 | 192276/155613 |
| freshdev03 | 1 | 2 | 1/1 | 936745/984882 | 141145/183819 |
| freshdev04 | 2 | 2 | 1/1 | 991347/973224 | 186469/169204 |
| freshdev05 | 1 | 1 | 1/1 | 1024332/1064339 | 217296/254712 |
| freshdev06 | miss/unlabelled | miss/unlabelled | 0/0 | 908046/1062990 | 114329/257046 |
| freshnegative01 | miss/unlabelled | miss/unlabelled | 0/0 | 938511/965135 | 140102/166489 |
| freshnegative02 | miss/unlabelled | miss/unlabelled | 0/0 | 968466/986613 | 163968/175888 |

The mechanism tradeoff is observable: freshdev01 gains rank4 from a miss, but freshdev03 moves rank1 to rank2. The rank gain contributes 1/4 while the loss costs 1/2 in summed reciprocal rank. This bounded result does not establish that whole-token matching is generally better or worse.

## Verification
- Focused synthetic/new-interface plus existing Collect compatibility tests: **41 passed in 20.02s**; not a full-suite claim.
- All eight frozen synthetic scoring contracts pass. The committed synthetic fixture omits the baseline pin from the shared test fixture; its case values are unchanged from the frozen input.
- Six baseline-versus-candidate default-mode serialized payloads have exact SHA256/length parity (`baseline-default.json`, `candidate-default.json`). This includes plain default collection, relevance+context, substring query, filter, explicit ID and undersized budget.
- Existing compatibility plus new tests exercise explicit IDs/order/revision, substring-AND query, filters, required resources/budget omission, deterministic ties and CLI opt-in validation. Explicit-ID results differ only in requested selection-method metadata when that option changes.
- Source optional-resource scorer `context_view` is untouched; explicit-ID context parity verifies unchanged optional-resource delivery for the same cue.
- Development and diagnostic emitted contexts passed full indexed_skill required-path presence and exact emitted byte/hash checks; pinned read validates revision. Relevant complete counts are separate from misses and budget omissions. Full outputs retain all context_omissions.
- Independent post-run audit (`independent-review.json`): **38 emitted contexts per arm** have full required sets and exact source bytes/hash/revision; relevant complete4→5 and saved default parity reconfirmed. This is supplemental review, not a new prospective gate or retrieval rerun.
- Ruff source/new-test check PASS; git diff --check PASS. No corpus changes; original efficiency evidence untouched.

## Reproduce without exposing heldout
Apply `../patch/candidate.patch` to the pinned baseline, or fetch `../patch/candidate.bundle` with the baseline prerequisite. Set PREP_ROOT to this campaign's `validator/` directory and OUTPUT_DIR to a new external directory; create it first with `mkdir -p "$OUTPUT_DIR"`; keep frozen outputs unchanged. Scripts live in `validator/`. Use an existing Python environment with PyYAML/pytest; no models, services or hardware are required. `evaluate_development.py BASELINE_ROOT PREP_ROOT OUTPUT_DIR baseline` and `evaluate_development.py CANDIDATE_ROOT PREP_ROOT OUTPUT_DIR token` read only development.json and negative-controls.json. Full JSON results are deterministic gzip (mtime0); decompress for audit. `compatibility_capture.py ROOT` generates the six unchanged-default hashes. Test command: `PYTHONPATH=src python -m pytest tests/test_collect_token_selection.py tests/test_collect_selection.py -rA`.

## Limits
Small deliberately selected partial positives, not population efficacy, complete Recall/precision, or downstream agent benefit. No latency/performance campaign was run, so no speed/nonregression claim; tokenization tradeoff unmeasured. No model, service, GPU or paid calls. Baseline/current corpus is frozen; future corpus changes invalidate direct comparison. Heldout is unused and can remain independent for a separately authorized future proposal; do not tune on it.
