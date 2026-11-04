# #255 raw-string lexical-presence contract study — prospective protocol

Draft for coordinator review, 2026-10-30T09:08Z. No candidate or scoring yet.

## Authority, baseline and objective

Continue owner-authorized #255 small constructed accuracy cases, without algorithm rewrite, corpus changes, paid/model calls or hardware. Public-query availability is NOT a prerequisite. Main verified through GitHub at preparation: `1052925ff22f9a850cebc64afd0083b35ed1fae9`, tree `bf2fc3880768c6c453e862b31c5fc658f8a400a8`. Freeze this historical baseline; a concurrent merge does not silently replace it.

Documented lexical contract: `docs/knowledge-operations.md:82–91` awards distinct casefolded cue words for substring presence in original title/description/core, weighted4/3/2/1. `_skill_selection.py:16–20` currently serializes all fields to JSON, introducing alphabetic escape prefixes absent from original string values. Objective is eliminate that specific false-positive contribution, not optimize semantic task success or improve natural-language retrieval generally.

## One candidate and protected paths

Add one explicitly named/versioned opt-in ranking method `weighted-raw-string-v1` (final name must freeze before implementation). For string fields only, compute membership in the original `value.casefold()`; for nonstring objects retain EXACT legacy `json.dumps(value, ensure_ascii=False).casefold()`. Keep cue regex/casefold/unique token set, substring morphology, field weights, score sums, positive-score admission, identity tie-break, filters, query, limits and resource semantics unchanged.

Default legacy method unchanged. Explicit-ID membership/order unchanged. Shared optional-resource scoring remains legacy for all modes; do not globally change `lexical_score` and accidentally alter default context delivery. No changes to metadata, generated indexes, skill text, query rewriting, method weights, services or schema. No token-boundary or stemming change. Historical v2/v3 failures retained separately.

## Independent fixtures and freezes

A fresh no-history independent author drafts exactly 14 scalar contract cases plus two small synthetic-record ordering fixtures (count declared before drafting) before seeing candidate code/scores, old DEV/heldout or catalog. Cases include actual newline/tab/carriage-return versus literal backslash escapes; genuine and absent cues; Unicode/casefold; duplicates; substring morphology; weights/ties; null/numeric/list/dict fields. Expected membership and scores are manually justified from original bytes under the stated contract, with JSON representation explicitly retained for nonstrings. Case author records exact count before drafting. No cases are replaced after scorer exposure. Reviewer audits labels and freezes their hash; candidate author may then see these as development/contract fixtures, not heldout.

Freeze protocol, fixtures, baseline source/corpus identities, runner and model/provenance preflight before candidate scoring. Coordinator must confirm required model-role provenance; unknown model identity must be recorded unknown, never invented. This work uses existing agent reasoning only, no separate model/API experiment. Candidate commit/hash frozen before executing its comparison. Old sealed semantic heldout remains unused and undisclosed.

## Evaluation and gates

One local CPU comparison only after protocol approval/preflight:
1. All frozen scalar/per-field contract labels must match candidate exactly (100%); report legacy mismatches separately as false-positive, false-negative or weight error.
2. At least one predeclared serialization-created false-positive contribution must be corrected; genuine substring contributions and nonstring behavior must be unchanged across all corresponding controls. Do not report a vague aggregate accuracy percentage without counts and denominator.
3. Both fixed ranking fixtures must match contract-derived order; no loss of the predeclared true-hit controls. Label results synthetic/adversarial and source-conditional to the contract.
4. Default output, explicit-ID order/membership, ordinary query/filter behavior, unsupported-method rejection, mandatory resource completeness, hashes/revisions and exact/insufficient context budgets must pass existing plus new isolated controls. Optional-resource selection must remain byte-identical to legacy for identical selected owners.
5. A fixed existing-corpus diagnostic is optional only if separately specified/frozen BEFORE execution; it is NOT needed to demonstrate this scalar contract discrepancy and cannot become posthoc selection of wins. No old DEV or heldout reuse to claim validation.

No latency-effect claim: only report available execution duration/output bytes as diagnostic overhead, never as paired performance evidence. No timing campaign/retries/threshold tuning. Any candidate contract or compatibility failure means FAIL and stops; unavailable safe execution/preflight means INCONCLUSIVE with no unprotected fallback. Preserve all outputs and errors. No second candidate automatically.

## Interpretation / integration boundary

PASS supports correcting phantom lexical evidence in this opt-in mode on explicit synthetic contracts, not general semantic retrieval superiority, real-user distribution, hardware efficacy or whole #255 closure. Fixed-corpus quality, broader task relevance and actual caller utility remain separately bounded. Runtime publication needs scoped source review and applicable CI; evidence may be delivered even if candidate fails. Default method may not be promoted under this protocol.
