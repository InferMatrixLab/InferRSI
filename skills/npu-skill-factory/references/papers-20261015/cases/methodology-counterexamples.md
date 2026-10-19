# Candidate cases: where seemingly useful rules fail

Status: candidate. Local validation: not_run. These are paper-reported historical cases, not InferRSI executions. P sections are proposed interpretations and boundaries.

## E-C1 — A useful default becomes an unjustified ban

**F locator:** Repo-To-Skill [Appendix A.2.4, paired verification and refinement](https://arxiv.org/html/2609.02749v1#A1.SS2.SSS4.Px3), Table 6.

**F case:** PassNet refinement encountered a special convolution structure that could undermine a blanket preference for vendor operators. The authors changed an absolute prohibition into an exception-sensitive prior. Construction-stage arithmetic mean fell (.9566→.7492) while geometric mean (.5352→.6941), median (.7340→.7941), match failures (10→1 of 50), and solve time (40→22 minutes) improved. These construction trials used DeepSeek v4 pro/Claude Code, unlike the final GPT-5.5/Codex evaluation.

**P mechanism:** a generally sensible precaution suppresses exploration after direct structural evidence suggests an exception. Preserve the precaution's conditions and the counterexample rather than deleting either.

**P proposed action:** revise only the implicated prohibition, retain a correct baseline, require task-specific correctness and outcome evidence before choosing the exception. Do not import the convolution optimization into an NPU skill from this narrative alone. The exact specialized implementation was not inspected here.

**P acceptance question:** does the narrower rule recover legitimate exceptions without encouraging unsupported rewrites elsewhere? This requires new evidence; the answer is not_run.

## E-C2 — Better repository familiarity can produce unnecessary caution

**F locator:** Learning to Commit [§4.3 case study](https://arxiv.org/html/2603.26664v1#S4.SS3.SSS0.Px3), Tables 2–4.

**F case:** the paper contrasts successful localization of a shared-RNG issue with a training-step fix where skill-guided work retained a redundant guard. The quantitative seq-bycat condition also has worse line deviation and weak judge preference in the [ledger](../references/learning-to-commit.md).

**P mechanism:** a historical defensive pattern can be activated beyond its original preconditions. Repository memory is most useful when it retains the reason and boundary for the rule, not only the coding pattern.

**P proposed action:** keep the historical change as a case until the invariant can be stated precisely. Scope a new convention to the subsystem and condition actually supported. Do not equate a smaller oracle-like patch with functional correctness, and do not infer the private repository's exact code from the narrative.

**P acceptance question:** are there both positive examples and cases where applying the rule adds needless behavior? Use both before a broad memory update.

## E-C3 — Fixing targeted failures can break unrelated successes

**F locator:** Trace2Skill [§4.3](https://arxiv.org/html/2603.25158v5#S4.SS3), [Appendix C.2](https://arxiv.org/html/2603.25158v5#A3.SS2), Appendix E.

**F case:** the greedy patch study reports bidirectional task flips, including 57 failure-to-pass against 21 pass-to-failure at one step and 26 against 46 at another. Recurring patch themes also overlap semantically. Individually selected edits did not match whole-pool consolidation in that study.

**P mechanism:** patch effects interact; a narrowly successful fix can redirect broader agent behavior. Duplicate guidance can change emphasis without adding capability.

**P proposed action:** evaluate the combined candidate and retain an unrelated-success regression sample. Review semantic overlap and contradictory instructions before writing. Do not infer from this case that all patches should always be merged or that greedy selection is universally inferior.

**P acceptance question:** what improved, what regressed, and which changes are attributable to the edited instruction rather than stochastic execution? No such test was run in this pack.

## E-C4 — A scorer-compatible procedure can violate a deployment contract

**F locator:** SkillOpt [§4.5 spreadsheet case](https://arxiv.org/html/2605.23904v2#S4.SS5), [Fig.4](https://arxiv.org/html/2605.23904v2#S4.F4); Trace2Skill [Appendix I.3 examples](https://arxiv.org/html/2603.25158v5#A9.SS3).

**F case:** learned spreadsheet guidance includes static-value fallbacks and automation preferences conditioned on benchmark behavior. These examples are reported skill text, not independent proof of suitability for every spreadsheet request.

**P mechanism:** optimizing the available evaluator can reward a shortcut that is valid for the benchmark but conflicts with a real request for reusable formulas or a particular automation format.

**P proposed action:** preserve the user's output contract above any learned heuristic. Record the evaluator's view of success and flag dimensions it cannot test. A candidate update must not silently change the requested artifact type.

**P acceptance question:** would the output still satisfy the user if evaluated outside the benchmark? Treat this as an explicit transfer boundary rather than generic skill quality.
