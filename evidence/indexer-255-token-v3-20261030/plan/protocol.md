# #255 prospective single-candidate v3 protocol

Frozen before implementation/evaluation on 2026-10-30 UTC. Owner explicitly requested indexer continuation (02:53); coordinator delegated this bounded trial. This is a new experiment, not a retry/relabel of failed v2. Prior v2 FAIL and all prior efficiency results remain unchanged.

## Question / exact candidate
Does tokenizing actual structured-field scalar strings instead of JSON serialization avoid boundary/schema artifacts while meeting the original retrieval gates?

Baseline production: `b3549ce1aea1556f76de1d2e14a4240474947b6b`. Production src is byte-identical to previous1147; source-manifest.json pins 813 src files. Corpus and metadata must not change. Candidate method `weighted-token-v3` is explicitly opt-in; existing weighted-lexical-v1 and unspecified/default calls remain byte-identical. Implement exactly one fixed candidate:

- Query tokens: unchanged Unicode `re.findall(r"\w+", cue.casefold())` unique set.
- For each existing weighted field, recursively visit scalar string VALUES only: a string yields its tokens; list/tuple elements recurse; dict values recurse; keys and non-string scalars (numbers, booleans, null) contribute nothing. Tokens are unioned within each field, so repeated values do not increase score. Do not concatenate distinct leaves before tokenization.
- Preserve field weights title4, summary3, [tags, applicability]2, core1; weighted query/field set intersection. Decode actual core UTF-8 string without JSON encoding; no special newline substitution list.
- Preserve filtering, substring-AND query, explicit IDs/order/revision, score-positive inclusion and ascending-ref ties, optional-resource lexical scorer, mandatory resource/budget semantics.
- No morphology/stemming/synonyms/stopwords/term rarity/boosts, no corpus edits or model/service calls. Dictionary-key removal is an explicit policy consequence of values-only semantics, tested prospectively, not silently presented as solely whitespace repair.

## Inputs and independence
Six prior semantic DEV positives are reused TRAINING DIAGNOSTICS: previously observed and used to motivate this hypothesis, not fresh validation. Two prior out-of-domain cases remain nongating diagnostics, not labelled false positives. Eighteen synthetic contracts (prior8 +10 structured/boundary contrasts) and seven unchanged operational contracts are frozen separately. Lexical-absence and incompatible-filter no-match gates remain distinct from domain diagnostics.

Six sealed source-reviewed positives remain unused for retrieval evaluation. Original source reviewers and case author accessed labels; candidate implementer explicitly confirmed on 2026-10-30 ~02:54 UTC that they have never opened/read their queries/labels or received contents/outcomes (only hash/count and aggregate preparation descriptions). Independent reviewer has never run these cases. This is an access attestation and retained task-history check, not an OS access-log proof. Heldout content must stay out of implementer messages/artifacts until the one frozen independent evaluation, if allowed below. No new selection based on v3 outputs.

Original semantic manifest SHA256 `a4d6d0d18c3bdb4fbbed887a33fe6cbc07ca1b705650018e8ef13a27d527dd81`.
DEV SHA256 `02b03af2319c48336d103d6ea88b7bc7e96baadd6de034b52f62f17773e1cad5`.
Heldout SHA256 `ac54bd7b55687bce8d7c6727e3d63b7fe184f5de84b3300bb4f1f9e49baa9500`.
Domain diagnostic SHA256 `f624283f7f4305d7067ad1cf4e115ce512b8dba2b6459af6458ce4e5f8e308b2`.

## Prospective gates and order
1. Freeze protocol/input hashes before implementation. Freeze candidate commit/source hashes and evaluation runner before semantic retrieval. One implementation only; repairs needed after results invalidate this candidate rather than allowing tune-until-pass.
2. Synthetic18/18 and unchanged contracts7/7; separately lexical-absence/incompatible-filter no-match; exact serialized default-mode parity vs production baseline on retained six parity scenarios. No default/runtime promotion.
3. Run six DEV paired against production baseline, one time. Hit@5 AND MRR@5 must be no lower than production baseline. Keep the same gates as v2, not a weaker comparator chosen to pass. Historical v2 frozen DEV is reported in a separate diagnostic column (no new v2 run, no pooling; same corpus). V3 must not merely beat failed v2. All complete-resource/budget audits below must pass. If DEV fails, STOP before heldout; retain FAIL, no tuning or retries.
4. Only if all prior gates pass: independent reviewer (not implementer) runs six heldout once paired vs production baseline. Hit@5 must gain at least ONE labelled positive hit; no baseline positive hit may be lost; MRR@5 nondecreasing. Do not publish/release labels for tuning or rerun after seeing outcomes.
5. Every emitted context must carry its full indexed_skill required set, byte/hash/revision fidelity and proper omission/budget accounting. Relevant complete delivery count must not decrease vs baseline. Minimum case suffixes are anchors only, not exhaustive coverage. Preserve raw outputs, exclusions and failures; no hidden dropped cases.
6. Full passed gates yield only bounded small-set evidence suitable for independent code/CI review; not automatic production promotion, merge, efficacy claim or #255 closure. Failure = FAIL; missing evidence/identity drift = INCONCLUSIVE, not pass. No latency/performance conclusions from this untimed CPU retrieval trial.

## Limits / reporting
Report per-case labelled rank, Hit@5/MRR@5, complete relevant deliveries, context bytes and omissions. Partial positives do not establish population accuracy, complete precision/recall, downstream agent benefit or hardware efficacy. Reused DEV results are hypothesis-development evidence. Historical v2 FAIL is never overwritten. If heldout is accessed/evaluated prematurely or exposed to implementer, stop and report independence compromised rather than silently replacing cases. No installations, model/API/hardware or paid experiments; no broad benchmark or new service. Any further candidate requires a separate prospective decision, not this authorization.
