# #255 input-expression feasibility study — prospective draft

Status: DRAFT FOR COORDINATOR ACCEPTANCE before case authoring or retrieval. Owner accepted this direction at03:30 UTC2026-10-30; no scorer change or automatic query rewrite was authorized by this study. One bounded CPU comparison, six fresh development tasks. No paid/model/hardware calls, installs, external writes or old-heldout access.

## Question and baseline
Can task-preserving, manually prepared `操作＋对象＋约束` relevance cues improve retrieval ordering compared with the same task expressed as a longer narrative, using unchanged production ranking?

Pin production `b3549ce1aea1556f76de1d2e14a4240474947b6b` and the existing813-file source manifest SHA256 `9a1a7d9fda980602ca344a4cf8be10fbfa7eef96c2dc1feaea8eab75647c4215`. Refresh main before acceptance; if source/corpus changed, pin and disclose the new baseline before inputs rather than quietly comparing across snapshots. Runtime/source and corpus must be identical for both arms. Existing weighted-lexical-v1 only; no v2/v3 opt-in mode, code/scorer changes, field weights, filters, query tuning or metadata edits.

## Roles and information barriers
1. A fresh input author with no catalog, target-label, old case wording or retrieval-result access authors exactly six plausible engineering tasks and concise cues. Supply only this protocol plus a broad neutral remit: inference/training engineering tasks involving a concrete operation, object and constraint; do not supply selected skill names, keyword lists, old failure examples or intended targets. Task author records an access attestation and cue-editing time/effort.
2. An independent intent reviewer checks each raw/cue pair BEFORE source labelling: operations/objects/constraints, negation, causal uncertainty, environment, thresholds and requested deliverable must agree. Reviewer does not rewrite cues or inject repository terminology. Disagreement marks the pair invalid; no replacement after seeing retrieval results.
3. A separate source-label reviewer may inspect the frozen six tasks and pinned corpus, then assigns partial positive IDs and exact source support. No rank calls, scorer simulation or candidate outputs. Do not change task/cue wording after seeing catalog matches. Record unlabelled/ambiguous cases honestly, not forced targets.
4. Evaluator receives the final input commitment only after all above receipts. One paired retrieval run; report both arms including misses. Old six sealed heldout cases remain sealed and are neither accessed nor repurposed.

A role-separated author process can use subagents, but these are human/assistant-curated experimental inputs, NOT observed user traffic or an automatic normalizer. Attestations/history establish the intended barrier; do not claim forensic access isolation.

## Fixed cue-editing rule (manual, auditable, no model rewrite service)
The author first writes the raw task as a natural narrative, then annotates verbatim spans into three ordered slots:

- OPERATION: the actual action/question to answer, including uncertainty or requested diagnosis rather than turning it into a prescription.
- OBJECT: workload/component/data object and explicit environment identifiers needed to interpret it.
- CONSTRAINTS: ALL explicit correctness/safety/resource/performance conditions, negations, thresholds and required output.

Construct the cue by joining those verbatim spans in order with `; `. Do not paraphrase, add synonyms/keywords, singularize, translate, remove negation, introduce desired answers or rename objects after catalog terms. Repeated exact spans may appear once; otherwise preserve the selected text. Remove only greetings, politeness, redundant framing or incidental chronology not used by the task. If meaningful information cannot be removed safely, retain it; a cue need not be short. Record every removed span and a reason from this fixed list, plus raw/cue character and token counts. This is a deterministic serialization of manually selected slots, NOT deterministic automatic semantic extraction. Report that distinction explicitly.

To prevent an artificial advantage, raw tasks must not be padded with arbitrary unrelated vocabulary, intentionally bait substring matches, or hide a known skill title. At least two naturally concise tasks should act as identity/near-identity controls: if they already consist of operation/object/constraints, keep the wording unchanged. Do not search for tasks that produce a requested score.

## Input counts and pre-evaluation validity gate
Exactly six fresh tasks, at least four distinct task intents, including at least two identity/near-identity controls within six. Distinctness reviewed semantically, not proven statistical independence. Avoid reusing previous case wording or known failed tasks; the coordinator can check overlap using IDs/hashes and coarse intent without disclosing old sealed labels to author.

All six pairs must pass intent preservation. At least four of six must have source-supported positives; otherwise preparation yields INCONCLUSIVE coverage and STOP before retrieval. Freeze all six original pairs, all partial labels/ambiguities, source hashes, retained/removed-span maps and the eligible metric denominator. Do not replace source-uncovered cases just to manufacture success. Remaining unlabelled cases still run and are reported descriptively, not called failures or true negatives. No labels may be added after viewing output ranks for the gate calculation.

## Retrieval settings and prospective gates
Both arms use `query=''`, no filters, `limit=5`, `context_bytes=262144`, same production `relevance` interface. Only the cue string differs. Paired outputs captured once per frozen pair; no retries/tuning/relabel after outcomes.

- All pre-evaluation validity checks pass.
- On frozen source-labelled eligible pairs, no baseline positive Hit@5 is lost; Hit@5 is nondecreasing; MRR@5 is STRICTLY greater than raw-task baseline. Minimum benefit is ordinal/effect direction, not statistical confidence. Report absolute per-case rank changes, denominator, summed RR and MRR; no rounding into a pass.
- Identity controls yield exact serialized output parity when raw and cue are byte-identical. Near-identity controls remain descriptive pairs, not an exact-parity assertion. At least one byte-identical control is required.
- Existing six unchanged/default contract captures have exact parity against baseline; source/scorer hash equality and no code diff mandatory.
- Full indexed_skill mandatory resources, emitted bytes/hashes/revision, context-budget accounting and explicit omissions must pass in both arms; complete relevant delivery count must not decrease. Required suffixes alone are insufficient.
- Any valid negative gate result is FAIL. Missing/broken input identity or too few source-supported cases is INCONCLUSIVE. Stop; retain all outputs and no second rule/case replacement/search-until-pass.

## Decision and limits
PASS supports only feasibility of this manually prepared input contract on a small curated set. It does not prove an automatic rewriting algorithm, lower user effort, speed, population accuracy, complete precision/recall, downstream agent benefit or hardware efficacy. Require reporting how much task-author effort was needed and any information that could not be compressed. No shipping caller burden, default change, promotion or #255 closure follows automatically. A next validation/implementation decision is separate.

Previous cache/v2/v3 FAIL reports remain unchanged. The six old heldout cases stay unused regardless of this study's outcome.
