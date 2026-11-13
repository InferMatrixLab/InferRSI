# Pack F — which part of an improver should adapt?

Candidate; empirically unvalidated. **F** = historical paper fact; **P** = proposed InferRSI rule. Exact pins, read locators and evidence context are in [source notes](references/source-notes.md). Existing RRSI/search-policy references were inspected first; this pack contributes missing paper-level interfaces, acceptance conditions and counter-evidence rather than another repository summary.

## F/P comparison

| Adaptation target | Objective → assumptions | Variables and constraints → mechanism | Resource benefit / cost | Author evidence and limit → P operational rule |
|---|---|---|---|---|
| **RRSI: harness transition** | F: improve reusable harness behavior under frozen policy and finite noisy evolve feedback | F: edit count, component choice, critic, empirical noise floor, relative-token allowance and pruning window; sparse proposals plus non-compensatory selection gates | F: restrains expensive harness growth; adds repeated evaluation/critic work; policy tokens are a proxy, not total resource cost | F: Table2 workspace OOD average43.6 at2.42M tokens/trial versus unregularized40.3 at3.80M; base remains cheaper at1.56M. Group ablations do not identify every gate. **P:** add attribution/noise/cost fields to existing search-policy evidence; do not copy thresholds or treat a rejected bundled edit as a causal failure of each component |
| **Dream-RSI: exploration controller** | F: allocate discovery calls better using accumulated outcomes; fixed agent/evaluator/interface and replay support | F: root/frontier choices, width, depth, parallel batches, stop decisions; prefix-safe historical replay scores quality–calls frontier and sequential-round penalty | F: avoids fresh execution for supported replay outcomes; still pays discovery, policy development and online confirmation; no information about unrecorded outcomes | F: Table2 ConvDiv all-history1.90 at786 calls versus current-history1.59 at430. **P:** use supported replay to shortlist controller changes; require fresh evidence for new branches and do not call replay-score monotonicity an online guarantee |
| **AIDE²: research agent / possible improver** | F: better task optimization under fixed inner budgets, with public feedback separated from private solution grading | F: mutable search/context/inner selection; outer selection fixed to aggregate grade; tokens and solution execution count toward inner budgets | F: bounded context can buy more search at fixed dollars; nested grading dominates proposal cost; step-capped and dollar-capped benchmarks differ | F: held-out gains are non-monotonic across checkpoints; ignition test endpoints0.780/0.782 with3 seeds/arm is explicitly inconclusive. **P:** separate executor quality from improver quality; retain multiple scoped checkpoint results rather than declare the final checkpoint universally best |
| **JitRL: per-state action distribution** | F: repeated experiences, relevant state/action matching and a trustworthy reward estimator; frozen weights | F: memory neighborhoods, action support, return discount, exploration and logit adjustment; exact KL optimizer given supplied advantages, stronger assumptions for consistency | F: avoids gradient training but pays retrieval, evaluator and candidate scoring; memory cost and stale/aliased evidence remain | F: matched offline Table13 gives40.88% JitRL versus46.06% WebRL, while Table8 favors logit over prompt update in two domains. **P:** keep as interface-dependent knowledge; a text skill cannot itself provide candidate logits or reliable rewards |

## P: route feedback to the smallest justified target

1. **One failed action:** preserve its state, outcome and causal uncertainty as a case. Do not immediately rewrite a persistent skill.
2. **Repeated comparable action failures:** investigate representation/retrieval/credit assignment before assuming a global policy defect. JitRL is relevant only if candidate identities and scoring access exist.
3. **Useful history but poor allocation of attempts:** assess a search-policy change. Dream-RSI requires prefix-observable, replayable histories with stable evaluators; unsupported branches remain unknown.
4. **Repeated cross-task procedure failure:** consider a bounded skill update through Pack E's acquisition rules. Pack F does not replace the evidence needed to distill knowledge.
5. **Control-flow/context/tool-contract failure:** frame a harness-change proposal with RRSI-style attribution and explicit resource cost. The user has not authorized implementing that proposal.
6. **Claim that an improved agent should replace its improver:** require an independent improver comparison. AIDE²'s inconclusive ignition test is a counterexample to inferring this from task-level gains alone.

These are candidate routing rules, not a framework design or automatic promotion pipeline. No fresh persistent registry is proposed; records remain attached to existing cases/knowledge/skills.

## P: preserve three non-equivalences

- Better replay score ≠ better unseen online discovery. A recorded tree is support-limited and outcomes are reused, not regenerated.
- Fewer policy tokens or discovery calls ≠ lower total cost. Include evaluator execution, memory/serialization, parallel workers, policy development and the actual billing/runtime denominator when available.
- Private inner-task scores ≠ untouched external evaluation. AIDE²'s outer loop adaptively receives grades; independent task families provide a distinct generalization check.

See the [bounded update proposal](updates/optimization-search-policy.md) and [interface knowledge records](knowledge/adaptation-interfaces.md). No new executable skill is forced: existing search/evolution skills are the natural integration candidates, and the supplier did not inspect their current bodies.
